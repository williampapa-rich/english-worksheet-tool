"""TranslationORM — shared/schemas/translation.Translation 의 DB 매핑 (ADR-0005 §D-5.1).

1:1 UNIQUE 제약 (PM 결정 D-2):
  ``passage_id`` 에 UNIQUE 제약을 박아 1 Passage : 1 Translation 을 DB 레벨에서 강제.

Enum 컬럼 (ADR-0005 함정 #3 회피):
  ``created_by`` 를 String 저장.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field

from worksheet_api.models.base import WorkspaceScopedORMBase, _utc_now


class TranslationORM(WorkspaceScopedORMBase, table=True):
    """Translation(한글 해석) ORM 모델.

    ``shared/schemas/translation.Translation`` 의 DB 매핑.
    ``passage_id`` UNIQUE 제약으로 1:1 강제 (PM 결정 D-2).
    인덱스:
      - ``(tenant_id, workspace_id)`` 복합 인덱스.
      - ``(tenant_id, passage_id)`` + unique 가 사실상 passage 기준 단일 조회를 보장.
    """

    __tablename__ = "translations"
    __table_args__ = (
        Index("ix_translations_tenant_workspace", "tenant_id", "workspace_id"),
        Index("ix_translations_tenant_passage", "tenant_id", "passage_id"),
        # 1:1 강제 — PM 결정 D-2. UNIQUE(passage_id) 로 DB 레벨에서 보장.
        UniqueConstraint("passage_id", name="uq_translations_passage_id"),
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
            ForeignKey("passages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        description="참조 Passage ID (FK → passages.id, NOT NULL, UNIQUE, RESTRICT).",
    )
    language: str = Field(
        default="ko",
        sa_column=Column(String(8), nullable=False, server_default="'ko'"),
        description="해석 언어. v0.1 은 'ko' 고정.",
    )
    text: str = Field(
        sa_column=Column(Text, nullable=False),
        description="전체 해석 본문.",
    )
    # Enum → String (ADR-0005 함정 #3 회피)
    created_by: str = Field(
        sa_column=Column(String(32), nullable=False),
        description="TranslationCreatedBy StrEnum 값 → String 저장.",
    )
