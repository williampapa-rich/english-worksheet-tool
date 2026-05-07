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
from shared.schemas.translation import Translation, TranslationCreatedBy
from shared.schemas.vocabulary import Vocabulary, VocabularySelectedBy

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


def _make_extraction_result(
    passage: Passage,
    *,
    translation: Translation | None = None,
    vocabulary: list[Vocabulary] | None = None,
) -> ExtractionResult:
    """ExtractionResult 헬퍼."""
    return ExtractionResult(
        passage=passage,
        questions=[],
        translation=translation,
        vocabulary=vocabulary or [],
        extraction_meta=ExtractionMetaRef(
            request_id=uuid.uuid4(),
            model="claude-sonnet-4-20250514",
            prompt_template_id="extract-text-v0",
            extracted_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        ),
    )


def _make_sentinel_translation(
    text: str = "경제는 꾸준히 성장하고 있다.",
) -> Translation:
    """sentinel UUID 로 채워진 Translation (extractor 출력 시뮬레이션)."""
    return Translation(
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        passage_id=SENTINEL_UUID,
        text=text,
        created_by=TranslationCreatedBy.LLM,
    )


def _make_saved_translation(
    passage_id: uuid.UUID = PASSAGE_ID_1,
    text: str = "경제는 꾸준히 성장하고 있다.",
) -> Translation:
    """repository.create() 반환값 시뮬레이션."""
    return Translation(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=passage_id,
        text=text,
        created_by=TranslationCreatedBy.LLM,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )


def _make_sentinel_vocabulary(word: str = "economy", meaning: str = "경제") -> Vocabulary:
    """sentinel UUID 로 채워진 Vocabulary (extractor 출력 시뮬레이션)."""
    return Vocabulary(
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        passage_id=SENTINEL_UUID,
        word=word,
        headword_normalized=word.lower(),
        meaning_ko=meaning,
        selected_by=VocabularySelectedBy.LLM,
    )


def _make_saved_vocabulary(
    passage_id: uuid.UUID = PASSAGE_ID_1,
    word: str = "economy",
    meaning: str = "경제",
) -> Vocabulary:
    """repository.create() 반환값 시뮬레이션."""
    return Vocabulary(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=passage_id,
        word=word,
        headword_normalized=word.lower(),
        meaning_ko=meaning,
        selected_by=VocabularySelectedBy.LLM,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
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
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
    ):
        prepo_instance = mock_prepo.return_value
        prepo_instance.get = AsyncMock(return_value=saved)
        qrepo_instance = mock_qrepo.return_value
        qrepo_instance.list_by_passage = AsyncMock(return_value=[])
        mock_trepo.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_vrepo.return_value.list_by_passage = AsyncMock(return_value=[])

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
        patch("worksheet_api.routers.passages.TranslationRepository"),
        patch("worksheet_api.routers.passages.VocabularyRepository"),
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
        patch("worksheet_api.routers.passages.TranslationRepository"),
        patch("worksheet_api.routers.passages.VocabularyRepository"),
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


# ─── B1 — Translation / Vocabulary 영속화 (옵션 B) 테스트 ────────────────────


@pytest.mark.asyncio
async def test_extract_persists_translation_when_present(async_client: AsyncClient) -> None:
    """extract 결과에 translation 이 있으면 TranslationRepository.create() 호출."""
    saved_passage = _make_saved_passage()
    saved_translation = _make_saved_translation(passage_id=saved_passage.id)
    sentinel_translation = _make_sentinel_translation()

    with (
        patch("worksheet_api.routers.passages.extract_from_text") as mock_ext,
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository"),
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
    ):
        mock_ext.return_value = [
            _make_extraction_result(_make_sentinel_passage(), translation=sentinel_translation)
        ]
        mock_prepo.return_value.create = AsyncMock(return_value=saved_passage)
        mock_trepo.return_value.create = AsyncMock(return_value=saved_translation)
        mock_vrepo.return_value.create = AsyncMock()

        resp = await async_client.post(
            "/passages/extract",
            json={"kind": "text", "payload": "The economy is growing steadily."},
        )

    assert resp.status_code == 200
    body = resp.json()
    # translation 응답 본문에 saved tenant/workspace + passage_id 채워짐
    assert body["results"][0]["translation"] is not None
    assert body["results"][0]["translation"]["tenant_id"] == str(TENANT_A)
    assert body["results"][0]["translation"]["passage_id"] == str(saved_passage.id)
    # repository.create() 가 정확히 한 번 호출됨 + sentinel 누수 없이 실제 tenant_id 주입
    mock_trepo.return_value.create.assert_awaited_once()
    create_arg = mock_trepo.return_value.create.await_args.args[0]
    assert create_arg.tenant_id == TENANT_A
    assert create_arg.workspace_id == WORKSPACE_A
    assert create_arg.passage_id == saved_passage.id


