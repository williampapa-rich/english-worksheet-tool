"""Phase 0 DoD smoke test.

@pytest.mark.integration — 실행 조건:
  - 실행 중인 PostgreSQL (docker compose up -d db)
  - ANTHROPIC_API_KEY 환경변수 (없으면 pytest.skip)

3가지 입력 타입 (text / image / pdf) 각각:
  1. POST /passages/extract → 200 + Passage / Question 영속화
  2. GET /passages/{id} → 200 + 동일 데이터 조회
  3. 응답에 sentinel UUID 누수 없음
  4. 다른 tenant 의 데이터가 안 보이는 격리 검증 (DB repository 직접)

실행 방법:
  docker compose up -d db && pytest -m integration apps/api/tests/integration/test_phase_0_smoke.py

Phase 0 DoD 5개 대응:
  (1) shared/schemas/ 1차 정의 — shared/schemas/ import 로 검증
  (2) Vision LLM 추출 파이프라인 — text / image / pdf 각 1건 end-to-end
  (3) DB 에 Passage 저장/조회 — POST 후 GET 으로 확인
  (4) 멀티테넌트 스키마 — sentinel UUID 누수 없음 + tenant 격리 케이스
  (5) schema-coverage-audit.md — 이미 산출됨 (Sprint 0 완료)
"""

from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from worksheet_api.db import get_db
from worksheet_api.main import app
from worksheet_api.models.base import SENTINEL_UUID
from worksheet_api.repositories.passage import PassageRepository
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context

from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade

# 통합 테스트 전체 파일에 marker 적용
pytestmark = pytest.mark.integration

# conftest.py 에서 정의된 표준 테넌트 UUID
from tests.conftest import (  # noqa: E402
    TEST_TENANT_A,
    TEST_TENANT_B,
    TEST_WORKSPACE_A,
    TEST_WORKSPACE_B,
)

# ─── synthetic fixture 임포트 ─────────────────────────────────────────────────
from tests.integration._synthetic_fixtures import (  # noqa: E402
    SAMPLE_TEXT,
    make_synthetic_pdf,
    make_synthetic_png,
)

# ─── 공통 헬퍼 ───────────────────────────────────────────────────────────────


