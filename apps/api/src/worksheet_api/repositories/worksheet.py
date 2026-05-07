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
from typing import Any

from sqlalchemy import desc, func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.worksheet import Worksheet, WorksheetItem
from worksheet_api.models.base import _utc_now
from worksheet_api.models.passage import PassageORM
from worksheet_api.models.worksheet import WorksheetItemORM, WorksheetORM
from worksheet_api.repositories.base import BaseRepository
from worksheet_api.repositories.tenant_context import TenantContext

# update_meta 허용 필드 (R-3 — 호출 시점 재생성 회피, 모듈 레벨 상수).
_ALLOWED_META_FIELDS: frozenset[str] = frozenset({
    "title", "subtitle", "kind", "template_id", "orientation",
    "instruction", "branding", "school", "grade", "exam_date", "time_limit",
})

# WorksheetORM 에서 nullable=False 인 메타 필드 (W-1 — null patch 차단 대상).
# WorksheetORM 컬럼 정의의 nullable=False 와 1:1 동기화 — 변경 시 함께 수정.
_NONNULL_META_FIELDS: frozenset[str] = frozenset({
    "title", "kind", "template_id", "orientation",
})


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

    # ─── update ─────────────────────────────────────────────────────────────

    async def update_meta(
        self,
        worksheet_id: uuid.UUID,
        patch: dict[str, Any],
    ) -> Worksheet | None:
        """Worksheet 의 메타 필드만 부분 수정. items 는 건드리지 않음.

        허용 패치 필드: title / subtitle / kind / template_id / orientation /
        instruction / branding / school / grade / exam_date / time_limit.
        ``patch`` 에 ``items`` 키가 포함되어 있으면 ValueError 로 명시 차단한다.

        흐름:
          1. ``items`` 키 포함 여부 사전 차단 (도메인 정책 강제).
          2. NOT NULL 메타 필드에 ``None`` 설정 시도 차단 (W-1 — IntegrityError 500 회피).
          3. ``self._get_orm()`` 으로 tenant_id + workspace_id 필터를 적용해 ORM
             인스턴스 조회 (cross-tenant 이면 None 반환). ``BaseRepository.get()`` 은
             도메인 모델을 반환하므로 ORM 직접 setattr 패턴에 부적합 (R-1).
          4. 허용 필드만 ORM 에 직접 패치 (setattr).
          5. updated_at 갱신 (R-2 (a) — PATCH 한정 부분 fix, ORM-wide 자동 갱신 별 ADR).
          6. session.flush() 후 refresh → 최신 상태 반환.

        호출 전제: 호출자가 ``async with session.begin():`` 컨텍스트 안에 있어야 한다.
        commit 은 caller 책임.

        Args:
            worksheet_id: 수정할 Worksheet UUID.
            patch: 수정할 필드 dict (model_dump(exclude_unset=True) 로 set 된 필드만).
                ``items`` 키 포함 시 ValueError.

        Returns:
            업데이트된 Worksheet (items 는 빈 리스트 — 단건 GET 라우터에서 별도 join).
            worksheet_id 가 없거나 cross-tenant 이면 None.

        Raises:
            ValueError: patch 에 ``items`` 키가 포함된 경우 (명시 차단) 또는
                NOT NULL 메타 필드를 ``None`` 으로 설정하려는 경우 (W-1).
        """
        # 1. items 키 사전 차단 (A2-b 별 라우트 정책 강제)
        if "items" in patch:
            raise ValueError(
                "update_meta 는 메타 필드만 수정합니다. "
                "items 변경은 POST/PATCH/DELETE /worksheets/{id}/items 를 사용하세요 (A2-b 예정)."
            )

        # 2. NOT NULL 메타 필드에 None 설정 시도 차단 (W-1)
        #    WorksheetUpdateRequest 의 None default 는 "변경 없음" 을 의미하며 (R-4),
        #    명시적 null 전송은 NOT NULL 컬럼 위반 → IntegrityError 500 으로 노출되므로
        #    Repository 레이어에서 명시 차단해 422 로 매핑한다.
        for field in _NONNULL_META_FIELDS:
            if field in patch and patch[field] is None:
                raise ValueError(
                    f"'{field}' 필드는 null 로 설정할 수 없습니다 (NOT NULL 메타 필드). "
                    f"변경하지 않으려면 요청 body 에서 키를 제외하세요."
                )

        # 3. tenant 검증 포함 단건 조회 (cross-tenant → None)
        #    self._get_orm() 으로 ORM 인스턴스 직접 반환 — setattr 패치를 위해.
        #    BaseRepository.get() 은 도메인 모델로 변환하므로 setattr 패턴에 부적합 (R-1).
        orm = await self._get_orm(worksheet_id)
        if orm is None:
            return None

        # 4. 허용 필드 패치 — branding 은 Pydantic 모델 또는 dict 모두 수용
        for field, value in patch.items():
            if field not in _ALLOWED_META_FIELDS:
                continue  # 미래 확장 필드는 silently 무시 (items 는 위에서 이미 차단)
            # branding 이 Pydantic 모델로 넘어온 경우 dict 로 직렬화 (JSONB 컬럼 호환)
            if field == "branding" and hasattr(value, "model_dump"):
                value = value.model_dump(mode="python")
            setattr(orm, field, value)

        # 5. updated_at 갱신 (R-2 (a) — PATCH 한정 부분 fix)
        #    ORM 의 onupdate 훅이 없는 현재 구조의 미봉책. ORM-wide 자동 갱신은 별 ADR.
        orm.updated_at = _utc_now()

        # 6. flush + refresh → 최신 DB 상태 반영
        await self._session.flush()
        await self._session.refresh(orm)
        return self._to_domain(orm)

    async def _get_orm(self, worksheet_id: uuid.UUID) -> WorksheetORM | None:
        """tenant_id + workspace_id 필터를 포함한 WorksheetORM 단건 조회.

        BaseRepository.get() 은 도메인 모델로 변환하지만, update_meta 는
        ORM 인스턴스에 직접 setattr 해야 하므로 ORM 레벨 조회를 별도 제공한다.

        Args:
            worksheet_id: 조회할 Worksheet UUID.

        Returns:
            WorksheetORM 인스턴스 또는 None (not found 또는 cross-tenant).
        """
        stmt = (
            select(WorksheetORM)
            .where(WorksheetORM.id == worksheet_id)
            .where(WorksheetORM.tenant_id == self._tenant_ctx.tenant_id)
            .where(WorksheetORM.workspace_id == self._tenant_ctx.workspace_id)
        )
        result = await self._session.exec(stmt)
        return result.first()

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
