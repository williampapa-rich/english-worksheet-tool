"""Passage API 엔드포인트.

ADR-0003 §D-3.4 / §D-3.6 흐름:
  HTTP 요청 → tenant_ctx 주입 → extractor 호출 (sentinel UUID) →
  model_copy 로 실제 tenant_id 주입 → 단일 트랜잭션 영속화.

ADR-0003 §D-3.5 에러 매핑:
  EmptyInputError / UnsupportedMediaTypeError / PdfParseError → 422
  LLMSchemaValidationError → 502
  LLMTimeoutError → 504
  PermanentLLMError → 500
  기타 → 500

PM-1: 다중 지문 — ExtractResponse.results 가 list (단일 지문도 길이 1).
PM-3: force_vision 은 kind=pdf 에서만 의미.
PM-5: extractor 가 자료에 보이는 translation / vocabulary 포함.
PM-6: 비어있어도 정상 (translation=None, vocabulary=[]).

translation / vocabulary 영속화 결정 (B1 — 옵션 A → 옵션 B 전환, 2026-05-07):
  Phase 2 진입에 맞춰 옵션 B (extract 시점 영속화) 로 전환. 기존 옵션 A (in-memory
  만 유지) 는 GET /{id} 응답에서 translation / vocabulary 가 항상 비어있는 가짜
  관계가 발생해 보강 라우트 (B3 — POST /passages/{id}/translation 등) 와 정합 깨짐.
  옵션 B 로 전환 시:
    - extract 결과의 translation 이 비어있지 않으면 같은 트랜잭션에 저장 (1:1).
    - vocabulary list 도 같은 트랜잭션에 저장 (passage_id FK).
    - GET /{id} 도 translation / vocabulary 를 함께 조회해 응답.
  PM-6 가정 그대로 — 실유저 입력 default 는 비어있음. 비어있으면 저장 skip 만.

base64 결정:
  request body 에 binary 를 base64 str 로 받는다.
  multipart/form-data 대안 검토: FastAPI UploadFile 지원 우수하나,
  JSON body 통일이 OpenAPI 스키마 일관성 및 테스트 편의 면에서 유리.
  Phase 2 에서 UploadFile 전환 검토 가능 — 현재는 base64 유지.
"""

from __future__ import annotations

import base64
from typing import Annotated, Literal
from uuid import UUID

from extractor.errors import (
    EmptyInputError,
    ExtractionError,
    PdfParseError,
    UnsupportedMediaTypeError,
)
from extractor.image import extract_from_image
from extractor.pdf import extract_from_pdf
from extractor.text import extract_from_text
from fastapi import APIRouter, Depends, HTTPException, Response
from hwpx_renderer.render import render_passage_with_annotations
from llm.client import StructuredLLMClient
from llm.errors import (
    LLMSchemaValidationError,
    LLMTimeoutError,
    PermanentLLMError,
)
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.extraction import ExtractionResult
from shared.schemas.passage import Passage
from shared.schemas.question import Question
from shared.schemas.translation import Translation
from shared.schemas.vocabulary import Vocabulary
from worksheet_api.db import get_db
from worksheet_api.llm_setup import get_llm_client
from worksheet_api.repositories import (
    PassageRepository,
    QuestionRepository,
    SyntaxAnnotationRepository,
    TenantContext,
    TranslationRepository,
    VocabularyRepository,
    get_tenant_context,
)

router = APIRouter(prefix="/passages", tags=["passages"])


# ─── 요청 / 응답 스키마 ───────────────────────────────────────────────────────


