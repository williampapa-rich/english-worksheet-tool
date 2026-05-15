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
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from hwpx_renderer.render import render_passage_with_annotations
from llm.augment import (
    DEFAULT_VOCABULARY_COUNT,
    augment_translation,
    augment_vocabulary,
)
from llm.client import StructuredLLMClient
from llm.errors import (
    LLMSchemaValidationError,
    LLMTimeoutError,
    PermanentLLMError,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.extraction import ExtractionResult
from shared.schemas.passage import Passage
from shared.schemas.question import Question
from shared.schemas.translation import Translation, TranslationCreatedBy
from shared.schemas.vocabulary import Vocabulary, VocabularySelectedBy
from shared.schemas.vocabulary_master import VocabularyMaster, VocabularyMasterCreatedBy
from worksheet_api.db import get_db
from worksheet_api.llm_setup import get_llm_client
from worksheet_api.repositories import (
    PassageRepository,
    QuestionRepository,
    SyntaxAnnotationRepository,
    TenantContext,
    TranslationRepository,
    VocabularyMasterRepository,
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


# ─── B3: 보강 라우트 (ADR-0013) ─────────────────────────────────────────────

# Translation 보강 mode (ADR-0013 D2)
TranslationAugmentMode = Literal["skip_if_user_edited", "replace", "skip_if_exists"]
# Vocabulary 보강 mode (ADR-0013 D3)
VocabularyAugmentMode = Literal["skip_if_user_edited", "replace", "append"]


def _raise_llm_http_exception(exc: Exception) -> None:
    """ADR-0003 §D-3.5 / ADR-0013 D7 LLM 에러 → HTTPException 매핑.

    extract_passages 의 try/except 와 같은 매핑을 보강 라우트에서도 재사용.
    """
    if isinstance(exc, LLMSchemaValidationError):
        raise HTTPException(
            status_code=502,
            detail=f"LLM structured output 검증 실패: {exc}",
        ) from exc
    if isinstance(exc, LLMTimeoutError):
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    if isinstance(exc, PermanentLLMError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    # 다른 LLM* 에러 (LLMNetworkError / LLMRateLimitError) 는 retry 소진 후 도달
    raise HTTPException(status_code=502, detail=f"LLM 호출 실패: {exc}") from exc


@router.post(
    "/{passage_id}/translation",
    response_model=Translation,
    status_code=200,
)
async def augment_passage_translation(
    passage_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
    mode: Annotated[
        TranslationAugmentMode, Query(description="ADR-0013 D2 mode.")
    ] = "skip_if_user_edited",
) -> Translation:
    """LLM 으로 Translation 보강 (ADR-0013 D1, D2).

    Mode 별 동작:
      - ``skip_if_user_edited`` (default): 기존 ``created_by=USER`` 면 LLM 호출 X +
        기존 반환. 그 외는 LLM 호출 → 덮어쓰기 (in-place UPDATE).
      - ``replace``: 항상 LLM 호출 → 덮어쓰기. ``created_by`` 가 USER 였어도 LLM 으로
        갱신.
      - ``skip_if_exists``: 기존 row 가 있으면 LLM 호출 X. 없을 때만 호출 + INSERT.

    트랜잭션 경계: ADR-0003 §D-3.4 — 핸들러 1건 = ``session.begin()`` 1건.

    Raises:
        HTTPException 404: passage_id 가 없거나 다른 tenant 소유.
        HTTPException 502: LLMSchemaValidationError / 기타 LLM 에러.
        HTTPException 504: LLMTimeoutError.
        HTTPException 500: PermanentLLMError.
    """
    async with session.begin():
        passage_repo = PassageRepository(session, tenant_ctx)
        translation_repo = TranslationRepository(session, tenant_ctx)

        passage = await passage_repo.get(passage_id)
        if passage is None:
            raise HTTPException(
                status_code=404,
                detail=f"Passage {passage_id} 를 찾을 수 없습니다.",
            )

        existing = await translation_repo.get_by_passage(passage_id)

        # mode 별 분기 — LLM 호출 skip 여부
        if mode == "skip_if_exists" and existing is not None:
            return existing
        if (
            mode == "skip_if_user_edited"
            and existing is not None
            and existing.created_by == TranslationCreatedBy.USER
        ):
            return existing

        # LLM 호출 (CLAUDE.md §8.3 — packages/llm/ 단일 경로)
        try:
            llm_translation = await augment_translation(
                passage,
                llm_client=llm_client,
            )
        except (
            LLMSchemaValidationError,
            LLMTimeoutError,
            PermanentLLMError,
        ) as exc:
            _raise_llm_http_exception(exc)
            raise  # unreachable, mypy 만족용

        # 영속화
        if existing is None:
            new_translation = llm_translation.model_copy(
                update={
                    "tenant_id": tenant_ctx.tenant_id,
                    "workspace_id": tenant_ctx.workspace_id,
                    "passage_id": passage_id,
                }
            )
            return await translation_repo.create(new_translation)
        # 기존 row 갱신 — passage_id UNIQUE 그대로, in-place UPDATE
        updated = await translation_repo.update_text(
            passage_id,
            text=llm_translation.text,
            created_by=TranslationCreatedBy.LLM,
        )
        if updated is None:
            # 위에서 existing != None 확인했는데 여기서 None — 이론상 도달 불가
            raise HTTPException(
                status_code=500,
                detail="Translation update 중 row 가 사라졌습니다 (race).",
            )
        return updated


# ─── E1-a — PATCH /passages/{id}/translation ────────────────────────────────


class TranslationUpdateRequest(BaseModel):
    """PATCH /passages/{passage_id}/translation request body.

    ADR-0015 Stage E1-a — 사용자가 Translation 을 인라인 편집할 때 호출.
    `text` 만 수정 — `created_by` 는 라우터가 자동으로 ``USER`` 로 갱신
    (ADR-0013 §사용자 검수 흐름 — `skip_if_user_edited` mode 의 1차 입력).
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        ...,
        min_length=1,
        description="사용자 수정 해석 본문. 빈 문자열 불가 (삭제는 별도 정책).",
    )


@router.patch(
    "/{passage_id}/translation",
    response_model=Translation,
    status_code=200,
)
async def update_passage_translation(
    passage_id: UUID,
    body: TranslationUpdateRequest,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Translation:
    """Translation 사용자 편집 (ADR-0015 Stage E1-a).

    `created_by=USER` 자동 갱신 — ADR-0013 의 `skip_if_user_edited` default
    mode 가 이 메타를 1차 입력으로 사용해 LLM 재보강 시 사용자 수정 보존.

    Translation 이 존재하지 않으면 404 — POST /translation 으로 먼저 생성 필요
    (LLM 보강 / replace mode 또는 향후 manual create 라우트).

    Raises:
        HTTPException 404: passage 없음 / cross-tenant / Translation row 없음.
    """
    async with session.begin():
        passage_repo = PassageRepository(session, tenant_ctx)
        translation_repo = TranslationRepository(session, tenant_ctx)

        passage = await passage_repo.get(passage_id)
        if passage is None:
            raise HTTPException(
                status_code=404,
                detail=f"Passage {passage_id} 를 찾을 수 없습니다.",
            )

        updated = await translation_repo.update_text(
            passage_id,
            text=body.text,
            created_by=TranslationCreatedBy.USER,
        )
        if updated is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Passage {passage_id} 의 Translation 이 존재하지 않습니다. "
                    "먼저 POST /passages/{id}/translation 으로 생성하세요."
                ),
            )
        return updated


class VocabularyAugmentResponse(BaseModel):
    """POST /passages/{id}/vocabulary 응답 — 보강 후 전체 vocabulary list."""

    vocabulary: list[Vocabulary]


# ─── Stage E1-c: VocabularyMaster 통합 헬퍼 ─────────────────────────────────


def _normalize_headword(word: str) -> str:
    """headword_normalized 계산 — LOWER(word).strip().

    v0.1 단순 정책 (ADR-0016 D2-b). lemmatize 는 Phase 4+ 검토.

    Args:
        word: 원형 (사용자 입력 또는 LLM 산출).

    Returns:
        정규화된 소문자 표제어.
    """
    return word.lower().strip()


async def _get_or_create_master(
    vocab_word: str,
    vocab_meaning_ko: str,
    vocab_pos: str | None,
    vocab_level_label: str | None,
    created_by: VocabularyMasterCreatedBy,
    master_repo: VocabularyMasterRepository,
    tenant_ctx: TenantContext,
) -> VocabularyMaster:
    """VocabularyMaster 조회 or 신규 생성 후 반환.

    Stage E1-c 흐름 (ADR-0016 D2-a/-b/-c):
      1. headword_normalized 계산 (LOWER + strip).
      2. (tenant_id, headword_normalized) 로 기존 master 검색.
      3. 있으면 → usage_count += 1 후 기존 master 반환 (reuse).
         없으면 → 신규 master 생성 (usage_count=1) 후 반환.

    ADR-0016 D2-c override 정책:
      master.default_meaning_ko 는 *prefill 용* — 사용자가 다른 meaning_ko 를
      입력해도 master 의 default 를 변경하지 않는다. passage-specific override 는
      Vocabulary.meaning_ko 에 저장 (caller 책임).

    멀티테넌트:
      master_repo 가 tenant_ctx.tenant_id 필터를 자동 적용하므로
      cross-tenant master reuse 구조적 불가.

    Args:
        vocab_word: 원형 어휘 표면형 (대소문자 보존).
        vocab_meaning_ko: 한국어 뜻 (passage-specific — master override 아님).
        vocab_pos: 품사 (None 가능 — 신규 master 생성 시 default_pos 로 사용).
        vocab_level_label: 등급 라벨 (None 가능 — 신규 master 생성 시 사용).
        created_by: 신규 master 생성 주체 (LLM / USER).
        master_repo: VocabularyMasterRepository 인스턴스.
        tenant_ctx: 현재 요청 테넌트 컨텍스트.

    Returns:
        기존 또는 신규 생성된 VocabularyMaster.
    """
    from uuid import uuid4

    headword_normalized = _normalize_headword(vocab_word)

    # 1. 기존 master 검색 (tenant_id + headword_normalized)
    existing_master = await master_repo.find_by_headword(headword_normalized)

    if existing_master is not None:
        # 2a. reuse — usage_count += 1
        await master_repo.increment_usage_count(existing_master.id)
        return existing_master

    # 2b. 신규 master 생성
    new_master = VocabularyMaster(
        id=uuid4(),
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
        headword_normalized=headword_normalized,
        word_canonical=vocab_word,
        default_meaning_ko=vocab_meaning_ko,
        default_pos=vocab_pos,
        default_level_label=vocab_level_label,
        usage_count=1,
        created_by=created_by,
    )
    return await master_repo.create(new_master)


@router.post(
    "/{passage_id}/vocabulary",
    response_model=VocabularyAugmentResponse,
    status_code=200,
)
async def augment_passage_vocabulary(
    passage_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
    mode: Annotated[
        VocabularyAugmentMode, Query(description="ADR-0013 D3 mode.")
    ] = "skip_if_user_edited",
    count: Annotated[
        int,
        Query(
            ge=1,
            le=30,
            description="요청 어휘 개수 (LLM 이 적게 반환 가능). 기본 10.",
        ),
    ] = DEFAULT_VOCABULARY_COUNT,
) -> VocabularyAugmentResponse:
    """LLM 으로 Vocabulary list 보강 (ADR-0013 D1, D3).

    Mode 별 동작:
      - ``skip_if_user_edited`` (default): 기존 USER / user_edited 항목 보존. LLM
        결과 중 USER 항목과 ``headword_normalized`` 충돌 항목은 skip. 나머지 INSERT.
      - ``replace``: ``selected_by=LLM`` 그리고 ``user_edited=False`` 인 row 만 DELETE,
        USER 항목 보존. LLM 결과 INSERT.
      - ``append``: 기존 그대로, LLM 결과만 INSERT (충돌 무시).

    응답: 보강 후 passage 의 전체 vocabulary list (call 후 새 상태).

    Raises:
        HTTPException 404: passage_id 가 없거나 다른 tenant 소유.
        HTTPException 502: LLM 에러.
        HTTPException 504: LLMTimeoutError.
        HTTPException 500: PermanentLLMError.
    """
    async with session.begin():
        passage_repo = PassageRepository(session, tenant_ctx)
        vocabulary_repo = VocabularyRepository(session, tenant_ctx)
        master_repo = VocabularyMasterRepository(session, tenant_ctx)

        passage = await passage_repo.get(passage_id)
        if passage is None:
            raise HTTPException(
                status_code=404,
                detail=f"Passage {passage_id} 를 찾을 수 없습니다.",
            )

        # USER / user_edited 항목의 headword set — skip_if_user_edited 충돌 검출용
        user_headwords: set[str] = set()
        if mode == "skip_if_user_edited":
            user_headwords = await vocabulary_repo.list_user_edited_headwords(passage_id)

        # LLM 호출
        try:
            llm_vocab = await augment_vocabulary(
                passage,
                llm_client=llm_client,
                count=count,
            )
        except (
            LLMSchemaValidationError,
            LLMTimeoutError,
            PermanentLLMError,
        ) as exc:
            _raise_llm_http_exception(exc)
            raise

        # mode 별 기존 데이터 처리
        if mode == "replace":
            await vocabulary_repo.delete_llm_for_passage(passage_id)

        # LLM 결과끼리 중복 제거 (replace / skip_if_user_edited 모드 — append 는 raw 유지)
        items_to_insert: list[Vocabulary] = []
        seen_headwords: set[str] = set()
        for v in llm_vocab:
            if mode == "skip_if_user_edited" and v.headword_normalized in user_headwords:
                continue  # USER 항목과 충돌 → skip (D4 사용자 수정 보존)
            if mode in ("skip_if_user_edited", "replace"):
                if v.headword_normalized in seen_headwords:
                    continue  # LLM 결과 내 중복 — 첫 항목만 (silent drift 방지)
                seen_headwords.add(v.headword_normalized)
            items_to_insert.append(v)

        # Stage E1-c: INSERT — 각 어휘마다 master 조회 or 생성 + master_id 채움
        for v in items_to_insert:
            # master 통합 (ADR-0016 D2-a/-b) — created_by=LLM
            master = await _get_or_create_master(
                vocab_word=v.word,
                vocab_meaning_ko=v.meaning_ko,
                vocab_pos=v.pos,
                vocab_level_label=v.level_label,
                created_by=VocabularyMasterCreatedBy.LLM,
                master_repo=master_repo,
                tenant_ctx=tenant_ctx,
            )
            v_with_ids = v.model_copy(
                update={
                    "tenant_id": tenant_ctx.tenant_id,
                    "workspace_id": tenant_ctx.workspace_id,
                    "passage_id": passage_id,
                    "master_id": master.id,
                }
            )
            await vocabulary_repo.create(v_with_ids)

        # 응답: 보강 후 전체 list
        final_list = await vocabulary_repo.list_by_passage(passage_id)
        return VocabularyAugmentResponse(vocabulary=final_list)


# ─── E1-c — POST /passages/{id}/vocabulary/manual (사용자 직접 추가) ─────────


class VocabularyManualCreateRequest(BaseModel):
    """POST /passages/{passage_id}/vocabulary/manual request body.

    ADR-0015 Stage E1-c — 사용자가 어휘 행을 LLM 보강 외 직접 추가.
    ``selected_by=USER``, ``user_edited=False`` 로 영속화 (ADR-0013 의 USER
    항목 — LLM 보강 시 ``skip_if_user_edited`` mode 가 보존, ``replace`` mode
    도 USER 항목은 DELETE 안 함).
    """

    model_config = ConfigDict(extra="forbid")

    word: str = Field(..., min_length=1, max_length=255)
    meaning_ko: str = Field(..., min_length=1, max_length=500)
    pos: str | None = Field(default=None, max_length=64)
    level_label: str | None = Field(default=None, max_length=64)
    headword_normalized: str | None = Field(
        default=None,
        max_length=255,
        description="None 이면 word.lower() 자동 계산. 글로벌 dedup 정합 위해 명시 권장.",
    )


@router.post(
    "/{passage_id}/vocabulary/manual",
    response_model=Vocabulary,
    status_code=201,
)
async def create_passage_vocabulary_manual(
    passage_id: UUID,
    body: VocabularyManualCreateRequest,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Vocabulary:
    """Vocabulary 사용자 직접 추가 (ADR-0015 Stage E1-c).

    selected_by=USER 로 영속화 — ADR-0013 의 LLM 보강 모드와 정합:
      - skip_if_user_edited (default): selected_by=USER 항목은 LLM 결과의
        headword 충돌 시 skip 되어 사용자 입력 보존.
      - replace: USER 항목 / user_edited=True 항목은 DELETE 대상에서 제외.

    ``headword_normalized`` 가 None 이면 ``word.lower()`` 로 자동 계산
    (Phase 2 v0.1 단순 정책 — VocabularyMaster 글로벌 dedup 별 ADR 시 lemmatizer
    재계산).

    Raises:
        HTTPException 404: passage 없음 / cross-tenant.
    """
    from uuid import uuid4

    async with session.begin():
        passage_repo = PassageRepository(session, tenant_ctx)
        vocabulary_repo = VocabularyRepository(session, tenant_ctx)
        master_repo = VocabularyMasterRepository(session, tenant_ctx)

        passage = await passage_repo.get(passage_id)
        if passage is None:
            raise HTTPException(
                status_code=404,
                detail=f"Passage {passage_id} 를 찾을 수 없습니다.",
            )

        # Stage E1-c: master 조회 or 생성 (created_by=USER)
        # ADR-0016 D2-c: 사용자 입력 meaning_ko 는 passage-specific override —
        # master.default_meaning_ko 를 변경하지 않음. Vocabulary 행에만 저장.
        master = await _get_or_create_master(
            vocab_word=body.word,
            vocab_meaning_ko=body.meaning_ko,
            vocab_pos=body.pos,
            vocab_level_label=body.level_label,
            created_by=VocabularyMasterCreatedBy.USER,
            master_repo=master_repo,
            tenant_ctx=tenant_ctx,
        )

        new_vocab = Vocabulary(
            id=uuid4(),
            tenant_id=tenant_ctx.tenant_id,
            workspace_id=tenant_ctx.workspace_id,
            passage_id=passage_id,
            word=body.word,
            headword_normalized=body.headword_normalized or _normalize_headword(body.word),
            meaning_ko=body.meaning_ko,
            pos=body.pos,
            level_label=body.level_label,
            master_id=master.id,
            selected_by=VocabularySelectedBy.USER,
            user_edited=False,
        )
        return await vocabulary_repo.create(new_vocab)


# ─── E1-b — PATCH /passages/{id}/vocabulary/{vid} ───────────────────────────


class VocabularyUpdateRequest(BaseModel):
    """PATCH /passages/{passage_id}/vocabulary/{vid} request body.

    ADR-0015 Stage E1-b — 사용자가 어휘 행 단위 편집. 모든 필드 optional —
    None 은 "변경 없음". ``user_edited`` 는 라우터가 자동으로 True 갱신.
    ``selected_by`` 는 변경 안 함 (LLM 산출 → user_edited=True 가 정상 상태).
    """

    model_config = ConfigDict(extra="forbid")

    word: str | None = Field(default=None, max_length=255)
    pos: str | None = Field(default=None, max_length=64)
    meaning_ko: str | None = Field(default=None, max_length=500)
    level_label: str | None = Field(default=None, max_length=64)
    headword_normalized: str | None = Field(
        default=None,
        max_length=255,
        description="word 변경 시 함께 보내는 것을 권장 (글로벌 dedup 정합).",
    )


@router.patch(
    "/{passage_id}/vocabulary/{vocabulary_id}",
    response_model=Vocabulary,
    status_code=200,
)
async def update_passage_vocabulary(
    passage_id: UUID,
    vocabulary_id: UUID,
    body: VocabularyUpdateRequest,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Vocabulary:
    """Vocabulary 행 사용자 편집 (ADR-0015 Stage E1-b).

    `user_edited=True` 자동 갱신 — ADR-0013 의 `skip_if_user_edited` default
    mode 가 이 메타를 1차 입력으로 사용해 LLM 재보강 시 사용자 수정 보존.

    body 가 모두 None 인 경우에도 200 + user_edited=True 갱신 (사용자 명시적
    편집 의도).

    Raises:
        HTTPException 404: passage 없음 / vocabulary_id 없음 / 다른 tenant
            소유 / vocabulary.passage_id 가 URL passage_id 와 불일치.
    """
    async with session.begin():
        passage_repo = PassageRepository(session, tenant_ctx)
        vocabulary_repo = VocabularyRepository(session, tenant_ctx)

        passage = await passage_repo.get(passage_id)
        if passage is None:
            raise HTTPException(
                status_code=404,
                detail=f"Passage {passage_id} 를 찾을 수 없습니다.",
            )

        # 기존 vocabulary 조회 — passage_id 정합 + tenant 가드
        existing = await vocabulary_repo.get(vocabulary_id)
        if existing is None or existing.passage_id != passage_id:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Vocabulary {vocabulary_id} 를 찾을 수 없습니다 "
                    f"(passage {passage_id})."
                ),
            )

        updated = await vocabulary_repo.update_fields(
            vocabulary_id,
            word=body.word,
            pos=body.pos,
            meaning_ko=body.meaning_ko,
            level_label=body.level_label,
            headword_normalized=body.headword_normalized,
        )
        if updated is None:
            # 위에서 existing 확인했는데 None — race
            raise HTTPException(
                status_code=500,
                detail="Vocabulary update 중 row 가 사라졌습니다 (race).",
            )
        return updated


# ─── E1-d — DELETE /passages/{id}/vocabulary/{vid} ──────────────────────────


@router.delete(
    "/{passage_id}/vocabulary/{vocabulary_id}",
    status_code=204,
)
async def delete_passage_vocabulary(
    passage_id: UUID,
    vocabulary_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Vocabulary 행 사용자 삭제 (ADR-0015 Stage E1-d, D3 (b) 채택).

    ``selected_by`` / ``user_edited`` 무관 — 모든 항목 삭제 허용 (PM 결정
    2026-05-07: 사용자 의도 명시적, ADR-0013 replace mode 가 LLM 산출 재생성).

    Cross-passage 가드: vocabulary.passage_id != URL passage_id 면 404.

    Raises:
        HTTPException 404: passage 없음 / vocabulary 없음 / cross-passage /
            cross-tenant.
    """
    async with session.begin():
        passage_repo = PassageRepository(session, tenant_ctx)
        vocabulary_repo = VocabularyRepository(session, tenant_ctx)
        master_repo = VocabularyMasterRepository(session, tenant_ctx)

        passage = await passage_repo.get(passage_id)
        if passage is None:
            raise HTTPException(
                status_code=404,
                detail=f"Passage {passage_id} 를 찾을 수 없습니다.",
            )

        existing = await vocabulary_repo.get(vocabulary_id)
        if existing is None or existing.passage_id != passage_id:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Vocabulary {vocabulary_id} 를 찾을 수 없습니다 "
                    f"(passage {passage_id})."
                ),
            )

        # Stage E1-c: master_id 가 있으면 usage_count -= 1 (ADR-0016 D4-a — master 는 유지)
        master_id_to_decrement = existing.master_id

        deleted = await vocabulary_repo.delete_by_id(vocabulary_id)
        if not deleted:
            # race
            raise HTTPException(
                status_code=500,
                detail="Vocabulary delete 중 row 가 사라졌습니다 (race).",
            )

        if master_id_to_decrement is not None:
            await master_repo.decrement_usage_count(master_id_to_decrement)

        return Response(status_code=204)


# ─── E1-e — PATCH /passages/{id} (body 수정 + annotation 강제 삭제) ─────────


class PassageBodyUpdateRequest(BaseModel):
    """PATCH /passages/{passage_id} request body.

    ADR-0015 Stage E1-e — 사용자가 본문 텍스트 + paragraph 분할 직접 수정.
    body_text / paragraphs 를 *동시에* 받아 정합 보장 (paragraphs 가 body_text
    의 분할 형태여야 함 — 검증은 클라이언트 책임).

    D4 (b) 채택 — Passage 메타 (`body_user_edited` 등) 추가 없음. UI 가
    PATCH 만 허용하므로 LLM 덮어쓰기 위험 없음.

    **annotation 처리**: body_text 변경 시 character offset 이 깨져 기존
    SyntaxAnnotation 이 무효화 — 라우터가 동일 트랜잭션에서 annotation 전체
    삭제. 클라이언트는 body 수정 후 annotation 을 다시 만들어야 함 (Phase 1
    에디터 모드와 분리, ADR-0015 §Stage E3 명시).
    """

    model_config = ConfigDict(extra="forbid")

    body_text: str = Field(..., min_length=1, description="새 본문 텍스트.")
    paragraphs: list[str] = Field(
        default_factory=list,
        description=(
            "새 paragraph 분할. 빈 리스트는 body_text 를 단일 paragraph 로 본다는 "
            "의도. 클라이언트는 paragraphs 가 body_text 의 분할 형태인지 검증."
        ),
    )


@router.patch(
    "/{passage_id}",
    response_model=Passage,
    status_code=200,
)
async def update_passage_body(
    passage_id: UUID,
    body: PassageBodyUpdateRequest,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Passage:
    """Passage body_text + paragraphs 사용자 편집 (ADR-0015 Stage E1-e).

    body_text 변경은 character offset 무효화 → 동일 트랜잭션에서 기존
    SyntaxAnnotation 전체 삭제 (`SyntaxAnnotationRepository.replace_all` 빈
    리스트 호출). 정밀 offset 재계산 보존은 별 ADR (Phase 3 진입 시 검토).

    Raises:
        HTTPException 404: passage 없음 / cross-tenant.
        HTTPException 422: body_text 빈 문자열 / extra field.
    """
    async with session.begin():
        passage_repo = PassageRepository(session, tenant_ctx)
        annotation_repo = SyntaxAnnotationRepository(session, tenant_ctx)

        existing = await passage_repo.get(passage_id)
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=f"Passage {passage_id} 를 찾을 수 없습니다.",
            )

        # 1. annotation 전체 삭제 (offset 깨짐 회피).
        await annotation_repo.replace_all(passage_id, [])

        # 2. body 갱신.
        updated = await passage_repo.update_body(
            passage_id,
            body_text=body.body_text,
            paragraphs=body.paragraphs,
        )
        if updated is None:
            # race
            raise HTTPException(
                status_code=500,
                detail="Passage update 중 row 가 사라졌습니다 (race).",
            )
        return updated
