"""QAValidationResultORM — shared/schemas/qa_validation_result.QAValidationResult 의 DB 매핑.

ADR-0017 D3-c 하이브리드 구현 (history 테이블 측).

테이블: ``qa_validation_results``
  - ``question_id`` FK → ``questions.id`` (ON DELETE CASCADE).
    question 삭제 시 history 도 함께 삭제 — history 는 question 의 파생 데이터.
  - Phase 3 qa-validator agent 활성 시 행이 생성된다. Phase 3 이전에는 비어있음.

Enum 없음:
  ``passed`` 는 Boolean, ``validator_note`` / ``validator_model`` / ``validator_version``
  은 모두 String. Pydantic 레이어에서 의미 검증.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field

from worksheet_api.models.base import WorkspaceScopedORMBase, _utc_now


class QAValidationResultORM(WorkspaceScopedORMBase, table=True):
    """QAValidationResult ORM 모델.

    ``shared/schemas/qa_validation_result.QAValidationResult`` 의 DB 매핑.

    인덱스:
      - ``(tenant_id, question_id)`` — question 기준 history 조회 최적화.
      - ``(tenant_id, workspace_id)`` 복합 인덱스 — workspace 기준 필터링.
    """

    __tablename__ = "qa_validation_results"
    __table_args__ = (
        Index("ix_qa_validation_results_tenant_workspace", "tenant_id", "workspace_id"),
        Index("ix_qa_validation_results_tenant_question", "tenant_id", "question_id"),
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

    # ─── FK ─────────────────────────────────────────────────────────────────
    question_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            # CASCADE: question 삭제 시 history 도 자동 삭제 (ADR-0017 D3-c).
            ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        description="검증 대상 Question ID.",
    )

    # ─── 검증 결과 ────────────────────────────────────────────────────────────
    validated_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="검증 실행 시각 (UTC).",
    )
    passed: bool = Field(
        sa_column=Column(Boolean, nullable=False),
        description="정답 유일성 검증 통과 여부.",
    )
    validator_note: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="검증 메모 (실패 사유 등).",
    )

    # ─── LLM 호출 trace (Phase 3 보강 예정) ──────────────────────────────────
    validator_model: str | None = Field(
        default=None,
        sa_column=Column(String(128), nullable=True),
        description="검증에 사용한 LLM 모델 ID.",
    )
    validator_version: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
        description="qa-validator 프롬프트 / 알고리즘 버전.",
    )
