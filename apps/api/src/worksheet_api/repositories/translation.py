"""TranslationRepository — Phase 0 read-only.

Phase 0 에서는 Translation 이 추출 파이프라인으로 생성되지 않거나 선택적으로 생성된다
(ADR-0003 PM-5 / PM-6: 실유저 입력은 영어만인 게 default). write 는 Phase 2 에서 도입.

판단 근거 (task-breakdown §2 P0-6):
  "vocabulary / translation / syntax_annotation 은 Phase 0 에서 read-only 가 안전 —
  write 는 Phase 2/1 에서."

write 메서드 (create/update/delete) 도 미리 구현해 두어, Phase 2 에서 API 핸들러가
즉시 사용할 수 있도록 한다. Phase 0 API 핸들러는 아직 이 메서드를 호출하지 않는다.
"""

from __future__ import annotations

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.translation import Translation
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
