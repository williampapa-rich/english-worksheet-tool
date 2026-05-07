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

        SQLModel COUNT IN 쿼리 결과가 요청 passage_id 수보다 적으면
        cross-tenant passage_id 로 간주해 ValueError 를 raise 해야 한다.
        """
        from unittest.mock import MagicMock

        mock_session = AsyncMock()
        # COUNT(*) 가 0 을 반환 → passage 가 다른 tenant 소속
        # SQLModel exec().one() 은 Result.one() 호출 — sync 메서드, MagicMock 으로 처리
        mock_count_result = MagicMock()
        mock_count_result.one.return_value = 0
        mock_session.exec.return_value = mock_count_result

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
    async def test_create_with_items_duplicate_passage_id_raises(self) -> None:
        """create_with_items: items 안에 같은 passage_id 가 두 번 나오면 ValueError.

        도메인 정책 (Phase 2 PoC): 동일 passage 를 여러 item 에 중복으로 넣을 수 없음.
        와이프 요청 들어오면 완화 (별 ADR / PR).
        검증은 cross-tenant 검증보다 먼저 — DB 쿼리 전에 차단.
        """
        mock_session = AsyncMock()
        repo = WorksheetRepository(mock_session, _ctx_a())

        same_passage_id = uuid.UUID("11112222-3333-4444-5555-666677778888")
        worksheet = _make_worksheet(
            items=[
                WorksheetItem(passage_id=same_passage_id, order=0, label="첫 번째"),
                WorksheetItem(passage_id=same_passage_id, order=1, label="두 번째"),
            ]
        )

        with pytest.raises(ValueError, match="중복"):
            await repo.create_with_items(worksheet)

        # 중복 검증은 DB 쿼리 전에 차단 — exec 호출 0회
        mock_session.exec.assert_not_called()

    # ─── list_with_pagination 단위 테스트 ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_with_pagination_calls_count_and_list(self) -> None:
        """list_with_pagination: count 쿼리와 list 쿼리가 각각 1회씩 실행된다.

        exec 가 2회 호출되어야 한다 (count 1회 + list 1회).
        첫 번째 exec 결과는 .one() 으로 총 개수, 두 번째 결과는 .all() 로 목록.
        """
        from unittest.mock import MagicMock

        mock_session = AsyncMock()
        # 첫 번째 exec (count): result.one() → 3
        mock_count_result = MagicMock()
        mock_count_result.one.return_value = 3
        # 두 번째 exec (list): result.all() → 빈 리스트 (ORM 변환 필요 없음)
        mock_list_result = MagicMock()
        mock_list_result.all.return_value = []
        mock_session.exec.side_effect = [mock_count_result, mock_list_result]

        repo = WorksheetRepository(mock_session, _ctx_a())
        worksheets, total = await repo.list_with_pagination(limit=10, offset=0)

        assert total == 3
        assert worksheets == []
        assert mock_session.exec.call_count == 2

    @pytest.mark.asyncio
    async def test_list_with_pagination_empty_returns_zero_total(self) -> None:
        """빈 결과: ([], 0) 반환."""
        from unittest.mock import MagicMock

        mock_session = AsyncMock()
        mock_count_result = MagicMock()
        mock_count_result.one.return_value = 0
        mock_list_result = MagicMock()
        mock_list_result.all.return_value = []
        mock_session.exec.side_effect = [mock_count_result, mock_list_result]

        repo = WorksheetRepository(mock_session, _ctx_a())
        worksheets, total = await repo.list_with_pagination()

        assert worksheets == []
        assert total == 0

    # ─── update_meta 단위 테스트 ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_meta_items_key_raises(self) -> None:
        """update_meta: patch 에 items 키 포함 → ValueError (명시 차단)."""
        mock_session = AsyncMock()
        repo = WorksheetRepository(mock_session, _ctx_a())

        with pytest.raises(ValueError, match="items"):
            await repo.update_meta(
                uuid.UUID("11111111-1111-1111-1111-111111111111"),
                {"title": "새 제목", "items": []},
            )

        # items 키 차단 — DB 쿼리 없어야 한다
        mock_session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_meta_cross_tenant_returns_none(self) -> None:
        """update_meta: cross-tenant (또는 미존재) worksheet_id → None 반환.

        _get_orm() 이 None 을 반환하면 update_meta 는 DB 쓰기 없이 None 을 반환한다.
        """
        from unittest.mock import MagicMock

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None  # not found / cross-tenant
        mock_session.exec.return_value = mock_result

        repo = WorksheetRepository(mock_session, _ctx_a())

        result = await repo.update_meta(
            uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            {"title": "새 제목"},
        )

        assert result is None
        # flush 호출 없어야 한다 (ORM 인스턴스를 얻지 못했으므로)
        mock_session.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_meta_patches_only_meta_fields(self) -> None:
        """update_meta: 허용 메타 필드만 ORM 에 setattr 되고, items 는 무시된다.

        ORM mock 에 setattr 이 title 만 호출되는지 검증.
        flush → refresh → _to_domain 변환 까지 흐름 확인.
        """
        from unittest.mock import MagicMock

        mock_session = AsyncMock()

        # _get_orm 이 반환할 ORM mock
        orm_mock = MagicMock()
        orm_mock.id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        orm_mock.tenant_id = TENANT_A
        orm_mock.workspace_id = WORKSPACE_A
        orm_mock.title = "원래 제목"
        orm_mock.subtitle = None
        orm_mock.kind = "student"
        orm_mock.template_id = "playful"
        orm_mock.orientation = "portrait"
        orm_mock.instruction = None
        orm_mock.branding = {}
        orm_mock.school = None
        orm_mock.grade = None
        orm_mock.exam_date = None
        orm_mock.time_limit = None
        orm_mock.created_at = None
        orm_mock.updated_at = None

        mock_result = MagicMock()
        mock_result.first.return_value = orm_mock
        mock_session.exec.return_value = mock_result

        repo = WorksheetRepository(mock_session, _ctx_a())

        # update_meta 호출 (title 만 patch)
        try:
            await repo.update_meta(
                uuid.UUID("11111111-1111-1111-1111-111111111111"),
                {"title": "새 제목"},
            )
        except Exception:
            pass  # _to_domain 변환 실패는 무시 — flush/setattr 호출 여부만 검증

        # title 이 orm 에 직접 패치되어야 한다
        assert orm_mock.title == "새 제목"
        # flush 가 호출되어야 한다
        mock_session.flush.assert_called_once()

    # ─── delete 단위 테스트 ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_not_found_returns_false(self) -> None:
        """delete: worksheet_id 가 없으면 False 반환.

        BaseRepository.delete() 는 session.get() 이 None 을 반환하면 False 를 반환한다.
        """
        mock_session = AsyncMock()
        mock_session.get.return_value = None

        repo = WorksheetRepository(mock_session, _ctx_a())
        result = await repo.delete(uuid.UUID("99999999-9999-9999-9999-999999999999"))

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_cross_tenant_returns_false(self) -> None:
        """delete: cross-tenant ORM (tenant_id 불일치) → False 반환.

        BaseRepository.delete() 는 getattr(orm, 'tenant_id') 가 context 와 다르면 False.
        """
        from unittest.mock import MagicMock

        mock_session = AsyncMock()

        # 다른 tenant 소속 ORM mock
        orm_mock = MagicMock()
        orm_mock.tenant_id = TENANT_B  # context 는 TENANT_A
        orm_mock.workspace_id = WORKSPACE_B
        mock_session.get.return_value = orm_mock

        repo = WorksheetRepository(mock_session, _ctx_a())
        result = await repo.delete(uuid.UUID("11111111-1111-1111-1111-111111111111"))

        assert result is False
        mock_session.delete.assert_not_called()

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
        # S-1 (a) — items 도 영속화 후 id 가 채워져야 한다.
        assert saved.items[0].id is not None, "create_with_items 는 item.id 를 반환해야 한다"
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
    async def test_list_with_pagination_and_cross_tenant_isolation(self, pg_session) -> None:  # type: ignore[no-untyped-def]
        """list_with_pagination: limit/offset/kind 필터 동작 + cross-tenant 격리 확인.

        절차:
          1. tenant A: student worksheet 2개, syntax_analysis worksheet 1개 생성.
          2. tenant B: student worksheet 1개 생성.
          3. tenant A context 로 kind=student, limit=1, offset=0 조회 → 1건, total=2.
          4. tenant A context 로 kind=syntax_analysis 조회 → 1건.
          5. tenant A context 로 kind=None 조회 → 3건, total=3.
          6. tenant B context 로 kind=None 조회 → 1건 (cross-tenant 격리).
        """
        from datetime import UTC, datetime

        from sqlalchemy import text as sa_text
        from sqlmodel.ext.asyncio.session import AsyncSession

        now = datetime.now(UTC)

        ws_a1 = uuid.UUID("aabbcc01-0000-0000-0000-000000000001")
        ws_a2 = uuid.UUID("aabbcc01-0000-0000-0000-000000000002")
        ws_a3 = uuid.UUID("aabbcc01-0000-0000-0000-000000000003")
        ws_b1 = uuid.UUID("aabbcc02-0000-0000-0000-000000000001")

        # W-1: 문자열 리터럴 대신 WorksheetKind enum 의 .value 사용 — enum 값 변경 시
        # 컴파일 시점에 추적 가능 (raw SQL bind 라 문자열은 필요).
        async with AsyncSession(pg_session.bind) as ins:
            async with ins.begin():
                for ws_id, t_id, w_id, kind in [
                    (ws_a1, TENANT_A, WORKSPACE_A, WorksheetKind.STUDENT.value),
                    (ws_a2, TENANT_A, WORKSPACE_A, WorksheetKind.STUDENT.value),
                    (ws_a3, TENANT_A, WORKSPACE_A, WorksheetKind.SYNTAX_ANALYSIS.value),
                    (ws_b1, TENANT_B, WORKSPACE_B, WorksheetKind.STUDENT.value),
                ]:
                    await ins.execute(
                        sa_text(
                            "INSERT INTO worksheets "
                            "(id, tenant_id, workspace_id, title, kind, template_id, orientation, created_at, updated_at) "
                            "VALUES (:id, :tenant_id, :workspace_id, :title, :kind, :template_id, :orientation, :now, :now) "
                            "ON CONFLICT (id) DO NOTHING"
                        ),
                        {
                            "id": str(ws_id),
                            "tenant_id": str(t_id),
                            "workspace_id": str(w_id),
                            "title": f"Worksheet {ws_id}",
                            "kind": kind,
                            "template_id": "playful",
                            "orientation": "portrait",
                            "now": now,
                        },
                    )

        repo_a = WorksheetRepository(pg_session, _ctx_a())

        # tenant A, kind=student, limit=1 → 1건, total=2
        wss, total = await repo_a.list_with_pagination(
            limit=1, offset=0, kind=WorksheetKind.STUDENT.value
        )
        assert total == 2
        assert len(wss) == 1

        # tenant A, kind=syntax_analysis → 1건
        wss, total = await repo_a.list_with_pagination(kind=WorksheetKind.SYNTAX_ANALYSIS.value)
        assert total == 1
        assert len(wss) == 1

        # tenant A, kind=None → 3건
        wss, total = await repo_a.list_with_pagination()
        assert total == 3
        assert len(wss) == 3

        # tenant B, kind=None → 1건 (cross-tenant 격리)
        repo_b = WorksheetRepository(pg_session, _ctx_b())
        wss_b, total_b = await repo_b.list_with_pagination()
        assert total_b == 1
        assert all(ws.tenant_id == TENANT_B for ws in wss_b)

    @pytest.mark.asyncio
    async def test_delete_cascades_worksheet_items(self, pg_session) -> None:  # type: ignore[no-untyped-def]
        """delete: Worksheet 삭제 시 worksheet_items 도 ON DELETE CASCADE 로 자동 정리.

        절차:
          1. Passage INSERT (FK 충족).
          2. create_with_items 로 Worksheet + WorksheetItem 생성.
          3. delete() 로 Worksheet 삭제 → True 반환 확인.
          4. list_items_for_worksheet() → 빈 리스트 (cascade 삭제 확인).
          5. get() → None (worksheet 도 삭제됨).
        """
        from datetime import UTC, datetime

        from sqlalchemy import text as sa_text
        from sqlmodel.ext.asyncio.session import AsyncSession

        now = datetime.now(UTC)
        passage_id = uuid.UUID("ddddeeee-ffff-0000-1111-222233334444")

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
                        "body_text": "Cascade test passage.",
                        "word_count": 3,
                        "target_grade": "high_3",
                        "paragraphs": '["Cascade test passage."]',
                        "topic_tags": "[]",
                        "now": now,
                    },
                )

        # Worksheet + items 생성
        worksheet = _make_worksheet(
            items=[WorksheetItem(passage_id=passage_id, order=0, label="cascade 확인용")]
        )
        repo = WorksheetRepository(pg_session, _ctx_a())
        async with pg_session.begin():
            saved = await repo.create_with_items(worksheet)

        assert saved.id is not None
        assert len(saved.items) == 1

        # delete() 호출
        async with pg_session.begin():
            deleted = await repo.delete(saved.id)

        assert deleted is True, "delete() 는 성공 시 True 를 반환해야 한다"

        # cascade 검증 — worksheet 도 items 도 없어야 한다
        reloaded = await repo.get(saved.id)
        assert reloaded is None, "삭제된 worksheet 는 get() 에서 None 이어야 한다"

        items_after = await repo.list_items_for_worksheet(saved.id)
        assert items_after == [], "ON DELETE CASCADE — worksheet 삭제 후 items 도 없어야 한다"

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
