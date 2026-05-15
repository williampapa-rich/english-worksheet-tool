"""VocabularyMasterORM — shared/schemas/vocabulary_master.VocabularyMaster 의 DB 매핑.

ADR-0016 D1 권장안 (a) ORM 구현.

테이블: ``vocabulary_master``
  - UNIQUE (tenant_id, headword_normalized) — 동일 tenant 안에서 동일 표제어 1행만 허용.
  - ``vocabulary.master_id`` FK 가 이 테이블을 참조 (ON DELETE SET NULL).

Enum 컬럼 (ADR-0005 함정 #3 회피):
  ``created_by`` 를 String 저장. Pydantic 레이어에서 검증.

usage_count:
  application 레이어 (보강 라우트 / Stage E1-c) 에서 갱신. DB 트리거 없음 (v0.1).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field

from worksheet_api.models.base import WorkspaceScopedORMBase, _utc_now


class VocabularyMasterORM(WorkspaceScopedORMBase, table=True):
    """VocabularyMaster ORM 모델.

    ``shared/schemas/vocabulary_master.VocabularyMaster`` 의 DB 매핑.

    인덱스:
      - UNIQUE ``(tenant_id, headword_normalized)`` — 동일 tenant 내 1행 보장.
      - ``(tenant_id, workspace_id)`` 복합 인덱스 — workspace 기준 필터링.
    """

    __tablename__ = "vocabulary_master"
    __table_args__ = (
        # ADR-0016 D3: tenant_id 별 UNIQUE
        UniqueConstraint(
            "tenant_id",
            "headword_normalized",
            name="uq_vocabulary_master_tenant_headword",
        ),
        Index("ix_vocabulary_master_tenant_workspace", "tenant_id", "workspace_id"),
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

    # ─── 표제어 ──────────────────────────────────────────────────────────────
    headword_normalized: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="정규화된 표제어 (소문자 + lemma). UNIQUE per tenant_id.",
    )
    word_canonical: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="lemma 표면형 (대소문자 보존 표시용).",
    )

    # ─── master 기본 뜻 / 품사 / 등급 ────────────────────────────────────────
    default_meaning_ko: str = Field(
        sa_column=Column(String(512), nullable=False),
        description="master 기본 한국어 뜻.",
    )
    default_pos: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
        description="master 기본 품사.",
    )
    default_level_label: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
        description="master 기본 등급 라벨.",
    )

    # ─── 통계 메타 ────────────────────────────────────────────────────────────
    usage_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
        description="이 master 에 link 된 Vocabulary 행 수 (캐시).",
    )

    # ─── 생성 주체 ────────────────────────────────────────────────────────────
    # Enum → String (ADR-0005 함정 #3 회피)
    created_by: str = Field(
        sa_column=Column(String(32), nullable=False),
        description="VocabularyMasterCreatedBy StrEnum 값 → String 저장.",
    )
