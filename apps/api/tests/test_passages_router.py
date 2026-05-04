"""POST /passages/extract + GET /passages/{id} 단위 테스트.

mock LLM client + mock repository 로 실제 DB / Anthropic API 없이 실행한다.
커버 케이스 (12개 이상):
  - kind=text 정상
  - kind=image + media_type 정상
  - kind=pdf force_vision=False 정상
  - kind=pdf force_vision=True 정상
  - kind=image media_type 없음 → 422
  - 빈 payload → 422 (EmptyInputError)
  - LLM schema validation 실패 → 502
  - LLM timeout → 504
  - 다중 지문 응답 (PM-1) — list 길이 > 1
  - GET /{id} 정상 → 200
  - GET /{id} not found → 404
  - GET /{id} 다른 tenant → 404 (멀티테넌트 격리)
  - sentinel UUID 누수 방어 — 응답에 sentinel 없음
"""

from __future__ import annotations

import base64
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from worksheet_api.db import get_db
from worksheet_api.llm_setup import get_llm_client
from worksheet_api.main import app
from worksheet_api.models.base import SENTINEL_UUID
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context

from shared.schemas.extraction import ExtractionMetaRef, ExtractionResult
from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade

# ─── 테스트용 고정 UUID ──────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TENANT_B = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
WORKSPACE_B = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
PASSAGE_ID_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
PASSAGE_ID_2 = uuid.UUID("22222222-2222-2222-2222-222222222222")


# ─── 헬퍼 팩토리 ────────────────────────────────────────────────────────────


def _make_passage(
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
    passage_id: uuid.UUID = PASSAGE_ID_1,
    body_text: str = "The economy is growing steadily.",
) -> Passage:
    """테스트용 Passage 생성 헬퍼."""
    return Passage(
        id=passage_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        body_text=body_text,
        word_count=5,
        source=SourceMeta(provider=SourceProvider.EVALUATOR),
        target_grade=TargetGrade.HIGH_3,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )


def _make_sentinel_passage(body_text: str = "The economy is growing steadily.") -> Passage:
    """sentinel UUID 로 채워진 Passage (extractor 출력 시뮬레이션)."""
    return Passage(
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        body_text=body_text,
        word_count=5,
        source=SourceMeta(provider=SourceProvider.EVALUATOR),
        target_grade=TargetGrade.HIGH_3,
    )


def _make_extraction_result(passage: Passage) -> ExtractionResult:
    """ExtractionResult 헬퍼."""
    return ExtractionResult(
        passage=passage,
        questions=[],
        translation=None,
        vocabulary=[],
        extraction_meta=ExtractionMetaRef(
            request_id=uuid.uuid4(),
            model="claude-sonnet-4-20250514",
            prompt_template_id="extract-text-v0",
            extracted_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        ),
    )


def _make_saved_passage(passage_id: uuid.UUID = PASSAGE_ID_1) -> Passage:
    """repository.create() 반환값 시뮬레이션 — 실제 tenant_id 주입됨."""
    return _make_passage(
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=passage_id,
    )


