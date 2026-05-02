"""LlmUsageLogRepository — write 전용, tenant_id nullable 허용.

ADR-0003 PM-4:
  - LLM 호출 로그는 시스템 호출 또는 pre-tenant 호출도 기록해야 하므로
    ``tenant_id`` / ``workspace_id`` 가 nullable.
  - ``WorkspaceScopedORMBase`` 상속이 아닌 ``LlmUsageLogORM`` 독립 모델.
  - sentinel UUID 검증 로직 **없음** — 이 테이블은 멀티테넌트 격리 대상이 아니라
    운영/비용 분석용.

schema 갭 (architect 처리 필요):
  현재 ``LlmUsageLog`` Pydantic 도메인 모델이 ``shared/schemas/`` 에 존재하지 않는다.
  본 PR 에서는 ORM 직접 받는 형태로 ``insert(orm: LlmUsageLogORM)`` 시그니처를 채택.
  architect 가 후속 PR 에서 ``shared/schemas/llm_usage.py`` 를 추가하면 그 때
  ``_to_domain`` / ``_to_orm`` 변환을 추가한다.

  참조: task-breakdown P0-6 산출물 §7 "schema 갭 명시"
"""

from __future__ import annotations

from sqlmodel.ext.asyncio.session import AsyncSession

from worksheet_api.models.llm_usage_log import LlmUsageLogORM
from worksheet_api.repositories.tenant_context import TenantContext


class LlmUsageLogRepository:
    """LLM 사용 로그 write 전용 repository.

    ``BaseRepository`` 를 상속하지 않는다:
      - ``LlmUsageLogORM`` 의 ``tenant_id`` / ``workspace_id`` 가 nullable (PM-4).
      - 멀티테넌트 필터 / sentinel 검증 로직이 여기에는 적합하지 않다.
      - P0-2b (LLM DB sink) 가 이 클래스를 직접 사용.

    Args:
        session: SQLModel AsyncSession.
        tenant_ctx: Optional — 시스템 호출 / pre-tenant 호출에서는 None 허용.
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_ctx: TenantContext | None = None,
    ) -> None:
        self._session = session
        self._tenant_ctx = tenant_ctx

    async def insert(self, orm: LlmUsageLogORM) -> None:
        """LLM 호출 로그 1건 삽입.

        commit 은 caller 책임 (BaseRepository 와 동일 원칙).

        현재 시그니처는 ORM 직접 받는 형태다. ``shared/schemas/llm_usage.py`` 가
        architect PR 에서 추가되면 domain 모델을 받는 오버로드로 교체.

        Args:
            orm: 삽입할 LlmUsageLogORM 인스턴스. tenant_id/workspace_id 는 nullable.
        """
        self._session.add(orm)
        await self._session.flush()

    async def insert_from_dict(self, log_data: dict) -> LlmUsageLogORM:
        """dict 로부터 LlmUsageLogORM 생성 후 삽입.

        P0-2b (LLM DB sink) 에서 StructuredLLMResult 의 usage 데이터를 dict 로
        전달받는 경우를 위한 편의 메서드.

        Args:
            log_data: LlmUsageLogORM 필드 값 dict. tenant_id/workspace_id 는 옵셔널.

        Returns:
            삽입된 LlmUsageLogORM 인스턴스 (flush 후).
        """
        # tenant_ctx 가 있으면 tenant_id / workspace_id 자동 채움 (없으면 None 유지)
        if self._tenant_ctx is not None:
            log_data.setdefault("tenant_id", self._tenant_ctx.tenant_id)
            log_data.setdefault("workspace_id", self._tenant_ctx.workspace_id)

        orm = LlmUsageLogORM.model_validate(log_data)
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return orm
