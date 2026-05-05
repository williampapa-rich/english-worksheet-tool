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
async def test_cross_tenant_isolation_get_404(pg_session: Any) -> None:
    """멀티테넌트 격리: tenant A 가 만든 preference 를 tenant B 가 GET 시 404.

    이 테스트가 멀티테넌트 함정 체크리스트의 핵심 검증이다.
    tenant_id + user_id 필터가 repository 에서 강제되므로,
    다른 tenant 의 preference 는 조회 불가.

    app.dependency_overrides 충돌 방지: 단계별로 context 를 교체하며 테스트한다.
    """
    ctx_a = _make_ctx(TEST_TENANT_A, TEST_WORKSPACE_A, TEST_USER_A)
    ctx_b = _make_ctx(TEST_TENANT_B, TEST_WORKSPACE_B, TEST_USER_B)

    async def _get_db():  # type: ignore[return]
        yield pg_session

    # Step 1: Tenant A 로 preference 생성
    app.dependency_overrides[get_db] = _get_db
    try:
        app.dependency_overrides[get_tenant_context] = lambda: ctx_a
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.patch(
                "/preferences/preset.sentence_role",
                json={"value": {"presets": ["S", "V", "O"]}},
            )
        assert resp.status_code == 200, resp.text

        # Step 2: Tenant B 로 동일 key 조회 → 404 (격리 확인)
        app.dependency_overrides[get_tenant_context] = lambda: ctx_b
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/preferences/preset.sentence_role")

        assert resp.status_code == 404, (
            f"cross-tenant 격리 실패: tenant B 가 tenant A 의 preference 를 볼 수 있음. "
            f"response: {resp.text}"
        )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cross_tenant_isolation_patch_separate_rows(pg_session: Any) -> None:
    """멀티테넌트 격리 — PATCH: tenant A 와 tenant B 가 같은 key 를 PATCH 시 별개 row.

    시나리오:
      1. Tenant A 가 preset.sentence_role PATCH → DB row (tenant_id=A, user_id=A).
      2. Tenant B 가 동일 key PATCH (같은 workspace_id) → DB row (tenant_id=B, user_id=B).
      3. Tenant A 의 GET 은 자신 row (value=["S","V","O"]) 반환.
      4. Tenant B 의 GET 은 자신 row (value=["X","Y"]) 반환.
      두 row 가 별개로 존재하며 서로 덮지 않음을 확인한다.

    app.dependency_overrides 충돌 방지: 단계별로 context 를 교체하며 테스트한다.
    """
    ctx_a = _make_ctx(TEST_TENANT_A, TEST_WORKSPACE_A, TEST_USER_A)
    ctx_b = _make_ctx(TEST_TENANT_B, TEST_WORKSPACE_B, TEST_USER_B)

    async def _get_db():  # type: ignore[return]
        yield pg_session

    app.dependency_overrides[get_db] = _get_db
    try:
        # 1. Tenant A 생성
        app.dependency_overrides[get_tenant_context] = lambda: ctx_a
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp_a = await c.patch(
                "/preferences/preset.sentence_role",
                json={"value": {"presets": ["S", "V", "O"]}},
            )
        assert resp_a.status_code == 200, resp_a.text

        # 2. Tenant B 생성 (같은 key)
        app.dependency_overrides[get_tenant_context] = lambda: ctx_b
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp_b = await c.patch(
                "/preferences/preset.sentence_role",
                json={"value": {"presets": ["X", "Y"]}},
            )
        assert resp_b.status_code == 200, resp_b.text

        # 3. Tenant A GET — 자신 row
        app.dependency_overrides[get_tenant_context] = lambda: ctx_a
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/preferences/preset.sentence_role")
        assert resp.status_code == 200
        assert resp.json()["value"] == {"presets": ["S", "V", "O"]}, (
            f"tenant A row 가 tenant B PATCH 로 덮인 것으로 보임: {resp.text}"
        )
        assert resp.json()["version"] == 1, "tenant A row 의 version 이 1 이어야 한다"

        # 4. Tenant B GET — 자신 row
        app.dependency_overrides[get_tenant_context] = lambda: ctx_b
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/preferences/preset.sentence_role")

        assert resp.status_code == 200
        assert resp.json()["value"] == {"presets": ["X", "Y"]}, (
            f"tenant B row 가 예상과 다름: {resp.text}"
        )
        assert resp.json()["version"] == 1, "tenant B row 의 version 이 1 이어야 한다 (cross-tenant version 공유 없음)"
    finally:
        app.dependency_overrides.clear()
