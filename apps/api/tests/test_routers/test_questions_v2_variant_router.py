"""POST /questions/{question_id}/variants/vocabulary-inline 라우터 단위 테스트.

mock session + mock repository + mock LLM client 로 실제 DB / LLM 없이 실행한다.

커버 케이스:
  - 201 정상 — vocabulary_30 원본 → V2 변형 Question 반환.
  - 201 정상 — blank_phrase_31 원본.
  - 201 정상 — QAValidationResult placeholder row 생성 확인.
  - 404 — 존재하지 않는 question_id.
  - 404 — cross-tenant (다른 tenant 의 question id — get 반환 None).
  - 404 — passage not found (Passage 가 없거나 다른 tenant 소유).
  - 422 — V2 비적용 type (gist_22).
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
from shared.schemas.question import (
    InlineChoice,
    InlineChoiceKind,
    Question,
    QuestionType,
    VariantKind,
)

# ─── 테스트용 고정 UUID ──────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
QUESTION_ID_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
PASSAGE_ID_1 = uuid.UUID("22222222-2222-2222-2222-222222222222")
VARIANT_QUESTION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

_ZERO_WASTE_PASSAGE_TEXT = (
    "Reducing waste starts with awareness. Individual effort, "
    "multiplied across an entire community, creates meaningful change."
)

_FIVE_CHOICES = [
    "(A) motivated, (B) significant",
    "(A) discouraged, (B) negligible",
    "(A) motivated, (B) negligible",
    "(A) discouraged, (B) significant",
    "(A) discouraged, (B) negligible",
]

_TWO_INLINE_CHOICES = [
    InlineChoice(
        label="(A)",
        options=["motivated", "discouraged"],
        answer_index=0,
        position_marker="they become more (A)",
        kind=InlineChoiceKind.VOCABULARY,
    ),
    InlineChoice(
        label="(B)",
        options=["significant", "negligible"],
        answer_index=0,
        position_marker="add up to (B) environmental",
        kind=InlineChoiceKind.VOCABULARY,
    ),
]


# ─── 팩토리 헬퍼 ─────────────────────────────────────────────────────────────


def _make_original_question(
    question_type: QuestionType = QuestionType.VOCABULARY_30,
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
        question_text="밑줄 친 (A), (B)에 들어갈 말로 가장 적절한 것은?",
        choices=[
            "기존 선택지 1",
            "기존 선택지 2",
            "기존 선택지 3",
            "기존 선택지 4",
            "기존 선택지 5",
        ],
        answer=3,
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
        body_text=_ZERO_WASTE_PASSAGE_TEXT,
        word_count=20,
        source=SourceMeta(provider=SourceProvider.USER_INPUT),
        target_grade=TargetGrade.HIGH_2,
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_saved_variant(
    question_type: QuestionType = QuestionType.VOCABULARY_30,
) -> Question:
    return Question(
        id=VARIANT_QUESTION_ID,
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=PASSAGE_ID_1,
        derived_from_question_id=QUESTION_ID_1,
        type=question_type,
        variant_kind=VariantKind.VOCABULARY_INLINE,
        question_text="밑줄 친 (A), (B)에 들어갈 말로 가장 적절한 것은?",
        choices=_FIVE_CHOICES,
        answer=1,
        explanation="글에서 인식이 동기를 유발한다고 서술되므로 (A)는 motivated 가 맞다.",
        inline_choices=_TWO_INLINE_CHOICES,
        variant_metadata={
            "modified_passage_text": _ZERO_WASTE_PASSAGE_TEXT,
            "box_count": 2,
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
    """임시 프롬프트 디렉토리 — V2 프롬프트 파일 포함."""
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "variant-vocabulary-inline-v0.md").write_text(
        "---\nversion: 0\n---\nPassage: {{passage_text}}\nBox count: {{box_count}}",
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
async def test_create_v2_variant_vocabulary_30_ok(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """201 정상 — vocabulary_30 원본 → V2 변형 Question 반환."""
    original = _make_original_question(QuestionType.VOCABULARY_30)
    passage = _make_passage()
    saved_variant = _make_saved_variant(QuestionType.VOCABULARY_30)
    qa_placeholder = _make_qa_placeholder()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.QAValidationResultRepository") as mock_qa_repo_cls,
        patch("worksheet_api.routers.questions.generate_v2_variant") as mock_generate,
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

        response = await async_client.post(f"/questions/{QUESTION_ID_1}/variants/vocabulary-inline")

    assert response.status_code == 201
    data = response.json()
    assert data["variant_kind"] == "vocabulary_inline"
    assert data["type"] == "vocabulary_30"
    assert len(data["choices"]) == 5
    assert data["inline_choices"] is not None
    assert len(data["inline_choices"]) == 2


@pytest.mark.asyncio
async def test_create_v2_variant_blank_phrase_31_ok(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """201 정상 — blank_phrase_31 원본 → V2 변형 반환 (type 은 vocabulary_30)."""
    original = _make_original_question(QuestionType.BLANK_PHRASE_31)
    passage = _make_passage()
    saved_variant = _make_saved_variant(QuestionType.VOCABULARY_30)
    qa_placeholder = _make_qa_placeholder()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.QAValidationResultRepository") as mock_qa_repo_cls,
        patch("worksheet_api.routers.questions.generate_v2_variant") as mock_generate,
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

        response = await async_client.post(f"/questions/{QUESTION_ID_1}/variants/vocabulary-inline")

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "vocabulary_30"
    assert data["variant_kind"] == "vocabulary_inline"


@pytest.mark.asyncio
async def test_create_v2_variant_qa_placeholder_created(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """QAValidationResult placeholder row 생성 확인 (qa_repo.create 호출 검증)."""
    original = _make_original_question(QuestionType.VOCABULARY_30)
    passage = _make_passage()
    saved_variant = _make_saved_variant()
    qa_placeholder = _make_qa_placeholder()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.QAValidationResultRepository") as mock_qa_repo_cls,
        patch("worksheet_api.routers.questions.generate_v2_variant") as mock_generate,
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

        response = await async_client.post(f"/questions/{QUESTION_ID_1}/variants/vocabulary-inline")

    assert response.status_code == 201
    mock_qa_repo.create.assert_awaited_once()
    created_qa: QAValidationResult = mock_qa_repo.create.call_args[0][0]
    assert created_qa.passed is False
    assert "pending" in (created_qa.validator_note or "")


# ─── 에러 케이스 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_v2_variant_question_not_found_404(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """404 — 존재하지 않는 question_id."""
    with patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls:
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=None)
        mock_q_repo_cls.return_value = mock_q_repo

        response = await async_client.post(f"/questions/{QUESTION_ID_1}/variants/vocabulary-inline")

    assert response.status_code == 404
    assert "찾을 수 없습니다" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_v2_variant_cross_tenant_404(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """404 — cross-tenant (다른 tenant 의 question → get 반환 None)."""
    with patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls:
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=None)
        mock_q_repo_cls.return_value = mock_q_repo

        response = await async_client.post(
            f"/questions/{uuid.UUID('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee')}"
            "/variants/vocabulary-inline"
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_v2_variant_passage_not_found_404(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """404 — Passage 가 없거나 다른 tenant 소유."""
    original = _make_original_question(QuestionType.VOCABULARY_30)

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

        response = await async_client.post(f"/questions/{QUESTION_ID_1}/variants/vocabulary-inline")

    assert response.status_code == 404
    assert "Passage" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_v2_variant_non_applicable_type_422(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """422 — V2 비적용 type (gist_22)."""
    original = _make_original_question(QuestionType.GIST_22)

    with patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls:
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo_cls.return_value = mock_q_repo

        response = await async_client.post(f"/questions/{QUESTION_ID_1}/variants/vocabulary-inline")

    assert response.status_code == 422
    assert "V2 변형" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_v2_variant_llm_schema_error_502(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """502 — LLMSchemaValidationError."""
    from llm.errors import LLMSchemaValidationError

    original = _make_original_question(QuestionType.VOCABULARY_30)
    passage = _make_passage()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.generate_v2_variant") as mock_generate,
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

        response = await async_client.post(f"/questions/{QUESTION_ID_1}/variants/vocabulary-inline")

    assert response.status_code == 502
    assert "LLM structured output" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_v2_variant_llm_timeout_504(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """504 — LLMTimeoutError."""
    from llm.errors import LLMTimeoutError

    original = _make_original_question(QuestionType.VOCABULARY_30)
    passage = _make_passage()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.generate_v2_variant") as mock_generate,
    ):
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo_cls.return_value = mock_q_repo

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=passage)
        mock_p_repo_cls.return_value = mock_p_repo

        mock_generate.side_effect = LLMTimeoutError("timeout")

        response = await async_client.post(f"/questions/{QUESTION_ID_1}/variants/vocabulary-inline")

    assert response.status_code == 504


@pytest.mark.asyncio
async def test_create_v2_variant_permanent_llm_error_500(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """500 — PermanentLLMError."""
    from llm.errors import PermanentLLMError

    original = _make_original_question(QuestionType.VOCABULARY_30)
    passage = _make_passage()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.generate_v2_variant") as mock_generate,
    ):
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo_cls.return_value = mock_q_repo

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=passage)
        mock_p_repo_cls.return_value = mock_p_repo

        mock_generate.side_effect = PermanentLLMError("api key invalid")

        response = await async_client.post(f"/questions/{QUESTION_ID_1}/variants/vocabulary-inline")

    assert response.status_code == 500
