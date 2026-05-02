"""BaseRepository 단위 테스트 — sentinel UUID 검증 + tenant mismatch + 변환 로직.

실제 DB 없이 mock session 으로 sentinel 검증과 변환 로직만 테스트한다.
ADR-0005 §D-5.7 의 이중 패턴 중 단위 테스트 레벨.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

# ─── 테스트용 최소 도메인 모델 / ORM 픽스쳐 ─────────────────────────────────
from pydantic import BaseModel, ConfigDict
from sqlmodel import SQLModel
from worksheet_api.models.base import SENTINEL_UUID
from worksheet_api.repositories.base import BaseRepository
from worksheet_api.repositories.tenant_context import TenantContext


class _FakeDomain(BaseModel):
    """테스트용 최소 도메인 모델 (sentinel 검증 대상)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = uuid.uuid4()
    tenant_id: uuid.UUID = SENTINEL_UUID
    workspace_id: uuid.UUID = SENTINEL_UUID
    name: str = "test"


class _FakeORM(SQLModel):
    """테스트용 최소 ORM 모델."""

    id: uuid.UUID = uuid.uuid4()
    tenant_id: uuid.UUID = SENTINEL_UUID
    workspace_id: uuid.UUID = SENTINEL_UUID
    name: str = "test"


class _FakeRepository(BaseRepository[_FakeORM, _FakeDomain]):
    """테스트용 concrete repository."""

    _orm_class = _FakeORM
    _domain_class = _FakeDomain


def _make_tenant_ctx(
    tenant_id: str = "00000000-0000-0000-0000-000000000001",
    workspace_id: str = "00000000-0000-0000-0000-000000000002",
) -> TenantContext:
    return TenantContext(
        tenant_id=uuid.UUID(tenant_id),
        workspace_id=uuid.UUID(workspace_id),
    )


def _make_repo(tenant_ctx: TenantContext | None = None) -> _FakeRepository:
    mock_session = AsyncMock()
    ctx = tenant_ctx or _make_tenant_ctx()
    return _FakeRepository(mock_session, ctx)


# ─── sentinel UUID 검증 테스트 ────────────────────────────────────────────────


class TestSentinelValidation:
    """_validate_tenant_fields: sentinel UUID 검증."""

    def test_sentinel_tenant_id_raises(self) -> None:
        """tenant_id 가 SENTINEL_UUID 이면 ValueError."""
        repo = _make_repo()
        domain = _FakeDomain(
            tenant_id=SENTINEL_UUID,
            workspace_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        )
        with pytest.raises(ValueError, match="sentinel UUID"):
            repo._validate_tenant_fields(domain)

    def test_sentinel_workspace_id_raises(self) -> None:
        """workspace_id 가 SENTINEL_UUID 이면 ValueError."""
        repo = _make_repo()
        domain = _FakeDomain(
            tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            workspace_id=SENTINEL_UUID,
        )
        with pytest.raises(ValueError, match="sentinel UUID"):
            repo._validate_tenant_fields(domain)

    def test_valid_ids_passes(self) -> None:
        """올바른 UUID 는 검증 통과."""
        ctx = _make_tenant_ctx()
        repo = _make_repo(ctx)
        domain = _FakeDomain(
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
        )
        # 예외 없이 통과
        repo._validate_tenant_fields(domain)


class TestTenantMismatch:
    """_validate_tenant_fields: tenant_id / workspace_id context 불일치."""

    def test_tenant_id_mismatch_raises(self) -> None:
        """domain.tenant_id != context.tenant_id 이면 ValueError."""
        repo = _make_repo()
        domain = _FakeDomain(
            tenant_id=uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            workspace_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        )
        with pytest.raises(ValueError, match="tenant_id 불일치"):
            repo._validate_tenant_fields(domain)

    def test_workspace_id_mismatch_raises(self) -> None:
        """domain.workspace_id != context.workspace_id 이면 ValueError."""
        ctx = _make_tenant_ctx()
        repo = _make_repo(ctx)
        domain = _FakeDomain(
            tenant_id=ctx.tenant_id,
            workspace_id=uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        )
        with pytest.raises(ValueError, match="workspace_id 불일치"):
            repo._validate_tenant_fields(domain)


class TestTransformMethods:
    """_to_orm / _to_domain 변환 로직 단위 테스트."""

    def test_to_orm_produces_orm_instance(self) -> None:
        """_to_orm 이 올바른 ORM 인스턴스를 반환."""
        ctx = _make_tenant_ctx()
        repo = _make_repo(ctx)
        domain = _FakeDomain(
            id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            name="hello",
        )
        orm = repo._to_orm(domain)
        assert isinstance(orm, _FakeORM)
        assert orm.tenant_id == domain.tenant_id
        assert orm.workspace_id == domain.workspace_id
        assert orm.name == "hello"

    def test_to_domain_produces_domain_instance(self) -> None:
        """_to_domain 이 올바른 도메인 인스턴스를 반환."""
        ctx = _make_tenant_ctx()
        repo = _make_repo(ctx)
        orm = _FakeORM(
            id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            name="world",
        )
        domain = repo._to_domain(orm)
        assert isinstance(domain, _FakeDomain)
        assert domain.tenant_id == orm.tenant_id
        assert domain.name == "world"

    def test_round_trip_preserves_data(self) -> None:
        """ORM → domain → ORM 라운드트립에서 데이터 보존."""
        ctx = _make_tenant_ctx()
        repo = _make_repo(ctx)
        original_orm = _FakeORM(
            id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            name="roundtrip",
        )
        domain = repo._to_domain(original_orm)
        back_orm = repo._to_orm(domain)
        assert back_orm.id == original_orm.id
        assert back_orm.name == original_orm.name


class TestDeleteBoundary:
    """delete 시 tenant 경계 확인 (mock session 사용)."""

    @pytest.mark.asyncio
    async def test_delete_returns_false_for_other_tenant_orm(self) -> None:
        """다른 tenant 소유의 ORM 이 session.get 에서 반환되면 False 반환."""
        ctx = _make_tenant_ctx()
        mock_session = AsyncMock()
        # session.get 이 다른 tenant 의 ORM 반환
        other_tenant_orm = _FakeORM(
            id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
            tenant_id=uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            workspace_id=ctx.workspace_id,
        )
        mock_session.get = AsyncMock(return_value=other_tenant_orm)
        repo = _FakeRepository(mock_session, ctx)

        result = await repo.delete(uuid.UUID("44444444-4444-4444-4444-444444444444"))
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self) -> None:
        """session.get 이 None 반환하면 False."""
        ctx = _make_tenant_ctx()
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)
        repo = _FakeRepository(mock_session, ctx)

        result = await repo.delete(uuid.uuid4())
        assert result is False
