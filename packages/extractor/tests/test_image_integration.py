"""image.py — 이미지 입력 통합 테스트.

실제 Vision LLM 호출을 사용한다. 로컬 실행 전용.
CI / 일반 단위 테스트 실행에서는 @pytest.mark.integration 으로 skip.

실행 방법:
    ANTHROPIC_API_KEY=sk-... uv run pytest -m integration -v

fixture 위치: admin/fixtures/extractor/image/
  - 자료가 없으면 pytest.skip 으로 graceful 처리.
  - 자료가 있으면 실제 Vision 호출 후 ExtractionResult 검증.
"""

from __future__ import annotations

import pathlib

import pytest
from extractor.image import extract_from_image
from llm.client import AnthropicStructuredLLMClient

# fixture 디렉토리 — admin/fixtures/extractor/image/
_FIXTURE_DIR = (
    pathlib.Path(__file__).parent.parent.parent.parent
    / "admin"
    / "fixtures"
    / "extractor"
    / "image"
)

# 지원 확장자 → media_type 매핑
_EXT_TO_MEDIA_TYPE: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _find_fixture_image() -> tuple[bytes, str] | None:
    """admin/fixtures/extractor/image/ 에서 첫 번째 지원 이미지를 반환.

    Returns:
        (image_bytes, media_type) tuple. 이미지가 없으면 None.
    """
    if not _FIXTURE_DIR.exists():
        return None
    for path in sorted(_FIXTURE_DIR.iterdir()):
        media_type = _EXT_TO_MEDIA_TYPE.get(path.suffix.lower())
        if media_type is not None:
            return path.read_bytes(), media_type
    return None


@pytest.mark.integration
class TestImageExtractorIntegration:
    """실제 Vision LLM 호출 통합 테스트.

    admin/fixtures/extractor/image/ 에 이미지가 없으면 전체 skip.
    """

    @pytest.fixture(autouse=True)
    def skip_if_no_fixture(self) -> None:
        """fixture 이미지가 없으면 이 클래스의 모든 테스트 skip."""
        if _find_fixture_image() is None:
            pytest.skip(
                f"통합 테스트 skip: {_FIXTURE_DIR} 에 이미지 fixture 없음. "
                "admin/fixtures/extractor/image/ 에 .png/.jpg/.webp 파일을 추가하세요."
            )

    @pytest.mark.asyncio
    async def test_extract_returns_list(self) -> None:
        """실제 Vision 호출 → list[ExtractionResult] 반환 (PM-1)."""
        fixture = _find_fixture_image()
        assert fixture is not None  # autouse fixture 가 보장
        image_bytes, media_type = fixture

        client = AnthropicStructuredLLMClient()
        results = await extract_from_image(image_bytes, media_type, llm_client=client)

        assert isinstance(results, list)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_extract_passage_not_empty(self) -> None:
        """추출된 Passage 의 body_text 가 비어있지 않다."""
        fixture = _find_fixture_image()
        assert fixture is not None
        image_bytes, media_type = fixture

        client = AnthropicStructuredLLMClient()
        results = await extract_from_image(image_bytes, media_type, llm_client=client)

        for result in results:
            assert result.passage.body_text.strip(), "body_text 가 비어있음"

    @pytest.mark.asyncio
    async def test_extract_has_questions_or_passage(self) -> None:
        """추출 결과에 지문이 있거나 문제가 있어야 한다."""
        fixture = _find_fixture_image()
        assert fixture is not None
        image_bytes, media_type = fixture

        client = AnthropicStructuredLLMClient()
        results = await extract_from_image(image_bytes, media_type, llm_client=client)

        # 최소 1개 결과에 지문 또는 문제가 있어야 함
        has_content = any(r.passage.body_text.strip() or r.questions for r in results)
        assert has_content, "추출 결과에 지문도 문제도 없음"

    @pytest.mark.asyncio
    async def test_sentinel_uuid_in_output(self) -> None:
        """Vision 추출 결과도 sentinel UUID 를 가진다 (ADR-0003 §D-3.6)."""
        from extractor.base import SENTINEL_UUID

        fixture = _find_fixture_image()
        assert fixture is not None
        image_bytes, media_type = fixture

        client = AnthropicStructuredLLMClient()
        results = await extract_from_image(image_bytes, media_type, llm_client=client)

        for result in results:
            assert result.passage.tenant_id == SENTINEL_UUID
            assert result.passage.workspace_id == SENTINEL_UUID

    @pytest.mark.asyncio
    async def test_extraction_meta_present(self) -> None:
        """ExtractionResult 에 extraction_meta 가 담긴다."""
        fixture = _find_fixture_image()
        assert fixture is not None
        image_bytes, media_type = fixture

        client = AnthropicStructuredLLMClient()
        results = await extract_from_image(image_bytes, media_type, llm_client=client)

        for result in results:
            assert result.extraction_meta is not None
            assert result.extraction_meta.prompt_template_id == "extract-image-v0"
