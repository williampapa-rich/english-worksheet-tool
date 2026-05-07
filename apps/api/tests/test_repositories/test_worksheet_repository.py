"""WorksheetRepository 단위 + 통합 테스트.

단위 테스트: mock session 으로 sentinel / tenant 검증.
통합 테스트: 실제 PostgreSQL (@pytest.mark.integration) 으로 멀티테넌트 격리.

W-2 가드 규칙 (models/worksheet.py):
  - WorksheetItemORM 단독 SELECT 금지 — 항상 부모 WorksheetORM 의 tenant_id 검증 후 조회.
  - list_items_for_worksheet() 가 이 패턴을 강제한다.
  - 다른 tenant 의 worksheet_id 로 list_items 호출 시 빈 리스트 반환 (차단).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from worksheet_api.models.base import SENTINEL_UUID
from worksheet_api.repositories.tenant_context import TenantContext
from worksheet_api.repositories.worksheet import WorksheetRepository

from shared.schemas.worksheet import Branding, Worksheet, WorksheetItem, WorksheetKind

# ─── 공통 픽스처 ─────────────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TENANT_B = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
WORKSPACE_B = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _make_worksheet(
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
    title: str = "테스트 워크시트",
    items: list[WorksheetItem] | None = None,
) -> Worksheet:
    """테스트용 Worksheet 생성 헬퍼."""
    return Worksheet(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        title=title,
        kind=WorksheetKind.STUDENT,
        template_id="playful",
        branding=Branding(academy_name="테스트학원"),
        items=items or [],
    )


def _ctx_a() -> TenantContext:
    return TenantContext(tenant_id=TENANT_A, workspace_id=WORKSPACE_A)


def _ctx_b() -> TenantContext:
    return TenantContext(tenant_id=TENANT_B, workspace_id=WORKSPACE_B)


# ─── 단위 테스트 (mock session) ───────────────────────────────────────────────


class TestWorksheetRepositoryUnit:
    """sentinel / tenant 검증 단위 테스트 (DB 없음)."""

    @pytest.mark.asyncio
    async def test_create_sentinel_tenant_id_raises(self) -> None:
        """tenant_id == SENTINEL_UUID 이면 create 에서 ValueError."""
        mock_session = AsyncMock()
        repo = WorksheetRepository(mock_session, _ctx_a())

        worksheet = _make_worksheet()
        worksheet_with_sentinel = worksheet.model_copy(update={"tenant_id": SENTINEL_UUID})

        with pytest.raises(ValueError, match="sentinel UUID"):
            await repo.create(worksheet_with_sentinel)

    @pytest.mark.asyncio
    async def test_create_cross_tenant_raises(self) -> None:
        """다른 tenant 의 worksheet 를 create 하려 하면 ValueError."""
        mock_session = AsyncMock()
        repo = WorksheetRepository(mock_session, _ctx_a())

        # TENANT_B 소속 worksheet 를 TENANT_A context repo 에 create 시도
        worksheet_b = _make_worksheet(tenant_id=TENANT_B, workspace_id=WORKSPACE_B)

        with pytest.raises(ValueError, match="tenant_id 불일치"):
            await repo.create(worksheet_b)

    @pytest.mark.asyncio
    async def test_list_items_w2_guard_returns_empty_for_foreign_tenant(self) -> None:
        """W-2 가드: 다른 tenant 의 worksheet_id 로 list_items 호출 시 빈 리스트.

        WorksheetRepository.get() 이 None 을 반환하면 list_items_for_worksheet() 는
        session 에 추가 쿼리를 보내지 않고 바로 [] 를 반환해야 한다.

        BaseRepository.get() 은 ``await session.exec(stmt)`` 후 ``result.first()`` (동기) 를
        호출한다. AsyncMock 에서 exec 의 return_value 는 synchronous MagicMock 으로 설정해야
        ``result.first()`` 가 코루틴이 아닌 None 을 직접 반환한다.
        """
        from unittest.mock import MagicMock

        mock_session = AsyncMock()
        # exec 는 async → await 후 result 반환. result.first() 는 동기 호출.
        mock_result = MagicMock()
        mock_result.first.return_value = None  # not found → get() returns None
        mock_session.exec.return_value = mock_result

        repo = WorksheetRepository(mock_session, _ctx_a())
        foreign_worksheet_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

        result = await repo.list_items_for_worksheet(foreign_worksheet_id)

        assert result == []
        # WorksheetORM get 이후 ItemORM 쿼리가 없어야 한다 (exec 는 1회 — get() 용으로만)
        assert mock_session.exec.call_count == 1


# ─── 통합 테스트 (PostgreSQL) ─────────────────────────────────────────────────


@pytest.mark.integration
class TestWorksheetRepositoryIntegration:
    """실제 PostgreSQL 통합 테스트.

    Docker compose PostgreSQL 이 필요하다.
    pytest -m integration 으로 실행.
    """

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation_list_items(self, pg_session) -> None:  # type: ignore[no-untyped-def]
        """W-2 가드 통합 검증: tenant B 의 worksheet_id 로 tenant A context 가 list_items 호출 시 차단.

        절차:
          1. tenant B context 로 worksheet + items 생성.
          2. tenant A context 의 repo 로 위 worksheet_id 로 list_items 호출.
          3. 빈 리스트 반환 확인 (cross-tenant 차단).
        """
        from datetime import UTC, datetime

        from sqlalchemy import text as sa_text
        from sqlmodel.ext.asyncio.session import AsyncSession

        # tenant B worksheet 직접 INSERT (통합 픽스처 테넌트 UUID)
        ws_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        now = datetime.now(UTC)

        async with AsyncSession(pg_session.bind) as insert_session:
            async with insert_session.begin():
                await insert_session.execute(
                    sa_text(
                        "INSERT INTO worksheets "
                        "(id, tenant_id, workspace_id, title, kind, template_id, orientation, created_at, updated_at) "
                        "VALUES (:id, :tenant_id, :workspace_id, :title, :kind, :template_id, :orientation, :now, :now) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": str(ws_id),
                        "tenant_id": str(TENANT_B),
                        "workspace_id": str(WORKSPACE_B),
                        "title": "Tenant B 워크시트",
                        "kind": "student",
                        "template_id": "playful",
                        "orientation": "portrait",
                        "now": now,
                    },
                )

        # tenant A context 로 조회 시도 → 빈 리스트 기대
        repo_a = WorksheetRepository(pg_session, _ctx_a())
        items = await repo_a.list_items_for_worksheet(ws_id)
        assert items == [], "cross-tenant item 노출은 W-2 가드로 차단되어야 한다"
