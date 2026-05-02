"""LlmUsageLogORM — ADR-0003 PM-4 명세의 llm_usage_logs 테이블.

WorkspaceScopedORMBase 를 상속하지 않는 이유 (PM-4 명세):
  - ``tenant_id`` / ``workspace_id`` 가 nullable — 시스템 호출 또는 pre-tenant 호출
    (테넌트 컨텍스트 없이 발생하는 LLM 호출) 을 허용해야 한다.
  - 멀티테넌트 방어가 필요 없는 관리/운영 데이터 — Repository 레이어가 아니라
    LLM 래퍼 내부에서 직접 기록 (P0-2b / packages/llm/ 구현 범위).

인덱스:
  - ``(tenant_id, created_at)`` — 테넌트별 비용 집계 쿼리.
  - ``(purpose, created_at)`` — 목적별 LLM 사용 패턴 분석.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Column, DateTime, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    """timezone-aware UTC datetime 반환."""
    return datetime.now(UTC)


class LlmUsageLogORM(SQLModel, table=True):
    """LLM 호출 로그 ORM 모델 (PM-4 명세).

    WorkspaceScopedORMBase 를 상속하지 않음 — tenant_id / workspace_id nullable 허용.
    인덱스:
      - ``(tenant_id, created_at)``: 테넌트별 비용 집계.
      - ``(purpose, created_at)``: 목적별 사용 패턴 분석.
    """

    __tablename__ = "llm_usage_logs"
    __table_args__ = (
        # 테넌트별 비용 집계 — tenant_id nullable 이므로 sparse 인덱스
        Index("ix_llm_usage_logs_tenant_created", "tenant_id", "created_at"),
        # 목적별 사용 패턴 분석
        Index("ix_llm_usage_logs_purpose_created", "purpose", "created_at"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True, nullable=False),
    )
    # nullable — 시스템 호출 / pre-tenant 호출 허용 (PM-4)
    tenant_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), nullable=True),
    )
    workspace_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), nullable=True),
    )

    request_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), nullable=False),
        description="동일 요청 묶음 식별자.",
    )
    parent_request_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), nullable=True),
        description="재시도 체인 추적 (ADR-0003 §D-3.5).",
    )

    model: str = Field(
        sa_column=Column(String(128), nullable=False),
        description="사용한 LLM 모델명 (예: 'claude-sonnet-4-...').",
    )
    purpose: str = Field(
        sa_column=Column(String(64), nullable=False),
        description="호출 목적 (예: 'extract_text', 'extract_pdf_vision').",
    )

    input_tokens: int = Field(
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    output_tokens: int = Field(
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    cache_read_tokens: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    latency_ms: int = Field(
        sa_column=Column(Integer, nullable=False),
        description="LLM 호출 지연 시간 (ms).",
    )

    status: str = Field(
        sa_column=Column(String(32), nullable=False),
        description=(
            "호출 결과 상태: 'success' | 'schema_invalid' | 'timeout' | "
            "'network_error' | 'rate_limited' | 'other'."
        ),
    )
    error_class: str | None = Field(
        default=None,
        sa_column=Column(String(128), nullable=True),
        description="에러 클래스명 (실패 시).",
    )

    # Decimal: PostgreSQL NUMERIC — 금액 정밀도 보장. float 사용 금지.
    cost_usd: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(precision=12, scale=8), nullable=True),
        description="USD 환산 비용 (nullable — 추후 백필 가능).",
    )

    created_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
