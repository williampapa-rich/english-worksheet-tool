"""PDF 추출 통합 테스트 — 실제 Anthropic API + 실제 PDF 파일 사용.

@pytest.mark.integration 마킹. CI / 일반 단위 테스트 실행에서는 skip.

실행 방법:
  ANTHROPIC_API_KEY=sk-... uv run pytest -m integration -v

fixture 경로:
  - text-layer: admin/fixtures/extractor/pdf/text-layer/
    PM-7: PM 이 수집 완료. 변형문제 / 상세분석 폴더.
  - scanned: admin/fixtures/extractor/pdf/scanned/
    PM-7: PM 이 수집 진행 중. 현재 비어있음 — pytest.skip 으로 graceful 처리.

테스트 케이스:
  1. text-layer 케이스 — 휴리스틱 통과 + 텍스트 경로 → ExtractionResult 검증.
  2. scanned 케이스 — 휴리스틱 미통과 + Vision fallback → ExtractionResult 검증.
     (자료 없으면 pytest.skip)
  3. force_vision=True 케이스 — text-layer 자료를 force_vision 으로 → Vision 경로.

ADR-0003 §D-3.3: PDF 분기 로직.
PM-7: fixture 경로 규약.
"""

from __future__ import annotations

import os
import pathlib

import pytest
from extractor.base import SENTINEL_UUID
from extractor.pdf import extract_from_pdf

# fixture 디렉토리 경로
_FIXTURE_ROOT = (
    pathlib.Path(__file__).parent.parent.parent.parent / "admin" / "fixtures" / "extractor" / "pdf"
)

_TEXT_LAYER_DIR = _FIXTURE_ROOT / "text-layer"
_SCANNED_DIR = _FIXTURE_ROOT / "scanned"


def _find_first_pdf(directory: pathlib.Path) -> pathlib.Path | None:
    """디렉토리에서 첫 번째 PDF 파일을 재귀 검색해 반환.

    파일이 없으면 None.
    """
    if not directory.exists():
        return None
    for path in sorted(directory.rglob("*.pdf")):
        if path.is_file():
            return path
    return None


def _get_api_key() -> str | None:
    """ANTHROPIC_API_KEY 환경변수를 반환. 없으면 None."""
    return os.environ.get("ANTHROPIC_API_KEY")


@pytest.mark.integration
class TestPdfTextLayerIntegration:
    """text-layer PDF 통합 테스트.

    admin/fixtures/extractor/pdf/text-layer/ 에 PDF 가 있어야 실행.
    없으면 pytest.skip.
    """

    @pytest.fixture(autouse=True)
    def skip_if_no_api_key(self) -> None:
        """ANTHROPIC_API_KEY 없으면 skip."""
        if not _get_api_key():
            pytest.skip("ANTHROPIC_API_KEY 환경변수 없음 — 통합 테스트 skip")

    @pytest.fixture(autouse=True)
    def skip_if_no_fixture(self) -> None:
        """text-layer fixture PDF 없으면 skip."""
        if _find_first_pdf(_TEXT_LAYER_DIR) is None:
            pytest.skip(
                f"통합 테스트 skip: {_TEXT_LAYER_DIR} 에 PDF fixture 없음. "
                "admin/fixtures/extractor/pdf/text-layer/ 에 PDF 파일을 추가하세요."
            )

    @pytest.mark.asyncio
    async def test_text_layer_pdf_returns_extraction_result(self) -> None:
        """text-layer PDF → ExtractionResult 반환 (최소 1개).

        휴리스틱이 통과하면 텍스트 경로로 분기, ExtractionResult 검증.
        """
        from llm.client import AnthropicStructuredLLMClient

        pdf_path = _find_first_pdf(_TEXT_LAYER_DIR)
        assert pdf_path is not None
        pdf_bytes = pdf_path.read_bytes()

        client = AnthropicStructuredLLMClient(api_key=_get_api_key())
        results = await extract_from_pdf(pdf_bytes, llm_client=client)

        assert isinstance(results, list)
        assert len(results) >= 1, "최소 1개 ExtractionResult 반환"

    @pytest.mark.asyncio
    async def test_text_layer_passage_not_empty(self) -> None:
        """추출된 Passage 의 body_text 가 비어있지 않다."""
        from llm.client import AnthropicStructuredLLMClient

        pdf_path = _find_first_pdf(_TEXT_LAYER_DIR)
        assert pdf_path is not None
        pdf_bytes = pdf_path.read_bytes()

        client = AnthropicStructuredLLMClient(api_key=_get_api_key())
        results = await extract_from_pdf(pdf_bytes, llm_client=client)

        for result in results:
            assert result.passage.body_text.strip(), "body_text 가 비어있음"

    @pytest.mark.asyncio
    async def test_text_layer_sentinel_uuid(self) -> None:
        """text-layer 추출 결과도 sentinel UUID (ADR-0003 §D-3.6)."""
        from llm.client import AnthropicStructuredLLMClient

        pdf_path = _find_first_pdf(_TEXT_LAYER_DIR)
        assert pdf_path is not None
        pdf_bytes = pdf_path.read_bytes()

        client = AnthropicStructuredLLMClient(api_key=_get_api_key())
        results = await extract_from_pdf(pdf_bytes, llm_client=client)

        for result in results:
            assert result.passage.tenant_id == SENTINEL_UUID
            assert result.passage.workspace_id == SENTINEL_UUID

    @pytest.mark.asyncio
    async def test_text_layer_extraction_meta_present(self) -> None:
        """ExtractionResult 에 extraction_meta 가 담긴다."""
        from llm.client import AnthropicStructuredLLMClient

        pdf_path = _find_first_pdf(_TEXT_LAYER_DIR)
        assert pdf_path is not None
        pdf_bytes = pdf_path.read_bytes()

        client = AnthropicStructuredLLMClient(api_key=_get_api_key())
        results = await extract_from_pdf(pdf_bytes, llm_client=client)

        for result in results:
            assert result.extraction_meta is not None
            assert result.extraction_meta.model != ""