# ─── 픽스처 ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session() -> AsyncMock:
    """트랜잭션 컨텍스트 매니저를 지원하는 mock AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    # async with session.begin(): 지원
    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = begin_cm
    return session


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """테스트 전용 mock LLM client."""
    return MagicMock()


@pytest.fixture
def tenant_ctx_a() -> TenantContext:
    """테넌트 A 컨텍스트."""
    return TenantContext(tenant_id=TENANT_A, workspace_id=WORKSPACE_A)


@pytest.fixture
def override_deps(
    mock_session: AsyncMock,
    mock_llm_client: MagicMock,
    tenant_ctx_a: TenantContext,
) -> dict[Any, Any]:
    """FastAPI dependency_overrides 딕셔너리 반환."""

    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def _get_tenant() -> TenantContext:
        return tenant_ctx_a

    def _get_llm() -> MagicMock:
        return mock_llm_client

    return {
        get_db: _get_db,
        get_tenant_context: _get_tenant,
        get_llm_client: _get_llm,
    }


@pytest.fixture
async def async_client(override_deps: dict[Any, Any]) -> AsyncGenerator[AsyncClient, None]:
    """의존성 오버라이드가 적용된 AsyncClient."""
    app.dependency_overrides.update(override_deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ─── POST /passages/extract 테스트 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_text_ok(async_client: AsyncClient, mock_session: AsyncMock) -> None:
    """kind=text 정상 케이스 → 200, results 길이 1."""
    saved = _make_saved_passage()

    with (
        patch("worksheet_api.routers.passages.extract_from_text") as mock_ext,
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository"),
    ):
        mock_ext.return_value = [_make_extraction_result(_make_sentinel_passage())]
        instance = mock_prepo.return_value
        instance.create = AsyncMock(return_value=saved)

        resp = await async_client.post(
            "/passages/extract",
            json={"kind": "text", "payload": "The economy is growing steadily."},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["passage"]["id"] == str(PASSAGE_ID_1)


@pytest.mark.asyncio
async def test_extract_image_ok(async_client: AsyncClient) -> None:
    """kind=image + media_type=image/png + base64 payload → 200."""
    saved = _make_saved_passage()
    dummy_image = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100).decode()

    with (
        patch("worksheet_api.routers.passages.extract_from_image") as mock_ext,
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository"),
    ):
        mock_ext.return_value = [_make_extraction_result(_make_sentinel_passage())]
        instance = mock_prepo.return_value
        instance.create = AsyncMock(return_value=saved)

        resp = await async_client.post(
            "/passages/extract",
            json={
                "kind": "image",
                "payload": dummy_image,
                "media_type": "image/png",
            },
        )

    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1


@pytest.mark.asyncio
async def test_extract_pdf_no_force_vision_ok(async_client: AsyncClient) -> None:
    """kind=pdf force_vision=False → 200."""
    saved = _make_saved_passage()
    dummy_pdf = base64.b64encode(b"%PDF-1.4 test").decode()

    with (
        patch("worksheet_api.routers.passages.extract_from_pdf") as mock_ext,
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository"),
    ):
        mock_ext.return_value = [_make_extraction_result(_make_sentinel_passage())]
        instance = mock_prepo.return_value
        instance.create = AsyncMock(return_value=saved)

        resp = await async_client.post(
            "/passages/extract",
            json={"kind": "pdf", "payload": dummy_pdf, "force_vision": False},
        )

    assert resp.status_code == 200
    # force_vision=False 로 호출됐는지 확인
    mock_ext.assert_awaited_once()
    call_kwargs = mock_ext.call_args.kwargs
    assert call_kwargs["force_vision"] is False


@pytest.mark.asyncio
async def test_extract_pdf_force_vision_ok(async_client: AsyncClient) -> None:
    """kind=pdf force_vision=True → 200, extractor 에 force_vision=True 전달."""
    saved = _make_saved_passage()
    dummy_pdf = base64.b64encode(b"%PDF-1.4 test").decode()

    with (
        patch("worksheet_api.routers.passages.extract_from_pdf") as mock_ext,
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository"),
    ):
        mock_ext.return_value = [_make_extraction_result(_make_sentinel_passage())]
        instance = mock_prepo.return_value
        instance.create = AsyncMock(return_value=saved)

        resp = await async_client.post(
            "/passages/extract",
            json={"kind": "pdf", "payload": dummy_pdf, "force_vision": True},
        )

    assert resp.status_code == 200
    call_kwargs = mock_ext.call_args.kwargs
    assert call_kwargs["force_vision"] is True


@pytest.mark.asyncio
async def test_extract_image_no_media_type_422(async_client: AsyncClient) -> None:
    """kind=image, media_type 없음 → 422 (EmptyInputError 매핑)."""
    dummy_image = base64.b64encode(b"\x89PNG" + b"\x00" * 10).decode()

    resp = await async_client.post(
        "/passages/extract",
        json={"kind": "image", "payload": dummy_image},
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_extract_empty_text_422(async_client: AsyncClient) -> None:
    """kind=text 빈 payload → 422 (EmptyInputError)."""
    from extractor.errors import EmptyInputError

    with patch("worksheet_api.routers.passages.extract_from_text") as mock_ext:
        mock_ext.side_effect = EmptyInputError("입력 텍스트가 비어있습니다.")

        resp = await async_client.post(
            "/passages/extract",
            json={"kind": "text", "payload": "   "},
        )

    assert resp.status_code == 422
    assert "비어있" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_extract_llm_schema_validation_502(async_client: AsyncClient) -> None:
    """LLMSchemaValidationError → 502."""
    from llm.errors import LLMSchemaValidationError

    with patch("worksheet_api.routers.passages.extract_from_text") as mock_ext:
        mock_ext.side_effect = LLMSchemaValidationError(
            "schema 위반",
            validation_error="field required",
            raw_response=None,
        )

        resp = await async_client.post(
            "/passages/extract",
            json={"kind": "text", "payload": "Some text content here."},
        )

    assert resp.status_code == 502
    assert "LLM" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_extract_llm_timeout_504(async_client: AsyncClient) -> None:
    """LLMTimeoutError → 504."""
    from llm.errors import LLMTimeoutError

    with patch("worksheet_api.routers.passages.extract_from_text") as mock_ext:
        mock_ext.side_effect = LLMTimeoutError("LLM 호출 타임아웃")

        resp = await async_client.post(
            "/passages/extract",
            json={"kind": "text", "payload": "Some text content here."},
        )

    assert resp.status_code == 504


@pytest.mark.asyncio
async def test_extract_multiple_passages_pm1(async_client: AsyncClient) -> None:
    """PM-1: 다중 지문 — results 길이 > 1."""
    saved_1 = _make_saved_passage(PASSAGE_ID_1)
    saved_2 = _make_saved_passage(PASSAGE_ID_2)

    sentinel_1 = _make_sentinel_passage("First passage text here.")
    sentinel_2 = _make_sentinel_passage("Second passage text here.")

    # create 가 두 번 호출되면 각각 다른 Passage 반환
    create_returns = [saved_1, saved_2]

    with (
        patch("worksheet_api.routers.passages.extract_from_text") as mock_ext,
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository"),
    ):
        mock_ext.return_value = [
            _make_extraction_result(sentinel_1),
            _make_extraction_result(sentinel_2),
        ]
        instance = mock_prepo.return_value
        instance.create = AsyncMock(side_effect=create_returns)

        resp = await async_client.post(
            "/passages/extract",
            json={"kind": "text", "payload": "First passage. Second passage."},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 2


@pytest.mark.asyncio
async def test_sentinel_uuid_not_in_response(async_client: AsyncClient) -> None:
    """sentinel UUID 누수 방어 — 응답에 sentinel (00000000-...) 이 없어야 한다.

    ADR-0003 §D-3.6: extractor 가 sentinel UUID 를 반환하고,
    API 핸들러가 model_copy 로 실제 tenant_id/workspace_id 를 주입.
    repository.create() 가 실제 값이 채워진 Passage 를 반환.
    """
    saved = _make_saved_passage()  # 실제 TENANT_A / WORKSPACE_A 로 채워진 Passage

    with (
        patch("worksheet_api.routers.passages.extract_from_text") as mock_ext,
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository"),
    ):
        mock_ext.return_value = [_make_extraction_result(_make_sentinel_passage())]
        instance = mock_prepo.return_value
        instance.create = AsyncMock(return_value=saved)

        resp = await async_client.post(
            "/passages/extract",
            json={"kind": "text", "payload": "The economy is growing steadily."},
        )

    assert resp.status_code == 200
    resp_text = resp.text
    # sentinel UUID 는 모두 0 으로 된 UUID
    assert str(SENTINEL_UUID) not in resp_text


# ─── GET /passages/{id} 테스트 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_passage_ok(async_client: AsyncClient) -> None:
    """GET /{id} 정상 → 200, passage 반환."""
    saved = _make_saved_passage()

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository") as mock_qrepo,
    ):
        prepo_instance = mock_prepo.return_value
        prepo_instance.get = AsyncMock(return_value=saved)
        qrepo_instance = mock_qrepo.return_value
        qrepo_instance.list_by_passage = AsyncMock(return_value=[])

        resp = await async_client.get(f"/passages/{PASSAGE_ID_1}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["passage"]["id"] == str(PASSAGE_ID_1)
    assert body["passage"]["tenant_id"] == str(TENANT_A)


@pytest.mark.asyncio
async def test_get_passage_not_found_404(async_client: AsyncClient) -> None:
    """GET /{id} not found → 404."""
    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository"),
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.get(f"/passages/{PASSAGE_ID_1}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_passage_other_tenant_404(async_client: AsyncClient) -> None:
    """GET /{id} 다른 tenant 소유 → 404 (멀티테넌트 격리).

    repository.get() 이 tenant_id 필터를 적용하므로,
    다른 tenant 의 Passage 는 None 을 반환 → 404.

    이 테스트는 repository 의 멀티테넌트 강제가 API 응답에 올바르게 전파되는지 검증.
    tenant_ctx 는 TENANT_A 이고, repository 는 TENANT_B 소유 Passage 에 대해 None 반환.
    """
    # tenant_ctx 는 TENANT_A 이므로 TENANT_B 소유 passage 는 None
    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository"),
    ):
        # repository 가 tenant 필터 후 None 반환 (다른 tenant 소유)
        mock_prepo.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.get(f"/passages/{PASSAGE_ID_2}")

    assert resp.status_code == 404
    # 존재 여부 노출 없이 단순 404
    assert "찾을 수 없" in resp.json()["detail"]


# ─── GET /passages/{id}/hwpx 테스트 (P1-9) ───────────────────────────────────


@pytest.mark.asyncio
async def test_download_passage_hwpx_ok(async_client: AsyncClient) -> None:
    """GET /{id}/hwpx 정상 → 200, application/hwp+zip + attachment header."""
    saved = _make_saved_passage()

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.SyntaxAnnotationRepository") as mock_arepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved)
        mock_arepo.return_value.list_by_passage = AsyncMock(return_value=[])

        resp = await async_client.get(f"/passages/{PASSAGE_ID_1}/hwpx")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/hwp+zip"
    assert "attachment" in resp.headers["content-disposition"]
    assert f"passage_{PASSAGE_ID_1}.hwpx" in resp.headers["content-disposition"]
    # ZIP magic bytes (HWPX 는 ZIP 컨테이너) — 첫 4바이트 PK\x03\x04
    assert resp.content[:2] == b"PK"


@pytest.mark.asyncio
async def test_download_passage_hwpx_not_found_404(async_client: AsyncClient) -> None:
    """GET /{id}/hwpx not found → 404."""
    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.SyntaxAnnotationRepository"),
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.get(f"/passages/{PASSAGE_ID_1}/hwpx")

    assert resp.status_code == 404
    assert "찾을 수 없" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_download_passage_hwpx_other_tenant_404(async_client: AsyncClient) -> None:
    """GET /{id}/hwpx 다른 tenant 소유 → 404 (멀티테넌트 격리).

    repository.get() 이 tenant_id 필터를 적용하므로 다른 tenant 의 Passage 는
    None → 404. annotation 도 같은 tenant_ctx 기반 repository 로 조회되므로
    cross-tenant 누수 차단.
    """
    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.SyntaxAnnotationRepository"),
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.get(f"/passages/{PASSAGE_ID_2}/hwpx")

    assert resp.status_code == 404
