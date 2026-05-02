"""VocabularyORM — shared/schemas/vocabulary.Vocabulary 의 DB 매핑 (ADR-0005 §D-5.1).

passage_id nullable 결정 (audit §4-3):
  Phase 2/3 에서 글로벌 VocabularyMaster 도입 여지를 위해 nullable 로 둔다.
  현재 v0.1 에서는 항상 passage_id 가 있지만, Phase 2+ 에서 passage_id 없는
  글로벌 어휘 레코드가 생길 수 있다.

Enum 컬럼 (ADR-0005 함정 #3 회피):
  ``selected_by`` 를 String 저장. Pydantic 레이어에서 검증.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field

from worksheet_api.models.base import WorkspaceScopedORMBase, _utc_now


class VocabularyORM(WorkspaceScopedORMBase, table=True):
    """Vocabulary(어휘) ORM 모델.

    ``shared/schemas/vocabulary.Vocabulary`` 의 DB 매핑.
    인덱스:
      - ``(tenant_id, workspace_id)`` 복합 인덱스.
      - ``(tenant_id, passage_id)`` — passage 기준 필터링 (passage_id nullable 이므로
        NULL 행은 인덱스에서 제외됨, PostgreSQL 표준 동작).
    """

    __tablename__ = "vocabulary"
    __table_args__ = (
        Index("ix_vocabulary_tenant_workspace", "tenant_id", "workspace_id"),
        Index("ix_vocabulary_tenant_passage", "tenant_id", "passage_id"),
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

    # passage_id nullable (audit §4-3 — Phase 2/3 글로벌화 여지)
    passage_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("passages.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        description="참조 Passage ID (nullable — Phase 2/3 글로벌 마스터 도입 여지).",
    )

    # ─── 표제어 ──────────────────────────────────────────────────────────────
    word: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="원형 (사용자 입력 표면형, 대소문자/굴절 보존).",
    )
    headword_normalized: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="정규화된 표제어 (소문자 + lemma). Phase 2/3 dedup 마스터 join 키.",
    )

    # ─── 뜻 / 등급 / 품사 ─────────────────────────────────────────────────────
    pos: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
        description="품사.",
    )
    meaning_ko: str = Field(
        sa_column=Column(String(512), nullable=False),
        description="한국어 뜻.",
    )
    level_label: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
        description="어휘 등급 라벨 (자유 문자열).",
    )

    # ─── 추적 메타 ────────────────────────────────────────────────────────────
    # Enum → String (ADR-0005 함정 #3 회피)
    selected_by: str = Field(
        sa_column=Column(String(32), nullable=False),
        description="VocabularySelectedBy StrEnum 값 → String 저장.",
    )
    user_edited: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
