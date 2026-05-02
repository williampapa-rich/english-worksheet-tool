"""PassageRepository 단위 + 통합 테스트.

단위 테스트: mock session 으로 sentinel / tenant 검증.
통합 테스트: 실제 PostgreSQL (@pytest.mark.integration) 으로 CRUD + 멀티테넌트 격리.

통합 테스트는 Docker compose PostgreSQL 이 필요하다.
  pytest -m integration --run-integration 으로 실행.
  CI 에서는 기본 skip (API key / DB 없는 환경).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from worksheet_api.models.base import SENTINEL_UUID
from worksheet_api.repositories.passage import PassageRepository
from worksheet_api.repositories.tenant_context import TenantContext

from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade

# ─── 공통 픽스처 ─────────────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TENANT_B = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
WORKSPACE_B = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _make_passage(
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
    body_text: str = "The economy is growing steadily.",
) -> Passage:
    """테스트용 Passage 생성 헬퍼."""
    return Passage(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        body_text=body_text,
        word_count=5,
        source=SourceMeta(provider=SourceProvider.EVALUATOR),
        target_grade=TargetGrade.HIGH_3,
    )


def _ctx_a() -> TenantContext:
    return TenantContext(tenant_id=TENANT_A, workspace_id=WORKSPACE_A)


def _ctx_b() -> TenantContext:
    return TenantContext(tenant_id=TENANT_B, workspace_id=WORKSPACE_B)


# ─── 단위 테스트 (mock session) ───────────────────────────────────────────────


class TestPassageRepositoryUnit:
    """sentinel / tenant 검증 단위 테스트 (DB 없음)."""

    @pytest.mark.asyncio
    async def test_create_sentinel_tenant_id_raises(self) -> None:
        """tenant_id == SENTINEL_UUID 이면 create 에서 ValueError."""
        mock_session = AsyncMock()
        repo = PassageRepository(mock_session, _ctx_a())

        passage = _make_passage()
        # sentinel 주입
        passage_with_sentinel = passage.model_copy(update={"tenant_id": SENTINEL_UUID})

        with pytest.raises(ValueError, match="sentinel UUID"):
            await repo.create(passage_with_sentinel)

    @pytest.mark.asyncio
    async def test_create_workspace_sentinel_raises(self) -> None:
        """workspace_id == SENTINEL_UUID 이면 create 에서 ValueError."""
        mock_session = AsyncMock()
        repo = PassageRepository(mock_session, _ctx_a())

        passage = _make_passage()
        passage_with_sentinel = passage.model_copy(update={"workspace_id": SENTINEL_UUID})

        with pytest.raises(ValueError, match="sentinel UUID"):
            await repo.create(passage_with_sentinel)

    @pytest.mark.asyncio
    async def test_create_tenant_mismatch_raises(self) -> None:
        """domain.tenant_id != context.tenant_id 이면 ValueError."""
        mock_session = AsyncMock()
        repo = PassageRepository(mock_session, _ctx_a())

        # tenant_b 의 passage 를 tenant_a context 로 create 시도
        passage = _make_passage(tenant_id=TENANT_B, workspace_id=WORKSPACE_B)

        with pytest.raises(ValueError, match="tenant_id 불일치"):
            await repo.create(passage)

    @pytest.mark.asyncio
    async def test_create_workspace_mismatch_raises(self) -> None:
        """workspace_id 불일치 시 ValueError."""
        mock_session = AsyncMock()
        repo = PassageRepository(mock_session, _ctx_a())

        passage = _make_passage(
            tenant_id=TENANT_A,
            workspace_id=WORKSPACE_B,  # workspace 불일치
        )

        with pytest.raises(ValueError, match="workspace_id 불일치"):
            await repo.create(passage)


# ─── 통합 테스트 (실제 PostgreSQL) ───────────────────────────────────────────


@pytest.mark.integration
class TestPassageRepositoryIntegration:
    """실제 PostgreSQL 을 사용한 통합 테스트.

    Docker compose PostgreSQL 이 필요하다.
    ``pytest -m integration`` 으로 실행.
    """

    @pytest.mark.asyncio
    async def test_create_and_get(self, pg_session) -> None:
        """create 후 get 으로 동일 데이터 조회 가능."""
        repo = PassageRepository(pg_session, _ctx_a())
        passage = _make_passage()

        saved = await repo.create(passage)
        assert saved.id is not None
        assert saved.tenant_id == TENANT_A
        assert saved.body_text == passage.body_text

        fetched = await repo.get(saved.id)
        assert fetched is not None
        assert fetched.id == saved.id
        assert fetched.body_text == saved.body_text

    @pytest.mark.asyncio
    async def test_list_returns_only_own_tenant(self, pg_session) -> None:
        """list() 는 자신의 tenant 데이터만 반환 (멀티테넌트 격리)."""
        repo_a = PassageRepository(pg_session, _ctx_a())
        repo_b = PassageRepository(pg_session, _ctx_b())

        # tenant A 에 2개, tenant B 에 1개 저장
        await repo_a.create(_make_passage(tenant_id=TENANT_A, workspace_id=WORKSPACE_A))
        await repo_a.create(
            _make_passage(
                tenant_id=TENANT_A,
                workspace_id=WORKSPACE_A,
                body_text="Second passage.",
            )
        )
        await repo_b.create(_make_passage(tenant_id=TENANT_B, workspace_id=WORKSPACE_B))

        passages_a = await repo_a.list()
        passages_b = await repo_b.list()

        # tenant A 는 2개, tenant B 는 1개
        assert len(passages_a) == 2
        assert len(passages_b) == 1
        # tenant A 의 결과에 tenant B 데이터 없음
        tenant_ids_a = {p.tenant_id for p in passages_a}
        assert tenant_ids_a == {TENANT_A}

    @pytest.mark.asyncio
    async def test_get_other_tenant_returns_none(self, pg_session) -> None:
        """다른 tenant 의 Passage ID 로 get 하면 None 반환."""
        repo_a = PassageRepository(pg_session, _ctx_a())
        repo_b = PassageRepository(pg_session, _ctx_b())

        saved_b = await repo_b.create(_make_passage(tenant_id=TENANT_B, workspace_id=WORKSPACE_B))

        # tenant A 로 tenant B 의 ID 조회 → None
        result = await repo_a.get(saved_b.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_own_passage(self, pg_session) -> None:
        """자신의 tenant 데이터 삭제 성공."""
        repo = PassageRepository(pg_session, _ctx_a())
        saved = await repo.create(_make_passage())

        result = await repo.delete(saved.id)
        assert result is True

        fetched = await repo.get(saved.id)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_delete_other_tenant_returns_false(self, pg_session) -> None:
        """다른 tenant 의 Passage 삭제 시도 → False."""
        repo_a = PassageRepository(pg_session, _ctx_a())
        repo_b = PassageRepository(pg_session, _ctx_b())

        saved_b = await repo_b.create(_make_passage(tenant_id=TENANT_B, workspace_id=WORKSPACE_B))

        # tenant A 로 tenant B 의 데이터 삭제 시도 → False
        result = await repo_a.delete(saved_b.id)
        assert result is False

    @pytest.mark.asyncio
    async def test_source_meta_jsonb_roundtrip(self, pg_session) -> None:
        """SourceMeta JSONB 컬럼이 정확히 저장/복원된다."""
        repo = PassageRepository(pg_session, _ctx_a())
        passage = _make_passage()
        # school_internal + school_name 조합
        passage_with_school = passage.model_copy(
            update={
                "source": SourceMeta(
                    provider=SourceProvider.SCHOOL_INTERNAL,
                    school_name="강남고등학교",
                    exam_year=2025,
                    exam_round="1학기 중간고사",
                )
            }
        )

        saved = await repo.create(passage_with_school)
        fetched = await repo.get(saved.id)

        assert fetched is not None
        assert fetched.source.provider == SourceProvider.SCHOOL_INTERNAL
        assert fetched.source.school_name == "강남고등학교"
        assert fetched.source.exam_year == 2025

    @pytest.mark.asyncio
    async def test_list_with_limit_and_offset(self, pg_session) -> None:
        """limit / offset 페이지네이션 동작 확인."""
        repo = PassageRepository(pg_session, _ctx_a())

        for i in range(5):
            await repo.create(_make_passage(body_text=f"Passage number {i}."))

        first_page = await repo.list(limit=3, offset=0)
        second_page = await repo.list(limit=3, offset=3)

        assert len(first_page) == 3
        assert len(second_page) == 2  # 5개 중 3개 skip 후 2개
