"""BaseRepository — Generic + async + commit-free (ADR-0005 §D-5.3).

설계 원칙:
  - ``BaseRepository[TORM, TDomain]`` generic — ORM 클래스와 도메인 Pydantic 모델을
    타입 파라미터로 받는다. 서브클래스는 클래스 변수 ``_orm_class`` / ``_domain_class`` 를
    선언해 bind 한다.
  - **commit 금지** — ``session.flush()`` 까지만. commit 은 API 핸들러의
    ``async with session.begin():`` 이 담당. ADR-0003 §D-3.4 재확인.
  - **tenant_id + workspace_id 자동 필터** — ``TenantContext`` 를 생성자에서 주입.
    모든 query/write 에 필터를 강제하므로 구조적으로 누락 불가.
  - **sentinel UUID 이중 방어** (ADR-0003 §D-3.6, ADR-0005 §D-5.2):
    - extractor 출력의 ``tenant_id == SENTINEL_UUID`` 를 create/update 시점에 감지 → raise.
    - context 와 domain 의 tenant_id 불일치 → raise.

변환 경계 (ADR-0005 §D-5.5):
  ``_to_orm`` / ``_to_domain`` 은 BaseRepository 에 기본 구현이 있고,
  복잡한 변환이 필요한 서브클래스는 override 한다.
"""

from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from pydantic import BaseModel
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from worksheet_api.models.base import SENTINEL_UUID
from worksheet_api.repositories.tenant_context import TenantContext

# ORM 클래스 (SQLModel table=True)
TORM = TypeVar("TORM", bound=SQLModel)
# 도메인 Pydantic 모델 (shared/schemas/)
TDomain = TypeVar("TDomain", bound=BaseModel)


