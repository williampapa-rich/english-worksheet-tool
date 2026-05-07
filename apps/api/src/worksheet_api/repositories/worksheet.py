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

from sqlalchemy import desc, func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.worksheet import Worksheet, WorksheetItem
from worksheet_api.models.passage import PassageORM
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
        return Worksheet.model_validate(orm).model_copy(update={"items": []})

    # ─── create ─────────────────────────────────────────────────────────────

    async def create_with_items(self, worksheet: Worksheet) -> Worksheet:
        """Worksheet + 모든 items 를 단일 트랜잭션에 영속화.

        호출 전제: 호출자가 ``async with session.begin():`` 컨텍스트 안에 있어야 한다.
        commit 은 caller 책임 (BaseRepository 패턴 준수).

        흐름:
          1. tenant_id / workspace_id 일치 검증 (BaseRepository._validate_tenant_fields).
          2. items 중복 passage_id 검증 (도메인 정책 — 동일 passage 두 번 금지).
          3. passage_id cross-tenant 사전 검증 (SQLModel IN 쿼리 1회).
          4. WorksheetORM insert + flush → id 확보.
          5. WorksheetItemORM bulk insert (단일 flush — N→1 round-trip 최적화).
          6. 최신 상태 Worksheet (items id 포함) 반환.

        Args:
            worksheet: 영속화할 Worksheet 도메인 모델.
                tenant_id / workspace_id 는 TenantContext 와 일치해야 한다.

        Returns:
            id 가 채워진 Worksheet (items 도 id 포함).

        Raises:
            ValueError: sentinel UUID / tenant_id 불일치 / 중복 passage_id /
                cross-tenant passage_id.
            sqlalchemy.exc.IntegrityError: passage_id 가 DB 에 존재하지 않을 때
                (ondelete=RESTRICT FK 위배). 라우터에서 422 매핑.
        """
        # 1. tenant 검증 (sentinel + 불일치)
        self._validate_tenant_fields(worksheet)

        # 2. 중복 passage_id 검증 (도메인 정책 — Phase 2 PoC 기준 동일 passage 두 번 금지)
        #    이유: 같은 지문을 다른 옵션으로 두 번 넣는 use case 가 모호 — 와이프 요청 들어오면
        #    완화 (len(set(passage_ids)) 비교로 변경).
        if worksheet.items:
            passage_ids = [item.passage_id for item in worksheet.items]
            if len(set(passage_ids)) != len(passage_ids):
                duplicates = sorted({pid for pid in passage_ids if passage_ids.count(pid) > 1})
                raise ValueError(
                    f"같은 passage_id 를 여러 item 에 중복으로 넣을 수 없습니다. "
                    f"중복된 passage_id: {duplicates}."
                )

            # 3. passage_id cross-tenant 사전 검증 — SQLModel IN 쿼리 (UUID 인덱스 활용).
            #    BaseRepository._tenant_ctx 가 보장한 tenant 안의 passages 만 카운트.
            count_stmt = (
                select(func.count())
                .select_from(PassageORM)
                .where(PassageORM.id.in_(passage_ids))  # type: ignore[attr-defined]
                .where(PassageORM.tenant_id == self._tenant_ctx.tenant_id)
            )
            count_result = await self._session.exec(count_stmt)
            count = count_result.one()

            if count != len(passage_ids):
                raise ValueError(
                    f"passage_id 중 하나 이상이 현재 tenant({self._tenant_ctx.tenant_id}) "
                    f"소유가 아니거나 존재하지 않습니다. "
                    f"요청된 passage_id 개수={len(passage_ids)}, "
                    f"검증 통과 개수={count}. "
                    f"cross-tenant passage_id 또는 삭제된 passage 참조 시도."
                )

        # 4. WorksheetORM insert (items 제외)
        worksheet_orm = self._to_orm(worksheet)
        self._session.add(worksheet_orm)
        await self._session.flush()
        await self._session.refresh(worksheet_orm)

        # 5. WorksheetItemORM bulk add → 단일 flush (N round-trip → 1 round-trip)
        item_orms: list[WorksheetItemORM] = []
        for item in worksheet.items:
            item_orm = WorksheetItemORM(
                worksheet_id=worksheet_orm.id,
                passage_id=item.passage_id,
                order=item.order,
                label=item.label,
                include_translation=item.include_translation,
                include_vocabulary=item.include_vocabulary,
                include_syntax_annotations=item.include_syntax_annotations,
                include_questions=item.include_questions,
                include_variants=item.include_variants,
            )
            self._session.add(item_orm)
            item_orms.append(item_orm)

        if item_orms:
            await self._session.flush()
            for item_orm in item_orms:
                await self._session.refresh(item_orm)

        saved_items = [
            WorksheetItem(
                id=item_orm.id,
                passage_id=item_orm.passage_id,
                order=item_orm.order,
                label=item_orm.label,
                include_translation=item_orm.include_translation,
                include_vocabulary=item_orm.include_vocabulary,
                include_syntax_annotations=item_orm.include_syntax_annotations,
                include_questions=item_orm.include_questions,
                include_variants=item_orm.include_variants,
            )
            for item_orm in item_orms
        ]

        # 6. 최신 상태 도메인 모델 (items id 포함) 반환
        saved_worksheet = self._to_domain(worksheet_orm)
        return saved_worksheet.model_copy(update={"items": saved_items})

    # ─── list ────────────────────────────────────────────────────────────────

    async def list_with_pagination(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        kind: str | None = None,
    ) -> tuple[list[Worksheet], int]:
        """Worksheet 목록 + 전체 개수 (pagination 메타용).

        tenant_id / workspace_id 필터 자동 적용 (BaseRepository._tenant_ctx).
        items 는 lazy 로드하지 않음 (목록은 메타만, 단건 조회로 items 별도 호출).
        정렬: created_at DESC (가장 최근 워크시트 먼저).

        Args:
            limit: 최대 반환 건수 (default 20, max 100 는 라우터에서 강제).
            offset: 건너뛸 건수 (default 0).
            kind: WorksheetKind 문자열 필터. None 이면 전체.

        Returns:
            (worksheets, total_count) — total 은 클라이언트가 다음 페이지 결정용.
            items 는 항상 빈 리스트 (_to_domain 의 update={"items": []} 준수).
        """
        base_filter = [
            WorksheetORM.tenant_id == self._tenant_ctx.tenant_id,
            WorksheetORM.workspace_id == self._tenant_ctx.workspace_id,
        ]
        if kind is not None:
            base_filter.append(WorksheetORM.kind == kind)

        # 전체 개수 쿼리
        count_stmt = (
            select(func.count())
            .select_from(WorksheetORM)
            .where(*base_filter)
        )
        count_result = await self._session.exec(count_stmt)
        total: int = count_result.one()

        # 목록 쿼리 — created_at DESC (최신 먼저)
        list_stmt = (
            select(WorksheetORM)
            .where(*base_filter)
            .order_by(desc(WorksheetORM.created_at))  # type: ignore[arg-type]
            .limit(limit)
            .offset(offset)
        )
        list_result = await self._session.exec(list_stmt)
        worksheets = [self._to_domain(orm) for orm in list_result.all()]

        return worksheets, total

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

        성능 비용 (R-2): caller 가 이미 ``self.get(worksheet_id)`` 로 존재를 확인한
        경우에도 본 메서드 내부에서 부모 worksheet 를 재조회한다 (round-trip 2회).
        W-2 가드 일관성을 위한 의도적 비용 — Phase 2 / 3 에서 필요 시 caller 가
        검증 통과한 parent 를 넘기는 오버로드를 별 ADR 로 도입 검토.

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
            .order_by(WorksheetItemORM.order)  # type: ignore[arg-type]
        )
        result = await self._session.exec(stmt)
        return list(result.all())
