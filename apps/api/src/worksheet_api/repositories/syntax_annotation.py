"""SyntaxAnnotationRepository — P1-5 replace-all + list_by_passage.

Phase 0 에서는 read-only 였고, P1-5 (Annotation DB 영속화 + API) 에서 write 활성화.

**replace_all 설계 결정 (P1-5 ADR-Lite)**:
  replace-all 채택. 에디터의 저장 동작이 본질적으로 "현 상태로 갈아엎기" 이며,
  batch upsert 는 부분 갱신이 필요한 경우에만 의미가 있다 (현재 없음).
  단순성 우선, 동시성 문제는 "MVP 단일 사용자 가정" 으로 Phase 4 OAuth 와 함께 처리.

ADR Phase 1 DoD: Tiptap 에디터에서 annotation 작업 결과가 SyntaxAnnotation[] 으로
직렬화되고 DB 에 저장. replace_all / list_by_passage 가 사용된다.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.annotation import SyntaxAnnotation
from worksheet_api.models.syntax_annotation import SyntaxAnnotationORM
from worksheet_api.repositories.base import BaseRepository
from worksheet_api.repositories.tenant_context import TenantContext


class SyntaxAnnotationRepository(BaseRepository[SyntaxAnnotationORM, SyntaxAnnotation]):
    """SyntaxAnnotation(구문분석 마크) repository.

    P1-5 에서 replace_all (write) 활성화.
    list_by_passage (read) 는 Phase 0 에서 이미 구현됨.

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

    # ─── write 메서드 ────────────────────────────────────────────────────────

    async def replace_all(
        self,
        passage_id: uuid.UUID,
        annotations: list[SyntaxAnnotation],
    ) -> list[SyntaxAnnotation]:
        """Passage 의 annotation 을 전체 교체 (replace-all).

        **설계 결정 (P1-5 ADR-Lite)**:
          에디터 저장 = "현 상태로 갈아엎기" 이므로 replace-all 이 자연스럽다.
          batch upsert 는 부분 갱신 필요 시에만 의미 — 현재 요건 없음.
          동시성 (다중 에디터 세션) 은 MVP 단일 사용자 가정으로 Phase 4 OAuth 와 함께 처리.

        트랜잭션 경계: caller (API 핸들러) 의 ``async with session.begin()`` 이 담당.
        본 메서드는 flush 만, commit 금지.

        Args:
            passage_id: 대상 Passage UUID.
            annotations: 새로 저장할 SyntaxAnnotation 리스트 (빈 리스트 = 전체 삭제).
                각 항목의 tenant_id / workspace_id / passage_id 는 현재 tenant_ctx 와
                일치해야 한다 (sentinel UUID 검증 포함).

        Returns:
            저장 후 flush 된 SyntaxAnnotation 리스트 (DB 부여 id 포함).

        Raises:
            ValueError: sentinel UUID 누수 또는 tenant / workspace / passage_id 불일치.
        """
        # 1. 기존 annotation 전체 삭제 (tenant + passage 필터 강제)
        del_stmt = (
            delete(SyntaxAnnotationORM)
            .where(SyntaxAnnotationORM.tenant_id == self._tenant_ctx.tenant_id)
            .where(SyntaxAnnotationORM.workspace_id == self._tenant_ctx.workspace_id)
            .where(SyntaxAnnotationORM.passage_id == passage_id)
        )
        await self._session.exec(del_stmt)  # type: ignore[call-overload]

        # 2. 새 annotation insert
        saved: list[SyntaxAnnotation] = []
        for ann in annotations:
            # passage_id 일치 검증 — passage 에 속하지 않는 annotation 거부
            if ann.passage_id != passage_id:
                raise ValueError(
                    f"annotation.passage_id ({ann.passage_id}) 가 "
                    f"요청 passage_id ({passage_id}) 와 다릅니다."
                )
            saved_ann = await self.create(ann)
            saved.append(saved_ann)

        return saved

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
