"""Tenant / Workspace 도메인 모델.

PM 결정 D-3 (`docs/adr/_pm-decisions-sprint-0.md`) 반영:
  - Tenant → (1:N) Workspace 계층을 v0.1부터 박는다.
  - 모든 도메인 엔티티는 ``workspace_id`` FK NOT NULL.
  - v0.1 운영 stub: Tenant 생성 시 default workspace 1개 자동 생성 (별도 application
    로직 — 본 모델은 그 동작을 강제하지 않는다).

PM 추가 코멘트 (D-3): "와이프가 맡게될 학교/학년도 다양할거라 나누는게 좋아."
→ Workspace 의 멘탈 모델은 "학교 × 학년 × 시즌" 의 조합 단위. 향후 v0.2+ 에서
   ``school_name`` / ``grade`` / ``season`` 등 구조화된 필드 추가 가능 (별도 ADR).
"""

from __future__ import annotations

from pydantic import Field

from shared.schemas.common import BaseEntity, EntityId, TenantScopedEntity


class Tenant(BaseEntity):
    """테넌트 — 멀티테넌트 격리의 최상위 단위.

    Phase 4 에서 Google OAuth 와 연결된다. 현재 (Phase 0~3) 는 환경변수
    ``MVP_TENANT_ID`` 로 stub 운영.
    """

    name: str = Field(
        ...,
        max_length=255,
        description="테넌트 표시 이름 (예: 'Default Tenant', 학원명 등).",
    )


class Workspace(TenantScopedEntity):
    """워크스페이스 — 테넌트 내 작업 공간 단위.

    1차 사용자(영어 강사)의 멘탈 모델은 "학교 × 학년 × 시즌" 조합. v0.1 은 단순히
    ``name`` 자유 문자열만 갖고, 구조화 필드는 v0.2+ 에서 ADR 로 도입.

    예시 ``name``:
      - "고2 내신반"
      - "수능 대비반"
      - "중3 강남고 1학기 중간"
    """

    name: str = Field(
        ...,
        max_length=255,
        description="워크스페이스 표시 이름 (사용자 자유 명명).",
    )

    # tenant_id 는 TenantScopedEntity 에서 상속.
    # 자기 자신이 Workspace 이므로 workspace_id 는 박지 않는다 (TenantScopedEntity 사용).

    # 명시 — Workspace 자신의 ID 는 BaseEntity.id 와 동일.
    @property
    def workspace_id(self) -> EntityId:
        """편의 별칭 — 자기 자신의 ``id`` 를 반환.

        다른 ``WorkspaceScopedEntity`` 와 인터페이스를 맞추기 위함.
        """
        return self.id
