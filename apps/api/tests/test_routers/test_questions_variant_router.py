"""POST /questions/{question_id}/variants/topic-main-idea-swap 라우터 단위 테스트.

mock session + mock repository + mock LLM client 로 실제 DB / LLM 없이 실행한다.

커버 케이스:
  - 201 정상 — main_idea_22 원본 → 변형 Question 반환.
  - 201 정상 — theme_23 원본.
  - 201 정상 — title_24 원본.
  - 201 정상 — QAValidationResult placeholder row 생성 확인.
  - 404 — 존재하지 않는 question_id.
  - 404 — cross-tenant (다른 tenant 의 question id — get 반환 None).
  - 404 — passage not found (Passage 가 없거나 다른 tenant 소유).
  - 422 — V6 비적용 type (grammar_29).
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
TENANT_B = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
QUESTION_ID_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
PASSAGE_ID_1 = uuid.UUID("22222222-2222-2222-2222-222222222222")
VARIANT_QUESTION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

_ZERO_WASTE_PASSAGE_TEXT = (
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
        question_text="다음 글의 요지로 가장 적절한 것은?",
        choices=["기존 선택지 1", "기존 선택지 2", "기존 선택지 3", "기존 선택지 4", "기존 선택지 5"],
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
    question_type: QuestionType = QuestionType.GIST_22,
) -> Question:
    return Question(
        id=VARIANT_QUESTION_ID,
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=PASSAGE_ID_1,
        derived_from_question_id=QUESTION_ID_1,
        type=question_type,
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
    """임시 프롬프트 디렉토리 — 최소 V6 프롬프트 파일 포함."""
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "variant-topic-main-idea-swap-v0.md").write_text(
        "---\nversion: 0\n---\n"
        "Passage: {{passage_text}}\nType: {{question_type}}\n"
        "Original choices: {{original_choices}}",
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
async def test_create_v6_variant_main_idea_22_ok(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """201 정상 — main_idea_22 원본 → V6 변형 Question 반환."""
    original = _make_original_question(QuestionType.GIST_22)
    passage = _make_passage()
    saved_variant = _make_saved_variant(QuestionType.GIST_22)
    qa_placeholder = _make_qa_placeholder()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.QAValidationResultRepository") as mock_qa_repo_cls,
        patch("worksheet_api.routers.questions.generate_v6_variant") as mock_generate,
        patch("worksheet_api.routers.questions.validate_question_uniqueness") as mock_validate,
    ):
        # 첫 번째 QuestionRepository.get (원본 조회)
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        # 두 번째 QuestionRepository.create (변형 저장)
        mock_q_repo2 = AsyncMock()
        mock_q_repo2.create = AsyncMock(return_value=saved_variant)
        # QuestionRepository() 호출 순서에 맞게 반환
        mock_q_repo_cls.side_effect = [mock_q_repo, mock_q_repo2]

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=passage)
        mock_p_repo_cls.return_value = mock_p_repo

        mock_qa_repo = AsyncMock()
        mock_qa_repo.create = AsyncMock(return_value=qa_placeholder)
        mock_qa_repo_cls.return_value = mock_qa_repo

        # generate_v6_variant 가 sentinel UUID 채운 Question 반환 (sentinel id=0)
        sentinel_variant = saved_variant.model_copy(
            update={"id": uuid.UUID(int=0), "tenant_id": uuid.UUID(int=0)}
        )
        mock_generate.return_value = sentinel_variant
        mock_validate.return_value = qa_placeholder

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    assert response.status_code == 201
    data = response.json()
    assert data["variant_kind"] == "topic_main_idea_swap"
    assert data["type"] == "gist_22"
    assert len(data["choices"]) == 5


@pytest.mark.asyncio
async def test_create_v6_variant_theme_23_ok(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """201 정상 — theme_23 원본."""
    original = _make_original_question(QuestionType.THEME_23)
    passage = _make_passage()
    saved_variant = _make_saved_variant(QuestionType.THEME_23)
    qa_placeholder = _make_qa_placeholder()

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
        mock_qa_repo.create = AsyncMock(return_value=qa_placeholder)
        mock_qa_repo_cls.return_value = mock_qa_repo

        sentinel_variant = saved_variant.model_copy(
            update={"id": uuid.UUID(int=0), "tenant_id": uuid.UUID(int=0)}
        )
        mock_generate.return_value = sentinel_variant
        mock_validate.return_value = qa_placeholder

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "theme_23"


@pytest.mark.asyncio
async def test_create_v6_variant_title_24_ok(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """201 정상 — title_24 원본."""
    original = _make_original_question(QuestionType.TITLE_24)
    passage = _make_passage()
    saved_variant = _make_saved_variant(QuestionType.TITLE_24)
    qa_placeholder = _make_qa_placeholder()

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
        mock_qa_repo.create = AsyncMock(return_value=qa_placeholder)
        mock_qa_repo_cls.return_value = mock_qa_repo

        sentinel_variant = saved_variant.model_copy(
            update={"id": uuid.UUID(int=0), "tenant_id": uuid.UUID(int=0)}
        )
        mock_generate.return_value = sentinel_variant
        mock_validate.return_value = qa_placeholder

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "title_24"


@pytest.mark.asyncio
async def test_create_v6_variant_qa_result_created(
    async_client: AsyncClient,
    mock_session: AsyncMock,
    mock_llm_client: AsyncMock,
) -> None:
    """QAValidationResult row 생성 확인 (qa-validator 활성화 후 실제 검증 결과 저장).

    Phase 3 qa-validator 활성화 이후:
      - placeholder (passed=False, note="pending") 대신 실제 검증 결과 저장.
      - validate_question_uniqueness 가 1회 호출됨.
      - QAValidationResultRepository.create 가 1회 호출됨.
    """
    original = _make_original_question(QuestionType.GIST_22)
    passage = _make_passage()
    saved_variant = _make_saved_variant()
    qa_result = _make_qa_placeholder()  # 픽스처 재사용 (passed=False → 검증 결과로 채워짐)

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
    # validate_question_uniqueness 가 1회 호출되었는지 확인
    mock_validate.assert_awaited_once()
    # QAValidationResultRepository.create 가 1회 호출되었는지 확인
    mock_qa_repo.create.assert_awaited_once()


# ─── 에러 케이스 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_v6_variant_question_not_found_404(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """404 — 존재하지 않는 question_id."""
    with patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls:
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=None)
        mock_q_repo_cls.return_value = mock_q_repo

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    assert response.status_code == 404
    assert "찾을 수 없습니다" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_v6_variant_cross_tenant_404(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """404 — cross-tenant (다른 tenant 의 question → get 반환 None)."""
    with patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls:
        mock_q_repo = AsyncMock()
        # tenant 필터로 인해 다른 tenant 소유 question 은 None 반환
        mock_q_repo.get = AsyncMock(return_value=None)
        mock_q_repo_cls.return_value = mock_q_repo

        response = await async_client.post(
            f"/questions/{uuid.UUID('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee')}"
            "/variants/topic-main-idea-swap"
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_v6_variant_passage_not_found_404(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """404 — Passage 가 없거나 다른 tenant 소유."""
    original = _make_original_question(QuestionType.GIST_22)

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
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    assert response.status_code == 404
    assert "Passage" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_v6_variant_non_applicable_type_422(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """422 — V6 비적용 type (grammar_29)."""
    original = _make_original_question(QuestionType.GRAMMAR_29)

    with patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls:
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo_cls.return_value = mock_q_repo

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    assert response.status_code == 422
    assert "V6 변형" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_v6_variant_llm_schema_error_502(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """502 — LLMSchemaValidationError."""
    from llm.errors import LLMSchemaValidationError

    original = _make_original_question(QuestionType.GIST_22)
    passage = _make_passage()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.generate_v6_variant") as mock_generate,
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
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    assert response.status_code == 502
    assert "LLM structured output" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_v6_variant_llm_timeout_504(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """504 — LLMTimeoutError."""
    from llm.errors import LLMTimeoutError

    original = _make_original_question(QuestionType.GIST_22)
    passage = _make_passage()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.generate_v6_variant") as mock_generate,
    ):
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo_cls.return_value = mock_q_repo

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=passage)
        mock_p_repo_cls.return_value = mock_p_repo

        mock_generate.side_effect = LLMTimeoutError("timeout")

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    assert response.status_code == 504


@pytest.mark.asyncio
async def test_create_v6_variant_permanent_llm_error_500(
    async_client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """500 — PermanentLLMError."""
    from llm.errors import PermanentLLMError

    original = _make_original_question(QuestionType.GIST_22)
    passage = _make_passage()

    with (
        patch("worksheet_api.routers.questions.QuestionRepository") as mock_q_repo_cls,
        patch("worksheet_api.routers.questions.PassageRepository") as mock_p_repo_cls,
        patch("worksheet_api.routers.questions.generate_v6_variant") as mock_generate,
    ):
        mock_q_repo = AsyncMock()
        mock_q_repo.get = AsyncMock(return_value=original)
        mock_q_repo_cls.return_value = mock_q_repo

        mock_p_repo = AsyncMock()
        mock_p_repo.get = AsyncMock(return_value=passage)
        mock_p_repo_cls.return_value = mock_p_repo

        mock_generate.side_effect = PermanentLLMError("api key invalid")

        response = await async_client.post(
            f"/questions/{QUESTION_ID_1}/variants/topic-main-idea-swap"
        )

    assert response.status_code == 500