class ExtractRequest(BaseModel):
    """POST /passages/extract 의 request body.

    PM-1: kind=image/pdf 일 때 payload 가 base64 인코딩된 bytes.
    PM-3: force_vision 은 kind=pdf 에서만 의미.

    base64 선택 사유:
      JSON body 통일로 OpenAPI 스키마 일관성 확보.
      multipart/form-data 대비 테스트 편의 우선.
      Phase 2 에서 UploadFile 전환 검토 가능.
    """

    kind: Literal["text", "image", "pdf"] = Field(
        ...,
        description="입력 페이로드 종류. text=원시 텍스트, image/pdf=base64 인코딩 bytes.",
    )
    payload: str = Field(
        ...,
        description=(
            "kind=text 일 때 원시 텍스트(UTF-8). kind=image/pdf 일 때 base64 인코딩된 bytes."
        ),
    )
    media_type: str | None = Field(
        default=None,
        description="kind=image 일 때 필수. 예: image/png, image/jpeg, image/webp.",
    )
    force_vision: bool = Field(
        default=False,
        description="kind=pdf 에서만 의미. True 이면 PyMuPDF 휴리스틱 우회 + 즉시 Vision 경로 (PM-3).",
    )


class PassageWithRelations(BaseModel):
    """Passage + 연관 도메인 모델 컨테이너.

    B1 (2026-05-07) 부터 translation / vocabulary 도 DB 영속화 (옵션 B).
    POST /passages/extract 은 추출 시점에 같은 트랜잭션으로 저장하고,
    GET /passages/{id} 는 DB 에서 함께 조회해 반환한다. 비어있는 경우는
    PM-6 가정 그대로 (translation=None, vocabulary=[]).
    """

    passage: Passage
    questions: list[Question] = Field(default_factory=list)
    translation: Translation | None = Field(
        default=None,
        description="한글 해석. extract 결과가 채워져 있으면 DB 영속화 (1:1). 없으면 None.",
    )
    vocabulary: list[Vocabulary] = Field(
        default_factory=list,
        description="어휘 박스 항목. extract 결과가 채워져 있으면 DB 영속화. 없으면 빈 list.",
    )


class ExtractResponse(BaseModel):
    """POST /passages/extract 응답.

    PM-1: 다중 지문 — results 가 list. 단일 지문도 길이 1.
    """

    results: list[PassageWithRelations]


# ─── 엔드포인트 ──────────────────────────────────────────────────────────────


@router.post("/extract", response_model=ExtractResponse, status_code=200)
async def extract_passages(
    body: ExtractRequest,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ExtractResponse:
    """파일 / 텍스트 입력 → 추출 → 영속화 → 응답.

    ADR-0003 §D-3.4 단일 트랜잭션 경계:
      API 핸들러 1건 = async with session.begin() 1건.

    ADR-0003 §D-3.6 sentinel UUID 교체:
      extractor 출력의 sentinel UUID 를 model_copy 로 실제 tenant_id/workspace_id 로 교체.
      repository 의 _validate_tenant_fields() 가 sentinel 누수를 이중 방어.

    PM-1: 다중 지문 — list 반환.
    PM-3: force_vision 은 kind=pdf 에서만 사용.

    Raises:
        HTTPException 422: EmptyInputError / UnsupportedMediaTypeError / PdfParseError.
        HTTPException 502: LLMSchemaValidationError.
        HTTPException 504: LLMTimeoutError.
        HTTPException 500: PermanentLLMError / 기타.
    """
    # 1. extractor 분기 — sentinel UUID 로 채워진 ExtractionResult list
    try:
        extraction_results = await _dispatch_extract(body, llm_client)
    except EmptyInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UnsupportedMediaTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PdfParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMSchemaValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM structured output 검증 실패: {exc}",
        ) from exc
    except LLMTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except PermanentLLMError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # 2. tenant_id 주입 + 단일 트랜잭션 영속화 (ADR-0003 §D-3.4)
    saved: list[PassageWithRelations] = []
    async with session.begin():
        passage_repo = PassageRepository(session, tenant_ctx)
        question_repo = QuestionRepository(session, tenant_ctx)
        translation_repo = TranslationRepository(session, tenant_ctx)
        vocabulary_repo = VocabularyRepository(session, tenant_ctx)

        for result in extraction_results:
            # ADR-0003 §D-3.6: sentinel UUID → 실제 tenant_id / workspace_id 교체
            passage_with_ids = result.passage.model_copy(
                update={
                    "tenant_id": tenant_ctx.tenant_id,
                    "workspace_id": tenant_ctx.workspace_id,
                }
            )
            saved_passage = await passage_repo.create(passage_with_ids)

            saved_questions: list[Question] = []
            for q in result.questions:
                q_with_ids = q.model_copy(
                    update={
                        "tenant_id": tenant_ctx.tenant_id,
                        "workspace_id": tenant_ctx.workspace_id,
                        "passage_id": saved_passage.id,
                    }
                )
                saved_q = await question_repo.create(q_with_ids)
                saved_questions.append(saved_q)

            # B1 — translation / vocabulary 영속화 (옵션 B).
            # PM-6 가정: 비어있을 수 있음 — 비어있으면 저장 skip.
            saved_translation: Translation | None = None
            if result.translation is not None:
                t_with_ids = result.translation.model_copy(
                    update={
                        "tenant_id": tenant_ctx.tenant_id,
                        "workspace_id": tenant_ctx.workspace_id,
                        "passage_id": saved_passage.id,
                    }
                )
                saved_translation = await translation_repo.create(t_with_ids)

            saved_vocabulary: list[Vocabulary] = []
            for vocab in result.vocabulary:
                v_with_ids = vocab.model_copy(
                    update={
                        "tenant_id": tenant_ctx.tenant_id,
                        "workspace_id": tenant_ctx.workspace_id,
                        "passage_id": saved_passage.id,
                    }
                )
                saved_v = await vocabulary_repo.create(v_with_ids)
                saved_vocabulary.append(saved_v)

            saved.append(
                PassageWithRelations(
                    passage=saved_passage,
                    questions=saved_questions,
                    translation=saved_translation,
                    vocabulary=saved_vocabulary,
                )
            )

    return ExtractResponse(results=saved)


