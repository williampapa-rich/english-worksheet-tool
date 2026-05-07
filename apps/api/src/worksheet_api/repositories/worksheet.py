"""WorksheetRepository — Worksheet + WorksheetItem CRUD + 멀티테넌트 강제.

ADR-0005 §D-5.1 boilerplate 패턴.

멀티테넌트 격리 전략 (models/worksheet.py W-2 docstring 가드):
  - WorksheetORM 은 tenant_id / workspace_id 컬럼을 가진다 — BaseRepository 자동 필터.
  - WorksheetItemORM 자체는 tenant_id 컬럼이 없으므로 단독 SELECT 금지.
    반드시 ``WorksheetORM`` 을 통해 tenant_id 를 검증한 후 worksheet_id 로 item 을 조회한다.
  - ``list_items_for_worksheet()`` 가 이 패턴을 강제 — 외부에서 raw WorksheetItemORM
    SELECT 를 허용하지 않는다.
"""

from __future__ import annotations

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.worksheet import Worksheet
from worksheet_api.models.worksheet import WorksheetItemORM, WorksheetORM
from worksheet_api.repositories.base import BaseRepository
from worksheet_api.repositories.tenant_context import TenantContext


class WorksheetRepository(BaseRepository[WorksheetORM, Worksheet]):
    """Worksheet CRUD repository.

    BaseRepository 의 sentinel UUID 검증과 tenant/workspace 필터가 모든
    메서드에 자동 적용된다.

    Args:
        session: SQLModel AsyncSession.
        tenant_ctx: 현재 요청의 TenantContext.
    """

    _orm_class = WorksheetORM
    _domain_class = Worksheet

    def __init__(self, session: AsyncSession, tenant_ctx: TenantContext) -> None:
        super().__init__(session, tenant_ctx)

    # ─── 변환 ────────────────────────────────────────────────────────────────

    def _to_orm(self, domain: Worksheet) -> WorksheetORM:
        """Worksheet → WorksheetORM 변환.

        ``branding`` (Pydantic 모델) 은 JSONB 컬럼이므로 model_dump(mode="python") 으로
        dict 로 변환해 넘긴다. ``items`` 는 WorksheetItemORM 으로 별도 저장 — 여기서는
        제외하고 WorksheetORM 만 생성 (items 영속화는 create_with_items 에서).
        ADR-0005 §D-5.6 패턴.
        """
        data = domain.model_dump(mode="python", exclude={"items"})
        return WorksheetORM.model_validate(data)

    def _to_domain(self, orm: WorksheetORM) -> Worksheet:
        """WorksheetORM → Worksheet 변환.

        ADR-0005 §D-5.1 boilerplate.
        ``items`` 는 lazy 로드하지 않으므로 빈 리스트로 반환.
        items 가 필요하면 ``list_items_for_worksheet()`` 를 별도로 호출해야 한다.

        PassageRepository._to_domain 패턴과 동일: from_attributes=True 덕분에
        ORM attribute 접근으로 Pydantic 모델 복원. branding JSONB dict →
        Branding Pydantic 역직렬화도 자동 처리.
        ``items`` 는 WorksheetORM 에 없는 필드이므로, model_validate 전에
        ``Worksheet`` 의 default_factory 빈 리스트가 적용된다.
        """
        return Worksheet.model_validate(orm, update={"items": []})

    # ─── items 조회 ──────────────────────────────────────────────────────────

    async def list_items_for_worksheet(
        self,
        worksheet_id: uuid.UUID,
    ) -> list[WorksheetItemORM]:
        """WorksheetItemORM 목록 조회 — tenant_id 이중 검증.

        W-2 가드 규칙 (models/worksheet.py docstring) 구현:
          1. 부모 WorksheetORM 을 tenant_id + workspace_id 필터로 먼저 조회.
          2. 존재하지 않거나 다른 tenant 소유이면 빈 리스트 반환 (404 결정은 호출자 책임).
          3. 검증 통과 후 worksheet_id 로 WorksheetItemORM 을 조회.

        WorksheetItemORM 단독 SELECT 를 허용하지 않는 이 패턴이
        cross-tenant item 노출을 구조적으로 차단한다.

        Args:
            worksheet_id: item 을 조회할 Worksheet UUID.

        Returns:
            WorksheetItemORM 리스트 (order 기준 정렬). 부모 Worksheet 가 없거나 다른
            tenant 소유이면 빈 리스트.
        """
        # 1. 부모 WorksheetORM tenant 검증 (BaseRepository.get 이 tenant 필터 자동 적용)
        parent = await self.get(worksheet_id)
        if parent is None:
            # 존재하지 않거나 다른 tenant 소유 — items 조회 금지
            return []

        # 2. 검증 통과 → worksheet_id 로 items 조회
        stmt = (
            select(WorksheetItemORM)
            .where(WorksheetItemORM.worksheet_id == worksheet_id)
            .order_by(WorksheetItemORM.order)
        )
        result = await self._session.exec(stmt)
        return list(result.all())
