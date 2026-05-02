"""pdf.py — extract_from_pdf 단위 테스트.

mock LLM client 로 실제 Anthropic API 호출 없이 동작 검증.
PyMuPDF 는 synthetic PDF 생성으로 실제 동작 검증 (fixture 파일 불필요).

테스트 대상:
  - _TextLayerQuality.is_extractable() — 4종 휴리스틱 로직 + 경계값
  - _assess_quality() — 비율 계산 정확도
  - _extract_text_layer() — PyMuPDF 텍스트 추출
  - extract_from_pdf() — 분기 동작 (텍스트 / Vision / force_vision)
  - PM-1: 다중 지문 / 다중 페이지 결과 평탄화
  - PM-3: force_vision 옵션
  - ADR-0003 §D-3.6: sentinel UUID

ADR-0003 §D-3.3: 4종 휴리스틱 + force_vision 분기.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import fitz  # PyMuPDF
import pytest
from extractor.base import SENTINEL_UUID
from extractor.errors import EmptyInputError, PdfParseError
from extractor.normalizer import (
    RawExtractionItem,
    RawExtractionResponse,
    RawPassage,
    make_llm_meta,
    normalize,
)
from extractor.pdf import (
    MAX_BROKEN_UNICODE_RATIO,
    MIN_CHARS_PER_PAGE,
    MIN_DENSITY_CHARS_PER_PAGE,
    MIN_ENGLISH_ALPHA_RATIO,
    VISION_DPI,
    _assess_quality,
    _extract_text_layer,
    _TextLayerQuality,
    extract_from_pdf,
)
from llm.usage import StructuredLLMResult, TokenUsage

from shared.schemas.extraction import ExtractionResult

# ─── 헬퍼 ────────────────────────────────────────────────────────────────────


def _make_llm_result(data: RawExtractionResponse) -> StructuredLLMResult[RawExtractionResponse]:
    """테스트용 StructuredLLMResult 생성."""
    return StructuredLLMResult(
        data=data,
        raw_response={"mocked": True},
        usage=TokenUsage(input_tokens=150, output_tokens=350),
        model="claude-sonnet-4-6",
        elapsed_ms=1000,
        request_id=uuid.uuid4(),
        parent_request_id=None,
    )


def _make_mock_client(response: RawExtractionResponse) -> AsyncMock:
    """extract_structured 를 mock 하는 LLM 클라이언트."""
    client = AsyncMock()
    client.extract_structured = AsyncMock(return_value=_make_llm_result(response))
    return client


def _simple_passage(text: str = "The sky is blue and the grass is green.") -> RawPassage:
    return RawPassage(
        body_text=text,
        paragraphs=[text],
        word_count=len(text.split()),
    )


def _make_single_item_response(text: str = "The sky is blue.") -> RawExtractionResponse:
    """단일 지문 RawExtractionResponse 생성 헬퍼."""
    return RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage(text))])


def _make_fake_extraction_results(
    count: int = 1, prompt_id: str = "extract-image-v0"
) -> list[ExtractionResult]:
    """테스트용 ExtractionResult 리스트 생성.

    normalizer.normalize() 를 통하지 않고 직접 만들어 테스트 독립성 유지.
    """
    raw = RawExtractionResponse(
        items=[
            RawExtractionItem(
                passage=_simple_passage(f"Passage {i} text for test."),
            )
            for i in range(count)
        ]
    )
    meta = make_llm_meta(
        request_id=uuid.uuid4(),
        model="claude-sonnet-4-6",
        prompt_template_id=prompt_id,
    )
    return normalize(raw, llm_meta=meta)


def _make_synthetic_pdf(text: str, line_count: int = 1) -> bytes:
    """테스트용 synthetic PDF 생성.

    PyMuPDF 로 단일 페이지 PDF 를 만들어 반환.
    line_count > 1 이면 같은 텍스트를 여러 줄로 반복 삽입 — 밀도 휴리스틱 통과 필요 시 사용.
    실제 fitz 동작도 검증된다.
    """
    doc = fitz.open()
    page = doc.new_page()
    for i in range(line_count):
        y = 50 + i * 14  # 줄간격 14pt
        page.insert_text((50, y), text)
    pdf_bytes: bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_empty_pdf(page_count: int = 1) -> bytes:
    """텍스트 없는 빈 PDF (스캔본 시뮬레이션)."""
    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page()
    pdf_bytes: bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_multipage_pdf(texts: list[str]) -> bytes:
    """다중 페이지 PDF 생성."""
    doc = fitz.open()
    for text in texts:
        page = doc.new_page()
        page.insert_text((50, 50), text)
    pdf_bytes: bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ─── _TextLayerQuality.is_extractable() 단위 테스트 ─────────────────────────


class TestTextLayerQualityIsExtractable:
    """4종 휴리스틱 로직 — is_extractable() 직접 테스트."""

    def _quality(
        self,
        total_chars: int = 5000,
        page_count: int = 5,
        english_alpha_ratio: float = 0.70,
        broken_unicode_ratio: float = 0.00,
    ) -> _TextLayerQuality:
        return _TextLayerQuality(
            total_chars=total_chars,
            page_count=page_count,
            english_alpha_ratio=english_alpha_ratio,
            broken_unicode_ratio=broken_unicode_ratio,
        )

    def test_normal_text_is_extractable(self) -> None:
        """정상 영어 본문 → True."""
        q = self._quality(total_chars=5000, page_count=5)
        assert q.is_extractable() is True

    def test_zero_page_count_returns_false(self) -> None:
        """page_count == 0 → False."""
        q = self._quality(total_chars=1000, page_count=0)
        assert q.is_extractable() is False

    def test_zero_total_chars_returns_false(self) -> None:
        """total_chars == 0 → False."""
        q = self._quality(total_chars=0, page_count=3)
        assert q.is_extractable() is False

    # ── 휴리스틱 1 / 4: 페이지당 평균 문자 수 임계값 ─────────────────────────

    def test_chars_per_page_49_returns_false(self) -> None:
        """페이지당 49자 (< 50, 휴리스틱 1 실패) → False."""
        # 1페이지, 49자
        q = self._quality(total_chars=49, page_count=1)
        assert q.is_extractable() is False

    def test_chars_per_page_50_still_fails_density(self) -> None:
        """페이지당 50자 — 휴리스틱 1 통과, 휴리스틱 4 (< 200) 에서 실패."""
        q = self._quality(total_chars=50, page_count=1)
        assert q.is_extractable() is False

    def test_chars_per_page_199_fails_density(self) -> None:
        """페이지당 199자 (< 200, 휴리스틱 4 실패) → False."""
        q = self._quality(total_chars=199, page_count=1)
        assert q.is_extractable() is False

    def test_chars_per_page_200_passes_both(self) -> None:
        """페이지당 200자 — 휴리스틱 1, 4 모두 통과."""
        q = self._quality(
            total_chars=200,
            page_count=1,
            english_alpha_ratio=0.70,
            broken_unicode_ratio=0.00,
        )
        assert q.is_extractable() is True

    # ── 휴리스틱 2: 영어 알파벳 비율 경계값 ─────────────────────────────────

    def test_english_alpha_ratio_0_29_returns_false(self) -> None:
        """영어 비율 0.29 (< 0.30) → False."""
        q = self._quality(total_chars=2000, page_count=5, english_alpha_ratio=0.29)
        assert q.is_extractable() is False

    def test_english_alpha_ratio_0_30_passes(self) -> None:
        """영어 비율 정확히 0.30 → 통과 (다른 조건 정상)."""
        q = self._quality(
            total_chars=2000,
            page_count=5,
            english_alpha_ratio=MIN_ENGLISH_ALPHA_RATIO,
            broken_unicode_ratio=0.00,
        )
        assert q.is_extractable() is True

    def test_english_alpha_ratio_zero_returns_false(self) -> None:
        """영어 비율 0 (한글만 또는 이미지 노이즈) → False."""
        q = self._quality(total_chars=2000, page_count=5, english_alpha_ratio=0.0)
        assert q.is_extractable() is False

    # ── 휴리스틱 3: 깨진 unicode 비율 경계값 ─────────────────────────────────

    def test_broken_unicode_0_051_returns_false(self) -> None:
        """깨진 unicode 비율 0.051 (> 0.05) → False."""
        q = self._quality(total_chars=2000, page_count=5, broken_unicode_ratio=0.051)
        assert q.is_extractable() is False

    def test_broken_unicode_0_05_passes(self) -> None:
        """깨진 unicode 비율 정확히 0.05 → 통과 (다른 조건 정상)."""
        q = self._quality(
            total_chars=2000,
            page_count=5,
            english_alpha_ratio=0.70,
            broken_unicode_ratio=MAX_BROKEN_UNICODE_RATIO,
        )
        assert q.is_extractable() is True

    def test_high_broken_unicode_returns_false(self) -> None:
        """깨진 unicode 비율 50% → False."""
        q = self._quality(total_chars=2000, page_count=5, broken_unicode_ratio=0.50)
        assert q.is_extractable() is False

    # ── 복합 조건 ─────────────────────────────────────────────────────────────

    def test_all_conditions_pass(self) -> None:
        """4종 휴리스틱 모두 통과 → True."""
        q = _TextLayerQuality(
            total_chars=10_000,
            page_count=10,
            english_alpha_ratio=0.65,
            broken_unicode_ratio=0.01,
        )
        assert q.is_extractable() is True

    def test_one_failing_condition_makes_false(self) -> None:
        """1개만 실패해도 False — 영어 비율만 실패."""
        q = _TextLayerQuality(
            total_chars=10_000,
            page_count=10,
            english_alpha_ratio=0.20,  # 실패 (< 0.30)
            broken_unicode_ratio=0.01,
        )
        assert q.is_extractable() is False


# ─── _assess_quality 단위 테스트 ─────────────────────────────────────────────


class TestAssessQuality:
    """_assess_quality() — 실제 텍스트로 비율 계산 검증."""

    def test_pure_english_text_alpha_ratio(self) -> None:
        """순수 영어 알파벳만 있으면 alpha_ratio = 1.0."""
        text = "HelloWorld"  # 10 chars, 10 alpha → ratio = 1.0
        quality = _assess_quality(text, page_count=1)
        assert quality.total_chars == 10
        assert quality.english_alpha_ratio == pytest.approx(1.0, rel=1e-3)
        assert quality.broken_unicode_ratio == 0.0

    def test_mixed_text_alpha_ratio(self) -> None:
        """알파벳 + 공백 혼합 — 비율 정확히 계산."""
        text = "Hello World"  # 11 chars, 10 alpha, 1 space → ratio = 10/11
        quality = _assess_quality(text, page_count=1)
        assert quality.english_alpha_ratio == pytest.approx(10 / 11, rel=1e-3)

    def test_replacement_char_detected_as_broken(self) -> None:
        """replacement character (U+FFFD, ◌ 표시) 가 broken_unicode 로 계산된다."""
        # '�' = replacement char (U+FFFD)
        text = "abc" + "��"  # 3 alpha + 2 broken = 5 chars
        quality = _assess_quality(text, page_count=1)
        assert quality.broken_unicode_ratio == pytest.approx(2 / 5, rel=1e-3)

    def test_pua_char_detected_as_broken(self) -> None:
        """PUA 문자 (U+E000) 가 broken_unicode 로 계산된다."""
        text = "abc" + ""  # 3 alpha + 1 PUA = 4 chars
        quality = _assess_quality(text, page_count=1)
        assert quality.broken_unicode_ratio == pytest.approx(1 / 4, rel=1e-3)

    def test_empty_text_returns_zero_ratios(self) -> None:
        """빈 텍스트 → 모든 비율 0.0."""
        quality = _assess_quality("", page_count=0)
        assert quality.total_chars == 0
        assert quality.english_alpha_ratio == 0.0
        assert quality.broken_unicode_ratio == 0.0

    def test_multipage_count_propagated(self) -> None:
        """page_count 가 _TextLayerQuality 에 그대로 전달된다."""
        text = "a" * 1000
        quality = _assess_quality(text, page_count=5)
        assert quality.page_count == 5
        assert quality.total_chars == 1000


# ─── _extract_text_layer 단위 테스트 ─────────────────────────────────────────


class TestExtractTextLayer:
    """_extract_text_layer() — PyMuPDF 텍스트 추출 검증 (synthetic PDF 사용)."""

    def test_single_page_text_extracted(self) -> None:
        """단일 페이지 텍스트가 추출된다."""
        text = "Hello World"
        pdf_bytes = _make_synthetic_pdf(text)
        extracted, page_count = _extract_text_layer(pdf_bytes)
        assert page_count == 1
        assert "Hello" in extracted

    def test_multipage_text_joined_with_double_newline(self) -> None:
        """다중 페이지 텍스트가 이중 줄바꿈으로 합쳐진다."""
        pdf_bytes = _make_multipage_pdf(["Page one text", "Page two text"])
        extracted, page_count = _extract_text_layer(pdf_bytes)
        assert page_count == 2
        assert "\n\n" in extracted

    def test_empty_pdf_returns_empty_text(self) -> None:
        """텍스트 없는 PDF 는 빈 텍스트 반환, 페이지 수는 정확."""
        pdf_bytes = _make_empty_pdf(page_count=3)
        extracted, page_count = _extract_text_layer(pdf_bytes)
        assert page_count == 3
        assert extracted.strip() == ""


# ─── extract_from_pdf 분기 동작 테스트 ───────────────────────────────────────


class TestExtractFromPdfErrorHandling:
    """에러 처리 — 빈 bytes, corrupt PDF."""

    @pytest.mark.asyncio
    async def test_empty_bytes_raises_empty_input_error(self) -> None:
        """빈 bytes → EmptyInputError."""
        client = AsyncMock()
        with pytest.raises(EmptyInputError):
            await extract_from_pdf(b"", llm_client=client)

    @pytest.mark.asyncio
    async def test_empty_bytes_does_not_call_llm(self) -> None:
        """빈 bytes 시 LLM 호출하지 않는다."""
        client = AsyncMock()
        client.extract_structured = AsyncMock()
        try:
            await extract_from_pdf(b"", llm_client=client)
        except EmptyInputError:
            pass
        client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_corrupt_pdf_raises_pdf_parse_error(self) -> None:
        """corrupt PDF bytes → PdfParseError."""
        corrupt_bytes = b"NOT A PDF CONTENT AT ALL"
        client = AsyncMock()
        with pytest.raises(PdfParseError):
            await extract_from_pdf(corrupt_bytes, llm_client=client)

    @pytest.mark.asyncio
    async def test_pdf_parse_error_message_contains_hint(self) -> None:
        """PdfParseError 메시지에 force_vision 힌트가 있다."""
        corrupt_bytes = b"CORRUPTED"
        client = AsyncMock()
        with pytest.raises(PdfParseError) as exc_info:
            await extract_from_pdf(corrupt_bytes, llm_client=client)
        assert "force_vision" in str(exc_info.value)


class TestExtractFromPdfBranching:
    """분기 로직 — 텍스트 경로 vs Vision 경로."""

    @pytest.mark.asyncio
    async def test_force_vision_bypasses_heuristic(self) -> None:
        """force_vision=True 이면 텍스트 레이어 있어도 Vision 경로 (PM-3)."""
        long_english = " ".join(["word"] * 300)
        pdf_bytes = _make_synthetic_pdf(long_english)
        client = AsyncMock()
        fake_results = _make_fake_extraction_results(1, "extract-image-v0")

        with patch(
            "extractor.pdf.extract_from_image", new=AsyncMock(return_value=fake_results)
        ) as mock_image:
            with patch("extractor.pdf.extract_from_text", new=AsyncMock()) as mock_text:
                results = await extract_from_pdf(pdf_bytes, llm_client=client, force_vision=True)

        mock_image.assert_called_once()
        mock_text.assert_not_called()
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_good_text_layer_uses_text_path(self) -> None:
        """텍스트 레이어 품질 우수 → extract_from_text 경로.

        _assess_quality 를 패치해 is_extractable() == True 강제 — 분기 로직만 검증.
        """
        pdf_bytes = _make_synthetic_pdf("any pdf content for test")
        client = AsyncMock()
        fake_results = _make_fake_extraction_results(1, "extract-text-v0")

        good_quality = _TextLayerQuality(
            total_chars=5000,
            page_count=5,
            english_alpha_ratio=0.70,
            broken_unicode_ratio=0.00,
        )

        with patch("extractor.pdf._assess_quality", return_value=good_quality):
            with patch(
                "extractor.pdf.extract_from_text", new=AsyncMock(return_value=fake_results)
            ) as mock_text:
                with patch("extractor.pdf.extract_from_image", new=AsyncMock()) as mock_image:
                    results = await extract_from_pdf(pdf_bytes, llm_client=client)

        mock_text.assert_called_once()
        mock_image.assert_not_called()
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_empty_pdf_uses_vision_fallback(self) -> None:
        """텍스트 없는 스캔본 PDF → Vision fallback."""
        empty_pdf = _make_empty_pdf(page_count=1)
        client = AsyncMock()
        fake_results = _make_fake_extraction_results(1, "extract-image-v0")

        with patch(
            "extractor.pdf.extract_from_image", new=AsyncMock(return_value=fake_results)
        ) as mock_image:
            with patch("extractor.pdf.extract_from_text", new=AsyncMock()) as mock_text:
                results = await extract_from_pdf(empty_pdf, llm_client=client)

        mock_image.assert_called()
        mock_text.assert_not_called()
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_poor_quality_text_layer_uses_vision_fallback(self) -> None:
        """휴리스틱 실패 → Vision fallback.

        _assess_quality 를 패치해 is_extractable() == False 강제.
        """
        pdf_bytes = _make_synthetic_pdf("text")
        client = AsyncMock()
        fake_results = _make_fake_extraction_results(1, "extract-image-v0")

        poor_quality = _TextLayerQuality(
            total_chars=10,
            page_count=1,
            english_alpha_ratio=0.10,  # 실패
            broken_unicode_ratio=0.50,  # 실패
        )

        with patch("extractor.pdf._assess_quality", return_value=poor_quality):
            with patch(
                "extractor.pdf.extract_from_image", new=AsyncMock(return_value=fake_results)
            ) as mock_image:
                with patch("extractor.pdf.extract_from_text", new=AsyncMock()) as mock_text:
                    results = await extract_from_pdf(pdf_bytes, llm_client=client)

        mock_image.assert_called()
        mock_text.assert_not_called()
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_text_prompt_template_id_passed(self) -> None:
        """텍스트 경로 시 text_prompt_template_id 가 extract_from_text 에 전달된다."""
        pdf_bytes = _make_synthetic_pdf("any content")
        client = AsyncMock()
        fake_results = _make_fake_extraction_results(1)

        good_quality = _TextLayerQuality(
            total_chars=5000, page_count=5, english_alpha_ratio=0.70, broken_unicode_ratio=0.00
        )

        with patch("extractor.pdf._assess_quality", return_value=good_quality):
            with patch(
                "extractor.pdf.extract_from_text", new=AsyncMock(return_value=fake_results)
            ) as mock_text:
                await extract_from_pdf(
                    pdf_bytes,
                    llm_client=client,
                    text_prompt_template_id="extract-text-v1",
                )

        call_kwargs = mock_text.call_args.kwargs
        assert call_kwargs.get("prompt_template_id") == "extract-text-v1"

    @pytest.mark.asyncio
    async def test_image_prompt_template_id_passed_to_vision(self) -> None:
        """Vision 경로 시 image_prompt_template_id 가 extract_from_image 에 전달된다."""
        empty_pdf = _make_empty_pdf(page_count=1)
        client = AsyncMock()
        fake_results = _make_fake_extraction_results(1)

        with patch(
            "extractor.pdf.extract_from_image", new=AsyncMock(return_value=fake_results)
        ) as mock_image:
            await extract_from_pdf(
                empty_pdf,
                llm_client=client,
                image_prompt_template_id="extract-image-v1",
            )

        call_kwargs = mock_image.call_args.kwargs
        assert call_kwargs.get("prompt_template_id") == "extract-image-v1"


# ─── 다중 페이지 / 다중 지문 테스트 (PM-1) ───────────────────────────────────


class TestMultiPageMultiPassage:
    """PM-1: 다중 페이지 / 다중 지문 평탄화."""

    @pytest.mark.asyncio
    async def test_multipage_vision_calls_per_page(self) -> None:
        """Vision 경로 2페이지 PDF → extract_from_image 2회 호출."""
        empty_pdf = _make_empty_pdf(page_count=2)
        client = AsyncMock()

        call_count = 0

        async def mock_image_side_effect(*args: object, **kwargs: object) -> list[ExtractionResult]:
            nonlocal call_count
            results = _make_fake_extraction_results(1)
            call_count += 1
            return results

        with patch(
            "extractor.pdf.extract_from_image", new=AsyncMock(side_effect=mock_image_side_effect)
        ):
            results = await extract_from_pdf(empty_pdf, llm_client=client)

        assert call_count == 2
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_multipage_vision_results_flattened(self) -> None:
        """Vision 경로 3페이지 PDF → 결과 평탄화 (PM-1)."""
        empty_pdf = _make_empty_pdf(page_count=3)
        client = AsyncMock()
        # 각 페이지에서 지문 1개씩
        fake_results = [_make_fake_extraction_results(1) for _ in range(3)]
        call_index = 0

        async def mock_image_side_effect(*args: object, **kwargs: object) -> list[ExtractionResult]:
            nonlocal call_index
            result = fake_results[call_index]
            call_index += 1
            return result

        with patch(
            "extractor.pdf.extract_from_image", new=AsyncMock(side_effect=mock_image_side_effect)
        ):
            results = await extract_from_pdf(empty_pdf, llm_client=client)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_text_path_multiple_items_pm1(self) -> None:
        """텍스트 경로에서 LLM 이 다중 지문 반환 → list 길이 == N (PM-1)."""
        pdf_bytes = _make_synthetic_pdf("any content")
        client = AsyncMock()
        multi_results = _make_fake_extraction_results(3)

        good_quality = _TextLayerQuality(
            total_chars=5000, page_count=5, english_alpha_ratio=0.70, broken_unicode_ratio=0.00
        )

        with patch("extractor.pdf._assess_quality", return_value=good_quality):
            with patch(
                "extractor.pdf.extract_from_text", new=AsyncMock(return_value=multi_results)
            ):
                results = await extract_from_pdf(pdf_bytes, llm_client=client)

        assert len(results) == 3


# ─── sentinel UUID 테스트 (ADR-0003 §D-3.6) ─────────────────────────────────


class TestSentinelUUID:
    """Vision 경로 결과의 sentinel UUID 검증."""

    @pytest.mark.asyncio
    async def test_vision_result_has_sentinel_uuid(self) -> None:
        """Vision 경로 결과 Passage 의 tenant_id / workspace_id 는 sentinel."""
        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)
        empty_pdf = _make_empty_pdf(page_count=1)

        # force_vision=True 로 Vision 경로 강제, 실제 LLM mock 호출
        results = await extract_from_pdf(empty_pdf, llm_client=client, force_vision=True)

        assert len(results) >= 1
        assert results[0].passage.tenant_id == SENTINEL_UUID
        assert results[0].passage.workspace_id == SENTINEL_UUID


# ─── 휴리스틱 임계값 상수 검증 ───────────────────────────────────────────────


class TestHeuristicConstants:
    """ADR-0003 §D-3.3 에 명시된 임계값과 일치하는지 검증."""

    def test_min_chars_per_page_value(self) -> None:
        """MIN_CHARS_PER_PAGE == 50."""
        assert MIN_CHARS_PER_PAGE == 50

    def test_min_english_alpha_ratio_value(self) -> None:
        """MIN_ENGLISH_ALPHA_RATIO == 0.30."""
        assert MIN_ENGLISH_ALPHA_RATIO == pytest.approx(0.30)

    def test_max_broken_unicode_ratio_value(self) -> None:
        """MAX_BROKEN_UNICODE_RATIO == 0.05."""
        assert MAX_BROKEN_UNICODE_RATIO == pytest.approx(0.05)

    def test_min_density_chars_per_page_value(self) -> None:
        """MIN_DENSITY_CHARS_PER_PAGE == 200."""
        assert MIN_DENSITY_CHARS_PER_PAGE == 200

    def test_vision_dpi_value(self) -> None:
        """VISION_DPI == 200 — 정확도와 비용 균형."""
        assert VISION_DPI == 200