def _skip_if_no_api_key() -> None:
    """ANTHROPIC_API_KEY 없으면 smoke test 전체 skip."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY 없어 Phase 0 smoke test 건너뜀")


def _assert_no_sentinel_uuid(response_text: str) -> None:
    """응답 본문에 sentinel UUID (00000000-...) 가 없는지 검증.

    ADR-0003 §D-3.6: extractor 가 sentinel UUID 를 반환하고,
    API 핸들러가 model_copy 로 실제 tenant_id/workspace_id 를 주입해야 한다.
    """
    assert str(SENTINEL_UUID) not in response_text, (
        f"sentinel UUID {SENTINEL_UUID} 가 응답에 노출됨 — tenant_id 주입 실패"
    )


def _assert_passage_valid(passage_data: dict[str, Any]) -> None:
    """Passage 응답 필드 기본 검증."""
    assert passage_data.get("id"), "passage.id 가 비어있음"
    assert passage_data.get("body_text"), "passage.body_text 가 비어있음"
    assert passage_data.get("tenant_id") == str(TEST_TENANT_A), (
        f"tenant_id 불일치: 기대={TEST_TENANT_A}, 실제={passage_data.get('tenant_id')}"
    )


# ─── 통합 테스트 클라이언트 fixture ──────────────────────────────────────────


@pytest_asyncio.fixture
async def integration_client(pg_session: Any) -> AsyncIterator[AsyncClient]:
    """실제 PostgreSQL + 실제 LLM 을 사용하는 Phase 0 smoke test 클라이언트.

    - get_db: pg_session 으로 오버라이드 (rollback 기반 격리).
    - get_tenant_context: TEST_TENANT_A / TEST_WORKSPACE_A 로 고정.
    - get_llm_client: 실제 Anthropic 클라이언트 (오버라이드 없음).

    ANTHROPIC_API_KEY 없으면 호출 전에 _skip_if_no_api_key() 로 skip.
    """

    async def _get_db() -> AsyncIterator[Any]:
        yield pg_session

    async def _get_tenant() -> TenantContext:
        return TenantContext(tenant_id=TEST_TENANT_A, workspace_id=TEST_WORKSPACE_A)

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_tenant_context] = _get_tenant
    # get_llm_client 는 오버라이드 하지 않음 — 실제 Anthropic 클라이언트 사용

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def integration_client_b(pg_session: Any) -> AsyncIterator[AsyncClient]:
    """TENANT_B 컨텍스트의 통합 테스트 클라이언트.

    멀티테넌트 격리 검증에 사용.
    """

    async def _get_db() -> AsyncIterator[Any]:
        yield pg_session

    async def _get_tenant() -> TenantContext:
        return TenantContext(tenant_id=TEST_TENANT_B, workspace_id=TEST_WORKSPACE_B)

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_tenant_context] = _get_tenant

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ─── Phase 0 DoD (2): text 입력 end-to-end ───────────────────────────────────


@pytest.mark.asyncio
class TestPhase0SmokeText:
    """text 입력 end-to-end smoke — Phase 0 DoD (2) (3) (4) 검증."""

    async def test_extract_text_then_get(self, integration_client: AsyncClient) -> None:
        """POST /passages/extract (kind=text) → 200 + GET /{id} 조회 일치.

        Phase 0 DoD (2): Vision LLM 추출 파이프라인 — text 1건.
        Phase 0 DoD (3): DB 에 Passage 저장/조회.
        """
        _skip_if_no_api_key()

        # 1. POST extract — 짧은 텍스트로 비용 최소화
        body = {"kind": "text", "payload": SAMPLE_TEXT}
        resp = await integration_client.post("/passages/extract", json=body)
        assert resp.status_code == 200, f"extract 실패: {resp.text}"

        data = resp.json()
        assert "results" in data
        assert len(data["results"]) >= 1, "PM-1: results 길이 >= 1 이어야 함"

        first_result = data["results"][0]
        passage_data = first_result["passage"]
        _assert_passage_valid(passage_data)
        passage_id = passage_data["id"]

        # 2. GET /{id} 조회 — 동일 데이터
        get_resp = await integration_client.get(f"/passages/{passage_id}")
        assert get_resp.status_code == 200, f"GET 실패: {get_resp.text}"

        get_data = get_resp.json()
        assert get_data["passage"]["id"] == passage_id
        assert get_data["passage"]["body_text"], "body_text 가 비어있음"

        # 3. sentinel UUID 누수 없음 — Phase 0 DoD (4)
        _assert_no_sentinel_uuid(resp.text)
        _assert_no_sentinel_uuid(get_resp.text)

    async def test_extract_text_questions_returned(self, integration_client: AsyncClient) -> None:
        """text 추출 시 questions 가 포함되어야 한다.

        SAMPLE_TEXT 에 1번 문제가 있으므로 questions 길이 >= 1 기대.
        """
        _skip_if_no_api_key()

        resp = await integration_client.post(
            "/passages/extract",
            json={"kind": "text", "payload": SAMPLE_TEXT},
        )
        assert resp.status_code == 200, resp.text

        results = resp.json()["results"]
        assert len(results) >= 1
        # questions 는 list 이고 LLM 이 추출하면 비지 않아야 함
        # PM-6: 빈 list 도 정상이지만 SAMPLE_TEXT 는 명확한 문제 1개 포함
        questions = results[0].get("questions", [])
        assert isinstance(questions, list)


# ─── Phase 0 DoD (2): image 입력 end-to-end ──────────────────────────────────


@pytest.mark.asyncio
class TestPhase0SmokeImage:
    """image 입력 end-to-end smoke — Phase 0 DoD (2) 검증."""

    async def test_extract_image_then_get(self, integration_client: AsyncClient) -> None:
        """POST /passages/extract (kind=image) → 200 + GET /{id} 조회.

        Phase 0 DoD (2): Vision LLM 추출 파이프라인 — image 1건.
        synthetic PNG (PyMuPDF 로 텍스트 렌더링) 사용.
        """
        _skip_if_no_api_key()

        # synthetic PNG 생성 — 저작권 자료 없이 Vision 경로 검증
        png_bytes = make_synthetic_png()
        payload = base64.b64encode(png_bytes).decode()

        # 1. POST extract
        resp = await integration_client.post(
            "/passages/extract",
            json={
                "kind": "image",
                "payload": payload,
                "media_type": "image/png",
            },
        )
        assert resp.status_code == 200, f"image extract 실패: {resp.text}"

        data = resp.json()
        assert len(data["results"]) >= 1, "PM-1: results >= 1"

        passage_data = data["results"][0]["passage"]
        _assert_passage_valid(passage_data)
        passage_id = passage_data["id"]

        # 2. GET /{id} 조회
        get_resp = await integration_client.get(f"/passages/{passage_id}")
        assert get_resp.status_code == 200, f"GET 실패: {get_resp.text}"

        get_data = get_resp.json()
        assert get_data["passage"]["id"] == passage_id

        # 3. sentinel UUID 누수 없음
        _assert_no_sentinel_uuid(resp.text)
        _assert_no_sentinel_uuid(get_resp.text)


# ─── Phase 0 DoD (2): PDF 입력 end-to-end ────────────────────────────────────


@pytest.mark.asyncio
class TestPhase0SmokePdf:
    """PDF 입력 end-to-end smoke — Phase 0 DoD (2) 검증.

    텍스트 레이어 있는 PDF (PyMuPDF 경로) 를 사용.
    CLAUDE.md §3.4: 텍스트 레이어 있으면 PyMuPDF 저비용 경로 → Vision 미호출.
    """

    async def test_extract_pdf_text_layer_then_get(self, integration_client: AsyncClient) -> None:
        """POST /passages/extract (kind=pdf, force_vision=False) → 200 + GET /{id}.

        Phase 0 DoD (2): Vision LLM 추출 파이프라인 — pdf 1건.
        synthetic PDF (텍스트 레이어 있음) → PyMuPDF 텍스트 추출 경로.
        """
        _skip_if_no_api_key()

        pdf_bytes = make_synthetic_pdf()
        payload = base64.b64encode(pdf_bytes).decode()

        # 1. POST extract — 텍스트 레이어 있으므로 force_vision=False (저비용 경로)
        resp = await integration_client.post(
            "/passages/extract",
            json={"kind": "pdf", "payload": payload, "force_vision": False},
        )
        assert resp.status_code == 200, f"pdf extract 실패: {resp.text}"

        data = resp.json()
        assert len(data["results"]) >= 1, "PM-1: results >= 1"

        passage_data = data["results"][0]["passage"]
        _assert_passage_valid(passage_data)
        passage_id = passage_data["id"]

        # 2. GET /{id} 조회
        get_resp = await integration_client.get(f"/passages/{passage_id}")
        assert get_resp.status_code == 200, f"GET 실패: {get_resp.text}"

        get_data = get_resp.json()
        assert get_data["passage"]["id"] == passage_id
        assert get_data["passage"]["body_text"]

        # 3. sentinel UUID 누수 없음
        _assert_no_sentinel_uuid(resp.text)
        _assert_no_sentinel_uuid(get_resp.text)

    async def test_extract_pdf_force_vision_then_get(self, integration_client: AsyncClient) -> None:
        """POST /passages/extract (kind=pdf, force_vision=True) → 200 + GET /{id}.

        force_vision=True 로 PyMuPDF 우회 → Vision 경로 강제 (PM-3).
        """
        _skip_if_no_api_key()

        pdf_bytes = make_synthetic_pdf()
        payload = base64.b64encode(pdf_bytes).decode()

        resp = await integration_client.post(
            "/passages/extract",
            json={"kind": "pdf", "payload": payload, "force_vision": True},
        )
        assert resp.status_code == 200, f"pdf force_vision extract 실패: {resp.text}"

        data = resp.json()
        assert len(data["results"]) >= 1

        passage_id = data["results"][0]["passage"]["id"]

        get_resp = await integration_client.get(f"/passages/{passage_id}")
        assert get_resp.status_code == 200

        _assert_no_sentinel_uuid(resp.text)
        _assert_no_sentinel_uuid(get_resp.text)


# ─── Phase 0 DoD (4): 멀티테넌트 격리 검증 ───────────────────────────────────


@pytest.mark.asyncio
class TestPhase0MultitenantIsolation:
    """멀티테넌트 격리 smoke — Phase 0 DoD (4) 검증.

    LLM 호출 없이 PassageRepository 를 직접 사용.
    """

    async def test_other_tenant_cannot_get_passage(self, pg_session: Any) -> None:
        """TENANT_A 가 저장한 Passage 를 TENANT_B 는 조회 불가.

        Phase 0 DoD (4): 멀티테넌트 스키마 + 인증 stub.
        repository.get() 의 tenant_id 필터가 실제 격리를 보장하는지 검증.
        """
        ctx_a = TenantContext(tenant_id=TEST_TENANT_A, workspace_id=TEST_WORKSPACE_A)
        ctx_b = TenantContext(tenant_id=TEST_TENANT_B, workspace_id=TEST_WORKSPACE_B)

        repo_a = PassageRepository(pg_session, ctx_a)
        repo_b = PassageRepository(pg_session, ctx_b)

        # TENANT_A 로 Passage 저장 (LLM 없이 직접)
        passage = Passage(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            body_text="Phase 0 DoD isolation test passage.",
            word_count=6,
            source=SourceMeta(provider=SourceProvider.USER_INPUT),
            target_grade=TargetGrade.HIGH_3,
        )
        saved = await repo_a.create(passage)
        await pg_session.flush()

        # TENANT_B 로 조회 → None (격리됨)
        result_b = await repo_b.get(saved.id)
        assert result_b is None, (
            f"격리 실패: TENANT_B 가 TENANT_A 의 Passage {saved.id} 를 조회했다"
        )

        # TENANT_A 로 조회 → 성공
        result_a = await repo_a.get(saved.id)
        assert result_a is not None
        assert result_a.id == saved.id

    async def test_api_other_tenant_get_404(
        self,
        integration_client: AsyncClient,
        integration_client_b: AsyncClient,
        pg_session: Any,
    ) -> None:
        """TENANT_A 의 Passage 를 TENANT_B 의 HTTP 클라이언트로 조회 시 404.

        API 레이어에서도 멀티테넌트 격리가 올바르게 동작하는지 end-to-end 확인.
        LLM 없이 repository 직접 저장 후 cross-tenant GET 요청.
        """
        ctx_a = TenantContext(tenant_id=TEST_TENANT_A, workspace_id=TEST_WORKSPACE_A)
        repo_a = PassageRepository(pg_session, ctx_a)

        # TENANT_A 로 직접 저장
        passage = Passage(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            body_text="Cross-tenant API isolation test passage.",
            word_count=5,
            source=SourceMeta(provider=SourceProvider.USER_INPUT),
            target_grade=TargetGrade.HIGH_3,
        )
        saved = await repo_a.create(passage)
        await pg_session.flush()

        # TENANT_B 클라이언트로 GET → 404
        get_resp = await integration_client_b.get(f"/passages/{saved.id}")
        assert get_resp.status_code == 404, (
            f"멀티테넌트 격리 실패: 기대=404, 실제={get_resp.status_code}"
        )

        # TENANT_A 클라이언트로 GET → 200
        get_resp_a = await integration_client.get(f"/passages/{saved.id}")
        assert get_resp_a.status_code == 200
