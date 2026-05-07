"""WorksheetORM / WorksheetItemORM — shared/schemas/worksheet.{Worksheet,WorksheetItem} 의 DB 매핑 (ADR-0005 §D-5.1).

이중 클래스 패턴:
  - ``shared/schemas/worksheet.py`` 의 Pydantic 모델은 순수 Pydantic 유지.
  - 본 ORM 클래스는 SQLModel(table=True) — DB 표현만 담당.
  - 변환: Repository._to_domain / _to_orm (boilerplate, ADR-0005 §D-5.1).

설계 결정:
  - ``branding`` — ``Branding`` Pydantic 모델 → JSONB (ADR-0005 §D-5.6 패턴, 기존
    PassageORM.source 와 동일). ``academy_name`` 은 JSONB 내 key 로 저장됨 →
    마이그레이션 불필요 (schema-less).
  - ``orientation`` — String(16) 저장 (ADR-0005 함정 #3 회피 — SQLEnum autogenerate 중복).
    Pydantic StrEnum 검증은 Repository._to_domain 의 model_validate 에서 자동 수행.
  - ``kind`` — 동일 이유로 String(32) 저장.
  - ``WorksheetItemORM.worksheet_id`` — FK → worksheets.id, ondelete=CASCADE.
    Worksheet 삭제 시 항목도 일괄 삭제.
  - tenant_id / workspace_id ondelete=CASCADE (WorkspaceScopedORMBase 공통 정책).

관련 문서:
  - ``docs/adr/0005-sqlalchemy-mapping-pattern.md``
  - ``docs/adr/0010-worksheet-output-parameters.md`` §D7 (worksheets / worksheet_items 신규 생성)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

from worksheet_api.models.base import WorkspaceScopedORMBase, _utc_now


class WorksheetORM(WorkspaceScopedORMBase, table=True):
    """Worksheet(출력물 단위) ORM 모델.

    ``shared/schemas/worksheet.Worksheet`` 의 DB 매핑.
    인덱스:
      - ``(tenant_id, workspace_id)`` 복합 인덱스 (모든 도메인 테이블 공통).
    """

    __tablename__ = "worksheets"
    __table_args__ = (Index("ix_worksheets_tenant_workspace", "tenant_id", "workspace_id"),)

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

    # ─── 기본 메타 ─────────────────────────────────────────────────────────────
    title: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="Worksheet 제목.",
    )
    subtitle: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
        description="Worksheet 부제 (ADR-0010 §D1 #1).",
    )
    # Enum 컬럼: String 저장 (ADR-0005 함정 #3 회피)
    kind: str = Field(
        sa_column=Column(String(32), nullable=False),
        description="WorksheetKind StrEnum 값 → String 저장.",
    )
    template_id: str = Field(
        sa_column=Column(String(128), nullable=False),
        description="템플릿 식별자 (예: 'playful').",
    )
    orientation: str = Field(
        default="portrait",
        sa_column=Column(String(16), nullable=False, server_default="'portrait'"),
        description="WorksheetOrientation StrEnum 값 → String 저장 (ADR-0010 §D1 #2).",
    )
    instruction: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="워크시트 지시문 (ADR-0010 §D1 #3).",
    )

    # ─── 브랜딩 (JSONB) ────────────────────────────────────────────────────────
    # Branding Pydantic 모델 전체를 JSONB 로 저장 (ADR-0005 §D-5.6 패턴).
    # academy_name 은 JSONB 내 key — 별도 컬럼 불필요 (ADR-0010 §D7).
    branding: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="Branding 모델 → JSONB (logo_url, primary_color, secondary_color, academy_name).",
    )

    # ─── exam-generator ExamMeta 흡수 ──────────────────────────────────────────
    school: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
        description="학교명.",
    )
    grade: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
        description="학년.",
    )
    exam_date: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
        description="시험 일자.",
    )
    time_limit: str | None = Field(
        default=None,
        sa_column=Column(String(32), nullable=True),
        description="제한 시간.",
    )


class WorksheetItemORM(SQLModel, table=True):
    """WorksheetItem ORM 모델.

    ``shared/schemas/worksheet.WorksheetItem`` 의 DB 매핑.
    WorksheetORM 의 하위 항목 — ``worksheet_id`` FK 로 Worksheet 에 귀속.

    ``WorkspaceScopedORMBase`` 를 상속하지 않는다:
      WorksheetItem 은 Workspace 에 직접 귀속된 엔티티가 아니라 Worksheet 의
      하위 구성 요소다. tenant_id 격리는 부모 WorksheetORM 을 통해 이뤄진다.
      Repository 에서 WorksheetORM 을 tenant_id 로 조회한 후 그 id 로 item 을 조인.

    ⚠️ 멀티테넌트 격리 함정 (code-reviewer W-2):
      ``WorksheetItemORM`` 자체는 ``tenant_id`` / ``workspace_id`` 컬럼이 없으므로
      안전망이 없다. 직접 쿼리 시 다음을 반드시 지킨다:
        1. ``WorksheetItemORM`` 단독 SELECT 금지 — 항상 ``WorksheetORM`` 을 거쳐
           ``tenant_id`` 필터를 적용한 후 ``worksheet_id`` 로 조인하거나 IN 쿼리.
        2. ``passage_id`` FK 가 있어 ``passages`` 와 직접 조인 가능하지만,
           반드시 부모 ``WorksheetORM.tenant_id == passages.tenant_id`` 도 동시 필터.
        3. 후속 ``WorksheetRepository`` 가 이 패턴을 강제하는 메서드(``list_items_for_worksheet``)
           를 제공해야 함 — 외부에서 raw query 금지.
      이 규칙은 ``packages/llm/.../passage_repo`` 등 다른 Repository 패턴과
      차별화되는 "파생 엔티티" 케이스이며, ADR-0005 보강 항목으로 검토 중.
    """

    __tablename__ = "worksheet_items"
    __table_args__ = (
        # worksheet_id 인덱스 — item 목록 조회 기본 패턴
        Index("ix_worksheet_items_worksheet_id", "worksheet_id"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )
    worksheet_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("worksheets.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    # ─── WorksheetItem 필드 ───────────────────────────────────────────────────
    passage_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("passages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        description="참조 Passage ID.",
    )
    order: int = Field(
        sa_column=Column(Integer, nullable=False),
        description="Worksheet 안의 노출 순서 (0-based).",
    )
    label: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
        description="항목 라벨 (ADR-0010 §D1 #4).",
    )
    # ─── kind 별 옵션 ──────────────────────────────────────────────────────────
    include_translation: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    include_vocabulary: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    include_syntax_annotations: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    include_questions: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    include_variants: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
