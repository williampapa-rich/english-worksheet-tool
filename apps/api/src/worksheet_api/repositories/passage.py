"""PassageRepository — Passage CRUD + 멀티테넌트 강제.

ADR-0003 §D-3.4: API 레이어가 영속화를 담당하며,
PassageRepository.create() 가 그 진입점이 된다.

write 가능 (create/get/list/delete) — Phase 0 에서 추출 결과 영속화에 사용.
"""

from __future__ import annotations

import uuid

from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.passage import Passage
from worksheet_api.models.passage import PassageORM
from worksheet_api.repositories.base import BaseRepository
from worksheet_api.repositories.tenant_context import TenantContext


class PassageRepository(BaseRepository[PassageORM, Passage]):
    """Passage(영어 지문) CRUD repository.

    ADR-0003 §D-3.4 의 영속화 흐름 진입점.
    BaseRepository 의 sentinel UUID 검증과 tenant 필터가 모든 메서드에 자동 적용된다.

    Args:
        session: SQLModel AsyncSession.
        tenant_ctx: 현재 요청의 TenantContext.
    """

    _orm_class = PassageORM
    _domain_class = Passage

    def __init__(self, session: AsyncSession, tenant_ctx: TenantContext) -> None:
        super().__init__(session, tenant_ctx)

    def _to_orm(self, domain: Passage) -> PassageORM:
        """Passage → PassageORM 변환.

        JSONB 컬럼 (source, topic_tags, paragraphs) 은 model_dump(mode="python") 으로
        nested Pydantic 모델 → dict 로 변환. ADR-0005 §D-5.6.
        """
        data = domain.model_dump(mode="python")
        return PassageORM.model_validate(data)

    def _to_domain(self, orm: PassageORM) -> Passage:
        """PassageORM → Passage 변환.

        from_attributes=True (BaseEntity.model_config) 덕분에 ORM attribute 접근으로
        Pydantic 모델 복원. JSONB dict → SourceMeta 는 Pydantic nested 역직렬화 자동 처리.
        """
        return Passage.model_validate(orm)

    async def list_by_workspace(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Passage]:
        """현재 workspace 의 Passage 목록 조회 (tenant 필터 자동 적용).

        BaseRepository.list() 의 alias — 호출부 가독성을 위해 제공.

        Args:
            limit: 최대 반환 건수.
            offset: 건너뛸 건수.

        Returns:
            Passage 리스트.
        """
        return await self.list(limit=limit, offset=offset)

    async def get_by_id(self, passage_id: uuid.UUID) -> Passage | None:
        """ID 로 단건 조회 (tenant 필터 자동 적용).

        BaseRepository.get() 의 alias — 호출부 가독성을 위해 제공.

        Args:
            passage_id: 조회할 Passage UUID.

        Returns:
            Passage 인스턴스 또는 None.
        """
        return await self.get(passage_id)

    async def update_body(
        self,
        passage_id: uuid.UUID,
        *,
        body_text: str,
        paragraphs: list[str],
    ) -> Passage | None:
        """Passage 의 body_text + paragraphs in-place 갱신 (E1-e).

        ADR-0015 D4 (b) 채택 — Passage 자체에 ``user_edited`` 메타 추가하지 않음.
        UI 가 PATCH 만 허용하므로 LLM 덮어쓰기 충돌 위험 없음.

        body_text 변경 시 character offset 이 깨져 기존 SyntaxAnnotation 이
        무효화 — 라우터에서 annotation 전체 삭제 후 본 메서드 호출 (또는 동일
        트랜잭션 안에서 처리).

        Args:
            passage_id: 갱신 대상 Passage UUID.
            body_text: 새 본문 텍스트.
            paragraphs: 새 paragraph 분할 (빈 리스트 가능 — body_text 단일 paragraph
                의도).

        Returns:
            갱신된 Passage 인스턴스. id 가 없거나 다른 tenant 면 None.
        """
        from sqlmodel import select

        from shared.schemas.common import utc_now

        stmt = (
            select(self._orm_class)
            .where(self._orm_class.id == passage_id)
            .where(self._orm_class.tenant_id == self._tenant_ctx.tenant_id)
            .where(self._orm_class.workspace_id == self._tenant_ctx.workspace_id)
        )
        result = await self._session.exec(stmt)
        orm = result.first()
        if orm is None:
            return None
        orm.body_text = body_text
        orm.paragraphs = list(paragraphs)
        # word_count 자동 재계산 (Passage schema 정합 — 사용자가 수정한 본문 기준)
        orm.word_count = len(body_text.split())
        orm.updated_at = utc_now()
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return self._to_domain(orm)
