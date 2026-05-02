"""phase_0_domain_tables: passages, questions, vocabulary, translations, syntax_annotations, llm_usage_logs

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-05-02 01:00:00.000000

P0-1 — Phase 0 도메인 테이블 일괄 추가.
ADR-0005 §D-5.1 이중 클래스 패턴 + §D-5.6 JSONB 컬럼 적용.

추가 테이블:
  - passages: 정규화된 영어 지문 (핵심 1급 엔티티)
  - questions: 문제 (원본 + 변형, 단일 테이블)
  - vocabulary: 어휘 (Passage 종속, passage_id nullable — Phase 2/3 글로벌화 여지)
  - translations: 한글 해석 (1 Passage : 1 Translation UNIQUE 제약)
  - syntax_annotations: 구문분석 마크
  - llm_usage_logs: LLM 호출 비용 로그 (ADR-0003 PM-4)

설계 결정:
  - tenant_id/workspace_id FK ondelete=CASCADE (워크스페이스 삭제 시 하위 데이터 일괄 삭제).
  - questions.passage_id FK ondelete=RESTRICT (지문 삭제 시 문제가 있으면 에러 — 실수 방지).
  - translations.passage_id FK ondelete=RESTRICT + UNIQUE (1:1 강제).
  - syntax_annotations.passage_id FK ondelete=CASCADE (마크는 지문에 강하게 종속).
  - vocabulary.passage_id FK nullable + ondelete=RESTRICT (Phase 2/3 글로벌화 여지).
  - Enum 컬럼은 모두 String 저장 (ADR-0005 함정 #3 회피 — SQLEnum autogenerate 중복 방지).
  - JSONB: source(SourceMeta), topic_tags, paragraphs, choices, choice_matrix,
           inline_choices, sub_passages, sub_questions, plan, referent_assignments,
           raw_paragraphs, paragraph_indices, span, arrow_target_span.

기존 마이그레이션(a1b2c3d4e5f6)의 tenants/workspaces 테이블은 수정하지 않는다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── passages 테이블 ─────────────────────────────────────────────────────
    op.create_table(
        "passages",
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
        # 본문
        sa.Column("body_text", sa.Text, nullable=False),
        sa.Column(
            "paragraphs",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("word_count", sa.Integer, nullable=False),
        # 메타
        sa.Column("source", JSONB, nullable=False),
        sa.Column(
            "topic_tags",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # Enum → String (ADR-0005 함정 #3)
        sa.Column("target_grade", sa.String(64), nullable=False),
    )
    op.create_index(
        "ix_passages_tenant_workspace",
        "passages",
        ["tenant_id", "workspace_id"],
        unique=False,
    )

    # ── questions 테이블 ────────────────────────────────────────────────────
    op.create_table(
        "questions",
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
        # 출처 / 분류
        sa.Column(
            "passage_id",
            UUID(as_uuid=True),
            sa.ForeignKey("passages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column(
            "variant_kind",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'original'"),
        ),
        # Self-referential FK (nullable)
        sa.Column(
            "derived_from_question_id",
            UUID(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # 시험지 메타
        sa.Column("number", sa.Integer, nullable=True),
        sa.Column("points", sa.Float, nullable=True),
        sa.Column("group_label", sa.String(128), nullable=True),
        # 문항 본체
        sa.Column("question_text", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column(
            "choices",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "choice_format",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'flat'"),
        ),
        sa.Column("choice_matrix", JSONB, nullable=True),
        sa.Column("answer", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("explanation", sa.Text, nullable=False, server_default=sa.text("''")),
        # 유형별 부가 필드
        sa.Column("given_sentence", sa.Text, nullable=True),
        sa.Column("sub_passages", JSONB, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("sub_questions", JSONB, nullable=True),
        # sub-form (Gap A)
        sa.Column("inline_choices", JSONB, nullable=True),
        # LLM 메타
        sa.Column("plan", JSONB, nullable=True),
        sa.Column("naturalness_check", sa.String(64), nullable=True),
        sa.Column("referent_assignments", JSONB, nullable=True),
        # parser 메타
        sa.Column(
            "has_passage_box",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "has_inline_markers",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "has_blanks",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "raw_paragraphs",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "paragraph_indices",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # qa-validator 메타
        sa.Column(
            "uniqueness_validated",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("uniqueness_validator_note", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_questions_tenant_workspace",
        "questions",
        ["tenant_id", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_questions_tenant_passage",
        "questions",
        ["tenant_id", "passage_id"],
        unique=False,
    )

    # ── vocabulary 테이블 ───────────────────────────────────────────────────
    op.create_table(
        "vocabulary",
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
        # passage_id nullable (audit §4-3 — Phase 2/3 글로벌화 여지)
        sa.Column(
            "passage_id",
            UUID(as_uuid=True),
            sa.ForeignKey("passages.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("word", sa.String(255), nullable=False),
        sa.Column("headword_normalized", sa.String(255), nullable=False),
        sa.Column("pos", sa.String(64), nullable=True),
        sa.Column("meaning_ko", sa.String(512), nullable=False),
        sa.Column("level_label", sa.String(64), nullable=True),
        sa.Column("selected_by", sa.String(32), nullable=False),
        sa.Column(
            "user_edited",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_vocabulary_tenant_workspace",
        "vocabulary",
        ["tenant_id", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_vocabulary_tenant_passage",
        "vocabulary",
        ["tenant_id", "passage_id"],
        unique=False,
    )

    # ── translations 테이블 ─────────────────────────────────────────────────
    op.create_table(
        "translations",
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
        # passage_id NOT NULL + UNIQUE (PM 결정 D-2: 1:1)
        sa.Column(
            "passage_id",
            UUID(as_uuid=True),
            sa.ForeignKey("passages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "language",
            sa.String(8),
            nullable=False,
            server_default=sa.text("'ko'"),
        ),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("created_by", sa.String(32), nullable=False),
        sa.UniqueConstraint("passage_id", name="uq_translations_passage_id"),
    )
    op.create_index(
        "ix_translations_tenant_workspace",
        "translations",
        ["tenant_id", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_translations_tenant_passage",
        "translations",
        ["tenant_id", "passage_id"],
        unique=False,
    )

    # ── syntax_annotations 테이블 ───────────────────────────────────────────
    op.create_table(
        "syntax_annotations",
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
        # passage_id NOT NULL, CASCADE (마크는 passage 에 강하게 종속)
        sa.Column(
            "passage_id",
            UUID(as_uuid=True),
            sa.ForeignKey("passages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("span", JSONB, nullable=False),
        sa.Column("color_index", sa.Integer, nullable=True),
        sa.Column("text", sa.String(512), nullable=True),
        sa.Column("bracket_style", sa.String(8), nullable=True),
        sa.Column("arrow_target_span", JSONB, nullable=True),
    )
    op.create_index(
        "ix_syntax_annotations_tenant_workspace",
        "syntax_annotations",
        ["tenant_id", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_syntax_annotations_tenant_passage",
        "syntax_annotations",
        ["tenant_id", "passage_id"],
        unique=False,
    )

    # ── llm_usage_logs 테이블 ───────────────────────────────────────────────
    op.create_table(
        "llm_usage_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        # nullable — 시스템 호출 / pre-tenant 호출 허용 (ADR-0003 PM-4)
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False),
        sa.Column("parent_request_id", UUID(as_uuid=True), nullable=True),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "cache_read_tokens",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_class", sa.String(128), nullable=True),
        # NUMERIC: 금액 정밀도 보장 (float 사용 금지)
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_llm_usage_logs_tenant_created",
        "llm_usage_logs",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_llm_usage_logs_purpose_created",
        "llm_usage_logs",
        ["purpose", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    # 역순으로 삭제 (FK 참조 역방향)
    op.drop_index("ix_llm_usage_logs_purpose_created", table_name="llm_usage_logs")
    op.drop_index("ix_llm_usage_logs_tenant_created", table_name="llm_usage_logs")
    op.drop_table("llm_usage_logs")

    op.drop_index("ix_syntax_annotations_tenant_passage", table_name="syntax_annotations")
    op.drop_index("ix_syntax_annotations_tenant_workspace", table_name="syntax_annotations")
    op.drop_table("syntax_annotations")

    op.drop_index("ix_translations_tenant_passage", table_name="translations")
    op.drop_index("ix_translations_tenant_workspace", table_name="translations")
    op.drop_table("translations")

    op.drop_index("ix_vocabulary_tenant_passage", table_name="vocabulary")
    op.drop_index("ix_vocabulary_tenant_workspace", table_name="vocabulary")
    op.drop_table("vocabulary")

    op.drop_index("ix_questions_tenant_passage", table_name="questions")
    op.drop_index("ix_questions_tenant_workspace", table_name="questions")
    op.drop_table("questions")

    op.drop_index("ix_passages_tenant_workspace", table_name="passages")
    op.drop_table("passages")
