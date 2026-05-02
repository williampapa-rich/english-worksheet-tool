"""image.py — extract_from_image 단위 테스트.

mock LLM client 로 실제 Anthropic API 호출 없이 동작 검증.

PM-1: 단일 이미지도 list[ExtractionResult] 반환.
PM-5: 이미지에 번역/어휘 있으면 함께 추출.
PM-6: 번역/어휘 없으면 translation=None, vocabulary=[] (정상).
ADR-0003 §D-3.6: sentinel UUID 패턴.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from extractor.base import SENTINEL_UUID
from extractor.errors import EmptyInputError, ExtractionError, UnsupportedMediaTypeError
from extractor.image import _SUPPORTED_MEDIA_TYPES, extract_from_image
from extractor.normalizer import (
    RawExtractionItem,
    RawExtractionResponse,
    RawPassage,
    RawQuestion,
    RawTranslation,
    RawVocabulary,
)
from llm.errors import LLMSchemaValidationError
from llm.usage import StructuredLLMResult, TokenUsage

# ─── 최소 유효 PNG 바이트 (1x1 투명 PNG) ─────────────────────────────────────
# 실제 이미지 디코딩 없이 "비어있지 않은 bytes" 역할
_MINIMAL_PNG: bytes = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
_MINIMAL_JPEG: bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 12 + b"\xff\xd9"
_MINIMAL_WEBP: bytes = b"RIFF\x24\x00\x00\x00WEBP" + b"\x00" * 24


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────


def _make_llm_result(data: RawExtractionResponse) -> StructuredLLMResult[RawExtractionResponse]:
    """테스트용 StructuredLLMResult 생성."""
    return StructuredLLMResult(
        data=data,
        raw_response={"mocked": True},
        usage=TokenUsage(input_tokens=200, output_tokens=400),
        model="claude-sonnet-4-6",
        elapsed_ms=1200,
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


# ─── 빈 입력 테스트 ──────────────────────────────────────────────────────────


class TestEmptyInput:
    """빈 bytes 입력 → EmptyInputError."""

    @pytest.mark.asyncio
    async def test_empty_bytes_raises(self) -> None:
        """bytes 가 비어있으면 EmptyInputError."""
        client = AsyncMock()
        with pytest.raises(EmptyInputError):
            await extract_from_image(b"", "image/png", llm_client=client)

    @pytest.mark.asyncio
    async def test_empty_bytes_does_not_call_llm(self) -> None:
        """빈 입력 시 LLM 호출하지 않는다."""
        client = AsyncMock()
        client.extract_structured = AsyncMock()
        try:
            await extract_from_image(b"", "image/png", llm_client=client)
        except EmptyInputError:
            pass
        client.extract_structured.assert_not_called()


# ─── media_type 검증 테스트 ───────────────────────────────────────────────────


class TestUnsupportedMediaType:
    """지원하지 않는 media_type → UnsupportedMediaTypeError."""

    @pytest.mark.asyncio
    async def test_gif_raises(self) -> None:
        """image/gif 는 지원하지 않음."""
        client = AsyncMock()
        with pytest.raises(UnsupportedMediaTypeError):
            await extract_from_image(_MINIMAL_PNG, "image/gif", llm_client=client)

    @pytest.mark.asyncio
    async def test_bmp_raises(self) -> None:
        """image/bmp 는 지원하지 않음."""
        client = AsyncMock()
        with pytest.raises(UnsupportedMediaTypeError):
            await extract_from_image(_MINIMAL_PNG, "image/bmp", llm_client=client)

    @pytest.mark.asyncio
    async def test_pdf_raises(self) -> None:
        """application/pdf 는 지원하지 않음 — PDF 는 별도 extractor."""
        client = AsyncMock()
        with pytest.raises(UnsupportedMediaTypeError):
            await extract_from_image(_MINIMAL_PNG, "application/pdf", llm_client=client)

    @pytest.mark.asyncio
    async def test_heic_raises(self) -> None:
        """image/heic 는 지원하지 않음."""
        client = AsyncMock()
        with pytest.raises(UnsupportedMediaTypeError):
            await extract_from_image(_MINIMAL_PNG, "image/heic", llm_client=client)

    @pytest.mark.asyncio
    async def test_unsupported_does_not_call_llm(self) -> None:
        """지원하지 않는 media_type 시 LLM 호출하지 않는다."""
        client = AsyncMock()
        client.extract_structured = AsyncMock()
        try:
            await extract_from_image(_MINIMAL_PNG, "image/tiff", llm_client=client)
        except UnsupportedMediaTypeError:
            pass
        client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_contains_media_type(self) -> None:
        """UnsupportedMediaTypeError 에 media_type 정보가 포함된다."""
        client = AsyncMock()
        with pytest.raises(UnsupportedMediaTypeError) as exc_info:
            await extract_from_image(_MINIMAL_PNG, "image/gif", llm_client=client)
        assert exc_info.value.media_type == "image/gif"


# ─── 지원 media_type 각각 통과 테스트 ────────────────────────────────────────


class TestSupportedMediaTypes:
    """지원 media_type (png/jpeg/webp) 각각 정상 통과."""

    @pytest.mark.asyncio
    async def test_png_passes(self) -> None:
        """image/png 는 지원된다."""
        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)
        results = await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_jpeg_passes(self) -> None:
        """image/jpeg 는 지원된다."""
        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)
        results = await extract_from_image(_MINIMAL_JPEG, "image/jpeg", llm_client=client)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_webp_passes(self) -> None:
        """image/webp 는 지원된다."""
        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)
        results = await extract_from_image(_MINIMAL_WEBP, "image/webp", llm_client=client)
        assert len(results) == 1


# ─── 정상 추출 테스트 ─────────────────────────────────────────────────────────


class TestExtractFromImage:
    """정상 동작 시나리오."""

    @pytest.mark.asyncio
    async def test_single_passage_pm1(self) -> None:
        """PM-1 — 단일 지문 입력도 list 반환 (길이 1)."""
        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        results = await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)

        assert isinstance(results, list)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_multiple_passages_pm1(self) -> None:
        """PM-1 — 이미지 1개에 여러 지문 → list 길이 > 1."""
        response = RawExtractionResponse(
            items=[
                RawExtractionItem(passage=_simple_passage("First passage on the exam.")),
                RawExtractionItem(passage=_simple_passage("Second passage on the exam.")),
                RawExtractionItem(passage=_simple_passage("Third passage on the exam.")),
            ]
        )
        client = _make_mock_client(response)

        results = await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_full_set_pm5(self) -> None:
        """PM-5 — 이미지에 한글 해석 + 어휘 보이면 포함."""
        response = RawExtractionResponse(
            items=[
                RawExtractionItem(
                    passage=_simple_passage("The quick fox jumps high."),
                    questions=[],
                    translation=RawTranslation(text="빠른 여우가 높이 뛴다."),
                    vocabulary=[
                        RawVocabulary(headword="quick", pos="adj", meaning_ko="빠른"),
                        RawVocabulary(headword="fox", pos="noun", meaning_ko="여우"),
                    ],
                )
            ]
        )
        client = _make_mock_client(response)

        results = await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)

        assert results[0].translation is not None
        assert results[0].translation.text == "빠른 여우가 높이 뛴다."
        assert len(results[0].vocabulary) == 2
        assert results[0].vocabulary[0].word == "quick"

    @pytest.mark.asyncio
    async def test_english_only_pm6(self) -> None:
        """PM-6 default — translation=None, vocabulary=[] 가 정상."""
        response = RawExtractionResponse(
            items=[
                RawExtractionItem(
                    passage=_simple_passage(),
                    questions=[],
                    translation=None,
                    vocabulary=[],
                )
            ]
        )
        client = _make_mock_client(response)

        results = await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)

        assert results[0].translation is None
        assert results[0].vocabulary == []

    @pytest.mark.asyncio
    async def test_sentinel_uuid_in_output(self) -> None:
        """출력 Passage 의 tenant_id / workspace_id 는 sentinel UUID (ADR-0003 §D-3.6)."""
        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        results = await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)

        assert results[0].passage.tenant_id == SENTINEL_UUID
        assert results[0].passage.workspace_id == SENTINEL_UUID

    @pytest.mark.asyncio
    async def test_sentinel_uuid_in_questions(self) -> None:
        """출력 Question 의 tenant_id / workspace_id 도 sentinel UUID."""
        response = RawExtractionResponse(
            items=[
                RawExtractionItem(
                    passage=_simple_passage(),
                    questions=[
                        RawQuestion(
                            type="vocabulary_30", stem="밑줄 친 단어의 의미로...", number=30
                        )
                    ],
                )
            ]
        )
        client = _make_mock_client(response)

        results = await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)

        assert results[0].questions[0].tenant_id == SENTINEL_UUID
        assert results[0].questions[0].workspace_id == SENTINEL_UUID


# ─── Vision payload 검증 테스트 ──────────────────────────────────────────────


class TestVisionPayload:
    """LLM 클라이언트에 Vision payload 가 정확히 전달되는지 검증."""

    @pytest.mark.asyncio
    async def test_images_kwarg_passed(self) -> None:
        """extract_structured 호출 시 images 인자가 전달된다."""
        from llm.client import ImageInput

        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)

        client.extract_structured.assert_called_once()
        call_kwargs = client.extract_structured.call_args.kwargs
        images = call_kwargs.get("images")
        assert images is not None
        assert len(images) == 1
        assert isinstance(images[0], ImageInput)

    @pytest.mark.asyncio
    async def test_image_bytes_and_media_type_passed(self) -> None:
        """ImageInput 에 정확한 bytes 와 media_type 이 들어간다."""
        from llm.client import ImageInput

        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        await extract_from_image(_MINIMAL_JPEG, "image/jpeg", llm_client=client)

        call_kwargs = client.extract_structured.call_args.kwargs
        image: ImageInput = call_kwargs["images"][0]
        assert image.data == _MINIMAL_JPEG
        assert image.media_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_purpose_is_extract_image(self) -> None:
        """LLM 클라이언트가 purpose='extract_image' 로 호출된다."""
        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)

        call_kwargs = client.extract_structured.call_args.kwargs
        assert call_kwargs.get("purpose") == "extract_image"

    @pytest.mark.asyncio
    async def test_prompt_template_default(self) -> None:
        """기본 prompt_template_id 가 'extract-image-v0' 이다."""
        from llm.prompt import PromptSpec

        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)

        call_kwargs = client.extract_structured.call_args.kwargs
        prompt: PromptSpec = call_kwargs["prompt"]
        assert prompt.template_id == "extract-image-v0"

    @pytest.mark.asyncio
    async def test_prompt_variables_empty(self) -> None:
        """Vision 입력 전용 — prompt.variables 가 비어있다 (텍스트 변수 없음)."""
        from llm.prompt import PromptSpec

        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)

        call_kwargs = client.extract_structured.call_args.kwargs
        prompt: PromptSpec = call_kwargs["prompt"]
        assert prompt.variables == {}

    @pytest.mark.asyncio
    async def test_custom_prompt_template_id(self) -> None:
        """custom prompt_template_id 가 올바르게 전달된다."""
        from llm.prompt import PromptSpec

        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        await extract_from_image(
            _MINIMAL_PNG,
            "image/png",
            llm_client=client,
            prompt_template_id="extract-image-v1",
        )

        call_kwargs = client.extract_structured.call_args.kwargs
        prompt: PromptSpec = call_kwargs["prompt"]
        assert prompt.template_id == "extract-image-v1"


# ─── extraction_meta 테스트 ───────────────────────────────────────────────────


class TestExtractionMeta:
    """extraction_meta 가 올바르게 채워지는지 확인."""

    @pytest.mark.asyncio
    async def test_extraction_meta_in_result(self) -> None:
        """ExtractionResult 에 extraction_meta 가 담긴다."""
        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        results = await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)

        assert results[0].extraction_meta is not None
        assert results[0].extraction_meta.model == "claude-sonnet-4-6"
        assert results[0].extraction_meta.prompt_template_id == "extract-image-v0"


# ─── LLM 에러 propagate 테스트 ───────────────────────────────────────────────


class TestLLMErrorPropagation:
    """LLM 에러는 extractor 가 그대로 propagate (ADR-0003 §D-3.5)."""

    @pytest.mark.asyncio
    async def test_schema_validation_error_propagates(self) -> None:
        """LLMSchemaValidationError 는 그대로 propagate."""
        client = AsyncMock()
        client.extract_structured = AsyncMock(
            side_effect=LLMSchemaValidationError(
                "schema 위반",
                validation_error="items field missing",
                raw_response={"bad": "response"},
            )
        )

        with pytest.raises(LLMSchemaValidationError):
            await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)

    @pytest.mark.asyncio
    async def test_question_type_mapping_failure(self) -> None:
        """LLM 이 24개 유형 외 type 반환 시 ExtractionError."""
        response = RawExtractionResponse(
            items=[
                RawExtractionItem(
                    passage=_simple_passage(),
                    questions=[
                        RawQuestion(
                            type="알_수_없는_유형_99",
                            stem="문제 발문",
                        )
                    ],
                )
            ]
        )
        client = _make_mock_client(response)

        with pytest.raises(ExtractionError, match="24개 유형"):
            await extract_from_image(_MINIMAL_PNG, "image/png", llm_client=client)


# ─── _SUPPORTED_MEDIA_TYPES 상수 확인 ────────────────────────────────────────


class TestSupportedMediaTypesConstant:
    """_SUPPORTED_MEDIA_TYPES 상수가 올바른 집합을 가진다."""

    def test_supported_types_set(self) -> None:
        """지원 목록은 png/jpeg/webp 세 가지이다."""
        assert _SUPPORTED_MEDIA_TYPES == frozenset({"image/png", "image/jpeg", "image/webp"})
