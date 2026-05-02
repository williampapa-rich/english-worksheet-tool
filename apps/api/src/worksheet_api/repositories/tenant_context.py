"""TenantContext — 멀티테넌트 컨텍스트 + FastAPI Depends 스텁.

ADR-0003 §D-3.6 / §D-3.4 명세:
  - API 핸들러가 ``TenantContext`` 를 FastAPI Depends 로 주입받는다.
  - v0.1 은 환경변수 ``MVP_TENANT_ID`` / ``MVP_WORKSPACE_ID`` 를 읽는 stub.
  - Phase 4 에서 OAuth 토큰 파싱으로 교체 — 이 파일만 수정하면 됨.

설계:
  - ``TenantContext`` 는 frozen Pydantic 모델 — 주입 후 변경 불가.
  - ``user_id`` 는 Phase 4 OAuth 도입 시 채워짐. v0.1 은 None.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from worksheet_api.config import get_settings


class TenantContext(BaseModel):
    """API 핸들러가 의존성 주입으로 받는 테넌트 컨텍스트.

    ADR-0003 §D-3.6: ``get_tenant_context`` Depends 를 통해 주입.
    frozen=True 로 주입 후 변경 불가 (불변성 보장).
    """

    model_config = ConfigDict(frozen=True)

    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None  # Phase 4 OAuth 도입 시 채워짐


async def get_tenant_context() -> TenantContext:
    """v0.1 stub — 환경변수에서 단일 테넌트/워크스페이스 컨텍스트 반환.

    Phase 4 에서 OAuth 토큰 파싱 로직으로 교체한다. 교체 시 이 함수의
    시그니처와 반환 타입은 동일하게 유지 — 호출부 변경 없음.

    Returns:
        TenantContext: 환경변수 기반 고정 컨텍스트.

    Raises:
        ValueError: 환경변수 ``MVP_TENANT_ID`` / ``MVP_WORKSPACE_ID`` 누락 또는
            유효하지 않은 UUID 형식.
    """
    settings = get_settings()

    try:
        tenant_id = uuid.UUID(settings.mvp_tenant_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"환경변수 MVP_TENANT_ID 가 유효한 UUID 형식이 아니다: "
            f"'{settings.mvp_tenant_id}'. "
            f"원인: {exc}"
        ) from exc

    try:
        workspace_id = uuid.UUID(settings.mvp_workspace_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"환경변수 MVP_WORKSPACE_ID 가 유효한 UUID 형식이 아니다: "
            f"'{settings.mvp_workspace_id}'. "
            f"원인: {exc}"
        ) from exc

    return TenantContext(tenant_id=tenant_id, workspace_id=workspace_id)
