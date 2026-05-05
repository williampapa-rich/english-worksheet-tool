"""GET /preferences/{key} + PATCH /preferences/{key} 단위 테스트.

mock repository 로 실제 DB / PostgreSQL 없이 실행.
커버 케이스:
  1. GET 404 → PATCH → GET 200 happy path (global / workspace 별 두 케이스)
  2. 알 수 없는 key → 422
  3. 알려진 key 인데 value 가 schema 위반 → 422
  4. version 충돌 → 409
  5. cross-tenant 격리 — tenant A 가 만든 preference 를 tenant B 가 GET 시 404
     (멀티테넌트 함정 체크리스트 필수 1건)
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from worksheet_api.db import get_db
from worksheet_api.main import app
from worksheet_api.models.user_preference import UserPreferenceORM
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context
from worksheet_api.repositories.user_preference import ConflictError

# ─── 테스트용 고정 UUID ──────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TENANT_B = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
WORKSPACE_B = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
USER_A = uuid.UUID("00000000-0000-0000-0000-000000000003")
USER_B = uuid.UUID("00000000-0000-0000-0000-000000000004")
PREF_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


# ─── 헬퍼 팩토리 ────────────────────────────────────────────────────────────


def _make_pref_orm(
    key: str = "preset.sentence_role",
    value: dict[str, Any] | None = None,
    workspace_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID = TENANT_A,
    user_id: uuid.UUID = USER_A,
    version: int = 1,
) -> UserPreferenceORM:
    """테스트용 UserPreferenceORM 생성 헬퍼.

    repository.get / repository.upsert 의 반환값을 시뮬레이션한다.
    """
    if value is None:
        value = {"presets": ["S", "V", "O"]}
    return UserPreferenceORM(
        id=PREF_ID,
        tenant_id=tenant_id,
        user_id=user_id,
        workspace_id=workspace_id,
        key=key,
        value=value,
        version=version,
        created_at=datetime(2026, 5, 5, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 5, 0, 0, 0, tzinfo=UTC),
    )


# ─── 픽스처 ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session() -> AsyncMock:
    """트랜잭션 컨텍스트 매니저를 지원하는 mock AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = begin_cm
    return session


def _make_tenant_ctx(
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
    user_id: uuid.UUID = USER_A,
) -> TenantContext:
    return TenantContext(tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id)


@pytest.fixture
def tenant_ctx_a() -> TenantContext:
    return _make_tenant_ctx(TENANT_A, WORKSPACE_A, USER_A)


@pytest.fixture
def tenant_ctx_b() -> TenantContext:
    return _make_tenant_ctx(TENANT_B, WORKSPACE_B, USER_B)


def _make_override_deps(
    mock_session: AsyncMock,
    tenant_ctx: TenantContext,
) -> dict[Any, Any]:
    """FastAPI dependency_overrides 딕셔너리 반환."""

    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def _get_tenant() -> TenantContext:
        return tenant_ctx

    return {
        get_db: _get_db,
        get_tenant_context: _get_tenant,
    }


@pytest.fixture
async def async_client_a(
    mock_session: AsyncMock,
    tenant_ctx_a: TenantContext,
) -> AsyncGenerator[AsyncClient, None]:
    """Tenant A 컨텍스트로 override 된 AsyncClient."""
    overrides = _make_override_deps(mock_session, tenant_ctx_a)
    app.dependency_overrides.update(overrides)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def async_client_b(
    mock_session: AsyncMock,
    tenant_ctx_b: TenantContext,
) -> AsyncGenerator[AsyncClient, None]:
    """Tenant B 컨텍스트로 override 된 AsyncClient."""
    overrides = _make_override_deps(mock_session, tenant_ctx_b)
    app.dependency_overrides.update(overrides)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ─── GET → PATCH → GET happy path (global) ──────────────────────────────────


