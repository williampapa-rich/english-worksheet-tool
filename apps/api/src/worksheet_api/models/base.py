"""ORM 모델 공통 베이스 — ADR-0005 §D-5.1 / §D-5.2 구현.

이중 클래스 패턴:
  - ``shared/schemas/`` 의 Pydantic 모델은 순수 Pydantic 유지 (SQLModel 의존성 없음).
  - ORM 클래스는 이 파일의 ``WorkspaceScopedORMBase`` 를 상속해 ``apps/api/`` 에서만 관리.
  - 변환은 Repository 의 ``_to_orm`` / ``_to_domain`` 에서 처리 (P0-6 에서 구현).

sentinel UUID 방어 (ADR-0005 §D-5.2):
  - ``SENTINEL_UUID = uuid.UUID(int=0)`` — extractor 출력의 미주입 placeholder.
  - DB CHECK constraint 는 v0.1 미채택 (Alembic autogenerate 이슈, ADR-0005 §D-5.2 참고).
  - Repository write 시 application 레이어 검증으로 방어 (P0-6 에서 구현).

SQLModel mixin 주의사항:
  ``WorkspaceScopedORMBase`` 는 ``table=False`` (기본값) 인 순수 mixin 이다.
  ``sa_column`` 을 mixin 에서 쓰면 ``table=True`` 서브클래스가 컬럼을 두 번 등록하는
  SQLAlchemy 이슈가 발생한다. 따라서 mixin 에서는 ``Field(foreign_key=...)`` 만 사용하고,
  ondelete 등 세부 SA 설정은 각 테이블 클래스에서 ``sa_column=Column(...)`` 으로 처리한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

# sentinel UUID: extractor 출력이 API 레이어에서 tenant_id / workspace_id 를
# 주입받기 전 placeholder 값. Repository write 시 이 값이 감지되면 ValidationError.
SENTINEL_UUID = uuid.UUID(int=0)


def _utc_now() -> datetime:
    """timezone-aware UTC datetime 반환."""
    return datetime.now(UTC)


class WorkspaceScopedORMBase(SQLModel):
    """Workspace 스코프 ORM 공통 필드 mixin (table=False, ADR-0005 §D-5.2).

    모든 도메인 ORM 모델이 상속한다 (``LlmUsageLogORM`` 제외 — PM-4 에서 nullable 허용).

    필드 선언 방식:
      ``sa_column`` 은 각 ``table=True`` 서브클래스에서 직접 선언한다. mixin 에서
      ``sa_column`` 을 쓰면 SQLAlchemy 가 컬럼을 두 번 등록하는 이슈가 발생하기 때문.
      본 mixin 에서는 ``Field(foreign_key=...)`` 를 사용하고, ondelete 등은 서브클래스에서
      ``sa_column=Column(ForeignKey(..., ondelete=...))`` 로 오버라이드한다.

    FK ondelete 결정 (서브클래스에서 구현):
      ``workspaces`` 가 삭제될 때 도메인 데이터도 일괄 삭제 (CASCADE) 를 선택한다.
      이유: Workspace 는 강사의 작업 공간 단위 — Workspace 삭제는 "전부 지우겠다" 의미.
      RESTRICT 를 선택하면 Workspace 삭제 전에 도메인 데이터를 직접 지워야 해
      UX 가 복잡해진다. Phase 4 (멀티테넌트 강화) ADR 에서 재검토 가능.
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )
    tenant_id: uuid.UUID = Field(
        ...,
        foreign_key="tenants.id",
    )
    workspace_id: uuid.UUID = Field(
        ...,
        foreign_key="workspaces.id",
    )
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
