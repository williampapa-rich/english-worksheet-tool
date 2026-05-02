"""PassageORM — shared/schemas/passage.Passage 의 DB 매핑 (ADR-0005 §D-5.1).

이중 클래스 패턴:
  - ``shared/schemas/passage.py`` 의 ``Passage`` 는 순수 Pydantic 유지.
  - 본 ``PassageORM`` 은 SQLModel(table=True) ORM 클래스 — DB 표현만 담당.
  - 변환: ``Passage.model_validate(passage_orm)`` (from_attributes=True 덕분).

JSONB 컬럼 (ADR-0005 §D-5.6):
  - ``source``: ``SourceMeta`` Pydantic 모델 → JSONB. 복원은 ``model_validate`` 가 자동 처리.
  - ``topic_tags``: list[str] → JSONB.
  - ``paragraphs``: list[str] → JSONB.

Enum 컬럼 (ADR-0005 함정 #3 회피):
  ``target_grade`` 를 ``SQLEnum`` 대신 ``String`` 컬럼으로 저장한다.
  이유: SQLEnum 을 사용하면 Alembic autogenerate 가 매 실행마다 불필요한
  ``ALTER TYPE`` 을 생성하는 알려진 이슈 (SQLModel GitHub #112, #216).
  Pydantic StrEnum 검증은 Repository._to_domain 의 model_validate 에서 자동 수행.

FK ondelete 결정:
  tenant_id/workspace_id → CASCADE (workspace 삭제 시 하위 데이터 일괄 삭제).
  WorkspaceScopedORMBase 의 Field(foreign_key=...) 선언을 sa_column 으로 오버라이드해
  ondelete 를 명시한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field

from worksheet_api.models.base import WorkspaceScopedORMBase, _utc_now


class PassageORM(WorkspaceScopedORMBase, table=True):
    """Passage(영어 지문) ORM 모델.

    ``shared/schemas/passage.Passage`` 의 DB 매핑.
    인덱스:
      - ``(tenant_id, workspace_id)`` 복합 인덱스 (모든 도메인 테이블 공통).
    """

    __tablename__ = "passages"
    __table_args__ = (
        # 복합 인덱스 — 모든 쿼리는 tenant_id + workspace_id 필터가 기본
        Index("ix_passages_tenant_workspace", "tenant_id", "workspace_id"),
    )

    # WorkspaceScopedORMBase 의 tenant_id / workspace_id 를 sa_column 으로 오버라이드
    # — ondelete=CASCADE 명시 (mixin 에서는 foreign_key 만 선언, ondelete 는 여기서)
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

    # ─── 본문 ────────────────────────────────────────────────────────────────
    body_text: str = Field(
        sa_column=Column(Text, nullable=False),
        description="본문 영어 텍스트.",
    )
    paragraphs: list[Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=False, server_default="'[]'::jsonb"),
        description="단락 분할 — JSONB list[str].",
    )
    word_count: int = Field(
        sa_column=Column(Integer, nullable=False),
        description="body_text 의 단어 수.",
    )

    # ─── 메타 ──────────────────────��─────────────────────────────────────────
    # SourceMeta Pydantic 모델 → JSONB (ADR-0005 §D-5.6)
    source: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=False),
        description="출처 메타 (SourceMeta → JSONB).",
    )
    topic_tags: list[Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=False, server_default="'[]'::jsonb"),
        description="주제 키워드 list[str] → JSONB.",
    )
    # Enum 컬럼: SQLEnum 대신 String 사용 (ADR-0005 함정 #3 회피 — autogenerate 중복 방지)
    target_grade: str = Field(
        sa_column=Column(String(64), nullable=False),
        description="학년 메타 (TargetGrade StrEnum 값 → String 저장).",
    )
