"""TranslationRepository — Phase 0 read-only + B1 영속화 + B3 보강 update.

Phase 0 에서는 Translation 이 추출 파이프라인으로 생성되지 않거나 선택적으로 생성된다
(ADR-0003 PM-5 / PM-6: 실유저 입력은 영어만인 게 default).

write 단계:
  - B1 (PR #51) — extract 시점 영속화 활성화 (옵션 B).
  - B3 (PR #54) — 보강 라우트의 in-place UPDATE (`update_text`). passage_id UNIQUE
    제약 그대로 유지, ``text`` / ``created_by`` / ``updated_at`` 갱신.
"""

from __future__ import annotations

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.common import utc_now
from shared.schemas.translation import Translation, TranslationCreatedBy
from worksheet_api.models.translation import TranslationORM
from worksheet_api.repositories.base import BaseRepository
from worksheet_api.repositories.tenant_context import TenantContext


class TranslationRepository(BaseRepository[TranslationORM, Translation]):
    """Translation(한글 해석) repository.

    Phase 0 에서는 get / get_by_passage 만 API 핸들러가 호출한다.
    write 메서드는 Phase 2 진입 시 사용 예정 — 미리 구현.

    Args:
        session: SQLModel AsyncSession.
        tenant_ctx: 현재 요청의 TenantContext.
    """

    _orm_class = TranslationORM
    _domain_class = Translation

    def __init__(self, session: AsyncSession, tenant_ctx: TenantContext) -> None:
        super().__init__(session, tenant_ctx)

    def _to_domain(self, orm: TranslationORM) -> Translation:
        """TranslationORM → Translation 변환."""
        return Translation.model_validate(orm)

    # ─── read 메서드 ─────────────────────────────────────────────────────────

    async def get_by_passage(self, passage_id: uuid.UUID) -> Translation | None:
        """Passage 에 속한 Translation 단건 조회 (1:1 관계, tenant 필터 포함).

        DB 레벨 UNIQUE(passage_id) 제약으로 결과는 항상 0 또는 1건.

        Args:
            passage_id: 조회 기준 Passage UUID.

        Returns:
            Translation 인스턴스 또는 None.
        """
        stmt = (
            select(self._orm_class)
            .where(self._orm_class.tenant_id == self._tenant_ctx.tenant_id)
            .where(self._orm_class.workspace_id == self._tenant_ctx.workspace_id)
            .where(self._orm_class.passage_id == passage_id)
        )
        result = await self._session.exec(stmt)
        orm = result.first()
        return self._to_domain(orm) if orm is not None else None

    # ─── write 메서드 — B3 보강 ──────────────────────────────────────────────

    async def update_text(
        self,
        passage_id: uuid.UUID,
        *,
        text: str,
        created_by: TranslationCreatedBy,
    ) -> Translation | None:
        """기존 Translation 의 ``text`` / ``created_by`` / ``updated_at`` in-place 갱신.

        Translation schema docstring (PM 결정 D-2): 사용자가 LLM 결과를 수정하면
        ``text`` 를 in-place 업데이트 + ``created_by`` 변경 + ``updated_at`` 갱신.
        **이전 버전 보존 없음**.

        ADR-0013 D2 의 ``mode=replace`` 가 사용. tenant 필터 포함 — cross-tenant
        update 불가.

        Args:
            passage_id: 갱신 대상 Translation 의 passage_id.
            text: 새 해석 본문.
            created_by: 갱신 후 created_by 값. LLM 보강 시 ``LLM``, 사용자 수정 시
                ``USER``.

        Returns:
            갱신된 Translation 인스턴스. passage_id 에 해당하는 row 가 없으면 None.
        """
        stmt = (
            select(self._orm_class)
            .where(self._orm_class.tenant_id == self._tenant_ctx.tenant_id)
            .where(self._orm_class.workspace_id == self._tenant_ctx.workspace_id)
            .where(self._orm_class.passage_id == passage_id)
        )
        result = await self._session.exec(stmt)
        orm = result.first()
        if orm is None:
            return None
        orm.text = text
        orm.created_by = created_by.value
        orm.updated_at = utc_now()
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return self._to_domain(orm)
