"""공통 mixin / 타입 정의.

도메인 엔티티 전반이 공유하는 식별자, 타임스탬프, 멀티테넌트 스코프 mixin을
정의한다. ``BaseEntity`` 는 모든 도메인 엔티티의 베이스로, ``WorkspaceScopedEntity``
는 Tenant/Workspace 자체를 제외한 모든 엔티티가 상속한다.

설계 결정:
  - ``datetime`` 은 timezone-aware (UTC). ``datetime.utcnow`` 는 사용 금지
    (Python 3.12+ deprecated, code-reviewer M-3 지적 사항).
  - 식별자는 ``UUID`` (v4). DB 측 ``uuid_generate_v4()`` 와 호환 의도.
  - ``model_config`` 는 ``ConfigDict(extra="forbid")`` — 알 수 없는 필드 거부
    (LLM 출력의 silent drift 방지).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

# UUID alias — 도메인 내에서 식별자임을 명시. DB FK도 동일 타입.
EntityId = UUID


def utc_now() -> datetime:
    """timezone-aware UTC ``datetime`` 을 반환한다.

    ``datetime.utcnow`` 는 naive 객체를 반환해 deprecated 됐으므로 본 함수를 사용한다.
    """
    return datetime.now(UTC)


class TimestampMixin(BaseModel):
    """``created_at`` / ``updated_at`` mixin.

    DB 측에서도 동일 컬럼이 존재하며, in-app 변경 시 application 코드가 ``updated_at``
    을 갱신하거나 SQLAlchemy ``onupdate`` 가 갱신한다.
    """

    created_at: datetime = Field(
        default_factory=utc_now,
        description="생성 시각 (UTC, timezone-aware).",
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        description="마지막 수정 시각 (UTC, timezone-aware).",
    )


class BaseEntity(TimestampMixin):
    """모든 도메인 엔티티의 베이스.

    ``id`` + ``created_at`` + ``updated_at`` 을 공유한다. ``model_config`` 로 추가 필드를
    거부해 LLM 출력의 silent drift 를 방지한다.
    """

    model_config = ConfigDict(
        # 알 수 없는 필드 거부 — LLM 출력의 silent drift 방지. Pydantic v2 의 datetime
        # JSON 직렬화는 기본 ISO 8601 (Tiptap / FastAPI / Anthropic 모두 호환).
        extra="forbid",
        # ORM 객체 (SQLModel / SQLAlchemy) 의 attribute 접근으로 model_validate 가능하게.
        # ADR-0005 §D-5.5 의 ORM → 도메인 변환 (`Passage.model_validate(passage_orm)`)
        # 이 동작하려면 필요. P0-1 (Repository 레이어) 차단 항목.
        from_attributes=True,
    )

    id: EntityId = Field(
        default_factory=uuid4,
        description="엔티티 고유 식별자 (UUID v4).",
    )


class TenantScopedEntity(BaseEntity):
    """Tenant 스코프 엔티티 (Workspace 등).

    ``tenant_id`` 가 NOT NULL. 모든 쿼리에 ``tenant_id`` 필터 강제 (CLAUDE.md §3.3).
    """

    tenant_id: EntityId = Field(
        ...,
        description="소속 테넌트 ID (FK → tenants.id, NOT NULL).",
    )


class WorkspaceScopedEntity(TenantScopedEntity):
    """Workspace 스코프 엔티티 (Passage / Question / Worksheet 등).

    ``tenant_id`` 와 ``workspace_id`` 모두 직접 컬럼으로 박는다 (transitive FK 만 두면
    모든 쿼리에 join 필요 — schema-coverage-audit §5.1 권고).
    """

    workspace_id: EntityId = Field(
        ...,
        description="소속 워크스페이스 ID (FK → workspaces.id, NOT NULL).",
    )