@pytest.mark.asyncio
async def test_extract_skips_translation_when_none(async_client: AsyncClient) -> None:
    """extract 결과에 translation 이 없으면 TranslationRepository.create() 미호출 (PM-6)."""
    saved_passage = _make_saved_passage()

    with (
        patch("worksheet_api.routers.passages.extract_from_text") as mock_ext,
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository"),
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
    ):
        mock_ext.return_value = [_make_extraction_result(_make_sentinel_passage())]
        mock_prepo.return_value.create = AsyncMock(return_value=saved_passage)
        mock_trepo.return_value.create = AsyncMock()
        mock_vrepo.return_value.create = AsyncMock()

        resp = await async_client.post(
            "/passages/extract",
            json={"kind": "text", "payload": "The economy is growing steadily."},
        )

    assert resp.status_code == 200
    assert resp.json()["results"][0]["translation"] is None
    mock_trepo.return_value.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_persists_vocabulary_list(async_client: AsyncClient) -> None:
    """extract 결과의 vocabulary list 가 모두 VocabularyRepository.create() 로 저장."""
    saved_passage = _make_saved_passage()
    sentinel_vocab_1 = _make_sentinel_vocabulary("economy", "경제")
    sentinel_vocab_2 = _make_sentinel_vocabulary("growing", "성장하는")
    saved_vocab_1 = _make_saved_vocabulary(saved_passage.id, "economy", "경제")
    saved_vocab_2 = _make_saved_vocabulary(saved_passage.id, "growing", "성장하는")

    with (
        patch("worksheet_api.routers.passages.extract_from_text") as mock_ext,
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository"),
        patch("worksheet_api.routers.passages.TranslationRepository"),
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
    ):
        mock_ext.return_value = [
            _make_extraction_result(
                _make_sentinel_passage(),
                vocabulary=[sentinel_vocab_1, sentinel_vocab_2],
            )
        ]
        mock_prepo.return_value.create = AsyncMock(return_value=saved_passage)
        mock_vrepo.return_value.create = AsyncMock(side_effect=[saved_vocab_1, saved_vocab_2])

        resp = await async_client.post(
            "/passages/extract",
            json={"kind": "text", "payload": "The economy is growing steadily."},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"][0]["vocabulary"]) == 2
    assert mock_vrepo.return_value.create.await_count == 2
    # 두 호출 모두 실제 tenant_id / passage_id 주입 확인
    for call in mock_vrepo.return_value.create.await_args_list:
        v = call.args[0]
        assert v.tenant_id == TENANT_A
        assert v.workspace_id == WORKSPACE_A
        assert v.passage_id == saved_passage.id


@pytest.mark.asyncio
async def test_extract_skips_vocabulary_when_empty(async_client: AsyncClient) -> None:
    """extract 결과의 vocabulary 가 빈 list 면 VocabularyRepository.create() 미호출 (PM-6)."""
    saved_passage = _make_saved_passage()

    with (
        patch("worksheet_api.routers.passages.extract_from_text") as mock_ext,
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository"),
        patch("worksheet_api.routers.passages.TranslationRepository"),
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
    ):
        mock_ext.return_value = [_make_extraction_result(_make_sentinel_passage())]
        mock_prepo.return_value.create = AsyncMock(return_value=saved_passage)
        mock_vrepo.return_value.create = AsyncMock()

        resp = await async_client.post(
            "/passages/extract",
            json={"kind": "text", "payload": "The economy is growing steadily."},
        )

    assert resp.status_code == 200
    assert resp.json()["results"][0]["vocabulary"] == []
    mock_vrepo.return_value.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_passage_returns_translation_and_vocabulary(
    async_client: AsyncClient,
) -> None:
    """GET /{id} 가 DB 의 translation / vocabulary 를 함께 조회해 응답."""
    saved_passage = _make_saved_passage()
    saved_translation = _make_saved_translation(passage_id=saved_passage.id)
    saved_vocab_1 = _make_saved_vocabulary(saved_passage.id, "economy", "경제")
    saved_vocab_2 = _make_saved_vocabulary(saved_passage.id, "growing", "성장하는")

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository") as mock_qrepo,
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_qrepo.return_value.list_by_passage = AsyncMock(return_value=[])
        mock_trepo.return_value.get_by_passage = AsyncMock(return_value=saved_translation)
        mock_vrepo.return_value.list_by_passage = AsyncMock(
            return_value=[saved_vocab_1, saved_vocab_2]
        )

        resp = await async_client.get(f"/passages/{PASSAGE_ID_1}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["translation"]["text"] == saved_translation.text
    assert body["translation"]["passage_id"] == str(saved_passage.id)
    assert len(body["vocabulary"]) == 2
    # tenant_ctx 기반 repo 호출 확인 — cross-tenant 방어
    mock_trepo.return_value.get_by_passage.assert_awaited_once_with(PASSAGE_ID_1)
    mock_vrepo.return_value.list_by_passage.assert_awaited_once_with(PASSAGE_ID_1)


@pytest.mark.asyncio
async def test_get_passage_empty_relations_when_no_translation(
    async_client: AsyncClient,
) -> None:
    """translation 이 DB 에 없으면 None, vocabulary 가 없으면 빈 list 반환 (PM-6)."""
    saved_passage = _make_saved_passage()

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.QuestionRepository") as mock_qrepo,
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_qrepo.return_value.list_by_passage = AsyncMock(return_value=[])
        mock_trepo.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_vrepo.return_value.list_by_passage = AsyncMock(return_value=[])

        resp = await async_client.get(f"/passages/{PASSAGE_ID_1}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["translation"] is None
    assert body["vocabulary"] == []


# ─── B3 — 보강 라우트 (ADR-0013) 테스트 ──────────────────────────────────────


def _make_llm_translation() -> Translation:
    """augment_translation 결과 시뮬레이션 — sentinel UUID 채움."""
    return Translation(
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        passage_id=SENTINEL_UUID,
        text="LLM 이 생성한 한국어 해석.",
        created_by=TranslationCreatedBy.LLM,
    )


def _make_llm_vocab(words: list[tuple[str, str]]) -> list[Vocabulary]:
    """augment_vocabulary 결과 시뮬레이션 — sentinel UUID 채움."""
    return [
        Vocabulary(
            tenant_id=SENTINEL_UUID,
            workspace_id=SENTINEL_UUID,
            passage_id=SENTINEL_UUID,
            word=w,
            headword_normalized=w.lower(),
            meaning_ko=m,
            selected_by=VocabularySelectedBy.LLM,
            user_edited=False,
        )
        for w, m in words
    ]


# ─── POST /passages/{id}/translation ────────────────────────────────────────


@pytest.mark.asyncio
async def test_augment_translation_creates_when_none(async_client: AsyncClient) -> None:
    """기존 translation 없음 → LLM 호출 + INSERT."""
    saved_passage = _make_saved_passage()
    saved_translation = _make_saved_translation(passage_id=saved_passage.id)

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
        patch("worksheet_api.routers.passages.augment_translation") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_trepo.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_trepo.return_value.create = AsyncMock(return_value=saved_translation)
        mock_aug.return_value = _make_llm_translation()

        resp = await async_client.post(f"/passages/{saved_passage.id}/translation")

    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == saved_translation.text
    assert body["passage_id"] == str(saved_passage.id)
    mock_aug.assert_awaited_once()
    mock_trepo.return_value.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_augment_translation_updates_when_llm_existing(async_client: AsyncClient) -> None:
    """기존 created_by=LLM → 덮어쓰기 (default mode)."""
    saved_passage = _make_saved_passage()
    existing = _make_saved_translation(passage_id=saved_passage.id, text="기존 LLM 해석")
    updated = _make_saved_translation(
        passage_id=saved_passage.id, text="LLM 이 생성한 한국어 해석."
    )

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
        patch("worksheet_api.routers.passages.augment_translation") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_trepo.return_value.get_by_passage = AsyncMock(return_value=existing)
        mock_trepo.return_value.update_text = AsyncMock(return_value=updated)
        mock_aug.return_value = _make_llm_translation()

        resp = await async_client.post(f"/passages/{saved_passage.id}/translation")

    assert resp.status_code == 200
    mock_aug.assert_awaited_once()
    mock_trepo.return_value.update_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_augment_translation_skip_if_user_edited(async_client: AsyncClient) -> None:
    """default mode: 기존 created_by=USER → LLM 호출 X + 기존 반환 (D4)."""
    saved_passage = _make_saved_passage()
    user_translation = Translation(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=saved_passage.id,
        text="사용자가 직접 수정한 해석",
        created_by=TranslationCreatedBy.USER,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
        patch("worksheet_api.routers.passages.augment_translation") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_trepo.return_value.get_by_passage = AsyncMock(return_value=user_translation)

        resp = await async_client.post(f"/passages/{saved_passage.id}/translation")

    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "사용자가 직접 수정한 해석"
    assert body["created_by"] == "user"
    mock_aug.assert_not_awaited()


@pytest.mark.asyncio
async def test_augment_translation_replace_overrides_user(async_client: AsyncClient) -> None:
    """mode=replace: created_by=USER 였어도 LLM 으로 덮어씀."""
    saved_passage = _make_saved_passage()
    user_translation = Translation(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=saved_passage.id,
        text="사용자 해석",
        created_by=TranslationCreatedBy.USER,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )
    updated = _make_saved_translation(
        passage_id=saved_passage.id, text="LLM 이 생성한 한국어 해석."
    )

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
        patch("worksheet_api.routers.passages.augment_translation") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_trepo.return_value.get_by_passage = AsyncMock(return_value=user_translation)
        mock_trepo.return_value.update_text = AsyncMock(return_value=updated)
        mock_aug.return_value = _make_llm_translation()

        resp = await async_client.post(f"/passages/{saved_passage.id}/translation?mode=replace")

    assert resp.status_code == 200
    mock_aug.assert_awaited_once()
    mock_trepo.return_value.update_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_augment_translation_skip_if_exists(async_client: AsyncClient) -> None:
    """mode=skip_if_exists: 기존 row 있으면 LLM 호출 X."""
    saved_passage = _make_saved_passage()
    existing = _make_saved_translation(passage_id=saved_passage.id, text="기존 해석")

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
        patch("worksheet_api.routers.passages.augment_translation") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_trepo.return_value.get_by_passage = AsyncMock(return_value=existing)

        resp = await async_client.post(
            f"/passages/{saved_passage.id}/translation?mode=skip_if_exists"
        )

    assert resp.status_code == 200
    assert resp.json()["text"] == "기존 해석"
    mock_aug.assert_not_awaited()


@pytest.mark.asyncio
async def test_augment_translation_passage_not_found_404(async_client: AsyncClient) -> None:
    """passage_id 없음 → 404, LLM 호출 X."""
    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.TranslationRepository"),
        patch("worksheet_api.routers.passages.augment_translation") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.post(f"/passages/{PASSAGE_ID_1}/translation")

    assert resp.status_code == 404
    mock_aug.assert_not_awaited()


@pytest.mark.asyncio
async def test_augment_translation_llm_timeout_504(async_client: AsyncClient) -> None:
    """LLMTimeoutError → 504."""
    from llm.errors import LLMTimeoutError

    saved_passage = _make_saved_passage()
    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
        patch("worksheet_api.routers.passages.augment_translation") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_trepo.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_aug.side_effect = LLMTimeoutError("LLM 호출 타임아웃")

        resp = await async_client.post(f"/passages/{saved_passage.id}/translation")

    assert resp.status_code == 504


# ─── E1-a — PATCH /passages/{id}/translation ────────────────────────────────


@pytest.mark.asyncio
async def test_patch_translation_updates_text_and_sets_user(
    async_client: AsyncClient,
) -> None:
    """E1-a: PATCH text 호출 시 update_text(created_by=USER) 호출."""
    saved_passage = _make_saved_passage()
    updated = Translation(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=saved_passage.id,
        text="사용자 수정 해석",
        created_by=TranslationCreatedBy.USER,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_trepo.return_value.update_text = AsyncMock(return_value=updated)

        resp = await async_client.patch(
            f"/passages/{saved_passage.id}/translation",
            json={"text": "사용자 수정 해석"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "사용자 수정 해석"
    assert body["created_by"] == "user"
    mock_trepo.return_value.update_text.assert_awaited_once()
    _args, kwargs = mock_trepo.return_value.update_text.call_args
    assert kwargs.get("created_by") == TranslationCreatedBy.USER


@pytest.mark.asyncio
async def test_patch_translation_404_when_passage_missing(
    async_client: AsyncClient,
) -> None:
    """E1-a: passage 없으면 404."""
    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=None)
        mock_trepo.return_value.update_text = AsyncMock()

        resp = await async_client.patch(
            f"/passages/{uuid.uuid4()}/translation",
            json={"text": "x"},
        )

    assert resp.status_code == 404
    mock_trepo.return_value.update_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_translation_404_when_translation_missing(
    async_client: AsyncClient,
) -> None:
    """E1-a: passage 는 있지만 translation row 없으면 404 (먼저 POST 로 생성하라는 안내)."""
    saved_passage = _make_saved_passage()

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.TranslationRepository") as mock_trepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_trepo.return_value.update_text = AsyncMock(return_value=None)

        resp = await async_client.patch(
            f"/passages/{saved_passage.id}/translation",
            json={"text": "x"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_translation_422_extra_field(async_client: AsyncClient) -> None:
    """E1-a: extra='forbid' — 정의되지 않은 필드 보내면 422."""
    saved_passage = _make_saved_passage()

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.TranslationRepository"),
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)

        resp = await async_client.patch(
            f"/passages/{saved_passage.id}/translation",
            json={"text": "x", "created_by": "user"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_translation_422_empty_text(async_client: AsyncClient) -> None:
    """E1-a: 빈 문자열 text 는 422 (min_length=1)."""
    saved_passage = _make_saved_passage()

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.TranslationRepository"),
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)

        resp = await async_client.patch(
            f"/passages/{saved_passage.id}/translation",
            json={"text": ""},
        )

    assert resp.status_code == 422


# ─── POST /passages/{id}/vocabulary ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_augment_vocabulary_default_mode_skip_user_collision(
    async_client: AsyncClient,
) -> None:
    """default skip_if_user_edited: USER 항목과 headword 충돌 → LLM 항목 skip."""
    saved_passage = _make_saved_passage()
    # 기존 USER 항목: 'economy'. LLM 결과: 'economy' + 'growing' → 'economy' skip.
    final_v1 = _make_saved_vocabulary(saved_passage.id, "growing", "성장하는")

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.augment_vocabulary") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_vrepo.return_value.list_user_edited_headwords = AsyncMock(return_value={"economy"})
        mock_aug.return_value = _make_llm_vocab([("economy", "경제"), ("growing", "성장하는")])
        mock_vrepo.return_value.create = AsyncMock(return_value=final_v1)
        mock_vrepo.return_value.list_by_passage = AsyncMock(return_value=[final_v1])
        mock_vrepo.return_value.delete_llm_for_passage = AsyncMock()

        resp = await async_client.post(f"/passages/{saved_passage.id}/vocabulary")

    assert resp.status_code == 200
    # USER 충돌 'economy' skip → create 1번만 (growing)
    assert mock_vrepo.return_value.create.await_count == 1
    create_arg = mock_vrepo.return_value.create.await_args.args[0]
    assert create_arg.headword_normalized == "growing"
    # delete_llm_for_passage 는 default mode 에서 호출 X
    mock_vrepo.return_value.delete_llm_for_passage.assert_not_awaited()


@pytest.mark.asyncio
async def test_augment_vocabulary_replace_deletes_llm_then_inserts(
    async_client: AsyncClient,
) -> None:
    """mode=replace: LLM 항목 DELETE 후 INSERT (USER 항목 보존은 repo 책임)."""
    saved_passage = _make_saved_passage()
    final_v1 = _make_saved_vocabulary(saved_passage.id, "economy", "경제")

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.augment_vocabulary") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_vrepo.return_value.delete_llm_for_passage = AsyncMock(return_value=2)
        mock_aug.return_value = _make_llm_vocab([("economy", "경제")])
        mock_vrepo.return_value.create = AsyncMock(return_value=final_v1)
        mock_vrepo.return_value.list_by_passage = AsyncMock(return_value=[final_v1])

        resp = await async_client.post(f"/passages/{saved_passage.id}/vocabulary?mode=replace")

    assert resp.status_code == 200
    mock_vrepo.return_value.delete_llm_for_passage.assert_awaited_once_with(saved_passage.id)
    assert mock_vrepo.return_value.create.await_count == 1


@pytest.mark.asyncio
async def test_augment_vocabulary_append_no_dedup(async_client: AsyncClient) -> None:
    """mode=append: 기존 그대로, LLM 결과 모두 INSERT (중복 무시)."""
    saved_passage = _make_saved_passage()
    final_v1 = _make_saved_vocabulary(saved_passage.id, "economy", "경제")

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.augment_vocabulary") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        # append 는 list_user_edited_headwords / delete 호출 안 함
        mock_aug.return_value = _make_llm_vocab([("economy", "경제"), ("economy", "경제 (중복)")])
        mock_vrepo.return_value.create = AsyncMock(return_value=final_v1)
        mock_vrepo.return_value.list_by_passage = AsyncMock(return_value=[final_v1])

        resp = await async_client.post(f"/passages/{saved_passage.id}/vocabulary?mode=append")

    assert resp.status_code == 200
    # append 는 LLM 결과 모두 INSERT — 중복 'economy' 도 둘 다 INSERT
    assert mock_vrepo.return_value.create.await_count == 2


@pytest.mark.asyncio
async def test_augment_vocabulary_dedup_within_llm_skip_user_edited_mode(
    async_client: AsyncClient,
) -> None:
    """skip_if_user_edited: LLM 결과 내 같은 headword 중복은 첫 항목만 INSERT."""
    saved_passage = _make_saved_passage()
    final_v1 = _make_saved_vocabulary(saved_passage.id, "economy", "경제")

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.augment_vocabulary") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_vrepo.return_value.list_user_edited_headwords = AsyncMock(return_value=set())
        mock_aug.return_value = _make_llm_vocab(
            [("economy", "경제"), ("economy", "경제 다른 의미")]
        )
        mock_vrepo.return_value.create = AsyncMock(return_value=final_v1)
        mock_vrepo.return_value.list_by_passage = AsyncMock(return_value=[final_v1])

        resp = await async_client.post(f"/passages/{saved_passage.id}/vocabulary")

    assert resp.status_code == 200
    # LLM 결과 내 중복 — 첫 항목만 INSERT
    assert mock_vrepo.return_value.create.await_count == 1


@pytest.mark.asyncio
async def test_augment_vocabulary_count_param_passed(async_client: AsyncClient) -> None:
    """count 파라미터가 augment_vocabulary 에 전달되는지 확인."""
    saved_passage = _make_saved_passage()

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.augment_vocabulary") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_vrepo.return_value.list_user_edited_headwords = AsyncMock(return_value=set())
        mock_aug.return_value = []
        mock_vrepo.return_value.list_by_passage = AsyncMock(return_value=[])

        resp = await async_client.post(f"/passages/{saved_passage.id}/vocabulary?count=15")

    assert resp.status_code == 200
    assert mock_aug.await_args.kwargs["count"] == 15


@pytest.mark.asyncio
async def test_augment_vocabulary_passage_not_found_404(async_client: AsyncClient) -> None:
    """passage_id 없음 → 404."""
    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository"),
        patch("worksheet_api.routers.passages.augment_vocabulary") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.post(f"/passages/{PASSAGE_ID_1}/vocabulary")

    assert resp.status_code == 404
    mock_aug.assert_not_awaited()


@pytest.mark.asyncio
async def test_augment_vocabulary_invalid_mode_422(async_client: AsyncClient) -> None:
    """mode 값 invalid → 422 (Pydantic Literal 검증)."""
    resp = await async_client.post(f"/passages/{PASSAGE_ID_1}/vocabulary?mode=invalid")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_augment_vocabulary_count_out_of_range_422(async_client: AsyncClient) -> None:
    """count > 30 → 422."""
    resp = await async_client.post(f"/passages/{PASSAGE_ID_1}/vocabulary?count=100")
    assert resp.status_code == 422


# ─── E1-b — PATCH /passages/{id}/vocabulary/{vid} ───────────────────────────


@pytest.mark.asyncio
async def test_patch_vocabulary_updates_fields_and_sets_user_edited(
    async_client: AsyncClient,
) -> None:
    """E1-b: 필드 부분 수정 + user_edited=True 자동 갱신."""
    saved_passage = _make_saved_passage()
    existing = _make_saved_vocabulary(saved_passage.id, "economy", "경제")
    updated = existing.model_copy(
        update={"meaning_ko": "사용자 수정 뜻", "user_edited": True}
    )

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_vrepo.return_value.get = AsyncMock(return_value=existing)
        mock_vrepo.return_value.update_fields = AsyncMock(return_value=updated)

        resp = await async_client.patch(
            f"/passages/{saved_passage.id}/vocabulary/{existing.id}",
            json={"meaning_ko": "사용자 수정 뜻"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["meaning_ko"] == "사용자 수정 뜻"
    assert body["user_edited"] is True
    mock_vrepo.return_value.update_fields.assert_awaited_once()


@pytest.mark.asyncio
async def test_patch_vocabulary_404_when_passage_missing(
    async_client: AsyncClient,
) -> None:
    """E1-b: passage 없으면 404."""
    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=None)
        mock_vrepo.return_value.update_fields = AsyncMock()

        resp = await async_client.patch(
            f"/passages/{uuid.uuid4()}/vocabulary/{uuid.uuid4()}",
            json={"word": "x"},
        )

    assert resp.status_code == 404
    mock_vrepo.return_value.update_fields.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_vocabulary_404_when_vocab_missing(
    async_client: AsyncClient,
) -> None:
    """E1-b: vocabulary 행 없으면 404."""
    saved_passage = _make_saved_passage()

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_vrepo.return_value.get = AsyncMock(return_value=None)
        mock_vrepo.return_value.update_fields = AsyncMock()

        resp = await async_client.patch(
            f"/passages/{saved_passage.id}/vocabulary/{uuid.uuid4()}",
            json={"word": "x"},
        )

    assert resp.status_code == 404
    mock_vrepo.return_value.update_fields.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_vocabulary_404_cross_passage(async_client: AsyncClient) -> None:
    """E1-b: vocabulary 의 passage_id 가 URL passage_id 와 불일치하면 404."""
    saved_passage = _make_saved_passage()
    other_passage_id = uuid.uuid4()
    existing = _make_saved_vocabulary(other_passage_id, "economy", "경제")

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)
        mock_vrepo.return_value.get = AsyncMock(return_value=existing)
        mock_vrepo.return_value.update_fields = AsyncMock()

        resp = await async_client.patch(
            f"/passages/{saved_passage.id}/vocabulary/{existing.id}",
            json={"word": "x"},
        )

    assert resp.status_code == 404
    mock_vrepo.return_value.update_fields.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_vocabulary_422_extra_field(async_client: AsyncClient) -> None:
    """E1-b: extra='forbid' — 정의되지 않은 필드 422."""
    saved_passage = _make_saved_passage()

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository"),
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=saved_passage)

        resp = await async_client.patch(
            f"/passages/{saved_passage.id}/vocabulary/{uuid.uuid4()}",
            json={"word": "x", "user_edited": False},
        )

    assert resp.status_code == 422
