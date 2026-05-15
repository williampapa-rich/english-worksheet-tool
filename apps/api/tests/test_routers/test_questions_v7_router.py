"""POST /questions/{question_id}/variants/order-shuffle 라우터 단위 테스트.

mock session + mock repository + mock LLM client 로 실제 DB / LLM 없이 실행한다.

커버 케이스:
  - 201 정상 — paragraph_order_36 원본 → V7 변형 Question 반환.
  - 201 정상 — paragraph_order_37 원본.
  - 201 정상 — QAValidationResult placeholder row 생성 확인.
  - 404 — 존재하지 않는 question_id.
  - 404 — passage not found.
  - 422 — V7 비적용 type (grammar_29).
  - 502 — LLMSchemaValidationError.
  - 504 — LLMTimeoutError.
  - 500 — PermanentLLMError.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
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

# ─── 테스트용 고정 UUID ──────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
QUESTION_ID_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
PASSAGE_ID_1 = uuid.UUID("22222222-2222-2222-2222-222222222222")
VARIANT_QUESTION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

_URBAN_CYCLING_PASSAGE_TEXT = (
    "Over the past decade, urban cycling has transformed from a niche hobby into a "
    "mainstream mode of transportation. City planners began investing in dedicated bike "
    "lanes, making cycling safer for commuters. Consequently, city authorities introduced "
    "stricter traffic regulations."
)

_FIVE_ORDER_CHOICES = [
    "(A) - (B) - (C)",
    "(B) - (A) - (C)",
    "(C) - (A) - (B)",
    "(A) - (C) - (B)",
    "(B) - (C) - (A)",
]

_SUB_PASSAGES = [
    ["City planners began investing in dedicated bike lanes, making cycling safer for commuters."],
    ["However, this growth brought new challenges."],
    ["Consequently, city authorities introduced stricter traffic regulations."],
]

_INTRO = "Over the past decade, urban cycling has transformed from a niche hobby into a mainstream mode of transportation."


# ─── 팩토리 헬퍼 ─────────────────────────────────────────────────────────────


def _make_original_question(
    question_type: QuestionType = QuestionType.ORDER_36,
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
) -> Question:
    return Question(
        id=QUESTION_ID_1,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        passage_id=PASSAGE_ID_1,
        type=question_type,
        variant_kind=VariantKind.ORIGINAL,
        question_text="주어진 글 다음에 이어질 글의 순서로 가장 적절한 것은?",
        choices=[],
        answer=1,
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_passage(
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
) -> Passage:
    return Passage(
        id=PASSAGE_ID_1,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        body_text=_URBAN_CYCLING_PASSAGE_TEXT,
        word_count=30,
        source=SourceMeta(provider=SourceProvider.USER_INPUT),
        target_grade=TargetGrade.HIGH_2,
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_saved_variant(
    question_type: QuestionType = QuestionType.ORDER_36,
) -> Question:
    return Question(
        id=VARIANT_QUESTION_ID,
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=PASSAGE_ID_1,
        derived_from_question_id=QUESTION_ID_1,
        type=question_type,
        variant_kind=VariantKind.ORDER_SHUFFLE,
        question_text="주어진 글 다음에 이어질 글의 순서로 가장 적절한 것은?",
        choices=_FIVE_ORDER_CHOICES,
        answer=1,
        explanation="(A)는 인프라 투자를 소개하며, (B)는 역접 전환, (C)는 결론을 맺는다.",
        sub_passages=_SUB_PASSAGES,
        variant_metadata={
            "intro_paragraph": _INTRO,
            "split_categories": ["conjunction", "anaphoric_pronoun"],
            "choice_pattern": ["correct", "distractor", "distractor", "distractor", "distractor"],
        },
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_qa_placeholder(question_id: uuid.UUID = VARIANT_QUESTION_ID) -> QAValidationResult:
    return QAValidationResult(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        question_id=question_id,
        passed=False,
        validator_note="pending — Phase 3 qa-validator 활성 시 검증 예정.",
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


# ─── 픽스처 ─────────────────────────────────────────────────────────────────


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
def prompts_dir(tmp_path: Path) -> Path:
    """임시 프롬프트 디렉토리 — 최소 V7 프롬프트 파일 포함."""
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "variant-order-shuffle-v0.md").write_text(
        "---\nversion: 0\n---\n"
        "Passage: {{passage_text}}\nType: {{question_type}}",
        encoding="utf-8",
    )
    return d


@pytest.fixture(autouse=True)
def set_prompts_dir(prompts_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMPTS_DIR", str(prompts_dir))


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


# ─── 정상 케이스 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_v7_variant_order_36_ok(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """201 정상 — paragraph_order_36 원본 → V7 변형 Question 반환.

    반환 JSON 에 variant_kind='order_shuffle', sub_passages (3개 inner list),
    choices (5개 순서 조합 문자열) 가 포함되는지 확인.
    """
    original = _make_original_question(QuestionType.ORDER_36)
    passage = _make_passage()
    saved_variant = _make_saved_variant(QuestionType.ORDER_36)
    qa_placeholder = _make_qa_placeholder()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.QAValidationResultRepository") as mock_qa_repo_cls,
        patch("worksheet_api.routers.questions.generate_v7_variant") as mock_generate,
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
        mock_qa_repo.create = AsyncMock(return_value=qa_placeholder)
        mock_qa_repo_cls.return_value = mock_qa_repo

        sentinel_variant = saved_variant.model_copy(
            update={"id": uuid.UUID(int=0), "tenant_id": uuid.UUID(int=0)}
        )
        mock_generate.return_value = sentinel_variant
        mock_validate.return_value = qa_placeholder

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/order-shuffle"
        )

    assert response.status_code == 201
    data = response.json()
    assert data["variant_kind"] == "order_shuffle"
    assert data["type"] == "order_36"
    assert len(data["choices"]) == 5
    assert data["sub_passages"] is not None
    assert len(data["sub_passages"]) == 3


@pytest.mark.asyncio
async def test_create_v7_variant_order_37_ok(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """201 정상 — paragraph_order_37 원본."""
    original = _make_original_question(QuestionType.ORDER_37)
    passage = _make_passage()
    saved_variant = _make_saved_variant(QuestionType.ORDER_37)
    qa_placeholder = _make_qa_placeholder()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.QAValidationResultRepository") as mock_qa_repo_cls,
        patch("worksheet_api.routers.questions.generate_v7_variant") as mock_generate,
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
        mock_qa_repo.create = AsyncMock(return_value=qa_placeholder)
        mock_qa_repo_cls.return_value = mock_qa_repo

        sentinel_variant = saved_variant.model_copy(
            update={"id": uuid.UUID(int=0), "tenant_id": uuid.UUID(int=0)}
        )
        mock_generate.return_value = sentinel_variant
        mock_validate.return_value = qa_placeholder

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/order-shuffle"
        )

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "order_37"
    assert data["variant_kind"] == "order_shuffle"


@pytest.mark.asyncio
async def test_create_v7_variant_qa_placeholder_created(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """201 정상 — QAValidationResult placeholder row 생성 확인."""
    original = _make_original_question(QuestionType.ORDER_36)
    passage = _make_passage()
    saved_variant = _make_saved_variant(QuestionType.ORDER_36)
    qa_placeholder = _make_qa_placeholder()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.QAValidationResultRepository") as mock_qa_repo_cls,
        patch("worksheet_api.routers.questions.generate_v7_variant") as mock_generate,
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
        mock_qa_repo.create = AsyncMock(return_value=qa_placeholder)
        mock_qa_repo_cls.return_value = mock_qa_repo

        sentinel_variant = saved_variant.model_copy(
            update={"id": uuid.UUID(int=0), "tenant_id": uuid.UUID(int=0)}
        )
        mock_generate.return_value = sentinel_variant
        mock_validate.return_value = qa_placeholder

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/order-shuffle"
        )

    assert response.status_code == 201
    # qa-validator 가 호출됨 (placeholder 아님 — 실제 검증 결과)
    mock_validate.assert_awaited_once()
    mock_qa_repo.create.assert_awaited_once()


# ─── 에러 케이스 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_v7_variant_question_not_found_404(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """404 — 존재하지 않는 question_id."""
    with patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls:
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=None)
        mock_q_repo_cls.return_value = mock_q_repo

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/order-shuffle"
        )

    assert response.status_code == 404
    assert "찾을 수 없습니다" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_v7_variant_passage_not_found_404(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """404 — Passage 가 없거나 다른 tenant 소유."""
    original = _make_original_question(QuestionType.ORDER_36)

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
    ):
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo_cls.return_value = mock_q_repo

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=None)
        mock_p_repo_cls.return_value = mock_p_repo

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/order-shuffle"
        )

    assert response.status_code == 404
    assert "Passage" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_v7_variant_non_applicable_type_422(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """422 — V7 비적용 type (grammar_29)."""
    original = _make_original_question(QuestionType.GRAMMAR_29)

    with patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls:
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo_cls.return_value = mock_q_repo

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/order-shuffle"
        )

    assert response.status_code == 422
    assert "V7 변형" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_v7_variant_llm_schema_error_502(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """502 — LLMSchemaValidationError."""
    from llm.errors import LLMSchemaValidationError

    original = _make_original_question(QuestionType.ORDER_36)
    passage = _make_passage()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.generate_v7_variant") as mock_generate,
        patch("worksheet_api.routers.questions.validate_question_uniqueness") as mock_validate,
    ):
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo_cls.return_value = mock_q_repo

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=passage)
        mock_p_repo_cls.return_value = mock_p_repo

        mock_generate.side_effect = LLMSchemaValidationError(
            "schema fail", validation_error="test", raw_response={}
        )

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/order-shuffle"
        )

    assert response.status_code == 502
    assert "LLM structured output" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_v7_variant_llm_timeout_504(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """504 — LLMTimeoutError."""
    from llm.errors import LLMTimeoutError

    original = _make_original_question(QuestionType.ORDER_36)
    passage = _make_passage()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.generate_v7_variant") as mock_generate,
        patch("worksheet_api.routers.questions.validate_question_uniqueness") as mock_validate,
    ):
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo_cls.return_value = mock_q_repo

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=passage)
        mock_p_repo_cls.return_value = mock_p_repo

        mock_generate.side_effect = LLMTimeoutError("timeout")

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/order-shuffle"
        )

    assert response.status_code == 504


@pytest.mark.asyncio
async def test_create_v7_variant_permanent_llm_error_500(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """500 — PermanentLLMError."""
    from llm.errors import PermanentLLMError

    original = _make_original_question(QuestionType.ORDER_36)
    passage = _make_passage()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.generate_v7_variant") as mock_generate,
        patch("worksheet_api.routers.questions.validate_question_uniqueness") as mock_validate,
    ):
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo_cls.return_value = mock_q_repo

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=passage)
        mock_p_repo_cls.return_value = mock_p_repo

        mock_generate.side_effect = PermanentLLMError("api key invalid")

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/order-shuffle"
        )

    assert response.status_code == 500