class BaseRepository(Generic[TORM, TDomain]):  # noqa: UP046
    """멀티테넌트 강제 + 변환 책임의 generic repository base.

    트랜잭션 경계는 caller (API 핸들러) 가 관리 — repository 는 commit 하지 않는다.

    서브클래스 선언 예:
    ::

        class PassageRepository(BaseRepository[PassageORM, Passage]):
            _orm_class = PassageORM
            _domain_class = Passage

    Args:
        session: SQLModel AsyncSession. commit 권한은 caller 가 가짐.
        tenant_ctx: 현재 요청의 TenantContext (ADR-0003 §D-3.6).
    """

    # 서브클래스가 반드시 선언해야 함. 누락 시 create/get/list/delete 호출 시 AttributeError.
    _orm_class: type[TORM]
    _domain_class: type[TDomain]

    def __init__(self, session: AsyncSession, tenant_ctx: TenantContext) -> None:
        self._session = session
        self._tenant_ctx = tenant_ctx

    # ─── sentinel + tenant 검증 ──────────────────────────────────────────────

    def _validate_tenant_fields(self, domain: TDomain) -> None:
        """sentinel UUID 누수 방어 + tenant_id / workspace_id 일치 검증.

        ADR-0005 §D-5.2 이중 방어:
          1. domain 의 tenant_id 가 SENTINEL_UUID 이면 API 핸들러가 model_copy 를
             누락한 코드 버그 → ValueError.
          2. domain 의 tenant_id 가 context 와 다르면 크로스-테넌트 시도 → ValueError.
          3. workspace_id 도 동일하게 검증.

        ``tenant_id`` / ``workspace_id`` 속성이 없는 도메인 모델 (예: 미래 확장 모델) 은
        검증을 건너뛴다 (hasattr 체크).

        Args:
            domain: write 하려는 도메인 모델 인스턴스.

        Raises:
            ValueError: sentinel UUID 누수 또는 tenant/workspace_id 불일치.
        """
        entity_name = type(domain).__name__

        if hasattr(domain, "tenant_id"):
            tenant_id: uuid.UUID = domain.tenant_id  # type: ignore[assignment]

            if tenant_id == SENTINEL_UUID:
                raise ValueError(
                    f"sentinel UUID 가 repository write 까지 누수됐다. "
                    f'API 핸들러에서 model_copy(update={{"tenant_id": tenant_ctx.tenant_id}}) '
                    f"를 누락한 것으로 보인다. "
                    f"entity={entity_name}"
                )
            if tenant_id != self._tenant_ctx.tenant_id:
                raise ValueError(
                    f"tenant_id 불일치: domain.tenant_id={tenant_id} "
                    f"vs context.tenant_id={self._tenant_ctx.tenant_id}. "
                    f"크로스-테넌트 write 시도 또는 API 핸들러의 model_copy 버그. "
                    f"entity={entity_name}"
                )

        if hasattr(domain, "workspace_id"):
            workspace_id: uuid.UUID = domain.workspace_id  # type: ignore[assignment]

            if workspace_id == SENTINEL_UUID:
                raise ValueError(
                    f"sentinel UUID (workspace_id) 가 repository write 까지 누수됐다. "
                    f"entity={entity_name}"
                )
            if workspace_id != self._tenant_ctx.workspace_id:
                raise ValueError(
                    f"workspace_id 불일치: domain.workspace_id={workspace_id} "
                    f"vs context.workspace_id={self._tenant_ctx.workspace_id}. "
                    f"entity={entity_name}"
                )

    # ─── CRUD ────────────────────────────────────────────────────────────────

    async def create(self, domain: TDomain) -> TDomain:
        """sentinel UUID 검증 + ORM 변환 + insert (flush 까지).

        commit 은 caller 책임.

        Args:
            domain: 저장할 도메인 모델. tenant_id / workspace_id 가 실제 값이어야 한다.

        Returns:
            DB flush 후 최신 상태의 도메인 모델 (id, created_at 포함).

        Raises:
            ValueError: sentinel UUID 누수 또는 tenant_id / workspace_id 불일치.
        """
        self._validate_tenant_fields(domain)
        orm = self._to_orm(domain)
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return self._to_domain(orm)

    async def get(self, entity_id: uuid.UUID) -> TDomain | None:
        """tenant_id + workspace_id 필터를 포함한 단건 조회.

        Args:
            entity_id: 조회할 엔티티 UUID.

        Returns:
            도메인 모델 인스턴스 또는 None (not found 또는 다른 tenant 소유).
        """
        stmt = (
            select(self._orm_class)
            .where(self._orm_class.id == entity_id)  # type: ignore[attr-defined]
            .where(self._orm_class.tenant_id == self._tenant_ctx.tenant_id)  # type: ignore[attr-defined]
            .where(self._orm_class.workspace_id == self._tenant_ctx.workspace_id)  # type: ignore[attr-defined]
        )
        result = await self._session.exec(stmt)
        orm = result.first()
        return self._to_domain(orm) if orm is not None else None

    async def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TDomain]:
        """tenant_id + workspace_id 필터를 포함한 목록 조회.

        Args:
            limit: 최대 반환 건수 (기본 100).
            offset: 건너뛸 건수 (기본 0).

        Returns:
            도메인 모델 리스트 (빈 리스트 가능).
        """
        stmt = (
            select(self._orm_class)
            .where(self._orm_class.tenant_id == self._tenant_ctx.tenant_id)  # type: ignore[attr-defined]
            .where(self._orm_class.workspace_id == self._tenant_ctx.workspace_id)  # type: ignore[attr-defined]
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.exec(stmt)
        return [self._to_domain(orm) for orm in result.all()]

    async def delete(self, entity_id: uuid.UUID) -> bool:
        """tenant 일치 검증 후 delete.

        Args:
            entity_id: 삭제할 엔티티 UUID.

        Returns:
            True 면 삭제 성공, False 면 not found (또는 다른 tenant 소유).
        """
        orm = await self._session.get(self._orm_class, entity_id)
        if orm is None:
            return False
        # 다른 tenant 소유인지 확인
        if getattr(orm, "tenant_id", None) != self._tenant_ctx.tenant_id:
            return False
        if getattr(orm, "workspace_id", None) != self._tenant_ctx.workspace_id:
            return False
        await self._session.delete(orm)
        await self._session.flush()
        return True

    # ─── 변환 헬퍼 (서브클래스가 override 가능) ─────────────────────────────

    def _to_orm(self, domain: TDomain) -> TORM:
        """도메인 Pydantic 모델 → SQLModel ORM 객체 변환.

        ADR-0005 §D-5.5: ``model_dump(mode="python")`` 으로 nested 객체 (JSONB 컬럼) 를
        dict 로 변환해 ORM 에 전달.

        서브클래스에서 특수 변환이 필요하면 override.

        Args:
            domain: 변환할 도메인 모델 인스턴스.

        Returns:
            SQLModel ORM 인스턴스 (session 에 add 전 상태).
        """
        return self._orm_class.model_validate(domain.model_dump(mode="python"))

    def _to_domain(self, orm: TORM) -> TDomain:
        """SQLModel ORM 객체 → 도메인 Pydantic 모델 변환.

        ADR-0005 §D-5.5: ``from_attributes=True`` (BaseEntity.model_config) 덕분에
        ORM 인스턴스를 그대로 전달해도 attribute 접근으로 모델 복원.

        Args:
            orm: SQLModel ORM 인스턴스.

        Returns:
            도메인 Pydantic 모델 인스턴스.
        """
        return self._domain_class.model_validate(orm)