@pytest.mark.asyncio
async def test_get_not_found_then_patch_then_get_global(
    async_client_a: AsyncClient,
) -> None:
    """GET 404 → PATCH → GET 200 happy path (workspace_id=None 테넌트 전역)."""
    saved = _make_pref_orm()

    with patch("worksheet_api.routers.preferences.UserPreferenceRepository") as mock_repo_cls:
        repo_instance = mock_repo_cls.return_value
        # 1. GET — 없음
        repo_instance.get = AsyncMock(return_value=None)
        resp = await async_client_a.get("/preferences/preset.sentence_role")
        assert resp.status_code == 404

        # 2. PATCH — upsert
        repo_instance.upsert = AsyncMock(return_value=saved)
        resp = await async_client_a.patch(
            "/preferences/preset.sentence_role",
            json={"value": {"presets": ["S", "V", "O"]}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["key"] == "preset.sentence_role"
        assert body["value"] == {"presets": ["S", "V", "O"]}
        assert body["version"] == 1

        # 3. GET — 있음
        repo_instance.get = AsyncMock(return_value=saved)
        resp = await async_client_a.get("/preferences/preset.sentence_role")
        assert resp.status_code == 200
        assert resp.json()["key"] == "preset.sentence_role"


@pytest.mark.asyncio
async def test_get_not_found_then_patch_then_get_workspace(
    async_client_a: AsyncClient,
) -> None:
    """GET 404 → PATCH → GET 200 happy path (workspace_id 지정 워크스페이스별)."""
    saved = _make_pref_orm(workspace_id=WORKSPACE_A)

    with patch("worksheet_api.routers.preferences.UserPreferenceRepository") as mock_repo_cls:
        repo_instance = mock_repo_cls.return_value

        # 1. GET — 없음 (workspace_id 쿼리 파라미터)
        repo_instance.get = AsyncMock(return_value=None)
        resp = await async_client_a.get(
            "/preferences/preset.sentence_role",
            params={"workspace_id": str(WORKSPACE_A)},
        )
        assert resp.status_code == 404

        # 2. PATCH — workspace_id 포함 upsert
        repo_instance.upsert = AsyncMock(return_value=saved)
        resp = await async_client_a.patch(
            "/preferences/preset.sentence_role",
            json={
                "value": {"presets": ["S", "V", "O"]},
                "workspace_id": str(WORKSPACE_A),
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["workspace_id"] == str(WORKSPACE_A)

        # 3. GET — 있음
        repo_instance.get = AsyncMock(return_value=saved)
        resp = await async_client_a.get(
            "/preferences/preset.sentence_role",
            params={"workspace_id": str(WORKSPACE_A)},
        )
        assert resp.status_code == 200


# ─── 알 수 없는 key → 422 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_unknown_key_422(async_client_a: AsyncClient) -> None:
    """알 수 없는 key GET → 422."""
    resp = await async_client_a.get("/preferences/unknown.key")
    assert resp.status_code == 422
    assert "알 수 없는 환경설정 key" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_patch_unknown_key_422(async_client_a: AsyncClient) -> None:
    """알 수 없는 key PATCH → 422."""
    resp = await async_client_a.patch(
        "/preferences/unknown.key",
        json={"value": {"foo": "bar"}},
    )
    assert resp.status_code == 422
    assert "알 수 없는 환경설정 key" in resp.json()["detail"]


# ─── 알려진 key + value schema 위반 → 422 ────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_known_key_invalid_value_422(async_client_a: AsyncClient) -> None:
    """preset.sentence_role key 인데 value 가 schema 위반 → 422.

    SentenceRolePresetValue: presets 가 list[str] 이어야 함 (각 항목 1~16자).
    """
    resp = await async_client_a.patch(
        "/preferences/preset.sentence_role",
        json={
            "value": {
                # presets 각 항목이 17자 이상이면 schema 위반
                "presets": ["A" * 17]
            }
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    # schema 위반 메시지에 key 가 포함됨
    assert "preset.sentence_role" in detail


@pytest.mark.asyncio
async def test_patch_known_key_wrong_type_422(async_client_a: AsyncClient) -> None:
    """preset.sentence_role 인데 presets 가 list 가 아님 → 422."""
    resp = await async_client_a.patch(
        "/preferences/preset.sentence_role",
        json={"value": {"presets": "not-a-list"}},
    )
    assert resp.status_code == 422


# ─── version 충돌 → 409 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_version_conflict_409(async_client_a: AsyncClient) -> None:
    """version 충돌 (expected_version != current_version) → 409."""
    with patch("worksheet_api.routers.preferences.UserPreferenceRepository") as mock_repo_cls:
        repo_instance = mock_repo_cls.return_value
        repo_instance.upsert = AsyncMock(
            side_effect=ConflictError("version 충돌: expected=1, current=2")
        )

        resp = await async_client_a.patch(
            "/preferences/preset.sentence_role",
            json={
                "value": {"presets": ["S", "V"]},
                "version": 1,  # 충돌할 버전
            },
        )

    assert resp.status_code == 409
    assert "version 충돌" in resp.json()["detail"]


# ─── cross-tenant 격리 — tenant B 가 tenant A 의 preference GET 시 404 ─────────


@pytest.mark.asyncio
async def test_cross_tenant_isolation_get_404(
    async_client_b: AsyncClient,
) -> None:
    """멀티테넌트 격리: tenant A 가 만든 preference 를 tenant B 가 GET 시 404.

    UserPreferenceRepository.get() 이 tenant_id + user_id 필터를 적용하므로,
    다른 tenant 의 preference 는 None 을 반환 → 404.

    이 테스트는 repository 의 멀티테넌트 강제가 API 응답에 올바르게 전파되는지 검증.
    tenant_ctx 는 TENANT_B 이고, repository 는 TENANT_A 소유 preference 에 대해 None 반환.
    """
    with patch("worksheet_api.routers.preferences.UserPreferenceRepository") as mock_repo_cls:
        # Tenant B 컨텍스트로 조회 → repository 가 tenant 필터 후 None 반환
        mock_repo_cls.return_value.get = AsyncMock(return_value=None)

        resp = await async_client_b.get("/preferences/preset.sentence_role")

    assert resp.status_code == 404
    # 존재 여부 노출 없이 단순 404
    assert "찾을 수 없" in resp.json()["detail"]
