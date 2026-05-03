"""SyntaxAnnotationORM — shared/schemas/annotation.SyntaxAnnotation 의 DB 매핑.

JSONB 컬럼 (ADR-0005 §D-5.6):
  - ``span``: AnnotationSpan Pydantic 모델 → JSONB (P1-3 / ADR-0004 적용 후 v0.2 구조 —
    discriminated union ``character_offset_v1``).
  - ``arrow_target_span``: AnnotationSpan nullable → JSONB.

Enum 컬럼 (ADR-0005 함정 #3 회피):
  ``kind``, ``category`` 를 String 저장.

passage_id FK ondelete CASCADE:
  구문분석 마크는 passage 에 강하게 종속 — passage 삭제 시 마크도 함께 삭제.
  question 과 달리 마크만 독립적으로 재사용하지 않으므로 CASCADE 가 자연스럽다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field

from worksheet_api.models.base import WorkspaceScopedORMBase, _utc_now


class SyntaxAnnotationORM(WorkspaceScopedORMBase, table=True):
    """SyntaxAnnotation(구문분석 마크) ORM 모델.

    ``shared/schemas/annotation.SyntaxAnnotation`` 의 DB 매핑.
    인덱스:
      - ``(tenant_id, workspace_id)`` 복합 인덱스.
      - ``(tenant_id, passage_id)`` — passage 기준 annotation 목록 조회 최적화.
    """

    __tablename__ = "syntax_annotations"
    __table_args__ = (
        Index("ix_syntax_annotations_tenant_workspace", "tenant_id", "workspace_id"),
        Index("ix_syntax_annotations_tenant_passage", "tenant_id", "passage_id"),
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

    passage_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("passages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        description=(
            "참조 Passage ID (FK → passages.id, NOT NULL, CASCADE). "
            "구문분석 마크는 passage 에 강하게 종속 — passage 삭제 시 함께 삭제."
        ),
    )

    # Enum → String (ADR-0005 함정 #3 회피)
    kind: str = Field(
        sa_column=Column(String(32), nullable=False),
        description="AnnotationKind StrEnum 값 → String 저장.",
    )
    category: str | None = Field(
        default=None,
        sa_column=Column(String(32), nullable=True),
        description="AnnotationCategory StrEnum 값 → String 저장 (nullable).",
    )

    span: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=False),
        description=(
            "본문 내 위치 (AnnotationSpan → JSONB). "
            "P1-3 (ADR-0004) 적용 후 v0.2 구조 — discriminated union character_offset_v1."
        ),
    )

    color_index: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
        description="12색 팔레트 인덱스 (1~12).",
    )
    text: str | None = Field(
        default=None,
        sa_column=Column(String(512), nullable=True),
        description="표시 텍스트 (top_label / bottom_label / inline_note).",
    )
    bracket_style: str | None = Field(
        default=None,
        sa_column=Column(String(8), nullable=True),
        description="괄호 모양 ('()' / '{}' / '[]'). kind == bracket 일 때.",
    )
    arrow_target_span: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description=(
            "P1-3 정식화 — arrow kind 의 도착점 span (출발점 = span 필드). "
            "AnnotationSpan → JSONB, nullable. kind == arrow 일 때만 non-None."
        ),
    )
