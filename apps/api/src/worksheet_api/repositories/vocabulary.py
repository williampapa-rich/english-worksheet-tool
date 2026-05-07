"""VocabularyRepository — Phase 0 read-only + B1 영속화 + B3 보강 update.

write 단계:
  - B1 (PR #51) — extract 시점 영속화 활성화 (옵션 B).
  - B3 (PR #54) — 보강 라우트의 selective DELETE (`delete_llm_for_passage`).
    ``selected_by=LLM`` 그리고 ``user_edited=False`` 인 row 만 삭제 (USER 항목 보존,
    ADR-0013 D3 / D4 — 사용자 수정 보존).
"""

from __future__ import annotations

import uuid

from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.vocabulary import Vocabulary, VocabularySelectedBy
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

    async def list_user_edited_headwords(
        self,
        passage_id: uuid.UUID,
    ) -> set[str]:
        """``selected_by=USER`` 또는 ``user_edited=True`` 인 항목의 headword set.

        ADR-0013 D3 ``mode=skip_if_user_edited`` 에서 LLM 결과의 충돌 검출에 사용.

        Args:
            passage_id: 조회 기준 Passage UUID.

        Returns:
            ``headword_normalized`` set. 사용자 수정 항목이 없으면 빈 set.
        """
        stmt = (
            select(self._orm_class.headword_normalized)
            .where(self._orm_class.tenant_id == self._tenant_ctx.tenant_id)
            .where(self._orm_class.workspace_id == self._tenant_ctx.workspace_id)
            .where(self._orm_class.passage_id == passage_id)
            .where(
                (self._orm_class.selected_by == VocabularySelectedBy.USER.value)
                | (self._orm_class.user_edited.is_(True))  # type: ignore[union-attr]
            )
        )
        result = await self._session.exec(stmt)
        return set(result.all())

    # ─── write 메서드 — B3 보강 ──────────────────────────────────────────────

    async def delete_llm_for_passage(
        self,
        passage_id: uuid.UUID,
    ) -> int:
        """Passage 의 LLM 산출 (``selected_by=LLM`` 그리고 ``user_edited=False``)
        Vocabulary row 만 DELETE. USER 항목 / 사용자 수정 항목은 보존.

        ADR-0013 D3 ``mode=replace`` / ``skip_if_user_edited`` 에서 LLM 항목만
        교체할 때 사용. tenant 필터 강제.

        Args:
            passage_id: 대상 Passage UUID.

        Returns:
            삭제된 row 수.
        """
        stmt = (
            delete(self._orm_class)
            .where(self._orm_class.tenant_id == self._tenant_ctx.tenant_id)
            .where(self._orm_class.workspace_id == self._tenant_ctx.workspace_id)
            .where(self._orm_class.passage_id == passage_id)
            .where(self._orm_class.selected_by == VocabularySelectedBy.LLM.value)
            .where(self._orm_class.user_edited.is_(False))  # type: ignore[union-attr]
        )
        result = await self._session.exec(stmt)  # type: ignore[call-overload]
        await self._session.flush()
        return result.rowcount if hasattr(result, "rowcount") else 0
