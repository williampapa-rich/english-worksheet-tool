"""사용자 환경설정 API 엔드포인트.

ADR-0009 §D1 / §D3 / §D7:
  - GET /preferences/{key}?workspace_id=... → UserPreference 또는 404.
  - PATCH /preferences/{key} → upsert (version 충돌 시 409).
  - key 별 value Pydantic 검증 dispatch — 알 수 없는 key 는 422.
  - tenant_id / user_id 는 TenantContext Depends 주입 — 클라이언트 위장 차단 (ADR-0009 §D7).

value 검증 전략 (ADR-0009 §D3):
  key → Pydantic 모델 매핑 dict (``VALUE_SCHEMA_REGISTRY``) 를 본 라우터에서 관리.
  알 수 없는 key 는 즉시 422. 알려진 key 인데 value 가 schema 위반이면 422.
  새 key 추가 시 ``VALUE_SCHEMA_REGISTRY`` 에 항목만 추가하면 된다 — 마이그레이션 불필요.

낙관적 동시성:
  PATCH body 의 ``version`` 이 현재 DB 버전과 다르면 409 Conflict.
  최초 생성(키가 없는 상태) 시 ``version`` 은 무시됨.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.user_preference import SentenceRolePresetValue
from worksheet_api.db import get_db
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context
from worksheet_api.repositories.user_preference import ConflictError, UserPreferenceRepository

router = APIRouter(prefix="/preferences", tags=["preferences"])


# ─── 응답 스키마 ──────────────────────────────────────────────────────────────


class UserPreferenceResponse(BaseModel):
    """GET / PATCH /preferences/{key} 응답 스키마.

    ``shared/schemas/user_preference.UserPreference`` 에 ``version`` 을 추가한
    API 레이어 전용 응답 모델.

    ``UserPreference`` 는 ``extra="forbid"`` 이므로 ``version`` 을 직접 추가할 수 없다
    (shared/schemas 는 읽기 전용 — ADR-0001). 본 응답 모델은 ``apps/api/`` 내부에서만
    사용하며 ``UserPreference`` 를 embed 한다.
    """

    model_config = ConfigDict(from_attributes=True)

    # UserPreference 필드 플랫 embed (ORM 변환 편의)
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    workspace_id: uuid.UUID | None
    key: str
    value: dict[str, Any]
    version: int
    created_at: Any
    updated_at: Any

    @classmethod
    def from_orm_row(cls, orm: Any) -> UserPreferenceResponse:
        """ORM 인스턴스 → 응답 변환."""
        return cls.model_validate(orm)


# ─── value schema 레지스트리 (ADR-0009 §D3) ──────────────────────────────────

# key → Pydantic 모델 매핑. 라우터가 관리 — 마이그레이션 불필요.
# 새 key 추가 시 여기에 항목만 추가.
VALUE_SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "preset.sentence_role": SentenceRolePresetValue,
    # 후속 추가 예정 (PR C-2 / Phase 2):
    # "palette.colors": PaletteColorsValue,
    # "editor.layout": EditorLayoutValue,
    # "editor.font_size": EditorFontSizeValue,
}


def _get_value_schema(key: str) -> type[BaseModel]:
    """key 에 해당하는 value Pydantic 모델을 반환. 알 수 없는 key 는 404/422 처리.

    Args:
        key: dot-notation 환경설정 key.

    Returns:
        key 에 맞는 Pydantic 모델 클래스.

    Raises:
        HTTPException 422: 알 수 없는 key.
    """
    schema = VALUE_SCHEMA_REGISTRY.get(key)
    if schema is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"알 수 없는 환경설정 key: {key!r}. "
                f"지원 key: {sorted(VALUE_SCHEMA_REGISTRY.keys())}"
            ),
        )
    return schema


def _validate_value(key: str, value: dict[str, Any]) -> None:
    """key 에 맞는 Pydantic 모델로 value 를 검증.

    Args:
        key: dot-notation 환경설정 key.
        value: 검증할 dict (JSONB 저장 전).

    Raises:
        HTTPException 422: value 가 schema 를 위반한 경우.
    """
    schema = _get_value_schema(key)
    try:
        schema.model_validate(value)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"value 가 key={key!r} 의 schema 를 위반합니다: {exc.errors()}",
        ) from exc


# ─── 요청 / 응답 스키마 ───────────────────────────────────────────────────────


class PreferencePatchRequest(BaseModel):
    """PATCH /preferences/{key} 의 request body.

    ADR-0009 §D7: tenant_id / user_id 를 포함하지 않는다 — 클라이언트 위장 차단.
    server-side TenantContext Depends 에서 주입.
    """

    model_config = ConfigDict(extra="forbid")

    value: dict[str, Any] = Field(
        ...,
        description=(
            "저장할 JSONB value. key 에 따라 서버가 별 Pydantic 모델로 추가 검증 (실패 시 422)."
        ),
    )
    workspace_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "워크스페이스 ID (Optional). None 이면 테넌트 전역 옵션."
        ),
    )
    version: int | None = Field(
        default=None,
        description=(
            "낙관적 동시성 버전 (Optional). 현재 DB 버전과 다르면 409. "
            "최초 생성 시 None 또는 임의 값 — 행이 없으므로 검사 안 함."
        ),
    )


# ─── 엔드포인트 ──────────────────────────────────────────────────────────────


@router.get("/{key}", response_model=UserPreferenceResponse, status_code=200)
async def get_preference(
    key: str,
    workspace_id: uuid.UUID | None = None,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)] = ...,
    session: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> UserPreferenceResponse:
    """사용자 환경설정 단건 조회.

    멀티테넌트: tenant_id + user_id 필터 자동 적용 (TenantContext Depends).
    알 수 없는 key 는 422. 존재하지 않으면 404.

    Args:
        key: dot-notation 환경설정 key (예: preset.sentence_role).
        workspace_id: 워크스페이스 ID (None 이면 테넌트 전역 옵션 조회).
        tenant_ctx: 현재 요청의 테넌트/사용자 컨텍스트.
        session: DB 세션.

    Raises:
        HTTPException 422: 알 수 없는 key.
        HTTPException 404: 해당 key 의 환경설정이 존재하지 않음.
    """
    # 알 수 없는 key → 422 (존재 여부 확인 전에 key 검증)
    _get_value_schema(key)

    repo = UserPreferenceRepository(session, tenant_ctx)
    orm = await repo.get(key, workspace_id=workspace_id)
    if orm is None:
        raise HTTPException(
            status_code=404,
            detail=f"환경설정 key={key!r} (workspace_id={workspace_id}) 를 찾을 수 없습니다.",
        )
    return UserPreferenceResponse.model_validate(orm)


@router.patch("/{key}", response_model=UserPreferenceResponse, status_code=200)
async def patch_preference(
    key: str,
    body: PreferencePatchRequest,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)] = ...,
    session: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> UserPreferenceResponse:
    """사용자 환경설정 upsert (생성 또는 갱신).

    멀티테넌트: tenant_id + user_id 필터 자동 적용.
    key → value schema 검증 후 upsert. version 충돌 시 409.

    Args:
        key: dot-notation 환경설정 key (예: preset.sentence_role).
        body: value + workspace_id + version.
        tenant_ctx: 현재 요청의 테넌트/사용자 컨텍스트.
        session: DB 세션.

    Raises:
        HTTPException 422: 알 수 없는 key 또는 value schema 위반.
        HTTPException 409: version 충돌 (낙관적 동시성).
    """
    # key 존재 여부 + value schema 검증 (둘 다 422)
    _validate_value(key, body.value)

    repo = UserPreferenceRepository(session, tenant_ctx)

    try:
        async with session.begin():
            orm = await repo.upsert(
                key,
                body.value,
                workspace_id=body.workspace_id,
                expected_version=body.version,
            )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return UserPreferenceResponse.model_validate(orm)
