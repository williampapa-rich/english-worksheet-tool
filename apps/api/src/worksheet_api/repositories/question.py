"""QuestionRepository — Question CRUD + passage_id FK 검증.

ADR-0003 §D-3.4: Passage 영속화 직후 Question 영속화 순서 보장.

write 가능 (create/get/list/delete).
``create()`` 에서 passage_id FK 존재 여부를 사전 검증해 명확한 에러 메시지 제공.
"""

from __future__ import annotations

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.question import Question
from worksheet_api.models.passage import PassageORM
from worksheet_api.models.question import QuestionORM
from worksheet_api.repositories.base import BaseRepository
from worksheet_api.repositories.tenant_context import TenantContext


class QuestionRepository(BaseRepository[QuestionORM, Question]):
    """Question(문제) CRUD repository.

    Args:
        session: SQLModel AsyncSession.
        tenant_ctx: 현재 요청의 TenantContext.
    """

    _orm_class = QuestionORM
    _domain_class = Question

    def __init__(self, session: AsyncSession, tenant_ctx: TenantContext) -> None:
        super().__init__(session, tenant_ctx)

    async def create(self, domain: Question) -> Question:
        """sentinel 검증 + passage_id FK 존재 확인 + insert.

        DB FK 제약이 있어도 명확한 에러 메시지를 위해 사전 검증한다.
        같은 tenant 의 Passage 가 존재하지 않으면 ValueError.

        Args:
            domain: 저장할 Question 도메인 모델.

        Returns:
            저장된 Question (id, created_at 포함).

        Raises:
            ValueError: sentinel UUID 누수, tenant 불일치, 또는
                passage_id 에 해당하는 Passage 가 같은 tenant 에 존재하지 않을 때.
        """
        # BaseRepository 의 sentinel + tenant 검증
        self._validate_tenant_fields(domain)

        # passage_id FK 사전 검증 — 같은 tenant 의 Passage 가 있어야 한다
        await self._assert_passage_exists(domain.passage_id)

        # derived_from_question_id 가 있으면 같은 tenant 의 Question 이 있어야 한다
        if domain.derived_from_question_id is not None:
            await self._assert_question_exists(domain.derived_from_question_id)

        orm = self._to_orm(domain)
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return self._to_domain(orm)

    async def _assert_passage_exists(self, passage_id: uuid.UUID) -> None:
        """같은 tenant/workspace 의 Passage 가 존재하는지 검증.

        Args:
            passage_id: 확인할 Passage UUID.

        Raises:
            ValueError: 해당 Passage 가 존재하지 않거나 다른 tenant 소유.
        """
        stmt = (
            select(PassageORM)
            .where(PassageORM.id == passage_id)
            .where(PassageORM.tenant_id == self._tenant_ctx.tenant_id)
            .where(PassageORM.workspace_id == self._tenant_ctx.workspace_id)
        )
        result = await self._session.exec(stmt)
        if result.first() is None:
            raise ValueError(
                f"passage_id={passage_id} 에 해당하는 Passage 가 "
                f"tenant_id={self._tenant_ctx.tenant_id} / "
                f"workspace_id={self._tenant_ctx.workspace_id} 에 존재하지 않는다. "
                f"Passage 를 먼저 저장하거나, passage_id 를 확인하라."
            )

    async def _assert_question_exists(self, question_id: uuid.UUID) -> None:
        """같은 tenant/workspace 의 Question 이 존재하는지 검증 (variant 참조용).

        Args:
            question_id: 확인할 Question UUID (derived_from_question_id).

        Raises:
            ValueError: 해당 Question 이 존재하지 않거나 다른 tenant 소유.
        """
        stmt = (
            select(QuestionORM)
            .where(QuestionORM.id == question_id)
            .where(QuestionORM.tenant_id == self._tenant_ctx.tenant_id)
            .where(QuestionORM.workspace_id == self._tenant_ctx.workspace_id)
        )
        result = await self._session.exec(stmt)
        if result.first() is None:
            raise ValueError(
                f"derived_from_question_id={question_id} 에 해당하는 Question 이 "
                f"tenant_id={self._tenant_ctx.tenant_id} 에 존재하지 않는다."
            )

    def _to_orm(self, domain: Question) -> QuestionORM:
        """Question → QuestionORM 변환.

        JSONB 컬럼 (choices, choice_matrix, inline_choices 등) 을
        model_dump(mode="python") 으로 dict 변환.
        """
        data = domain.model_dump(mode="python")
        return QuestionORM.model_validate(data)

    def _to_domain(self, orm: QuestionORM) -> Question:
        """QuestionORM → Question 변환."""
        return Question.model_validate(orm)

    async def list_by_passage(
        self,
        passage_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Question]:
        """특정 Passage 에 속한 Question 목록 조회 (tenant 필터 자동 적용).

        Args:
            passage_id: 조회 기준 Passage UUID.
            limit: 최대 반환 건수.
            offset: 건너뛸 건수.

        Returns:
            Question 리스트 (빈 리스트 가능).
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
