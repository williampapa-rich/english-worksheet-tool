"""Tenant / Workspace ORM 모델 (Sprint 0 초기 마이그레이션 대상).

NOTE: 이 모델은 architect 작업 #5 (shared/schemas/ v0.1) 완료 후
      shared/schemas/tenant.py의 Pydantic 모델과 연결되는 PLACEHOLDER다.
      Passage 등 다른 도메인 모델은 architect 결정 후 추가한다.

인덱스 결정:
  workspaces에 (tenant_id) 단일 인덱스를 추가한다 (복합 인덱스 불채택 이유:
  name은 아직 조회 조건으로 사용되지 않으며, 모든 쿼리는 tenant_id 필터가
  필수이므로 단일 인덱스가 현 시점 요구사항을 충족한다. name 검색이 필요해지면
  그때 복합 인덱스로 확장).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from worksheet_api.db import Base


class Tenant(Base):
    """테넌트 — 멀티테넌트 격리의 최상위 단위.

    Phase 4에서 Google OAuth와 연결된다. 현재는 환경변수 MVP_TENANT_ID로 stub.
    """

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,  # DB 기본값은 alembic server_default로 설정 가능
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # 관계 — 역참조
    workspaces: Mapped[list["Workspace"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )


class Workspace(Base):
    """워크스페이스 — 테넌트 내 작업 공간 단위.

    Phase 0에서는 Passage가 Workspace에 귀속된다.
    tenant_id 인덱스로 테넌트별 목록 조회를 최적화한다.
    """

    __tablename__ = "workspaces"

    # 테이블 수준 인덱스 선언 (tenant_id 단일 인덱스)
    __table_args__ = (Index("ix_workspaces_tenant_id", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # 관계
    tenant: Mapped[Tenant] = relationship(back_populates="workspaces")
