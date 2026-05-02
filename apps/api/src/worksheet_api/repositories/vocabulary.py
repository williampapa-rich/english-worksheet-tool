"""VocabularyRepository — Phase 0 read-only.

Phase 0 에서는 Vocabulary 가 선택적으로만 추출된다 (ADR-0003 PM-5 / PM-6).
write 는 Phase 2 에서 도입 예정.

write 메서드를 미리 구현해 Phase 2 진입 시 즉시 사용 가능하도록 한다.
"""

from __future__ import annotations

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.vocabulary import Vocabulary
from worksheet_api.models.vocabulary import VocabularyORM
from worksheet_api.repositories.base import BaseRepository
from worksheet_api.repositories.tenant_context import TenantContext


class VocabularyRepository(BaseRepository[VocabularyORM, Vocabulary]):
    """Vocabulary(어휘) repository.

    Phase 0 에서는 list_by_passage / get 만 API 핸들러가 호출한다.
    write 는 Phase 2 에서 사용 예정.

    Args:
        session: SQLModel AsyncSession.
        tenant_ctx: 현재 요청의 TenantContext.
    """

    _orm_class = VocabularyORM
    _domain_class = Vocabulary

    def __init__(self, session: AsyncSession, tenant_ctx: TenantContext) -> None:
        super().__init__(session, tenant_ctx)

    def _to_domain(self, orm: VocabularyORM) -> Vocabulary:
        """VocabularyORM → Vocabulary 변환."""
        return Vocabulary.model_validate(orm)

    # ─── read 메서드 ─────────────────────────────────────────────────────────

    async def list_by_passage(
        self,
        passage_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Vocabulary]:
        """Passage 에 속한 Vocabulary 목록 조회 (tenant 필터 포함).

        Args:
            passage_id: 조회 기준 Passage UUID.
            limit: 최대 반환 건수.
            offset: 건너뛸 건수.

        Returns:
            Vocabulary 리스트 (빈 리스트 가능).
        """
        stmt = (
            select(self._orm_class)
            .where(self._orm_class.tenant_id == self._tenant_ctx.tenant_id)
            .where(self._orm_class.workspace_id == self._tenant_ctx.workspace_id)
            .where(self._orm_class.passage_id == passage_id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.exec(stmt)
        return [self._to_domain(orm) for orm in result.all()]
