"""QuestionORM — shared/schemas/question.Question 의 DB 매핑 (ADR-0005 §D-5.1).

JSONB 컬럼 (ADR-0005 §D-5.6):
  - ``choices``: list[str] → JSONB.
  - ``choice_matrix``: ChoiceMatrix Pydantic 모델 → JSONB (nullable).
  - ``inline_choices``: list[InlineChoice] → JSONB (nullable).
  - ``sub_passages``: list[list[str]] → JSONB (nullable).
  - ``sub_questions``: list[SubQuestion] → JSONB (nullable).
  - ``plan``: QuestionPlan Pydantic 모델 → JSONB (nullable).
  - ``referent_assignments``: list[str] → JSONB (nullable).
  - ``raw_paragraphs`` / ``paragraph_indices``: JSONB.

Enum 컬럼 (ADR-0005 함정 #3 회피):
  ``type``, ``variant_kind``, ``choice_format`` 모두 String 저장.
  Pydantic 레이어에서 enum 검증 수행.

Self-referential FK:
  ``derived_from_question_id`` → ``questions.id`` (nullable). 변형문제 추적.

passage_id FK ondelete RESTRICT:
  passage 삭제 전 question 이 남아있으면 에러 (데이터 안전성 우선).
  CLAUDE.md §6.1: question 은 passage 의 자식 — 실수로 passage 삭제하면
  question 도 날아갈 수 있으므로 RESTRICT 로 명시적 삭제 강제.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field

from worksheet_api.models.base import WorkspaceScopedORMBase, _utc_now


class QuestionORM(WorkspaceScopedORMBase, table=True):
    """Question(문제) ORM 모델.

    ``shared/schemas/question.Question`` 의 DB 매핑.
    인덱스:
      - ``(tenant_id, workspace_id)`` 복합 인덱스.
      - ``(tenant_id, passage_id)`` — passage 기준 필터링 최적화.
    """

    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_tenant_workspace", "tenant_id", "workspace_id"),
        Index("ix_questions_tenant_passage", "tenant_id", "passage_id"),
    )

    # WorkspaceScopedORMBase 오버라이드 — ondelete 명시
    tenant_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    workspace_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    created_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # ─── 출처 / 분류 ────────────────────────────────────────────────────
    passage_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            # RESTRICT: passage 삭제 전 question 이 남아있으면 에러.
            # CASCADE 대신 RESTRICT 를 선택한 이유: passage 삭제는 "지문 자체 삭제"
            # 인데, 지문에 달린 문제가 있다면 실수로 삭제하는 게 위험하다.
            ForeignKey("passages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        description="참조 Passage ID (FK → passages.id, NOT NULL, RESTRICT).",
    )
    # Enum → String (ADR-0005 함정 #3 회피)
    type: str = Field(
        sa_column=Column(String(64), nullable=False),
        description="QuestionType StrEnum 값 → String 저장.",
    )
    variant_kind: str = Field(
        default="original",
        sa_column=Column(String(64), nullable=False, server_default="'original'"),
        description="VariantKind StrEnum 값 → String 저장.",
    )
    # Self-referential FK: variant 추적 (nullable)
    derived_from_question_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("questions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        description="원본 Question ID — variant_kind != ORIGINAL 일 때 NOT NULL.",
    )

    # ─── 시험지 메타 ─────────────────────────────────────────────────────
    number: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    points: float | None = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
    )
    group_label: str | None = Field(
        default=None,
        sa_column=Column(String(128), nullable=True),
    )

    # ─── 문항 본체 ───────────────────────────────────────────────────────
    question_text: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default="''"),
    )
    choices: list[Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=False, server_default="'[]'::jsonb"),
        description="5지선다 선택지 list[str] → JSONB.",
    )
    choice_format: str = Field(
        default="flat",
        sa_column=Column(String(32), nullable=False, server_default="'flat'"),
        description="ChoiceFormat StrEnum 값 → String 저장.",
    )
    choice_matrix: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="ChoiceMatrix Pydantic 모델 → JSONB (nullable).",
    )
    answer: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default="1"),
    )
    explanation: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default="''"),
    )

    # ─── 유형별 부가 필드 ─────────────────────────────────────────────────
    given_sentence: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    sub_passages: list[Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="list[list[str]] → JSONB.",
    )
    summary: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    sub_questions: list[Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="list[SubQuestion] → JSONB.",
    )

    # ─── 본문 내장형 sub-form (Gap A) ────────────────────────────────────
    inline_choices: list[Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="list[InlineChoice] → JSONB.",
    )

    # ─── LLM 자가검증 / 자가계획 메타 ─────────────────────────────────────
    plan: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="QuestionPlan → JSONB.",
    )
    naturalness_check: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
    )
    referent_assignments: list[Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="list[str] → JSONB.",
    )

    # ─── parser 메타 ────────────────────────────────────────────────────
    has_passage_box: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    has_inline_markers: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    has_blanks: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    raw_paragraphs: list[Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=False, server_default="'[]'::jsonb"),
    )
    paragraph_indices: list[Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=False, server_default="'[]'::jsonb"),
    )

    # ─── 변형 전용 메타 (ADR-0017 D2-c JSONB) ────────────────────────────────
    variant_metadata: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description=(
            "변형만의 추가 메타 (JSONB, nullable). "
            "variant_kind != ORIGINAL 일 때만 의미 있는 값 — 원본 행에서는 항상 NULL. "
            "v0.1 구조 미정 — Phase 3 첫 변형 생성 PR 에서 보강."
        ),
    )

    # ─── qa-validator 메타 ──────────────────────────────────────────────
    uniqueness_validated: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    uniqueness_validator_note: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