@router.get("/{passage_id}", response_model=PassageWithRelations, status_code=200)
async def get_passage(
    passage_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PassageWithRelations:
    """단일 Passage 조회 — 멀티테넌트 강제.

    tenant_ctx 기반 필터가 모든 쿼리에 자동 적용된다.
    다른 tenant 의 Passage 를 조회하면 404 반환 (존재 여부 노출 방지).

    Args:
        passage_id: 조회할 Passage UUID.
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        session: DB 세션.

    Raises:
        HTTPException 404: Passage 가 존재하지 않거나 다른 tenant 소유.
    """
    passage_repo = PassageRepository(session, tenant_ctx)
    question_repo = QuestionRepository(session, tenant_ctx)
    translation_repo = TranslationRepository(session, tenant_ctx)
    vocabulary_repo = VocabularyRepository(session, tenant_ctx)

    passage = await passage_repo.get(passage_id)
    if passage is None:
        raise HTTPException(
            status_code=404,
            detail=f"Passage {passage_id} 를 찾을 수 없습니다.",
        )

    questions = await question_repo.list_by_passage(passage_id)
    # B1 — translation / vocabulary 도 함께 조회. tenant_ctx 기반 repo 라
    # cross-tenant 누수 방지.
    translation = await translation_repo.get_by_passage(passage_id)
    vocabulary = await vocabulary_repo.list_by_passage(passage_id)
    return PassageWithRelations(
        passage=passage,
        questions=questions,
        translation=translation,
        vocabulary=vocabulary,
    )


@router.get("/{passage_id}/hwpx", status_code=200)
async def download_passage_hwpx(
    passage_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Passage + annotation 을 HWPX 파일로 렌더해 다운로드.

    Phase 1 DoD #3 — 와이프 검수용 HWPX 파일 출력. 에디터의 현재 저장 상태
    (DB 의 SyntaxAnnotation) 를 hwpx_renderer 로 직렬화한다.

    멀티테넌트: passage 존재 여부 + tenant 소유 확인 (다른 tenant 소유면 404).
    annotation 도 동일 tenant_ctx 기반 repository 로 조회 — cross-tenant 누수 차단.

    Args:
        passage_id: 다운로드할 Passage UUID.
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        session: DB 세션.

    Returns:
        HWPX (application/hwp+zip) 바이트 스트림. Content-Disposition 으로
        파일명 ``passage_{id}.hwpx`` 권장.

    Raises:
        HTTPException 404: Passage 가 존재하지 않거나 다른 tenant 소유.
    """
    passage_repo = PassageRepository(session, tenant_ctx)
    annotation_repo = SyntaxAnnotationRepository(session, tenant_ctx)

    passage = await passage_repo.get(passage_id)
    if passage is None:
        raise HTTPException(
            status_code=404,
            detail=f"Passage {passage_id} 를 찾을 수 없습니다.",
        )

    annotations = await annotation_repo.list_by_passage(passage_id)
    hwpx_bytes = render_passage_with_annotations(passage, annotations)

    return Response(
        content=hwpx_bytes,
        media_type="application/hwp+zip",
        headers={
            "Content-Disposition": f'attachment; filename="passage_{passage_id}.hwpx"',
        },
    )


# ─── extractor 분기 헬퍼 ─────────────────────────────────────────────────────


async def _dispatch_extract(
    body: ExtractRequest,
    llm_client: StructuredLLMClient,
) -> list[ExtractionResult]:
    """kind 별로 적합한 extractor 를 호출한다.

    ADR-0003 §D-3.2 / CLAUDE.md §8.3: 모든 LLM 호출은 packages/llm/ 경유.
    extractor 함수가 내부적으로 StructuredLLMClient 를 사용 — 여기서 직접 SDK 호출 없음.

    Args:
        body: ExtractRequest 인스턴스.
        llm_client: StructuredLLMClient 구현체 (get_llm_client Depends).

    Returns:
        list[ExtractionResult]: sentinel UUID 로 채워진 추출 결과 list.

    Raises:
        EmptyInputError: 입력이 비어있거나 base64 디코딩 실패.
        UnsupportedMediaTypeError: kind=image 에서 media_type 미지정 또는 미지원.
        PdfParseError: PyMuPDF 파싱 실패.
        ExtractionError: 정규화 실패 등 기타 extractor 에러.
        LLM*Error: LLM 호출 에러 (packages/llm/errors.py 계층).
    """
    if body.kind == "text":
        return await extract_from_text(body.payload, llm_client=llm_client)

    if body.kind == "image":
        if not body.media_type:
            # media_type 누락 — EmptyInputError 로 처리 (UnsupportedMediaTypeError 는 str media_type 필수)
            raise EmptyInputError(
                "kind=image 일 때 media_type 이 필요합니다 (예: image/png, image/jpeg, image/webp)."
            )
        try:
            image_bytes = base64.b64decode(body.payload, validate=True)
        except Exception as exc:
            raise EmptyInputError(
                f"image payload base64 디코딩 실패: {exc}. 올바른 base64 인코딩 값을 전달하세요."
            ) from exc
        if not image_bytes:
            raise EmptyInputError("image payload 가 비어있습니다.")
        return await extract_from_image(image_bytes, body.media_type, llm_client=llm_client)

    if body.kind == "pdf":
        try:
            pdf_bytes = base64.b64decode(body.payload, validate=True)
        except Exception as exc:
            raise EmptyInputError(
                f"pdf payload base64 디코딩 실패: {exc}. 올바른 base64 인코딩 값을 전달하세요."
            ) from exc
        if not pdf_bytes:
            raise EmptyInputError("pdf payload 가 비어있습니다.")
        return await extract_from_pdf(
            pdf_bytes,
            llm_client=llm_client,
            force_vision=body.force_vision,
        )

    # kind 가 Literal 에 없는 값은 Pydantic validation 에서 이미 차단되지만
    # 방어적으로 처리
    raise ValueError(f"알 수 없는 kind: {body.kind}")