@pytest.mark.integration
class TestPdfScannedIntegration:
    """scanned PDF 통합 테스트.

    admin/fixtures/extractor/pdf/scanned/ 에 PDF 가 없으면 전체 skip.
    PM-7: PM 이 수집 진행 중. 자료 도착 후 별 PR 에서 활성화.
    """

    @pytest.fixture(autouse=True)
    def skip_if_no_api_key(self) -> None:
        """ANTHROPIC_API_KEY 없으면 skip."""
        if not _get_api_key():
            pytest.skip("ANTHROPIC_API_KEY 환경변수 없음 — 통합 테스트 skip")

    @pytest.fixture(autouse=True)
    def skip_if_no_scanned_fixture(self) -> None:
        """scanned PDF fixture 없으면 graceful skip.

        PM-7: scanned 자료 수집 진행 중 — 자료 도착 전 skip 이 정상.
        자료 도착 후 이 skip 을 제거하고 별 PR 에서 활성화.
        """
        if _find_first_pdf(_SCANNED_DIR) is None:
            pytest.skip(
                f"TODO(PM-7): scanned PDF fixture 없음 — {_SCANNED_DIR} 에 스캔본 PDF 추가 필요. "
                "PM 이 자료 수집 진행 중. 자료 도착 후 이 skip 제거."
            )

    @pytest.mark.asyncio
    async def test_scanned_pdf_uses_vision_fallback(self) -> None:
        """scanned PDF → 휴리스틱 미통과 → Vision fallback → ExtractionResult.

        스캔본은 텍스트 레이어가 없거나 품질이 낮아 Vision 경로로 분기된다.
        """
        from llm.client import AnthropicStructuredLLMClient

        pdf_path = _find_first_pdf(_SCANNED_DIR)
        assert pdf_path is not None
        pdf_bytes = pdf_path.read_bytes()

        client = AnthropicStructuredLLMClient(api_key=_get_api_key())
        results = await extract_from_pdf(pdf_bytes, llm_client=client)

        assert isinstance(results, list)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_scanned_pdf_passage_not_empty(self) -> None:
        """Vision 경로로 추출한 Passage 의 body_text 가 비어있지 않다."""
        from llm.client import AnthropicStructuredLLMClient

        pdf_path = _find_first_pdf(_SCANNED_DIR)
        assert pdf_path is not None
        pdf_bytes = pdf_path.read_bytes()

        client = AnthropicStructuredLLMClient(api_key=_get_api_key())
        results = await extract_from_pdf(pdf_bytes, llm_client=client)

        for result in results:
            assert result.passage.body_text.strip(), "body_text 가 비어있음 (Vision 경로)"


@pytest.mark.integration
class TestPdfForceVisionIntegration:
    """force_vision=True 케이스 — text-layer 자료를 Vision 경로로 강제 (PM-3)."""

    @pytest.fixture(autouse=True)
    def skip_if_no_api_key(self) -> None:
        """ANTHROPIC_API_KEY 없으면 skip."""
        if not _get_api_key():
            pytest.skip("ANTHROPIC_API_KEY 환경변수 없음 — 통합 테스트 skip")

    @pytest.fixture(autouse=True)
    def skip_if_no_fixture(self) -> None:
        """text-layer fixture PDF 없으면 skip."""
        if _find_first_pdf(_TEXT_LAYER_DIR) is None:
            pytest.skip(f"통합 테스트 skip: {_TEXT_LAYER_DIR} 에 PDF fixture 없음.")

    @pytest.mark.asyncio
    async def test_force_vision_returns_result(self) -> None:
        """text-layer PDF + force_vision=True → Vision 경로 → ExtractionResult."""
        from llm.client import AnthropicStructuredLLMClient

        pdf_path = _find_first_pdf(_TEXT_LAYER_DIR)
        assert pdf_path is not None
        pdf_bytes = pdf_path.read_bytes()

        client = AnthropicStructuredLLMClient(api_key=_get_api_key())
        results = await extract_from_pdf(pdf_bytes, llm_client=client, force_vision=True)

        assert isinstance(results, list)
        assert len(results) >= 1
        for result in results:
            assert result.passage.body_text.strip(), "force_vision 경로 body_text 비어있음"

    @pytest.mark.asyncio
    async def test_force_vision_sentinel_uuid(self) -> None:
        """force_vision 경로 결과도 sentinel UUID (ADR-0003 §D-3.6)."""
        from llm.client import AnthropicStructuredLLMClient

        pdf_path = _find_first_pdf(_TEXT_LAYER_DIR)
        assert pdf_path is not None
        pdf_bytes = pdf_path.read_bytes()

        client = AnthropicStructuredLLMClient(api_key=_get_api_key())
        results = await extract_from_pdf(pdf_bytes, llm_client=client, force_vision=True)

        for result in results:
            assert result.passage.tenant_id == SENTINEL_UUID
            assert result.passage.workspace_id == SENTINEL_UUID
