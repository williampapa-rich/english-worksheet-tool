"""Question API 엔드포인트 (Phase 3 — 변형 생성 라우트).

Phase 3 변형 라우트:
  POST /questions/{question_id}/variants/vocabulary-swap — V1 변형 생성.
  POST /questions/{question_id}/variants/topic-main-idea-swap — V6 변형 생성.
  POST /questions/{question_id}/variants/vocabulary-inline — V2 변형 생성.
  POST /questions/{question_id}/variants/blank-inference — V5 변형 생성.
  POST /questions/{question_id}/variants/grammar-inline — V4 변형 생성.
  POST /questions/{question_id}/variants/grammar-swap — V3 변형 생성.
  POST /questions/{question_id}/variants/order-shuffle — V7 변형 생성.
  POST /questions/{question_id}/variants/sentence-insertion-shift — V8 변형 생성.
  POST /questions/{question_id}/variants/summary-blank-swap — V10 변형 생성.
  POST /questions/{question_id}/variants/irrelevant-sentence-inject — V9 변형 생성.

ADR-0017 D2-c + D3-c (qa-validator 활성화):
  - 변형은 항상 신규 Question row INSERT (augment 와 달리 mode 개념 없음).
  - variant_kind / derived_from_question_id 채워진 신규 Question 반환.
  - 변형 생성 직후 qa-validator LLM call 로 정답 유일성 검증.
  - QAValidationResult row 저장 (실제 검증 결과 — placeholder 아님).
  - Question.uniqueness_validated / uniqueness_validator_note 캐시 갱신.
  - 검증 LLM 실패 시 graceful degradation — 변형 생성 자체는 성공.

멀티테넌트 강제 (W-2 패턴):
  - 원본 question_id 조회 시 tenant_ctx 기반 repository 사용.
  - 원본 Question 과 연결된 Passage 도 같은 tenant 에서만 조회.
  - 신규 Question / QAValidationResult row 생성 전 sentinel UUID 교체.

에러 매핑:
  404: question_id 가 없거나 다른 tenant 소유.
  422: question type 이 해당 변형 비적용 type.
  502: LLMSchemaValidationError.
  504: LLMTimeoutError.
  500: PermanentLLMError.

LLM call 비용:
  변형 생성 1회 + qa-validator 검증 1회 = 2회 LLM call per request.
  캐싱 비활성 — 변형 결과가 매번 다름.
  Phase 4 비용 모니터링 영역.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from llm.client import StructuredLLMClient
from llm.errors import (
    LLMSchemaValidationError,
    LLMTimeoutError,
    PermanentLLMError,
)
from llm.variants.v1_vocabulary_swap import (
    V1_APPLICABLE_TYPES,
    generate_v1_variant,
)
from llm.variants.v2_vocabulary_inline import (
    V2_APPLICABLE_TYPES,
    generate_v2_variant,
)
from llm.variants.v3_grammar_swap import (
    V3_APPLICABLE_TYPES,
    generate_v3_variant,
)
from llm.variants.v4_grammar_inline import (
    V4_APPLICABLE_TYPES,
    generate_v4_variant,
)
from llm.variants.v5_blank_inference import (
    V5_APPLICABLE_TYPES,
    generate_v5_variant,
)
from llm.variants.v6_topic_main_idea_swap import (
    V6_APPLICABLE_TYPES,
    generate_v6_variant,
)
from llm.variants.v7_order_shuffle import (
    V7_APPLICABLE_TYPES,
    generate_v7_variant,
)
from llm.variants.v8_sentence_insertion_shift import (
    V8_APPLICABLE_TYPES,
    generate_v8_variant,
)
from llm.variants.v9_irrelevant_sentence_inject import (
    V9_APPLICABLE_TYPES,
    generate_v9_variant,
)
from llm.variants.v10_summary_blank_swap import (
    V10_APPLICABLE_TYPES,
    generate_v10_variant,
)
from qa_validator.uniqueness import validate_question_uniqueness
from sqlmodel.ext.asyncio.session import AsyncSession

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

logger = logging.getLogger(__name__)

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
    qa-validator 로 정답 유일성 검증 → 신규 Question row (variant_kind=TOPIC_MAIN_IDEA_SWAP)
    + QAValidationResult row 를 저장한다.

    카탈로그 v0.4 §V6:
      - 적용 type: main_idea_22 / theme_23 / title_24.
      - 본문 유지, 선택지 5개만 새로 생성.
      - 한 지문에서 22/23/24 모두 변형 생성 가능.

    QAValidationResult (ADR-0017 D3-c 활성):
      - 변형 생성 직후 별도 LLM call 로 정답 유일성 검증.
      - Question.uniqueness_validated / uniqueness_validator_note 캐시 갱신.
      - 검증 실패 시에도 변형 생성 자체는 성공 (비치명).

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

    # 5. sentinel UUID → 실제 ID 교체 (qa-validator 는 session.begin() 밖에서 호출)
    # qa-validator LLM call 은 DB 트랜잭션 밖 — LLM 은 rollback 불가, 트랜잭션 내 장시간 hold 금지
    qa_result = await validate_question_uniqueness(
        question=variant_with_ids,
        passage_text=passage.body_text,
        client=llm_client,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
    )

    # 6. 검증 결과를 variant 에 캐시 (ADR-0017 D3-c 하이브리드)
    variant_with_qa = variant_with_ids.model_copy(
        update={
            "uniqueness_validated": qa_result.passed,
            "uniqueness_validator_note": qa_result.validator_note,
        }
    )

    async with session.begin():
        question_repo2 = QuestionRepository(session, tenant_ctx)
        saved_variant = await question_repo2.create(variant_with_qa)

        # 7. QAValidationResult row 저장 (실제 검증 결과 — placeholder 아님)
        qa_result_with_question_id = qa_result.model_copy(update={"question_id": saved_variant.id})
        qa_repo = QAValidationResultRepository(session, tenant_ctx)
        await qa_repo.create(qa_result_with_question_id)

    return saved_variant


# ─── V2 변형 라우트 ─────────────────────────────────────────────────────────


@router.post(
    "/{question_id}/variants/vocabulary-inline",
    response_model=Question,
    status_code=201,
)
async def create_v2_variant(
    question_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Question:
    """V2 vocabulary_inline 변형 생성 (Phase 3).

    원본 question_id 의 Question + Passage 를 조회 → LLM 으로 어휘 인라인 박스 2개 생성 →
    신규 Question row (variant_kind=VOCABULARY_INLINE) + QAValidationResult
    placeholder row 를 같은 트랜잭션 안에 저장한다.

    카탈로그 v0.4 §V2:
      - 적용 type: vocabulary_30 / blank_phrase_31.
      - 본문 2~3곳에 (A) [opt1 / opt2] 박스 삽입.
      - 5개 매트릭스 선택지 (박스별 조합).
      - inline_choices 필드 채움.

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
        HTTPException 422: question type 이 V2 비적용 type
            (vocabulary_30 / blank_phrase_31 외).
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

    # 2. type 검증 — V2 적용 가능 type 인지
    if original_question.type not in V2_APPLICABLE_TYPES:
        applicable = sorted(str(t) for t in V2_APPLICABLE_TYPES)
        raise HTTPException(
            status_code=422,
            detail=(
                f"V2 변형은 {applicable} type 에만 적용 가능합니다. "
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
        variant_question_sentinel = await generate_v2_variant(
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

    # 5. sentinel UUID → 실제 ID 교체
    variant_with_ids = variant_question_sentinel.model_copy(  # type: ignore[union-attr]
        update={
            "tenant_id": tenant_ctx.tenant_id,
            "workspace_id": tenant_ctx.workspace_id,
            "passage_id": original_question.passage_id,
            "derived_from_question_id": original_question.id,
        }
    )

    # qa-validator LLM call — 트랜잭션 밖에서 실행 (CLAUDE.md §7.6 검증 분리)
    qa_result = await validate_question_uniqueness(
        question=variant_with_ids,
        passage_text=passage.body_text,
        client=llm_client,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
    )

    variant_with_qa = variant_with_ids.model_copy(
        update={
            "uniqueness_validated": qa_result.passed,
            "uniqueness_validator_note": qa_result.validator_note,
        }
    )

    async with session.begin():
        question_repo2 = QuestionRepository(session, tenant_ctx)
        saved_variant = await question_repo2.create(variant_with_qa)

        qa_result_with_question_id = qa_result.model_copy(update={"question_id": saved_variant.id})
        qa_repo = QAValidationResultRepository(session, tenant_ctx)
        await qa_repo.create(qa_result_with_question_id)

    return saved_variant


# ─── V5 변형 라우트 ─────────────────────────────────────────────────────────


@router.post(
    "/{question_id}/variants/blank-inference",
    response_model=Question,
    status_code=201,
)
async def create_v5_variant(
    question_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Question:
    """V5 blank_inference 변형 생성 (Phase 3).

    원본 question_id 의 Question + Passage 를 조회 → LLM 으로 빈칸 위치 선정 +
    5개 선택지 생성 → 신규 Question row (variant_kind=BLANK_INFERENCE) +
    QAValidationResult placeholder row 를 같은 트랜잭션 안에 저장한다.

    카탈로그 v0.4 §V5:
      - 적용 type: blank_phrase_31 / blank_clause_32 / blank_clause_33 / blank_clause_34.
      - thesis 핵심 어구/절을 `______` 로 가린 body_with_blank + 5개 선택지 생성.
      - variant_metadata 에 blank_position [start, end] (char offset) 기록.

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
        HTTPException 422: question type 이 V5 비적용 type
            (blank_phrase_31 / blank_clause_32~34 외).
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

    # 2. type 검증 — V5 적용 가능 type 인지
    if original_question.type not in V5_APPLICABLE_TYPES:
        applicable = sorted(str(t) for t in V5_APPLICABLE_TYPES)
        raise HTTPException(
            status_code=422,
            detail=(
                f"V5 변형은 {applicable} type 에만 적용 가능합니다. "
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
        variant_question_sentinel = await generate_v5_variant(
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

    # 5. sentinel UUID → 실제 ID 교체
    # ADR-0003 §D-3.6: model_copy 로 실제 tenant_id / workspace_id / passage_id / derived_from 주입
    variant_with_ids = variant_question_sentinel.model_copy(  # type: ignore[union-attr]
        update={
            "tenant_id": tenant_ctx.tenant_id,
            "workspace_id": tenant_ctx.workspace_id,
            "passage_id": original_question.passage_id,
            "derived_from_question_id": original_question.id,
        }
    )

    # qa-validator LLM call — 트랜잭션 밖에서 실행 (CLAUDE.md §7.6 검증 분리)
    qa_result = await validate_question_uniqueness(
        question=variant_with_ids,
        passage_text=passage.body_text,
        client=llm_client,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
    )

    variant_with_qa = variant_with_ids.model_copy(
        update={
            "uniqueness_validated": qa_result.passed,
            "uniqueness_validator_note": qa_result.validator_note,
        }
    )

    async with session.begin():
        question_repo2 = QuestionRepository(session, tenant_ctx)
        saved_variant = await question_repo2.create(variant_with_qa)

        qa_result_with_question_id = qa_result.model_copy(update={"question_id": saved_variant.id})
        qa_repo = QAValidationResultRepository(session, tenant_ctx)
        await qa_repo.create(qa_result_with_question_id)

    return saved_variant


# ─── V4 변형 라우트 ─────────────────────────────────────────────────────────


@router.post(
    "/{question_id}/variants/grammar-inline",
    response_model=Question,
    status_code=201,
)
async def create_v4_variant(
    question_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Question:
    """V4 grammar_inline 변형 생성 (Phase 3).

    원본 question_id 의 Question + Passage 를 조회 → LLM 으로 어법 인라인 박스 2개 생성 →
    신규 Question row (variant_kind=GRAMMAR_INLINE) + QAValidationResult
    placeholder row 를 같은 트랜잭션 안에 저장한다.

    카탈로그 v0.4 §V4:
      - 적용 type: grammar_29.
      - 본문 2~3곳에 (A) [opt1 / opt2] 박스 삽입 (어법 변별 포인트).
      - 5개 매트릭스 선택지 (박스별 조합).
      - inline_choices 필드 채움 (kind=GRAMMAR).

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
        HTTPException 422: question type 이 V4 비적용 type (grammar_29 외).
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

    # 2. type 검증 — V4 적용 가능 type 인지
    if original_question.type not in V4_APPLICABLE_TYPES:
        applicable = sorted(str(t) for t in V4_APPLICABLE_TYPES)
        raise HTTPException(
            status_code=422,
            detail=(
                f"V4 변형은 {applicable} type 에만 적용 가능합니다. "
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
        variant_question_sentinel = await generate_v4_variant(
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

    # 5. sentinel UUID → 실제 ID 교체
    # ADR-0003 §D-3.6: model_copy 로 실제 tenant_id / workspace_id / passage_id / derived_from 주입
    variant_with_ids = variant_question_sentinel.model_copy(  # type: ignore[union-attr]
        update={
            "tenant_id": tenant_ctx.tenant_id,
            "workspace_id": tenant_ctx.workspace_id,
            "passage_id": original_question.passage_id,
            "derived_from_question_id": original_question.id,
        }
    )

    # qa-validator LLM call — 트랜잭션 밖에서 실행 (CLAUDE.md §7.6 검증 분리)
    qa_result = await validate_question_uniqueness(
        question=variant_with_ids,
        passage_text=passage.body_text,
        client=llm_client,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
    )

    variant_with_qa = variant_with_ids.model_copy(
        update={
            "uniqueness_validated": qa_result.passed,
            "uniqueness_validator_note": qa_result.validator_note,
        }
    )

    async with session.begin():
        question_repo2 = QuestionRepository(session, tenant_ctx)
        saved_variant = await question_repo2.create(variant_with_qa)

        qa_result_with_question_id = qa_result.model_copy(update={"question_id": saved_variant.id})
        qa_repo = QAValidationResultRepository(session, tenant_ctx)
        await qa_repo.create(qa_result_with_question_id)

    return saved_variant


# ─── V3 변형 라우트 ─────────────────────────────────────────────────────────


@router.post(
    "/{question_id}/variants/grammar-swap",
    response_model=Question,
    status_code=201,
)
async def create_v3_variant(
    question_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Question:
    """V3 grammar_swap 변형 생성 (Phase 3).

    원본 question_id 의 Question + Passage 를 조회 → LLM 으로 어법 후보 5곳 선택 +
    1곳 어법 오류 swap + 5개 선택지 (①~⑤) 생성 → 신규 Question row
    (variant_kind=GRAMMAR_SWAP) + QAValidationResult row 를 저장한다.

    카탈로그 v0.4 §V3:
      - 적용 type: grammar_29.
      - 본문의 어법 후보 5곳 중 1곳을 어법 오류 단어로 swap.
      - 5개 선택지 (①~⑤) — 각 선택지가 후보 위치의 구문.
      - answer = 오류가 있는 위치 (1-based, 1~5).
      - variant_metadata 에 swap 상세 기록 (swapped_position_index / original_phrase /
        swapped_phrase / error_type).

    QAValidationResult (ADR-0017 D3-c 활성):
      - 변형 생성 직후 별도 LLM call 로 정답 유일성 검증.
      - Question.uniqueness_validated / uniqueness_validator_note 캐시 갱신.
      - 검증 실패 시에도 변형 생성 자체는 성공 (비치명).

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
        생성된 변형 Question (201). choices (①~⑤) + variant_metadata 채움.

    Raises:
        HTTPException 404: question_id 가 없거나 다른 tenant 소유.
        HTTPException 404: question 에 연결된 Passage 가 없거나 다른 tenant 소유.
        HTTPException 422: question type 이 V3 비적용 type (grammar_29 외).
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

    # 2. type 검증 — V3 적용 가능 type 인지
    if original_question.type not in V3_APPLICABLE_TYPES:
        applicable = sorted(str(t) for t in V3_APPLICABLE_TYPES)
        raise HTTPException(
            status_code=422,
            detail=(
                f"V3 변형은 {applicable} type 에만 적용 가능합니다. "
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

    # 4. LLM 변형 생성 (V3 grammar_swap) — 에러는 _raise_llm_http_exception 으로 매핑
    try:
        variant_question_sentinel = await generate_v3_variant(
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

    # 5. sentinel UUID → 실제 ID 교체
    # ADR-0003 §D-3.6: model_copy 로 실제 tenant_id / workspace_id / passage_id / derived_from 주입
    variant_with_ids_v3 = variant_question_sentinel.model_copy(  # type: ignore[union-attr]
        update={
            "tenant_id": tenant_ctx.tenant_id,
            "workspace_id": tenant_ctx.workspace_id,
            "passage_id": original_question.passage_id,
            "derived_from_question_id": original_question.id,
        }
    )

    # qa-validator LLM call — 트랜잭션 밖에서 실행 (CLAUDE.md §7.6 검증 분리)
    qa_result_v3 = await validate_question_uniqueness(
        question=variant_with_ids_v3,
        passage_text=passage.body_text,
        client=llm_client,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
    )

    variant_with_qa_v3 = variant_with_ids_v3.model_copy(
        update={
            "uniqueness_validated": qa_result_v3.passed,
            "uniqueness_validator_note": qa_result_v3.validator_note,
        }
    )

    async with session.begin():
        question_repo2 = QuestionRepository(session, tenant_ctx)
        saved_v3 = await question_repo2.create(variant_with_qa_v3)

        qa_result_v3_with_id = qa_result_v3.model_copy(update={"question_id": saved_v3.id})
        qa_repo_v3 = QAValidationResultRepository(session, tenant_ctx)
        await qa_repo_v3.create(qa_result_v3_with_id)

    return saved_v3


# ─── V7 변형 라우트 ─────────────────────────────────────────────────────────


@router.post(
    "/{question_id}/variants/order-shuffle",
    response_model=Question,
    status_code=201,
)
async def create_v7_variant(
    question_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Question:
    """V7 order_shuffle 변형 생성 (Phase 3).

    원본 question_id 의 Question + Passage 를 조회 → LLM 으로 도입 1단락 + (A)/(B)/(C)
    3단락 분할 + 5개 순서 조합 선택지 생성 → 신규 Question row
    (variant_kind=ORDER_SHUFFLE) + QAValidationResult placeholder row 를
    같은 트랜잭션 안에 저장한다.

    카탈로그 v0.4 §V7:
      - 적용 type: paragraph_order_36 / paragraph_order_37.
      - 원본 Passage 를 도입 + (A)/(B)/(C) 3단락으로 분할.
      - 5개 순서 조합 선택지 (예: "(A) - (B) - (C)").
      - sub_passages 필드 채움 — [(A) 문장들, (B) 문장들, (C) 문장들].

    QAValidationResult:
      - 변형 생성 직후 qa-validator LLM call 로 정답 유일성 검증.
      - passed / validator_note 실제 검증 결과로 채워짐 (ADR-0017 D3-c 활성).

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
        생성된 변형 Question (201). sub_passages 와 choices (순서 조합 문자열) 채움.

    Raises:
        HTTPException 404: question_id 가 없거나 다른 tenant 소유.
        HTTPException 404: question 에 연결된 Passage 가 없거나 다른 tenant 소유.
        HTTPException 422: question type 이 V7 비적용 type
            (paragraph_order_36 / paragraph_order_37 외).
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

    # 2. type 검증 — V7 적용 가능 type 인지
    if original_question.type not in V7_APPLICABLE_TYPES:
        applicable = sorted(str(t) for t in V7_APPLICABLE_TYPES)
        raise HTTPException(
            status_code=422,
            detail=(
                f"V7 변형은 {applicable} type 에만 적용 가능합니다. "
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

    # 4. LLM 변형 생성 (V7 order_shuffle) — 에러는 _raise_llm_http_exception 으로 매핑
    try:
        variant_question_sentinel = await generate_v7_variant(
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

    # 5. sentinel UUID → 실제 ID 교체
    variant_with_ids_v7 = variant_question_sentinel.model_copy(  # type: ignore[union-attr]
        update={
            "tenant_id": tenant_ctx.tenant_id,
            "workspace_id": tenant_ctx.workspace_id,
            "passage_id": original_question.passage_id,
            "derived_from_question_id": original_question.id,
        }
    )

    # qa-validator LLM call — 트랜잭션 밖에서 실행 (CLAUDE.md §7.6 검증 분리)
    qa_result_v7 = await validate_question_uniqueness(
        question=variant_with_ids_v7,
        passage_text=passage.body_text,
        client=llm_client,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
    )

    variant_with_qa_v7 = variant_with_ids_v7.model_copy(
        update={
            "uniqueness_validated": qa_result_v7.passed,
            "uniqueness_validator_note": qa_result_v7.validator_note,
        }
    )

    async with session.begin():
        question_repo2 = QuestionRepository(session, tenant_ctx)
        saved_v7 = await question_repo2.create(variant_with_qa_v7)

        qa_result_v7_with_id = qa_result_v7.model_copy(update={"question_id": saved_v7.id})
        qa_repo_v7 = QAValidationResultRepository(session, tenant_ctx)
        await qa_repo_v7.create(qa_result_v7_with_id)

    return saved_v7


# ─── V8 변형 라우트 ─────────────────────────────────────────────────────────


@router.post(
    "/{question_id}/variants/sentence-insertion-shift",
    response_model=Question,
    status_code=201,
)
async def create_v8_variant(
    question_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Question:
    """V8 sentence_insertion_shift 변형 생성 (Phase 3).

    원본 question_id 의 Question + Passage 를 조회 → LLM 으로 결정적 문장 추출 +
    ①~⑤ 위치 마커 삽입 → 신규 Question row (variant_kind=SENTENCE_INSERTION_SHIFT)
    + QAValidationResult row 를 저장한다.

    카탈로그 v0.4 §V8:
      - 적용 type: insertion_38 / insertion_39.
      - 본문에서 결정적 문장 1개 추출 → given_sentence.
      - 본문 안 ①~⑤ 위치 마커 5개 부착 → variant_metadata.body_with_markers.
      - choices 는 ["①", "②", "③", "④", "⑤"] 고정.
      - answer 는 원본 위치 (1-based).

    QAValidationResult (ADR-0017 D3-c 활성):
      - 변형 생성 직후 별도 LLM call 로 정답 유일성 검증.
      - Question.uniqueness_validated / uniqueness_validator_note 캐시 갱신.
      - 검증 실패 시에도 변형 생성 자체는 성공 (비치명).

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
        생성된 변형 Question (201). given_sentence 와 choices (위치 마커) 채움.

    Raises:
        HTTPException 404: question_id 가 없거나 다른 tenant 소유.
        HTTPException 404: question 에 연결된 Passage 가 없거나 다른 tenant 소유.
        HTTPException 422: question type 이 V8 비적용 type
            (insertion_38 / insertion_39 외).
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

    # 2. type 검증 — V8 적용 가능 type 인지
    if original_question.type not in V8_APPLICABLE_TYPES:
        applicable = sorted(str(t) for t in V8_APPLICABLE_TYPES)
        raise HTTPException(
            status_code=422,
            detail=(
                f"V8 변형은 {applicable} type 에만 적용 가능합니다. "
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

    # 4. LLM 변형 생성 (V8 sentence_insertion_shift) — 에러는 _raise_llm_http_exception 으로 매핑
    try:
        variant_question_sentinel = await generate_v8_variant(
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

    # 5. sentinel UUID → 실제 ID 교체
    variant_with_ids_v8 = variant_question_sentinel.model_copy(  # type: ignore[union-attr]
        update={
            "tenant_id": tenant_ctx.tenant_id,
            "workspace_id": tenant_ctx.workspace_id,
            "passage_id": original_question.passage_id,
            "derived_from_question_id": original_question.id,
        }
    )

    # qa-validator LLM call — 트랜잭션 밖에서 실행 (CLAUDE.md §7.6 검증 분리)
    qa_result_v8 = await validate_question_uniqueness(
        question=variant_with_ids_v8,
        passage_text=passage.body_text,
        client=llm_client,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
    )

    variant_with_qa_v8 = variant_with_ids_v8.model_copy(
        update={
            "uniqueness_validated": qa_result_v8.passed,
            "uniqueness_validator_note": qa_result_v8.validator_note,
        }
    )

    async with session.begin():
        question_repo2 = QuestionRepository(session, tenant_ctx)
        saved_v8 = await question_repo2.create(variant_with_qa_v8)

        qa_result_v8_with_id = qa_result_v8.model_copy(update={"question_id": saved_v8.id})
        qa_repo_v8 = QAValidationResultRepository(session, tenant_ctx)
        await qa_repo_v8.create(qa_result_v8_with_id)

    return saved_v8


# ─── V10 변형 라우트 ─────────────────────────────────────────────────────────


@router.post(
    "/{question_id}/variants/summary-blank-swap",
    response_model=Question,
    status_code=201,
)
async def create_v10_variant(
    question_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Question:
    """V10 summary_blank_swap 변형 생성 (Phase 3).

    원본 question_id 의 Question + Passage 를 조회 → LLM 으로 본문 thesis 1문장 요약 +
    (A)/(B) 이중 빈칸 + 5개 매트릭스 선택지 생성 → 신규 Question row
    (variant_kind=SUMMARY_BLANK_SWAP) + QAValidationResult row 를 저장한다.

    카탈로그 v0.4 §V10:
      - 적용 type: summary_40.
      - 본문 그대로 + 요약 1문장 새로 생성 (LLM 이 본문 thesis 압축).
      - 요약 문장에 (A) ______ ... (B) ______ 빈칸 2곳 (핵심 어휘 위치).
      - 5개 선택지 — 각 선택지가 (A) word …… (B) word 쌍.
      - choice_format=MATRIX_AB + choice_matrix 채움.
      - variant_metadata: { "summary_text": str, "blank_a_word": str, "blank_b_word": str }.

    QAValidationResult (ADR-0017 D3-c 활성):
      - 변형 생성 직후 별도 LLM call 로 정답 유일성 검증.
      - Question.uniqueness_validated / uniqueness_validator_note 캐시 갱신.
      - 검증 실패 시에도 변형 생성 자체는 성공 (비치명).

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
        생성된 변형 Question (201). summary + choices + choice_matrix 채움.

    Raises:
        HTTPException 404: question_id 가 없거나 다른 tenant 소유.
        HTTPException 404: question 에 연결된 Passage 가 없거나 다른 tenant 소유.
        HTTPException 422: question type 이 V10 비적용 type (summary_40 외).
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

    # 2. type 검증 — V10 적용 가능 type 인지
    if original_question.type not in V10_APPLICABLE_TYPES:
        applicable = sorted(str(t) for t in V10_APPLICABLE_TYPES)
        raise HTTPException(
            status_code=422,
            detail=(
                f"V10 변형은 {applicable} type 에만 적용 가능합니다. "
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

    # 4. LLM 변형 생성 (V10 summary_blank_swap) — 에러는 _raise_llm_http_exception 으로 매핑
    try:
        variant_question_sentinel = await generate_v10_variant(
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

    # 5. sentinel UUID → 실제 ID 교체
    # ADR-0003 §D-3.6: model_copy 로 실제 tenant_id / workspace_id / passage_id / derived_from 주입
    variant_with_ids_v10 = variant_question_sentinel.model_copy(  # type: ignore[union-attr]
        update={
            "tenant_id": tenant_ctx.tenant_id,
            "workspace_id": tenant_ctx.workspace_id,
            "passage_id": original_question.passage_id,
            "derived_from_question_id": original_question.id,
        }
    )

    # qa-validator LLM call — 트랜잭션 밖에서 실행 (CLAUDE.md §7.6 검증 분리)
    qa_result_v10 = await validate_question_uniqueness(
        question=variant_with_ids_v10,
        passage_text=passage.body_text,
        client=llm_client,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
    )

    variant_with_qa_v10 = variant_with_ids_v10.model_copy(
        update={
            "uniqueness_validated": qa_result_v10.passed,
            "uniqueness_validator_note": qa_result_v10.validator_note,
        }
    )

    async with session.begin():
        question_repo2 = QuestionRepository(session, tenant_ctx)
        saved_v10 = await question_repo2.create(variant_with_qa_v10)

        qa_result_v10_with_id = qa_result_v10.model_copy(update={"question_id": saved_v10.id})
        qa_repo_v10 = QAValidationResultRepository(session, tenant_ctx)
        await qa_repo_v10.create(qa_result_v10_with_id)

    return saved_v10


# ─── V9 변형 라우트 ─────────────────────────────────────────────────────────


@router.post(
    "/{question_id}/variants/irrelevant-sentence-inject",
    response_model=Question,
    status_code=201,
)
async def create_v9_variant(
    question_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Question:
    """V9 irrelevant_sentence_inject 변형 생성 (Phase 3).

    원본 question_id 의 Question + Passage 를 조회 → LLM 으로 무관 문장 주입 +
    ①~⑤ 위치 마커 삽입 → 신규 Question row (variant_kind=IRRELEVANT_SENTENCE_INJECT)
    + QAValidationResult row 를 저장한다.

    카탈로그 v0.4 §V9:
      - 적용 type: irrelevant_sentence_35.
      - 본문에서 무관 문장 주입 위치 선정 (시작/끝 제외, 중간 위치 선호).
      - lexical similarity 보존 + 논리 흐름 단절인 무관 문장 1개 생성.
      - 5문장 시퀀스에 ①~⑤ 마커 부착 (variant_metadata.body_with_markers).
      - choices 는 ["①", "②", "③", "④", "⑤"] 고정.
      - answer 는 주입된 무관 문장 위치 (1-based).

    QAValidationResult (ADR-0017 D3-c 활성):
      - 변형 생성 직후 별도 LLM call 로 정답 유일성 검증.
      - Question.uniqueness_validated / uniqueness_validator_note 캐시 갱신.
      - 검증 실패 시에도 변형 생성 자체는 성공 (비치명).

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
        생성된 변형 Question (201). choices (위치 마커) + variant_metadata 채움.

    Raises:
        HTTPException 404: question_id 가 없거나 다른 tenant 소유.
        HTTPException 404: question 에 연결된 Passage 가 없거나 다른 tenant 소유.
        HTTPException 422: question type 이 V9 비적용 type (irrelevant_sentence_35 외).
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

    # 2. type 검증 — V9 적용 가능 type 인지
    if original_question.type not in V9_APPLICABLE_TYPES:
        applicable = sorted(str(t) for t in V9_APPLICABLE_TYPES)
        raise HTTPException(
            status_code=422,
            detail=(
                f"V9 변형은 {applicable} type 에만 적용 가능합니다. "
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

    # 4. LLM 변형 생성 (V9 irrelevant_sentence_inject) — 에러는 _raise_llm_http_exception 으로 매핑
    try:
        variant_question_sentinel = await generate_v9_variant(
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

    # 5. sentinel UUID → 실제 ID 교체
    variant_with_ids_v9 = variant_question_sentinel.model_copy(  # type: ignore[union-attr]
        update={
            "tenant_id": tenant_ctx.tenant_id,
            "workspace_id": tenant_ctx.workspace_id,
            "passage_id": original_question.passage_id,
            "derived_from_question_id": original_question.id,
        }
    )

    # qa-validator LLM call — 트랜잭션 밖에서 실행 (CLAUDE.md §7.6 검증 분리)
    qa_result_v9 = await validate_question_uniqueness(
        question=variant_with_ids_v9,
        passage_text=passage.body_text,
        client=llm_client,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
    )

    variant_with_qa_v9 = variant_with_ids_v9.model_copy(
        update={
            "uniqueness_validated": qa_result_v9.passed,
            "uniqueness_validator_note": qa_result_v9.validator_note,
        }
    )

    async with session.begin():
        question_repo2 = QuestionRepository(session, tenant_ctx)
        saved_v9 = await question_repo2.create(variant_with_qa_v9)

        qa_result_v9_with_id = qa_result_v9.model_copy(update={"question_id": saved_v9.id})
        qa_repo_v9 = QAValidationResultRepository(session, tenant_ctx)
        await qa_repo_v9.create(qa_result_v9_with_id)

    return saved_v9


# ─── V1 변형 라우트 ─────────────────────────────────────────────────────────


@router.post(
    "/{question_id}/variants/vocabulary-swap",
    response_model=Question,
    status_code=201,
)
async def create_v1_variant(
    question_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Question:
    """V1 vocabulary_swap 변형 생성 (Phase 3).

    원본 question_id 의 Question + Passage 를 조회 → LLM 으로 5개 어휘 후보 위치 선택 +
    1개 부적절 단어 swap + ①~⑤ 마커 삽입 → 신규 Question row
    (variant_kind=VOCABULARY_SWAP) + QAValidationResult row 를 저장한다.

    카탈로그 v0.4 §V1:
      - 적용 type: vocabulary_30 / long_set_41_42.
      - 본문에서 5개 어휘 후보 위치 선택 (adjective / verb 권장, 의미 결정 단어).
      - 5개 중 1개를 의미 부적절 단어로 swap (반의어 또는 문맥 어긋남).
      - ①~⑤ 마커 인라인 삽입 → body_with_markers (variant_metadata 에 저장).
      - choices 는 5개 마커 위치의 단어.
      - answer 는 부적절 단어의 위치 (1-based).

    QAValidationResult (ADR-0017 D3-c 활성):
      - 변형 생성 직후 별도 LLM call 로 정답 유일성 검증.
      - Question.uniqueness_validated / uniqueness_validator_note 캐시 갱신.
      - 검증 실패 시에도 변형 생성 자체는 성공 (비치명).

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
        생성된 변형 Question (201). choices + answer + variant_metadata 채움.

    Raises:
        HTTPException 404: question_id 가 없거나 다른 tenant 소유.
        HTTPException 404: question 에 연결된 Passage 가 없거나 다른 tenant 소유.
        HTTPException 422: question type 이 V1 비적용 type
            (vocabulary_30 / long_set_41_42 외).
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

    # 2. type 검증 — V1 적용 가능 type 인지
    if original_question.type not in V1_APPLICABLE_TYPES:
        applicable = sorted(str(t) for t in V1_APPLICABLE_TYPES)
        raise HTTPException(
            status_code=422,
            detail=(
                f"V1 변형은 {applicable} type 에만 적용 가능합니다. "
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

    # 4. LLM 변형 생성 (V1 vocabulary_swap) — 에러는 _raise_llm_http_exception 으로 매핑
    try:
        variant_question_sentinel = await generate_v1_variant(
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

    # 5. sentinel UUID → 실제 ID 교체
    variant_with_ids_v1 = variant_question_sentinel.model_copy(  # type: ignore[union-attr]
        update={
            "tenant_id": tenant_ctx.tenant_id,
            "workspace_id": tenant_ctx.workspace_id,
            "passage_id": original_question.passage_id,
            "derived_from_question_id": original_question.id,
        }
    )

    # qa-validator LLM call — 트랜잭션 밖에서 실행 (CLAUDE.md §7.6 검증 분리)
    qa_result_v1 = await validate_question_uniqueness(
        question=variant_with_ids_v1,
        passage_text=passage.body_text,
        client=llm_client,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
    )

    variant_with_qa_v1 = variant_with_ids_v1.model_copy(
        update={
            "uniqueness_validated": qa_result_v1.passed,
            "uniqueness_validator_note": qa_result_v1.validator_note,
        }
    )

    async with session.begin():
        question_repo2 = QuestionRepository(session, tenant_ctx)
        saved_v1 = await question_repo2.create(variant_with_qa_v1)

        qa_result_v1_with_id = qa_result_v1.model_copy(update={"question_id": saved_v1.id})
        qa_repo_v1 = QAValidationResultRepository(session, tenant_ctx)
        await qa_repo_v1.create(qa_result_v1_with_id)

    return saved_v1
