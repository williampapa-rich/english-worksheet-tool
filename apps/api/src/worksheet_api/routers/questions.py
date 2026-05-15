"""Question API 엔드포인트 (Phase 3 — 변형 생성 라우트).

Phase 3 변형 라우트:
  POST /questions/{question_id}/variants/topic-main-idea-swap — V6 변형 생성.

ADR-0017 D2-c:
  - 변형은 항상 신규 Question row INSERT (augment 와 달리 mode 개념 없음).
  - variant_kind / derived_from_question_id 채워진 신규 Question 반환.
  - QAValidationResult placeholder row 동시 생성 (validated_at 설정, passed=False,
    validator_note="pending" — Phase 3 qa-validator 활성 시 실제 검증으로 갱신).

멀티테넌트 강제 (W-2 패턴):
  - 원본 question_id 조회 시 tenant_ctx 기반 repository 사용.
  - 원본 Question 과 연결된 Passage 도 같은 tenant 에서만 조회.
  - 신규 Question / QAValidationResult row 생성 전 sentinel UUID 교체.

에러 매핑:
  404: question_id 가 없거나 다른 tenant 소유.
  422: question type 이 V6 비적용 type.
  502: LLMSchemaValidationError.
  504: LLMTimeoutError.
  500: PermanentLLMError.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from llm.client import StructuredLLMClient
from llm.errors import (
    LLMSchemaValidationError,
    LLMTimeoutError,
    PermanentLLMError,
)
from llm.variants.v6_topic_main_idea_swap import (
    V6_APPLICABLE_TYPES,
    generate_v6_variant,
)
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.qa_validation_result import QAValidationResult
from shared.schemas.question import Question
from worksheet_api.db import get_db
from worksheet_api.llm_setup import get_llm_client
from worksheet_api.repositories import (
    PassageRepository,
    QAValidationResultRepository,
    QuestionRepository,
    TenantContext,
    get_tenant_context,
)

router = APIRouter(prefix="/questions", tags=["questions"])


# ─── 에러 매핑 헬퍼 (passages.py 의 _raise_llm_http_exception 과 동일 패턴) ────


def _raise_llm_http_exception(exc: Exception) -> None:
    """LLM 에러 → HTTPException 매핑 (ADR-0003 §D-3.5 / ADR-0013 D7 패턴).

    Args:
        exc: packages/llm/ 에러 계층의 예외.

    Raises:
        HTTPException: 매핑된 HTTP 상태 코드.
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
    raise HTTPException(status_code=502, detail=f"LLM 호출 실패: {exc}") from exc


# ─── V6 변형 라우트 ─────────────────────────────────────────────────────────


@router.post(
    "/{question_id}/variants/topic-main-idea-swap",
    response_model=Question,
    status_code=201,
)
async def create_v6_variant(
    question_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Question:
    """V6 topic_main_idea_swap 변형 생성 (Phase 3).

    원본 question_id 의 Question + Passage 를 조회 → LLM 으로 5개 선택지 새로 생성 →
    신규 Question row (variant_kind=TOPIC_MAIN_IDEA_SWAP) + QAValidationResult
    placeholder row 를 같은 트랜잭션 안에 저장한다.

    카탈로그 v0.4 §V6:
      - 적용 type: main_idea_22 / theme_23 / title_24.
      - 본문 유지, 선택지 5개만 새로 생성.
      - 한 지문에서 22/23/24 모두 변형 생성 가능.

    QAValidationResult:
      - validated_at: 생성 시각, passed=False (placeholder), validator_note="pending".
      - Phase 3 qa-validator 활성 시 실제 검증 결과로 갱신 (별 PR).

    멀티테넌트 강제 (W-2 패턴):
      - question_id 조회 시 tenant_ctx 기반 QuestionRepository 사용.
      - passage_id 조회 시 tenant_ctx 기반 PassageRepository 사용.
      - 신규 row 생성 전 sentinel UUID → 실제 tenant_id / workspace_id 교체.

    Args:
        question_id: 원본 Question UUID.
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        llm_client: StructuredLLMClient 구현체.
        session: DB 세션.

    Returns:
        생성된 변형 Question (201).

    Raises:
        HTTPException 404: question_id 가 없거나 다른 tenant 소유.
        HTTPException 404: question 에 연결된 Passage 가 없거나 다른 tenant 소유.
        HTTPException 422: question type 이 V6 비적용 type
            (main_idea_22 / theme_23 / title_24 외).
        HTTPException 502: LLMSchemaValidationError.
        HTTPException 504: LLMTimeoutError.
        HTTPException 500: PermanentLLMError.
    """
    # 1. 원본 Question 조회 — tenant 필터 강제 (W-2)
    question_repo = QuestionRepository(session, tenant_ctx)
    original_question = await question_repo.get(question_id)
    if original_question is None:
        raise HTTPException(
            status_code=404,
            detail=f"Question {question_id} 를 찾을 수 없습니다.",
        )

    # 2. type 검증 — V6 적용 가능 type 인지
    if original_question.type not in V6_APPLICABLE_TYPES:
        applicable = sorted(str(t) for t in V6_APPLICABLE_TYPES)
        raise HTTPException(
            status_code=422,
            detail=(
                f"V6 변형은 {applicable} type 에만 적용 가능합니다. "
                f"현재 question type: {original_question.type}."
            ),
        )

    # 3. 연결된 Passage 조회 — body_text 필요 (tenant 필터 강제)
    passage_repo = PassageRepository(session, tenant_ctx)
    passage = await passage_repo.get(original_question.passage_id)
    if passage is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Question {question_id} 에 연결된 Passage {original_question.passage_id} 를 "
                "찾을 수 없습니다."
            ),
        )

    # 4. LLM 변형 생성 — 에러는 _raise_llm_http_exception 으로 매핑
    try:
        variant_question_sentinel = await generate_v6_variant(
            passage_text=passage.body_text,
            original_question=original_question,
            llm_client=llm_client,
        )
    except LLMSchemaValidationError as exc:
        _raise_llm_http_exception(exc)
    except LLMTimeoutError as exc:
        _raise_llm_http_exception(exc)
    except PermanentLLMError as exc:
        _raise_llm_http_exception(exc)
    except Exception as exc:
        _raise_llm_http_exception(exc)

    # 5. sentinel UUID → 실제 ID 교체 + 영속화 (단일 트랜잭션)
    # ADR-0003 §D-3.6: model_copy 로 실제 tenant_id / workspace_id / passage_id / derived_from 주입
    variant_with_ids = variant_question_sentinel.model_copy(  # type: ignore[union-attr]
        update={
            "tenant_id": tenant_ctx.tenant_id,
            "workspace_id": tenant_ctx.workspace_id,
            "passage_id": original_question.passage_id,
            "derived_from_question_id": original_question.id,
        }
    )

    async with session.begin():
        question_repo2 = QuestionRepository(session, tenant_ctx)
        saved_variant = await question_repo2.create(variant_with_ids)

        # 6. QAValidationResult placeholder row 생성 (ADR-0017 D3-c)
        # Phase 3 qa-validator 활성 전 placeholder:
        #   passed=False (검증 미실시), validator_note="pending".
        qa_placeholder = QAValidationResult(
            tenant_id=tenant_ctx.tenant_id,
            workspace_id=tenant_ctx.workspace_id,
            question_id=saved_variant.id,
            passed=False,
            validator_note="pending — Phase 3 qa-validator 활성 시 검증 예정.",
        )
        qa_repo = QAValidationResultRepository(session, tenant_ctx)
        await qa_repo.create(qa_placeholder)

    return saved_variant
