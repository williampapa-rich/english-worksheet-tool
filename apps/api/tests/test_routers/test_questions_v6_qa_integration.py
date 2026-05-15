"""V6 라우트 + qa-validator 통합 테스트.

qa-validator 활성화 이후 (Phase 3 — 본 PR) 의 V6 라우트 동작 검증:
  - 변형 생성 후 qa-validator LLM call 이 호출되는지.
  - qa-validator 결과 (passed=True/False) 가 Question.uniqueness_validated 에 반영되는지.
  - qa-validator 결과가 QAValidationResult row 에 저장되는지.
  - qa-validator LLM 실패 시 변형 생성은 성공, passed=False graceful 처리.

mock 대상:
  - generate_v6_variant — 변형 생성 LLM call mock.
  - validate_question_uniqueness — qa-validator LLM call mock.
  - QuestionRepository / PassageRepository / QAValidationResultRepository — DB mock.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from worksheet_api.db import get_db
from worksheet_api.llm_setup import get_llm_client
from worksheet_api.main import app
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context

from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade
from shared.schemas.qa_validation_result import QAValidationResult
from shared.schemas.question import Question, QuestionType, VariantKind

# ─── 테스트 고정 UUID ────────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
QUESTION_ID_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
PASSAGE_ID_1 = uuid.UUID("22222222-2222-2222-2222-222222222222")
VARIANT_QUESTION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

_PASSAGE_TEXT = (
    "Reducing waste starts with awareness. Individual effort, "
    "multiplied across an entire community, creates meaningful change."
)

_FIVE_CHOICES = [
    "쓰레기를 줄이는 인식이 생기면 습관 변화로 이어져 지역 사회 전체에 긍정적 효과를 가져온다.",
    "재활용 가방 사용만으로 환경 문제를 완전히 해결할 수 있다.",
    "환경 보호를 위해서는 개인보다 기업의 역할이 더 중요하다.",
    "쓰레기 감량보다 무분별한 소비 자체를 막는 것이 더 시급한 과제이다.",
    "일회용품 사용을 줄이면 지방 자치 단체의 예산 문제도 해결된다.",
]


# ─── 팩토리 헬퍼 ─────────────────────────────────────────────────────────────


def _make_original_question(
    question_type: QuestionType = QuestionType.GIST_22,
) -> Question:
    return Question(
        id=QUESTION_ID_1,
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=PASSAGE_ID_1,
        type=question_type,
        variant_kind=VariantKind.ORIGINAL,
        question_text="다음 글의 요지로 가장 적절한 것은?",
        choices=["기존 선택지 1", "기존 선택지 2", "기존 선택지 3", "기존 선택지 4", "기존 선택지 5"],
        answer=3,
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_passage() -> Passage:
    return Passage(
        id=PASSAGE_ID_1,
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        body_text=_PASSAGE_TEXT,
        word_count=20,
        source=SourceMeta(provider=SourceProvider.USER_INPUT),
        target_grade=TargetGrade.HIGH_2,
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_saved_variant(
    uniqueness_validated: bool = True,
    uniqueness_validator_note: str | None = None,
) -> Question:
    return Question(
        id=VARIANT_QUESTION_ID,
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=PASSAGE_ID_1,
        derived_from_question_id=QUESTION_ID_1,
        type=QuestionType.GIST_22,
        variant_kind=VariantKind.TOPIC_MAIN_IDEA_SWAP,
        question_text="다음 글의 요지로 가장 적절한 것은?",
        choices=_FIVE_CHOICES,
        answer=1,
        explanation="이 글은 인식이 변화를 이끈다는 점을 주장한다.",
        variant_metadata={
            "sub_type": "main_idea_22",
            "choice_pattern": [
                "correct",
                "too-narrow",
                "too-broad",
                "opposite-conclusion",
                "plausible-unrelated",
            ],
        },
        uniqueness_validated=uniqueness_validated,
        uniqueness_validator_note=uniqueness_validator_note,
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_qa_result(
    passed: bool = True,
    validator_note: str = "[high] 정답이 thesis 와 정확히 일치.",
) -> QAValidationResult:
    return QAValidationResult(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        question_id=VARIANT_QUESTION_ID,
        passed=passed,
        validator_note=validator_note,
        validator_model="claude-sonnet-4-6",
        validator_version="v0.1",
        validated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


# ─── 픽스처 ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = begin_cm
    return session


@pytest.fixture
def tenant_ctx_a() -> TenantContext:
    return TenantContext(tenant_id=TENANT_A, workspace_id=WORKSPACE_A)


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def override_deps(
    mock_session: AsyncMock,
    tenant_ctx_a: TenantContext,
    mock_llm_client: AsyncMock,
) -> dict[Any, Any]:
    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def _get_tenant() -> TenantContext:
        return tenant_ctx_a

    def _get_llm() -> AsyncMock:
        return mock_llm_client

    return {
        get_db: _get_db,
        get_tenant_context: _get_tenant,
        get_llm_client: _get_llm,
    }


@pytest.fixture
async def async_client(override_deps: dict[Any, Any]) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides.update(override_deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ─── TC-1: qa-validator passed=True — Question.uniqueness_validated=True ─────


@pytest.mark.asyncio
async def test_v6_qa_validator_called_and_result_stored_passed(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """V6 라우트에서 qa-validator 가 호출되고, passed=True 결과가 Question 캐시 + QAValidationResult 에 저장된다."""
    original = _make_original_question()
    passage = _make_passage()
    qa_result = _make_qa_result(passed=True, validator_note="[high] 정답 유일.")
    saved_variant = _make_saved_variant(
        uniqueness_validated=True,
        uniqueness_validator_note="[high] 정답 유일.",
    )

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.QAValidationResultRepository") as mock_qa_repo_cls,
        patch("worksheet_api.routers.questions.generate_v6_variant") as mock_generate,
        patch("worksheet_api.routers.questions.validate_question_uniqueness") as mock_validate,
    ):
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo2 = AsyncMock()
        mock_q_repo2.create = AsyncMock(return_value=saved_variant)
        mock_q_repo_cls.side_effect = [mock_q_repo, mock_q_repo2]

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=passage)
        mock_p_repo_cls.return_value = mock_p_repo

        mock_qa_repo = AsyncMock()
        mock_qa_repo.create = AsyncMock(return_value=qa_result)
        mock_qa_repo_cls.return_value = mock_qa_repo

        sentinel_variant = saved_variant.model_copy(
            update={"id": uuid.UUID(int=0), "tenant_id": uuid.UUID(int=0)}
        )
        mock_generate.return_value = sentinel_variant
        mock_validate.return_value = qa_result

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    assert response.status_code == 201

    # qa-validator 가 1회 호출되었는지
    mock_validate.assert_awaited_once()
    call_kwargs = mock_validate.call_args.kwargs
    assert "question" in call_kwargs
    assert "passage_text" in call_kwargs
    assert call_kwargs["passage_text"] == _PASSAGE_TEXT

    # QAValidationResult 저장 확인 (실제 검증 결과 — placeholder 아님)
    mock_qa_repo.create.assert_awaited_once()
    stored_qa: QAValidationResult = mock_qa_repo.create.call_args[0][0]
    assert stored_qa.passed is True
    assert "pending" not in (stored_qa.validator_note or "")

    # Question.uniqueness_validated 캐시 확인
    data = response.json()
    assert data["uniqueness_validated"] is True


# ─── TC-2: qa-validator passed=False — Question.uniqueness_validated=False ───


@pytest.mark.asyncio
async def test_v6_qa_validator_failed_result_stored(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """qa-validator 가 passed=False 반환 시 Question.uniqueness_validated=False 로 저장."""
    original = _make_original_question()
    passage = _make_passage()
    fail_note = "[medium] 선지 ②와 ④ 모두 정답 가능."
    qa_result = _make_qa_result(passed=False, validator_note=fail_note)
    saved_variant = _make_saved_variant(
        uniqueness_validated=False,
        uniqueness_validator_note=fail_note,
    )

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.QAValidationResultRepository") as mock_qa_repo_cls,
        patch("worksheet_api.routers.questions.generate_v6_variant") as mock_generate,
        patch("worksheet_api.routers.questions.validate_question_uniqueness") as mock_validate,
    ):
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo2 = AsyncMock()
        mock_q_repo2.create = AsyncMock(return_value=saved_variant)
        mock_q_repo_cls.side_effect = [mock_q_repo, mock_q_repo2]

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=passage)
        mock_p_repo_cls.return_value = mock_p_repo

        mock_qa_repo = AsyncMock()
        mock_qa_repo.create = AsyncMock(return_value=qa_result)
        mock_qa_repo_cls.return_value = mock_qa_repo

        sentinel_variant = saved_variant.model_copy(
            update={"id": uuid.UUID(int=0), "tenant_id": uuid.UUID(int=0)}
        )
        mock_generate.return_value = sentinel_variant
        mock_validate.return_value = qa_result

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    assert response.status_code == 201  # 변형 생성은 성공

    data = response.json()
    # uniqueness_validated=False 라도 변형 자체는 201 반환
    assert data["uniqueness_validated"] is False

    # QAValidationResult 에 실제 실패 결과 저장
    stored_qa: QAValidationResult = mock_qa_repo.create.call_args[0][0]
    assert stored_qa.passed is False


# ─── TC-3: qa-validator LLM 실패 — 변형 생성은 성공 (graceful) ───────────────


@pytest.mark.asyncio
async def test_v6_qa_validator_error_graceful_variant_still_201(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """qa-validator LLM 실패 시 변형 생성은 201 성공, passed=False graceful 처리."""
    original = _make_original_question()
    passage = _make_passage()
    error_note = "validator_error: LLMTimeoutError: timeout after 60s"
    qa_error_result = _make_qa_result(passed=False, validator_note=error_note)
    saved_variant = _make_saved_variant(
        uniqueness_validated=False,
        uniqueness_validator_note=error_note,
    )

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.QAValidationResultRepository") as mock_qa_repo_cls,
        patch("worksheet_api.routers.questions.generate_v6_variant") as mock_generate,
        patch("worksheet_api.routers.questions.validate_question_uniqueness") as mock_validate,
    ):
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo2 = AsyncMock()
        mock_q_repo2.create = AsyncMock(return_value=saved_variant)
        mock_q_repo_cls.side_effect = [mock_q_repo, mock_q_repo2]

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=passage)
        mock_p_repo_cls.return_value = mock_p_repo

        mock_qa_repo = AsyncMock()
        mock_qa_repo.create = AsyncMock(return_value=qa_error_result)
        mock_qa_repo_cls.return_value = mock_qa_repo

        sentinel_variant = saved_variant.model_copy(
            update={"id": uuid.UUID(int=0), "tenant_id": uuid.UUID(int=0)}
        )
        mock_generate.return_value = sentinel_variant
        # validate_question_uniqueness 자체는 graceful — exception 대신 passed=False QAValidationResult 반환
        mock_validate.return_value = qa_error_result

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    # 변형 생성은 성공
    assert response.status_code == 201
    # qa-validator 실패도 QAValidationResult 저장됨
    mock_qa_repo.create.assert_awaited_once()
    stored_qa: QAValidationResult = mock_qa_repo.create.call_args[0][0]
    assert stored_qa.passed is False
    assert "validator_error" in (stored_qa.validator_note or "")


# ─── TC-4: qa-validator 에 passage_text 와 question 이 올바르게 전달됨 ─────────


@pytest.mark.asyncio
async def test_v6_qa_validator_receives_correct_inputs(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """validate_question_uniqueness 에 passage_text 와 question 이 올바르게 전달되는지 확인."""
    original = _make_original_question()
    passage = _make_passage()
    qa_result = _make_qa_result(passed=True)
    saved_variant = _make_saved_variant(uniqueness_validated=True)

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.QAValidationResultRepository") as mock_qa_repo_cls,
        patch("worksheet_api.routers.questions.generate_v6_variant") as mock_generate,
        patch("worksheet_api.routers.questions.validate_question_uniqueness") as mock_validate,
    ):
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo2 = AsyncMock()
        mock_q_repo2.create = AsyncMock(return_value=saved_variant)
        mock_q_repo_cls.side_effect = [mock_q_repo, mock_q_repo2]

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=passage)
        mock_p_repo_cls.return_value = mock_p_repo

        mock_qa_repo = AsyncMock()
        mock_qa_repo.create = AsyncMock(return_value=qa_result)
        mock_qa_repo_cls.return_value = mock_qa_repo

        sentinel_variant = saved_variant.model_copy(
            update={"id": uuid.UUID(int=0), "tenant_id": uuid.UUID(int=0)}
        )
        mock_generate.return_value = sentinel_variant
        mock_validate.return_value = qa_result

        await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    # validate_question_uniqueness 호출 인수 검증
    mock_validate.assert_awaited_once()
    call_kwargs = mock_validate.call_args.kwargs
    assert call_kwargs["passage_text"] == _PASSAGE_TEXT
    assert call_kwargs["tenant_id"] == TENANT_A
    assert call_kwargs["workspace_id"] == WORKSPACE_A
    # question 인수가 전달되었는지
    assert "question" in call_kwargs


# ─── TC-5: V2/V4/V5/V7 도 qa-validator 호출 확인 (smoke) ────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "variant_url,generate_fn_path,question_type",
    [
        (
            "vocabulary-inline",
            "worksheet_api.routers.questions.generate_v2_variant",
            QuestionType.VOCABULARY_30,
        ),
        (
            "grammar-inline",
            "worksheet_api.routers.questions.generate_v4_variant",
            QuestionType.GRAMMAR_29,
        ),
        (
            "blank-inference",
            "worksheet_api.routers.questions.generate_v5_variant",
            QuestionType.BLANK_PHRASE_31,
        ),
        (
            "order-shuffle",
            "worksheet_api.routers.questions.generate_v7_variant",
            QuestionType.ORDER_36,
        ),
    ],
)
async def test_other_variants_qa_validator_called(
    variant_url: str,
    generate_fn_path: str,
    question_type: QuestionType,
    mock_session: AsyncMock,
    tenant_ctx_a: TenantContext,
    mock_llm_client: AsyncMock,
) -> None:
    """V2/V4/V5/V7 라우트도 qa-validator 를 호출하는지 smoke 확인."""
    original = Question(
        id=QUESTION_ID_1,
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=PASSAGE_ID_1,
        type=question_type,
        variant_kind=VariantKind.ORIGINAL,
        question_text="문제 지시문",
        choices=["①", "②", "③", "④", "⑤"],
        answer=1,
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )
    passage = _make_passage()
    qa_result = _make_qa_result(passed=True)
    saved_variant = _make_saved_variant(uniqueness_validated=True)

    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def _get_tenant() -> TenantContext:
        return tenant_ctx_a

    def _get_llm() -> AsyncMock:
        return mock_llm_client

    app.dependency_overrides = {
        get_db: _get_db,
        get_tenant_context: _get_tenant,
        get_llm_client: _get_llm,
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            with (
                patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
                patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
                patch("worksheet_api.routers.questions.QAValidationResultRepository") as mock_qa_repo_cls,
                patch(generate_fn_path) as mock_generate,
                patch("worksheet_api.routers.questions.validate_question_uniqueness") as mock_validate,
            ):
                mock_q_repo = AsyncMock()
                mock_q_repo.get = AsyncMock(return_value=original)
                mock_q_repo2 = AsyncMock()
                mock_q_repo2.create = AsyncMock(return_value=saved_variant)
                mock_q_repo_cls.side_effect = [mock_q_repo, mock_q_repo2]

                mock_p_repo = AsyncMock()
                mock_p_repo.get = AsyncMock(return_value=passage)
                mock_p_repo_cls.return_value = mock_p_repo

                mock_qa_repo = AsyncMock()
                mock_qa_repo.create = AsyncMock(return_value=qa_result)
                mock_qa_repo_cls.return_value = mock_qa_repo

                sentinel_variant = saved_variant.model_copy(
                    update={"id": uuid.UUID(int=0), "tenant_id": uuid.UUID(int=0)}
                )
                mock_generate.return_value = sentinel_variant
                mock_validate.return_value = qa_result

                response = await client.post(
                    f"/questions/{QUESTION_ID_1}/variants/{variant_url}"
                )

        assert response.status_code == 201, (
            f"{variant_url} 라우트 실패: {response.status_code} {response.text}"
        )
        # qa-validator 가 1회 호출되었는지
        mock_validate.assert_awaited_once()

    finally:
        app.dependency_overrides.clear()
