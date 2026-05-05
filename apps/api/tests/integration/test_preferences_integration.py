"""user_preferences 통합 테스트 — 실제 PostgreSQL.

@pytest.mark.integration — 실행 조건:
  - 실행 중인 PostgreSQL (docker compose up -d db)
  - DATABASE_URL 환경변수

실행 방법:
  docker compose up -d db && pytest -m integration apps/api/tests/integration/test_preferences_integration.py

커버 케이스:
  1. PATCH (global) → GET → 200 happy path
  2. PATCH (workspace_id 지정) → GET → 200 happy path
  3. GET 없는 key → 404
  4. PATCH version 충돌 → 409
  5. **cross-tenant 격리**: tenant A 가 만든 preference 를 tenant B 가 GET 시 404
     (멀티테넌트 함정 체크리스트 필수 1건)
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from worksheet_api.db import get_db
from worksheet_api.main import app
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context

# 통합 테스트 전체 파일에 marker 적용
pytestmark = pytest.mark.integration

# conftest.py 의 표준 테넌트 / 워크스페이스 UUID
from tests.conftest import (  # noqa: E402
    TEST_TENANT_A,
    TEST_TENANT_B,
    TEST_WORKSPACE_A,
    TEST_WORKSPACE_B,
)

TEST_USER_A = uuid.UUID("00000000-0000-0000-0000-000000000003")
TEST_USER_B = uuid.UUID("00000000-0000-0000-0000-000000000004")


# ─── 픽스처 ──────────────────────────────────────────────────────────────────


def _make_ctx(
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> TenantContext:
    return TenantContext(tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id)


@pytest_asyncio.fixture
async def client_a(pg_session: Any) -> AsyncIterator[AsyncClient]:
    """Tenant A 컨텍스트 + 실제 DB 세션 AsyncClient."""
    ctx_a = _make_ctx(TEST_TENANT_A, TEST_WORKSPACE_A, TEST_USER_A)

    async def _get_db_override():  # type: ignore[return]
        yield pg_session

    async def _get_tenant_override() -> TenantContext:
        return ctx_a

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_tenant_context] = _get_tenant_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_b(pg_session: Any) -> AsyncIterator[AsyncClient]:
    """Tenant B 컨텍스트 + 실제 DB 세션 AsyncClient."""
    ctx_b = _make_ctx(TEST_TENANT_B, TEST_WORKSPACE_B, TEST_USER_B)

    async def _get_db_override():  # type: ignore[return]
        yield pg_session

    async def _get_tenant_override() -> TenantContext:
        return ctx_b

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_tenant_context] = _get_tenant_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ─── 테스트 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_and_get_global(client_a: AsyncClient) -> None:
    """PATCH (global, workspace_id=None) → GET 200 round-trip."""
    # PATCH — upsert
    resp = await client_a.patch(
        "/preferences/preset.sentence_role",
        json={"value": {"presets": ["S", "V", "O"]}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["key"] == "preset.sentence_role"
    assert body["value"] == {"presets": ["S", "V", "O"]}
    assert body["workspace_id"] is None
    assert body["version"] == 1

    # GET — 확인
    resp = await client_a.get("/preferences/preset.sentence_role")
    assert resp.status_code == 200, resp.text
    assert resp.json()["value"] == {"presets": ["S", "V", "O"]}


@pytest.mark.asyncio
async def test_patch_and_get_workspace(client_a: AsyncClient) -> None:
    """PATCH (workspace_id 지정) → GET 200 round-trip."""
    resp = await client_a.patch(
        "/preferences/preset.sentence_role",
        json={
            "value": {"presets": ["S", "V", "OC"]},
            "workspace_id": str(TEST_WORKSPACE_A),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workspace_id"] == str(TEST_WORKSPACE_A)
    assert body["version"] == 1

    resp = await client_a.get(
        "/preferences/preset.sentence_role",
        params={"workspace_id": str(TEST_WORKSPACE_A)},
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == {"presets": ["S", "V", "OC"]}


@pytest.mark.asyncio
async def test_get_not_existing_key_404(client_a: AsyncClient) -> None:
    """존재하지 않는 key GET → 404."""
    resp = await client_a.get("/preferences/preset.sentence_role")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_upsert_increments_version(client_a: AsyncClient) -> None:
    """동일 key 두 번 PATCH → version 이 2로 증가."""
    # 1차
    resp = await client_a.patch(
        "/preferences/preset.sentence_role",
        json={"value": {"presets": ["S"]}},
    )
    assert resp.status_code == 200
    v1 = resp.json()["version"]

    # 2차 (version 없이 — 충돌 검사 안 함)
    resp = await client_a.patch(
        "/preferences/preset.sentence_role",
        json={"value": {"presets": ["S", "V"]}},
    )
    assert resp.status_code == 200
    v2 = resp.json()["version"]
    assert v2 == v1 + 1


@pytest.mark.asyncio
async def test_patch_version_conflict_409(client_a: AsyncClient) -> None:
    """version 충돌 → 409.

    1차 PATCH (version=None) → DB version=1.
    2차 PATCH (version=999 — 충돌) → 409.
    """
    # 1차 생성
    resp = await client_a.patch(
        "/preferences/preset.sentence_role",
        json={"value": {"presets": ["S"]}},
    )
    assert resp.status_code == 200

    # 2차: 잘못된 version
    resp = await client_a.patch(
        "/preferences/preset.sentence_role",
        json={"value": {"presets": ["S", "V"]}, "version": 999},
    )
    assert resp.status_code == 409
    assert "version 충돌" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cross_tenant_isolation_get_404(
    client_a: AsyncClient,
    client_b: AsyncClient,
) -> None:
    """멀티테넌트 격리: tenant A 가 만든 preference 를 tenant B 가 GET 시 404.

    이 테스트가 멀티테넌트 함정 체크리스트의 핵심 검증이다.
    tenant_id + user_id 필터가 repository 에서 강제되므로,
    다른 tenant 의 preference 는 조회 불가.
    """
    # Tenant A 가 preference 생성
    resp = await client_a.patch(
        "/preferences/preset.sentence_role",
        json={"value": {"presets": ["S", "V", "O"]}},
    )
    assert resp.status_code == 200, resp.text

    # Tenant B 가 동일 key 조회 → 404 (격리 확인)
    resp = await client_b.get("/preferences/preset.sentence_role")
    assert resp.status_code == 404, (
        f"cross-tenant 격리 실패: tenant B 가 tenant A 의 preference 를 볼 수 있음. "
        f"response: {resp.text}"
    )
