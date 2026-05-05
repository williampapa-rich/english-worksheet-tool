"""UserPreferenceRepository — 사용자 환경설정 CRUD + 멀티테넌트 강제.

ADR-0009 §D1 / §D4:
  - 단일 ``user_preferences`` 테이블. dot-notation key + JSONB value.
  - 모든 쿼리에 ``tenant_id`` + ``user_id`` 필터 강제.
  - ``workspace_id`` 는 인자로 받음 (None 허용 — 테넌트 전역 vs 워크스페이스별 분기).
  - upsert 는 PostgreSQL dialect insert + ``on_conflict_do_update`` + ``index_elements``
    + ``index_where`` 로 partial unique index 추론.

설계:
  - BaseRepository 를 상속하지 않는다 — workspace_id 가 Optional 이어서 BaseRepository
    의 ``_validate_tenant_fields`` (workspace_id 강제) 와 호환되지 않음. 대신 동일
    sentinel / tenant 검증 로직을 직접 구현.
  - ``get`` / ``upsert`` 만 제공 (Phase 1 DoD 범위).
  - commit 금지 — ``session.flush()`` 까지만. commit 은 caller 책임 (ADR-0003 §D-3.4).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from worksheet_api.models.base import SENTINEL_UUID
from worksheet_api.models.user_preference import UserPreferenceORM
from worksheet_api.repositories.tenant_context import TenantContext


class UserPreferenceRepository:
    """사용자 환경설정 CRUD repository.

    멀티테넌트 강제:
      모든 메서드에 ``tenant_id`` + ``user_id`` 필터 자동 적용.
      ``user_id`` 는 ``TenantContext.user_id`` 에서 주입 — caller 가 임의 값을 넘길 수 없음.

    workspace_id 정책:
      - None → 테넌트 전역 옵션 (``workspace_id IS NULL`` partial index 사용).
      - UUID → 워크스페이스별 옵션 (``workspace_id IS NOT NULL`` partial index 사용).

    upsert 정책 (ADR-0009 §D4):
      두 개의 partial unique index 를 각각 ``index_where`` 로 명시해 PostgreSQL 이
      올바른 인덱스를 추론하도록 한다. workspace_id None / NOT NULL 분기 필수.

    Args:
        session: SQLModel AsyncSession. commit 권한은 caller 가 가짐.
        tenant_ctx: 현재 요청의 TenantContext (tenant_id + user_id 제공).
    """

    def __init__(self, session: AsyncSession, tenant_ctx: TenantContext) -> None:
        self._session = session
        self._tenant_ctx = tenant_ctx

    @property
    def _tenant_id(self) -> uuid.UUID:
        return self._tenant_ctx.tenant_id

    @property
    def _user_id(self) -> uuid.UUID:
        """user_id 는 TenantContext 에서 주입. None 이면 sentinel 에 준하는 에러."""
        uid = self._tenant_ctx.user_id
        if uid is None:
            raise ValueError(
                "TenantContext.user_id 가 None 입니다. "
                "get_tenant_context() 가 MVP_USER_ID 를 주입하지 않은 것으로 보입니다. "
                "ADR-0009 §D5 참조."
            )
        if uid == SENTINEL_UUID:
            raise ValueError(
                "TenantContext.user_id 가 sentinel UUID 입니다. "
                "환경변수 MVP_USER_ID 를 올바르게 설정하세요. "
                "ADR-0009 §D5 참조."
            )
        return uid

    # ─── 조회 ────────────────────────────────────────────────────────────────

    async def get(
        self,
        key: str,
        *,
        workspace_id: uuid.UUID | None = None,
    ) -> UserPreferenceORM | None:
        """key + workspace_id 로 단건 조회 (tenant_id + user_id 필터 자동 적용).

        Args:
            key: 환경설정 key (dot-notation).
            workspace_id: 워크스페이스 ID (None 이면 테넌트 전역 옵션 조회).

        Returns:
            UserPreferenceORM 인스턴스 또는 None.
        """
        stmt = (
            select(UserPreferenceORM)
            .where(UserPreferenceORM.tenant_id == self._tenant_id)
            .where(UserPreferenceORM.user_id == self._user_id)
            .where(UserPreferenceORM.key == key)
        )
        if workspace_id is None:
            stmt = stmt.where(UserPreferenceORM.workspace_id.is_(None))  # type: ignore[attr-defined]
        else:
            stmt = stmt.where(UserPreferenceORM.workspace_id == workspace_id)

        result = await self._session.exec(stmt)
        return result.first()

    # ─── upsert ──────────────────────────────────────────────────────────────

    async def upsert(
        self,
        key: str,
        value: dict,
        *,
        workspace_id: uuid.UUID | None = None,
        expected_version: int | None = None,
    ) -> UserPreferenceORM:
        """key-value upsert — partial unique index 기반 ON CONFLICT DO UPDATE.

        낙관적 동시성 제어:
          ``expected_version`` 이 주어지면 현재 DB 버전과 비교한다.
          불일치 시 ``ConflictError`` (라우터가 409 로 매핑).
          최초 생성(insert) 시 ``expected_version`` 은 무시됨 (행이 없으므로).

        upsert 전략:
          workspace_id None / NOT NULL 두 케이스에서 서로 다른 partial index 를 사용.
          PostgreSQL ``INSERT ... ON CONFLICT (index_elements) WHERE index_where DO UPDATE``
          로 정확하게 index 를 추론한다.

        Args:
            key: 환경설정 key (dot-notation).
            value: 저장할 dict (JSONB).
            workspace_id: 워크스페이스 ID (None 이면 테넌트 전역).
            expected_version: 낙관적 동시성 버전. None 이면 검사 안 함.

        Returns:
            저장된 UserPreferenceORM 인스턴스 (version 이 갱신된 상태).

        Raises:
            ConflictError: expected_version 불일치 (409 매핑).
        """
        # 낙관적 동시성 검사 — upsert 전에 현재 버전 확인
        if expected_version is not None:
            existing = await self.get(key, workspace_id=workspace_id)
            if existing is not None and existing.version != expected_version:
                raise ConflictError(
                    f"version 충돌: expected={expected_version}, "
                    f"current={existing.version}. 최신 데이터를 먼저 조회하세요."
                )

        now = datetime.now(UTC)
        new_id = uuid.uuid4()

        if workspace_id is None:
            # 테넌트 전역 옵션: uq_user_pref_global (workspace_id IS NULL)
            stmt = pg_insert(UserPreferenceORM).values(
                id=new_id,
                tenant_id=self._tenant_id,
                user_id=self._user_id,
                workspace_id=None,
                key=key,
                value=value,
                version=1,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id", "user_id", "key"],
                index_where=text("workspace_id IS NULL"),
                set_={
                    "value": stmt.excluded.value,
                    "version": UserPreferenceORM.__table__.c.version + 1,
                    "updated_at": now,
                },
            ).returning(UserPreferenceORM.__table__)
        else:
            # 워크스페이스별 옵션: uq_user_pref_workspace (workspace_id IS NOT NULL)
            stmt = pg_insert(UserPreferenceORM).values(
                id=new_id,
                tenant_id=self._tenant_id,
                user_id=self._user_id,
                workspace_id=workspace_id,
                key=key,
                value=value,
                version=1,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id", "user_id", "workspace_id", "key"],
                index_where=text("workspace_id IS NOT NULL"),
                set_={
                    "value": stmt.excluded.value,
                    "version": UserPreferenceORM.__table__.c.version + 1,
                    "updated_at": now,
                },
            ).returning(UserPreferenceORM.__table__)

        result = await self._session.execute(stmt)
        row = result.fetchone()
        if row is None:
            raise RuntimeError("upsert 후 RETURNING 이 빈 결과를 반환했습니다.")

        await self._session.flush()

        # RETURNING 결과를 ORM 인스턴스로 재구성해 반환
        return UserPreferenceORM(
            id=row.id,
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            workspace_id=row.workspace_id,
            key=row.key,
            value=row.value,
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class ConflictError(Exception):
    """낙관적 동시성 충돌 — version 불일치.

    라우터가 이 예외를 409 Conflict 로 매핑한다.
    """
