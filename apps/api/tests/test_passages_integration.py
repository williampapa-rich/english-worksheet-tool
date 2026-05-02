"""POST /passages/extract + GET /passages/{id} 통합 테스트.

@pytest.mark.integration — 실행 시 필요:
  - 실행 중인 PostgreSQL (Docker compose)
  - ANTHROPIC_API_KEY 환경변수

실행 방법:
  pytest -m integration apps/api/tests/test_passages_integration.py

이 테스트는 CI 에서는 기본 skip (DB/API key 없는 환경).
실제 LLM 비용이 발생하므로 단순한 텍스트 입력으로 최소 토큰 사용.

테스트 패턴:
  - end-to-end: POST text → DB 저장 → GET /{id} 조회 → 동일 데이터.
  - 멀티테넌트 격리: 서로 다른 tenant_id 환경에서 cross-tenant 조회 불가.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from worksheet_api.main import app
from worksheet_api.repositories.passage import PassageRepository
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context

from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade

# 통합 테스트 marker
pytestmark = pytest.mark.integration

# conftest.py 에서 시드된 표준 테넌트 UUID
from apps.api.tests.conftest import (  # noqa: E402
    TEST_TENANT_A,
    TEST_TENANT_B,
    TEST_WORKSPACE_A,
    TEST_WORKSPACE_B,
)


@pytest.fixture
def _skip_if_no_api_key() -> None:
    """ANTHROPIC_API_KEY 없으면 skip."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY 없음 — 통합 테스트 skip")


@pytest.fixture
async def integration_client(pg_session: Any):  # type: ignore[return]
    """실제 DB session + 실제 LLM client 를 사용하는 통합 테스트 클라이언트.

    tenant_ctx 는 TEST_TENANT_A / TEST_WORKSPACE_A 로 고정 (conftest 시드 데이터와 일치).
    get_db 는 pg_session 으로 오버라이드 — rollback 기반 격리.
    """
    from worksheet_api.db import get_db

    async def _get_db():  # type: ignore[return]
        yield pg_session

    async def _get_tenant() -> TenantContext:
        return TenantContext(tenant_id=TEST_TENANT_A, workspace_id=TEST_WORKSPACE_A)

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_tenant_context] = _get_tenant

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_e2e_text_extract_then_get(
    integration_client: AsyncClient,
    _skip_if_no_api_key: None,
) -> None:
    """end-to-end: POST /passages/extract (text) → DB 저장 → GET /{id} 조회.

    추출 결과가 DB 에 올바르게 저장되고, GET 으로 동일 데이터를 반환하는지 검증.
    실제 LLM 을 호출하므로 최소 토큰 텍스트 사용.
    """
    # 1. 추출 요청 — 짧은 텍스트로 비용 최소화
    extract_resp = await integration_client.post(
        "/passages/extract",
        json={
            "kind": "text",
            "payload": "The sun rises in the east. This is a simple English sentence.",
        },
    )
    assert extract_resp.status_code == 200, f"extract failed: {extract_resp.text}"

    body = extract_resp.json()
    assert len(body["results"]) >= 1

    passage_id = body["results"][0]["passage"]["id"]

    # 2. GET 으로 조회 — 동일 데이터 반환 확인
    get_resp = await integration_client.get(f"/passages/{passage_id}")
    assert get_resp.status_code == 200, f"get failed: {get_resp.text}"

    get_body = get_resp.json()
    assert get_body["passage"]["id"] == passage_id
    # tenant_id 는 TEST_TENANT_A
    assert get_body["passage"]["tenant_id"] == str(TEST_TENANT_A)


@pytest.mark.asyncio
async def test_e2e_multitenant_isolation(pg_session: Any) -> None:
    """멀티테넌트 격리 — TENANT_A 가 저장한 Passage 를 TENANT_B 는 조회 불가.

    실제 DB 에서 tenant_id 필터가 올바르게 동작하는지 검증.
    LLM 호출 없이 PassageRepository 를 직접 사용.
    """
    ctx_a = TenantContext(tenant_id=TEST_TENANT_A, workspace_id=TEST_WORKSPACE_A)
    ctx_b = TenantContext(tenant_id=TEST_TENANT_B, workspace_id=TEST_WORKSPACE_B)

    repo_a = PassageRepository(pg_session, ctx_a)
    repo_b = PassageRepository(pg_session, ctx_b)

    # TENANT_A 로 Passage 저장
    passage_a = Passage(
        tenant_id=TEST_TENANT_A,
        workspace_id=TEST_WORKSPACE_A,
        body_text="Tenant A exclusive passage.",
        word_count=4,
        source=SourceMeta(provider=SourceProvider.USER_INPUT),
        target_grade=TargetGrade.HIGH_3,
    )
    saved = await repo_a.create(passage_a)
    await pg_session.flush()

    # TENANT_B 로 같은 passage_id 조회 → None (다른 tenant)
    result = await repo_b.get(saved.id)
    assert result is None, "멀티테넌트 격리 실패: TENANT_B 가 TENANT_A 의 Passage 를 조회했다"

    # TENANT_A 로 조회 → 성공
    result_a = await repo_a.get(saved.id)
    assert result_a is not None
    assert result_a.id == saved.id
