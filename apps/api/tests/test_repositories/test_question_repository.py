"""QuestionRepository 단위 + 통합 테스트.

passage_id FK 검증, derived_from_question_id 검증, 멀티테넌트 격리를 확인한다.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from worksheet_api.models.base import SENTINEL_UUID
from worksheet_api.repositories.passage import PassageRepository
from worksheet_api.repositories.question import QuestionRepository
from worksheet_api.repositories.tenant_context import TenantContext

from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade
from shared.schemas.question import (
    Question,
    QuestionType,
    VariantKind,
)

# ─── 공통 픽스처 ─────────────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TENANT_B = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
WORKSPACE_B = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _ctx_a() -> TenantContext:
    return TenantContext(tenant_id=TENANT_A, workspace_id=WORKSPACE_A)


def _ctx_b() -> TenantContext:
    return TenantContext(tenant_id=TENANT_B, workspace_id=WORKSPACE_B)


def _make_passage(
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
) -> Passage:
    return Passage(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        body_text="The economy is growing.",
        word_count=4,
        source=SourceMeta(provider=SourceProvider.EVALUATOR),
        target_grade=TargetGrade.HIGH_3,
    )


def _make_question(
    passage_id: uuid.UUID,
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
    variant_kind: VariantKind = VariantKind.ORIGINAL,
    derived_from_question_id: uuid.UUID | None = None,
) -> Question:
    return Question(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        passage_id=passage_id,
        type=QuestionType.GIST_22,
        variant_kind=variant_kind,
        derived_from_question_id=derived_from_question_id,
        choices=["①", "②", "③", "④", "⑤"],
        answer=1,
    )


# ─── 단위 테스트 (mock session) ───────────────────────────────────────────────


class TestQuestionRepositoryUnit:
    """sentinel / tenant 검증 단위 테스트 (DB 없음)."""

    @pytest.mark.asyncio
    async def test_create_sentinel_tenant_id_raises(self) -> None:
        """tenant_id == SENTINEL_UUID 이면 ValueError."""
        mock_session = AsyncMock()
        repo = QuestionRepository(mock_session, _ctx_a())

        passage_id = uuid.uuid4()
        question = _make_question(passage_id=passage_id)
        question_with_sentinel = question.model_copy(update={"tenant_id": SENTINEL_UUID})

        with pytest.raises(ValueError, match="sentinel UUID"):
            await repo.create(question_with_sentinel)

    @pytest.mark.asyncio
    async def test_create_tenant_mismatch_raises(self) -> None:
        """domain.tenant_id != context.tenant_id 이면 ValueError."""
        mock_session = AsyncMock()
        repo = QuestionRepository(mock_session, _ctx_a())

        question = _make_question(
            passage_id=uuid.uuid4(),
            tenant_id=TENANT_B,
            workspace_id=WORKSPACE_B,
        )

        with pytest.raises(ValueError, match="tenant_id 불일치"):
            await repo.create(question)


# ─── 통합 테스트 (실제 PostgreSQL) ───────────────────────────────────────────


@pytest.mark.integration
class TestQuestionRepositoryIntegration:
    """실제 PostgreSQL 을 사용한 통합 테스트."""

    @pytest.mark.asyncio
    async def test_create_question_requires_existing_passage(self, pg_session) -> None:
        """존재하지 않는 passage_id 로 Question create 시 ValueError."""
        repo = QuestionRepository(pg_session, _ctx_a())
        nonexistent_passage_id = uuid.uuid4()

        question = _make_question(passage_id=nonexistent_passage_id)

        with pytest.raises(ValueError, match="passage_id"):
            await repo.create(question)

    @pytest.mark.asyncio
    async def test_create_and_get(self, pg_session) -> None:
        """Passage 저장 후 Question create/get 성공."""
        passage_repo = PassageRepository(pg_session, _ctx_a())
        question_repo = QuestionRepository(pg_session, _ctx_a())

        saved_passage = await passage_repo.create(_make_passage())
        question = _make_question(passage_id=saved_passage.id)
        saved_question = await question_repo.create(question)

        assert saved_question.id is not None
        assert saved_question.passage_id == saved_passage.id
        assert saved_question.type == QuestionType.GIST_22

        fetched = await question_repo.get(saved_question.id)
        assert fetched is not None
        assert fetched.id == saved_question.id

    @pytest.mark.asyncio
    async def test_list_by_passage(self, pg_session) -> None:
        """list_by_passage 가 해당 passage 의 question 만 반환."""
        passage_repo = PassageRepository(pg_session, _ctx_a())
        question_repo = QuestionRepository(pg_session, _ctx_a())

        passage1 = await passage_repo.create(_make_passage())
        passage2 = await passage_repo.create(_make_passage(body_text="Another passage."))

        # passage1 에 2개, passage2 에 1개 저장
        await question_repo.create(_make_question(passage_id=passage1.id))
        await question_repo.create(_make_question(passage_id=passage1.id))
        await question_repo.create(_make_question(passage_id=passage2.id))

        q_p1 = await question_repo.list_by_passage(passage1.id)
        q_p2 = await question_repo.list_by_passage(passage2.id)

        assert len(q_p1) == 2
        assert len(q_p2) == 1

    @pytest.mark.asyncio
    async def test_multitenancy_isolation(self, pg_session) -> None:
        """다른 tenant 의 Question 은 조회되지 않는다."""
        passage_repo_a = PassageRepository(pg_session, _ctx_a())
        question_repo_a = QuestionRepository(pg_session, _ctx_a())
        passage_repo_b = PassageRepository(pg_session, _ctx_b())
        question_repo_b = QuestionRepository(pg_session, _ctx_b())

        saved_passage_a = await passage_repo_a.create(_make_passage())
        saved_passage_b = await passage_repo_b.create(
            _make_passage(tenant_id=TENANT_B, workspace_id=WORKSPACE_B)
        )

        await question_repo_a.create(_make_question(passage_id=saved_passage_a.id))
        q_b = await question_repo_b.create(
            _make_question(
                passage_id=saved_passage_b.id,
                tenant_id=TENANT_B,
                workspace_id=WORKSPACE_B,
            )
        )

        # tenant A 로 tenant B 의 question ID 조회 → None
        result = await question_repo_a.get(q_b.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_variant_question_derived_from_must_exist(self, pg_session) -> None:
        """derived_from_question_id 가 존재하지 않으면 ValueError."""
        passage_repo = PassageRepository(pg_session, _ctx_a())
        question_repo = QuestionRepository(pg_session, _ctx_a())

        saved_passage = await passage_repo.create(_make_passage())
        nonexistent_question_id = uuid.uuid4()

        variant_question = _make_question(
            passage_id=saved_passage.id,
            variant_kind=VariantKind.VOCABULARY_SWAP,
            derived_from_question_id=nonexistent_question_id,
        )

        with pytest.raises(ValueError, match="derived_from_question_id"):
            await question_repo.create(variant_question)

    @pytest.mark.asyncio
    async def test_variant_question_with_valid_original(self, pg_session) -> None:
        """원본 Question 이 존재하면 variant Question create 성공."""
        passage_repo = PassageRepository(pg_session, _ctx_a())
        question_repo = QuestionRepository(pg_session, _ctx_a())

        saved_passage = await passage_repo.create(_make_passage())
        original_q = await question_repo.create(_make_question(passage_id=saved_passage.id))

        variant_q = _make_question(
            passage_id=saved_passage.id,
            variant_kind=VariantKind.VOCABULARY_SWAP,
            derived_from_question_id=original_q.id,
        )

        saved_variant = await question_repo.create(variant_q)
        assert saved_variant.derived_from_question_id == original_q.id
        assert saved_variant.variant_kind == VariantKind.VOCABULARY_SWAP

    @pytest.mark.asyncio
    async def test_delete_question(self, pg_session) -> None:
        """Question 삭제 후 get 이 None 반환."""
        passage_repo = PassageRepository(pg_session, _ctx_a())
        question_repo = QuestionRepository(pg_session, _ctx_a())

        saved_passage = await passage_repo.create(_make_passage())
        saved_q = await question_repo.create(_make_question(passage_id=saved_passage.id))

        result = await question_repo.delete(saved_q.id)
        assert result is True

        fetched = await question_repo.get(saved_q.id)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_other_tenant_passage_cannot_be_referenced(self, pg_session) -> None:
        """다른 tenant 의 passage_id 로 Question create 시 ValueError."""
        passage_repo_b = PassageRepository(pg_session, _ctx_b())
        question_repo_a = QuestionRepository(pg_session, _ctx_a())

        saved_passage_b = await passage_repo_b.create(
            _make_passage(tenant_id=TENANT_B, workspace_id=WORKSPACE_B)
        )

        # tenant A context 로 tenant B 의 passage 참조 시도
        question = _make_question(
            passage_id=saved_passage_b.id,
            tenant_id=TENANT_A,
            workspace_id=WORKSPACE_A,
        )

        with pytest.raises(ValueError, match="passage_id"):
            await question_repo_a.create(question)
