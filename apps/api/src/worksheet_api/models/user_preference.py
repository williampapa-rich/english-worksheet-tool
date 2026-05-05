"""UserPreferenceORM — shared/schemas/user_preference.UserPreference 의 DB 매핑.

ADR-0009 §D1 / §D4 구현:
  - 단일 ``user_preferences`` 테이블 + dot-notation key + JSONB value.
  - ``workspace_id`` 는 Optional — WorkspaceScopedORMBase 가 아닌 독립 선언.
  - ``user_id`` 는 MVP_USER_ID sentinel UUID stub (Phase 1). Phase 4 OAuth 도입 시
    실제 ``sub`` 클레임 매핑으로 교체.

UNIQUE 제약:
  ``workspace_id IS NOT NULL`` 과 ``IS NULL`` 케이스를 각각 partial unique index 로
  분리한다 (ADR-0009 §D4). PostgreSQL 의 NULL ≠ NULL 정책 때문에 일반 UNIQUE 로는
  workspace_id=NULL 행이 중복 허용되므로 conditional index 가 필수.
  인덱스 DDL 은 Alembic 마이그레이션에서 처리 — 본 ORM 은 ``__table_args__`` 로
  일반 인덱스만 선언 (partial index 는 ORM 레벨에서 autogenerate 지원 한계).

이중 클래스 패턴 (ADR-0005 §D-5.1):
  - ``shared/schemas/user_preference.UserPreference`` 는 순수 Pydantic 유지.
  - 본 ``UserPreferenceORM`` 은 SQLModel(table=True) — DB 표현만 담당.
  - 변환: ``UserPreference.model_validate(orm)`` (from_attributes=True 덕분).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

from worksheet_api.models.base import _utc_now


class UserPreferenceORM(SQLModel, table=True):
    """UserPreference(사용자 환경설정) ORM 모델.

    ``shared/schemas/user_preference.UserPreference`` 의 DB 매핑.
    ADR-0009 §D1 채택안 C — 단일 테이블 + dot-notation key + JSONB value.

    인덱스:
      - ``(tenant_id, user_id)`` 복합 인덱스 — 모든 쿼리의 기본 필터.
      - Partial unique index 는 Alembic 마이그레이션에서 별도 생성
        (ADR-0009 §D4 SQL 그대로).

    ``workspace_id`` 는 ``WorkspaceScopedORMBase`` 를 쓰지 않고 직접 Optional 로
    선언 — ADR-0009 §D4 의 의도적 설계 (테넌트 전역 옵션 지원).
    """

    __tablename__ = "user_preferences"
    __table_args__ = (
        # 기본 복합 인덱스 — 모든 쿼리는 tenant_id + user_id 필터가 기본
        Index("ix_user_preferences_tenant_user", "tenant_id", "user_id"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True, nullable=False),
    )
    tenant_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    # user_id: Phase 1 은 MVP_USER_ID sentinel UUID. Phase 4 OAuth 도입 시 실제 sub.
    # FK 없음 — users 테이블 미존재 (Phase 1 stub), Phase 4 에서 FK 추가 마이그레이션 예정.
    user_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            nullable=False,
        ),
    )
    # workspace_id: Optional — 워크스페이스별 분리 옵션은 채우고, 테넌트 전역은 NULL.
    workspace_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    key: str = Field(
        sa_column=Column(String(128), nullable=False),
        description="환경설정 key (dot-notation). 예: 'preset.sentence_role'.",
    )
    value: dict[str, Any] = Field(
        sa_column=Column(JSONB, nullable=False),
        description="JSONB value. key 별 Pydantic 모델로 application 레이어 검증.",
    )
    version: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default="1"),
        description="낙관적 동시성 버전. PATCH 시 충돌 감지용.",
    )
    created_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
