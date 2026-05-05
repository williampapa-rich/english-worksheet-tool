"""user_preferences: 사용자 환경설정 테이블 + 조건부 unique 인덱스

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-05-05 00:00:00.000000

ADR-0009 §D1 / §D4 구현 — PR C-2a.

추가 테이블:
  - user_preferences: 사용자 환경설정 (단일 key-value JSONB 테이블)

설계 결정:
  - tenant_id FK ondelete=CASCADE (테넌트 삭제 시 환경설정 일괄 삭제).
  - workspace_id FK ondelete=CASCADE, nullable=True (워크스페이스별 옵션은 채움, 전역은 NULL).
  - user_id: FK 없음 — Phase 1 stub (users 테이블 미존재). Phase 4 OAuth 진입 시 FK 추가.
  - version: 낙관적 동시성 제어 (PATCH 시 충돌 감지).

조건부 unique 인덱스 (ADR-0009 §D4 SQL 그대로):
  PostgreSQL 의 NULL ≠ NULL 정책 때문에 일반 UNIQUE(tenant_id, user_id, workspace_id, key)
  로는 workspace_id=NULL 행이 중복 허용된다. 두 개의 partial index 로 분리:

  1. uq_user_pref_workspace (workspace_id IS NOT NULL):
     UNIQUE(tenant_id, user_id, workspace_id, key) WHERE workspace_id IS NOT NULL
  2. uq_user_pref_global (workspace_id IS NULL):
     UNIQUE(tenant_id, user_id, key) WHERE workspace_id IS NULL

  op.create_index(postgresql_where=...) 로 partial index 표현.
  일반 UniqueConstraint 로 만들지 않는다 — null 비교가 partial 로만 정확하게 동작.

downgrade: 인덱스 → 테이블 역순 삭제.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── user_preferences 테이블 ─────────────────────────────────────────────
    op.create_table(
        "user_preferences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # user_id: FK 없음 (Phase 1 stub — users 테이블 미존재)
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        # workspace_id: Optional FK — 워크스페이스별 옵션은 채움, 테넌트 전역은 NULL
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column(
            "version",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 기본 복합 인덱스 — 모든 쿼리는 tenant_id + user_id 필터 기본
    op.create_index(
        "ix_user_preferences_tenant_user",
        "user_preferences",
        ["tenant_id", "user_id"],
        unique=False,
    )

    # 조건부 unique 인덱스 (ADR-0009 §D4 SQL 그대로)
    # workspace_id IS NOT NULL 케이스: (tenant_id, user_id, workspace_id, key) UNIQUE
    op.create_index(
        "uq_user_pref_workspace",
        "user_preferences",
        ["tenant_id", "user_id", "workspace_id", "key"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NOT NULL"),
    )

    # workspace_id IS NULL 케이스: (tenant_id, user_id, key) UNIQUE
    op.create_index(
        "uq_user_pref_global",
        "user_preferences",
        ["tenant_id", "user_id", "key"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_user_pref_global", table_name="user_preferences")
    op.drop_index("uq_user_pref_workspace", table_name="user_preferences")
    op.drop_index("ix_user_preferences_tenant_user", table_name="user_preferences")
    op.drop_table("user_preferences")
