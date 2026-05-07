"""WorksheetRepository 단위 + 통합 테스트.

단위 테스트: mock session 으로 sentinel / tenant 검증.
통합 테스트: 실제 PostgreSQL (@pytest.mark.integration) 으로 멀티테넌트 격리.

W-2 가드 규칙 (models/worksheet.py):
  - WorksheetItemORM 단독 SELECT 금지 — 항상 부모 WorksheetORM 의 tenant_id 검증 후 조회.
  - list_items_for_worksheet() 가 이 패턴을 강제한다.
  - 다른 tenant 의 worksheet_id 로 list_items 호출 시 빈 리스트 반환 (차단).

create_with_items 테스트:
  - 단위: mock session 으로 sentinel / tenant 검증 + cross-tenant passage_id 검증.
  - 통합: 실제 PostgreSQL 에 worksheet + items 영속화 확인.
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

    # ─── create_with_items 단위 테스트 ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_with_items_sentinel_tenant_id_raises(self) -> None:
        """create_with_items: tenant_id == SENTINEL_UUID 이면 ValueError."""
        mock_session = AsyncMock()
        repo = WorksheetRepository(mock_session, _ctx_a())

        worksheet = _make_worksheet()
        worksheet_with_sentinel = worksheet.model_copy(update={"tenant_id": SENTINEL_UUID})

        with pytest.raises(ValueError, match="sentinel UUID"):
            await repo.create_with_items(worksheet_with_sentinel)

        # sentinel 검증 실패 시 DB 쿼리가 전혀 없어야 한다
        mock_session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_with_items_cross_tenant_raises(self) -> None:
        """create_with_items: input tenant_id != context tenant_id → ValueError."""
        mock_session = AsyncMock()
        repo = WorksheetRepository(mock_session, _ctx_a())

        # TENANT_B 소속 worksheet 를 TENANT_A context repo 에 create 시도
        worksheet_b = _make_worksheet(tenant_id=TENANT_B, workspace_id=WORKSPACE_B)

        with pytest.raises(ValueError, match="tenant_id 불일치"):
            await repo.create_with_items(worksheet_b)

        mock_session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_with_items_cross_tenant_passage_id_raises(self) -> None:
        """create_with_items: passage_id 가 다른 tenant 소유이면 ValueError.

        sa_text IN 쿼리 결과가 요청 passage_id 수보다 적으면
        cross-tenant passage_id 로 간주해 ValueError 를 raise 해야 한다.
        """
        from unittest.mock import MagicMock

        mock_session = AsyncMock()
        # COUNT(*) 가 0 을 반환 → passage 가 다른 tenant 소속
        mock_scalar_result = MagicMock()
        mock_scalar_result.scalar_one.return_value = 0
        mock_session.exec.return_value = mock_scalar_result

        repo = WorksheetRepository(mock_session, _ctx_a())

        foreign_passage_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        worksheet = _make_worksheet(
            items=[
                WorksheetItem(passage_id=foreign_passage_id, order=0),
            ]
        )

        with pytest.raises(ValueError, match="cross-tenant passage_id"):
            await repo.create_with_items(worksheet)

        # passage count 쿼리 1회 실행됐어야 한다
        assert mock_session.exec.call_count == 1

    @pytest.mark.asyncio
    async def test_create_with_items_no_items_skips_passage_check(self) -> None:
        """create_with_items: items 가 빈 리스트이면 passage_id 검증 쿼리가 없어야 한다.

        passage count 쿼리는 items 가 있을 때만 실행된다.
        items=[] 이면 worksheet insert 만 실행.

        _to_orm 이 실제 WorksheetORM.model_validate 를 호출하므로 전체 흐름 검증은
        통합 테스트에서 진행. 여기서는 exec(passage count query) 가 없음만 검증.
        flush/refresh 실패는 무시 — exec 호출 여부만 검증.
        """
        from unittest.mock import MagicMock

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        worksheet = _make_worksheet(items=[])
        repo = WorksheetRepository(mock_session, _ctx_a())

        try:
            await repo.create_with_items(worksheet)
        except Exception:
            pass  # flush/refresh 실패는 무시 — exec 호출 여부만 검증

        mock_session.exec.assert_not_called()


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

    @pytest.mark.asyncio
    async def test_create_with_items_persists_worksheet_and_items(self, pg_session) -> None:  # type: ignore[no-untyped-def]
        """create_with_items: 실제 PostgreSQL 에 worksheet + items 영속화 확인.

        절차:
          1. Passage INSERT (passage_id 확보).
          2. create_with_items 로 Worksheet + WorksheetItem 생성.
          3. get() + list_items_for_worksheet() 로 재조회 → 데이터 일치 확인.
        """
        from datetime import UTC, datetime

        from sqlalchemy import text as sa_text
        from sqlmodel.ext.asyncio.session import AsyncSession

        now = datetime.now(UTC)
        passage_id = uuid.UUID("11112222-3333-4444-5555-666677778888")

        # Passage INSERT (FK 충족용)
        async with AsyncSession(pg_session.bind) as insert_session:
            async with insert_session.begin():
                await insert_session.execute(
                    sa_text(
                        "INSERT INTO passages "
                        "(id, tenant_id, workspace_id, body_text, word_count, target_grade, "
                        " paragraphs, topic_tags, created_at, updated_at) "
                        "VALUES (:id, :tenant_id, :workspace_id, :body_text, :word_count, "
                        "        :target_grade, :paragraphs::jsonb, :topic_tags::jsonb, :now, :now) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": str(passage_id),
                        "tenant_id": str(TENANT_A),
                        "workspace_id": str(WORKSPACE_A),
                        "body_text": "Test passage body.",
                        "word_count": 3,
                        "target_grade": "high_3",
                        "paragraphs": '["Test passage body."]',
                        "topic_tags": "[]",
                        "now": now,
                    },
                )

        # create_with_items
        worksheet = _make_worksheet(
            items=[
                WorksheetItem(passage_id=passage_id, order=0, label="독해 연습"),
            ]
        )

        repo = WorksheetRepository(pg_session, _ctx_a())
        async with pg_session.begin():
            saved = await repo.create_with_items(worksheet)

        assert saved.id is not None
        assert saved.title == "테스트 워크시트"
        assert len(saved.items) == 1
        assert saved.items[0].passage_id == passage_id
        assert saved.items[0].order == 0
        assert saved.items[0].label == "독해 연습"

        # 재조회로 영속화 확인
        reloaded = await repo.get(saved.id)
        assert reloaded is not None
        assert reloaded.title == "테스트 워크시트"

        items_orm = await repo.list_items_for_worksheet(saved.id)
        assert len(items_orm) == 1
        assert items_orm[0].passage_id == passage_id

    @pytest.mark.asyncio
    async def test_create_with_items_cross_tenant_passage_rejected(self, pg_session) -> None:  # type: ignore[no-untyped-def]
        """create_with_items: 다른 tenant 소속 passage_id → ValueError.

        절차:
          1. tenant B 소속 Passage INSERT.
          2. tenant A context 로 create_with_items — passage_id 가 tenant B 소속.
          3. ValueError 발생 확인.
        """
        from datetime import UTC, datetime

        from sqlalchemy import text as sa_text
        from sqlmodel.ext.asyncio.session import AsyncSession

        now = datetime.now(UTC)
        foreign_passage_id = uuid.UUID("aaaabbbb-cccc-dddd-eeee-ffff00001111")

        # tenant B 소속 Passage INSERT
        async with AsyncSession(pg_session.bind) as insert_session:
            async with insert_session.begin():
                await insert_session.execute(
                    sa_text(
                        "INSERT INTO passages "
                        "(id, tenant_id, workspace_id, body_text, word_count, target_grade, "
                        " paragraphs, topic_tags, created_at, updated_at) "
                        "VALUES (:id, :tenant_id, :workspace_id, :body_text, :word_count, "
                        "        :target_grade, :paragraphs::jsonb, :topic_tags::jsonb, :now, :now) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": str(foreign_passage_id),
                        "tenant_id": str(TENANT_B),
                        "workspace_id": str(WORKSPACE_B),
                        "body_text": "Tenant B passage.",
                        "word_count": 3,
                        "target_grade": "high_3",
                        "paragraphs": '["Tenant B passage."]',
                        "topic_tags": "[]",
                        "now": now,
                    },
                )

        # tenant A context 로 create — foreign passage_id 참조
        worksheet = _make_worksheet(
            items=[
                WorksheetItem(passage_id=foreign_passage_id, order=0),
            ]
        )

        repo = WorksheetRepository(pg_session, _ctx_a())
        with pytest.raises(ValueError, match="cross-tenant passage_id|tenant"):
            async with pg_session.begin():
                await repo.create_with_items(worksheet)
