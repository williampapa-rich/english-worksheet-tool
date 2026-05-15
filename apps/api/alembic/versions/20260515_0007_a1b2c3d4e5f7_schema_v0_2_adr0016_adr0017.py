"""schema_v0_2_adr0016_adr0017: VocabularyMaster + vocabulary.master_id + question.variant_metadata + qa_validation_results

Revision ID: a1b2c3d4e5f7
Revises: f8a9b0c1d2e3
Create Date: 2026-05-15 00:00:00.000000

ADR-0016 D2-d Migration 1 (online) + ADR-0017 D8 구현.

변경 사항:
  1. [ADR-0016] 신규 테이블 ``vocabulary_master`` 생성
     - UNIQUE (tenant_id, headword_normalized) 인덱스
     - FK: tenant_id → tenants.id (CASCADE), workspace_id → workspaces.id (CASCADE)

  2. [ADR-0016] ``vocabulary.master_id`` nullable 컬럼 추가
     - FK → vocabulary_master.id (ON DELETE SET NULL)
     - 기존 행은 master_id = NULL (master 미연결 legacy)

  3. [ADR-0017] ``questions.variant_metadata`` JSONB nullable 컬럼 추가
     - variant_kind != ORIGINAL 일 때만 의미 있음 — 원본 행은 NULL
     - v0.1 구조 미정 — Phase 3 첫 변형 생성 PR 에서 보강

  4. [ADR-0017] 신규 테이블 ``qa_validation_results`` 생성
     - FK: question_id → questions.id (ON DELETE CASCADE)
     - Phase 3 qa-validator 활성 전까지 비어있음

외부 동작 변경 0 — 모든 신규 컬럼은 nullable / default 있음:
  - vocabulary.master_id: NULL (기존 행 그대로)
  - questions.variant_metadata: NULL (기존 행 그대로)
  - qa_validation_results: 신규 테이블이므로 기존 데이터 영향 없음

Migration 2 (후속 PR 영역, 본 마이그레이션 범위 밖):
  # TODO: 별 PR — backfill
  # 기존 vocabulary 행 → vocabulary_master 생성 + vocabulary.master_id link
  # (tenant_id, headword_normalized) 기준 GROUP BY → 각 그룹마다 VocabularyMaster 1행 생성
  # (가장 흔한 meaning_ko / pos / level 을 default 로 — group MAX 또는 첫 행)
  # → 그룹 안 모든 vocabulary 의 master_id 채움

downgrade:
  역순으로 테이블/컬럼 제거.
  qa_validation_results 먼저 drop (questions FK 의존).
  vocabulary.master_id drop 후 vocabulary_master drop (FK 의존 순서).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: str | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. vocabulary_master 테이블 생성 (ADR-0016 D1 권장안 (a)) ──────────────
    op.create_table(
        "vocabulary_master",
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
        # ─── 표제어 ─────────────────────────────────────────────────────────
        sa.Column("headword_normalized", sa.String(255), nullable=False),
        sa.Column("word_canonical", sa.String(255), nullable=False),
        # ─── master 기본 뜻 / 품사 / 등급 ────────────────────────────────────
        sa.Column("default_meaning_ko", sa.String(512), nullable=False),
        sa.Column("default_pos", sa.String(64), nullable=True),
        sa.Column("default_level_label", sa.String(64), nullable=True),
        # ─── 통계 메타 ──────────────────────────────────────────────────────
        sa.Column(
            "usage_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        # ─── 생성 주체 (Enum → String) ──────────────────────────────────────
        sa.Column("created_by", sa.String(32), nullable=False),
    )

    # UNIQUE (tenant_id, headword_normalized) — ADR-0016 D3
    op.create_index(
        "ix_vocabulary_master_tenant_workspace",
        "vocabulary_master",
        ["tenant_id", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "uq_vocabulary_master_tenant_headword",
        "vocabulary_master",
        ["tenant_id", "headword_normalized"],
        unique=True,
    )

    # ── 2. vocabulary.master_id nullable 컬럼 추가 (ADR-0016 D2-b) ────────────
    op.add_column(
        "vocabulary",
        sa.Column(
            "master_id",
            UUID(as_uuid=True),
            sa.ForeignKey("vocabulary_master.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # 기존 행: master_id = NULL (master 미연결 legacy — BC 유지)

    # ── 3. questions.variant_metadata JSONB nullable 추가 (ADR-0017 D2-c) ──────
    op.add_column(
        "questions",
        sa.Column(
            "variant_metadata",
            JSONB,
            nullable=True,
        ),
    )
    # 기존 행: variant_metadata = NULL (원본 행 그대로 — BC 유지)

    # ── 4. qa_validation_results 테이블 생성 (ADR-0017 D3-c) ──────────────────
    op.create_table(
        "qa_validation_results",
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
        # ─── FK ─────────────────────────────────────────────────────────────
        sa.Column(
            "question_id",
            UUID(as_uuid=True),
            # CASCADE: question 삭제 시 history 도 자동 삭제 (ADR-0017 D3-c)
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # ─── 검증 결과 ──────────────────────────────────────────────────────
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("validator_note", sa.Text, nullable=True),
        # ─── LLM 호출 trace (Phase 3 보강 예정) ─────────────────────────────
        sa.Column("validator_model", sa.String(128), nullable=True),
        sa.Column("validator_version", sa.String(64), nullable=True),
    )

    op.create_index(
        "ix_qa_validation_results_tenant_workspace",
        "qa_validation_results",
        ["tenant_id", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_qa_validation_results_tenant_question",
        "qa_validation_results",
        ["tenant_id", "question_id"],
        unique=False,
    )


def downgrade() -> None:
    # 역순: FK 의존 순서 — qa_validation_results 먼저, 그 다음 vocabulary 컬럼/master

    # 4. qa_validation_results 삭제
    op.drop_index(
        "ix_qa_validation_results_tenant_question", table_name="qa_validation_results"
    )
    op.drop_index(
        "ix_qa_validation_results_tenant_workspace", table_name="qa_validation_results"
    )
    op.drop_table("qa_validation_results")

    # 3. questions.variant_metadata 삭제
    op.drop_column("questions", "variant_metadata")

    # 2. vocabulary.master_id 삭제
    op.drop_column("vocabulary", "master_id")

    # 1. vocabulary_master 삭제
    op.drop_index("uq_vocabulary_master_tenant_headword", table_name="vocabulary_master")
    op.drop_index("ix_vocabulary_master_tenant_workspace", table_name="vocabulary_master")
    op.drop_table("vocabulary_master")
