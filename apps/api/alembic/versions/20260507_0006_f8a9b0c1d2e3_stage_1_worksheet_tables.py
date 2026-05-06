"""stage_1_worksheet_tables: worksheets, worksheet_items 신규 생성

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-05-07 00:00:00.000000

ADR-0010 §D7 구현 — template-renderer Stage 1 backend PR.

신규 테이블:
  - worksheets: Worksheet 출력물 단위 (ADR-0010 §D1, §D2, §D3)
  - worksheet_items: Worksheet 하위 항목 (ADR-0010 §D1 #4)

설계 결정:
  - worksheets.branding — Branding Pydantic 모델 전체를 JSONB 로 저장 (ADR-0005 §D-5.6
    패턴). academy_name (ADR-0010 §D3) 은 JSONB 내 key — 별도 컬럼 불필요.
  - worksheets.orientation — String(16) 저장 (ADR-0005 함정 #3 회피, SQLEnum
    autogenerate 중복 방지). server_default='portrait' — 기존 row 및 마이그레이션 후
    미지정 row 모두 'portrait' 보장 (ADR-0010 §D1 #2).
  - worksheets.kind — String(32) 저장 (동일 이유).
  - worksheet_items.worksheet_id FK ondelete=CASCADE — Worksheet 삭제 시 항목 일괄 삭제.
  - worksheet_items.passage_id FK ondelete=RESTRICT — 지문 삭제 시 연결 항목이 있으면
    에러 (실수 방지, ADR-0010 §D7 패턴과 동일).
  - tenant_id / workspace_id FK ondelete=CASCADE (WorkspaceScopedORMBase 공통 정책).

참고:
  - worksheets 테이블은 이 revision 전까지 존재하지 않았음 (기존 마이그레이션 1~5에 없음).
  - worksheet_items 도 동일. 따라서 컬럼 추가가 아닌 신규 테이블 생성.

downgrade:
  worksheet_items 먼저 삭제 (FK 의존 순서), 그 다음 worksheets.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "f8a9b0c1d2e3"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── worksheets 테이블 ───────────────────────────────────────────────────────
    op.create_table(
        "worksheets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # 기본 메타
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("subtitle", sa.String(255), nullable=True),
        # kind: WorksheetKind StrEnum → String (ADR-0005 함정 #3)
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("template_id", sa.String(128), nullable=False),
        # orientation: WorksheetOrientation StrEnum → String(16), default='portrait'
        # (ADR-0010 §D1 #2, §D2). server_default 로 기존 row 호환.
        sa.Column(
            "orientation",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'portrait'"),
        ),
        sa.Column("instruction", sa.Text, nullable=True),
        # branding: Branding Pydantic 모델 → JSONB (ADR-0005 §D-5.6)
        # academy_name (ADR-0010 §D3) 은 JSONB 내 key — 별도 컬럼 불필요
        sa.Column("branding", JSONB, nullable=True),
        # exam-generator ExamMeta 흡수
        sa.Column("school", sa.String(255), nullable=True),
        sa.Column("grade", sa.String(64), nullable=True),
        sa.Column("exam_date", sa.String(64), nullable=True),
        sa.Column("time_limit", sa.String(32), nullable=True),
    )

    op.create_index(
        "ix_worksheets_tenant_workspace",
        "worksheets",
        ["tenant_id", "workspace_id"],
        unique=False,
    )

    # ── worksheet_items 테이블 ──────────────────────────────────────────────────
    op.create_table(
        "worksheet_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "worksheet_id",
            UUID(as_uuid=True),
            sa.ForeignKey("worksheets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "passage_id",
            UUID(as_uuid=True),
            sa.ForeignKey("passages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("order", sa.Integer, nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        # kind 별 옵션 플래그
        sa.Column(
            "include_translation",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "include_vocabulary",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "include_syntax_annotations",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "include_questions",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "include_variants",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_index(
        "ix_worksheet_items_worksheet_id",
        "worksheet_items",
        ["worksheet_id"],
        unique=False,
    )


def downgrade() -> None:
    # FK 의존 순서: worksheet_items 먼저 삭제
    op.drop_index("ix_worksheet_items_worksheet_id", table_name="worksheet_items")
    op.drop_table("worksheet_items")
    op.drop_index("ix_worksheets_tenant_workspace", table_name="worksheets")
    op.drop_table("worksheets")
