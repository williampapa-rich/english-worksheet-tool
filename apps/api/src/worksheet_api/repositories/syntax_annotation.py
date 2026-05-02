"""SyntaxAnnotationRepository — Phase 0 read-only.

Phase 0 에서는 SyntaxAnnotation write 가 없다 (Phase 1 Tiptap 에디터 이후 도입).
write 메서드를 미리 구현해 Phase 1 진입 시 즉시 사용 가능하도록 한다.

ADR Phase 1 DoD: Tiptap 에디터에서 annotation 작업 결과가 SyntaxAnnotation[] 으로
직렬화되고 DB 에 저장. 그 때 create / delete / list_by_passage 가 사용된다.
"""

from __future__ import annotations

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.annotation import SyntaxAnnotation
from worksheet_api.models.syntax_annotation import SyntaxAnnotationORM
from worksheet_api.repositories.base import BaseRepository
from worksheet_api.repositories.tenant_context import TenantContext


class SyntaxAnnotationRepository(BaseRepository[SyntaxAnnotationORM, SyntaxAnnotation]):
    """SyntaxAnnotation(구문분석 마크) repository.

    Phase 0 에서는 list_by_passage / get 만 API 핸들러가 호출한다.
    write 는 Phase 1 (Tiptap 에디터) 에서 사용 예정.

    Args:
        session: SQLModel AsyncSession.
        tenant_ctx: 현재 요청의 TenantContext.
    """

    _orm_class = SyntaxAnnotationORM
    _domain_class = SyntaxAnnotation

    def __init__(self, session: AsyncSession, tenant_ctx: TenantContext) -> None:
        super().__init__(session, tenant_ctx)

    def _to_orm(self, domain: SyntaxAnnotation) -> SyntaxAnnotationORM:
        """SyntaxAnnotation → SyntaxAnnotationORM 변환.

        JSONB 컬럼 (span, arrow_target_span) 을 model_dump(mode="python") 으로
        nested Pydantic 모델 → dict 변환.
        """
        data = domain.model_dump(mode="python")
        return SyntaxAnnotationORM.model_validate(data)

    def _to_domain(self, orm: SyntaxAnnotationORM) -> SyntaxAnnotation:
        """SyntaxAnnotationORM → SyntaxAnnotation 변환."""
        return SyntaxAnnotation.model_validate(orm)

    # ─── read 메서드 ─────────────────────────────────────────────────────────

    async def list_by_passage(
        self,
        passage_id: uuid.UUID,
        *,
        limit: int = 500,
        offset: int = 0,
    ) -> list[SyntaxAnnotation]:
        """Passage 에 속한 SyntaxAnnotation 목록 조회 (tenant 필터 포함).

        기본 limit 을 500 으로 높게 설정 — 한 지문의 annotation 은 수백 개일 수 있다.

        Args:
            passage_id: 조회 기준 Passage UUID.
            limit: 최대 반환 건수.
            offset: 건너뛸 건수.

        Returns:
            SyntaxAnnotation 리스트 (빈 리스트 가능).
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
