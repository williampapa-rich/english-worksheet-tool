"""QAValidationResultRepository — QAValidationResult history CRUD.

ADR-0017 D3-c 하이브리드 구현 (history 테이블 측):
  - Phase 3 변형 생성 라우트가 placeholder row 생성
    (validated_at 설정, passed=False 임시, validator_note="pending").
  - Phase 3 qa-validator agent 활성 시 실제 검증 결과로 갱신.

멀티테넌트 강제:
  question_id FK 를 통해 같은 tenant 의 question 임을 사전 검증한다.
  QAValidationResultORM 자체도 tenant_id / workspace_id 를 직접 보유 (W-2 패턴).
"""

from __future__ import annotations

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.qa_validation_result import QAValidationResult
from worksheet_api.models.qa_validation_result import QAValidationResultORM
from worksheet_api.repositories.base import BaseRepository
from worksheet_api.repositories.tenant_context import TenantContext


class QAValidationResultRepository(BaseRepository[QAValidationResultORM, QAValidationResult]):
    """QAValidationResult(검증 history) CRUD repository.

    Args:
        session: SQLModel AsyncSession.
        tenant_ctx: 현재 요청의 TenantContext.
    """

    _orm_class = QAValidationResultORM
    _domain_class = QAValidationResult

    def __init__(self, session: AsyncSession, tenant_ctx: TenantContext) -> None:
        super().__init__(session, tenant_ctx)

    def _to_orm(self, domain: QAValidationResult) -> QAValidationResultORM:
        """QAValidationResult → QAValidationResultORM 변환."""
        data = domain.model_dump(mode="python")
        return QAValidationResultORM.model_validate(data)

    def _to_domain(self, orm: QAValidationResultORM) -> QAValidationResult:
        """QAValidationResultORM → QAValidationResult 변환."""
        return QAValidationResult.model_validate(orm)

    async def list_by_question(
        self,
        question_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[QAValidationResult]:
        """특정 Question 의 검증 history 조회 (tenant 필터 자동 적용).

        Args:
            question_id: 조회 기준 Question UUID.
            limit: 최대 반환 건수.
            offset: 건너뛸 건수.

        Returns:
            QAValidationResult 리스트 (빈 리스트 가능).
        """
        stmt = (
            select(self._orm_class)
            .where(self._orm_class.tenant_id == self._tenant_ctx.tenant_id)
            .where(self._orm_class.workspace_id == self._tenant_ctx.workspace_id)
            .where(self._orm_class.question_id == question_id)
            .order_by(self._orm_class.validated_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.exec(stmt)
        return [self._to_domain(orm) for orm in result.all()]
