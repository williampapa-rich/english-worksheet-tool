"""text.py — extract_from_text 단위 테스트.

mock LLM client 로 실제 Anthropic API 호출 없이 동작 검증.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from extractor.errors import EmptyInputError, ExtractionError
from extractor.normalizer import (
    RawExtractionItem,
    RawExtractionResponse,
    RawPassage,
    RawQuestion,
    RawTranslation,
    RawVocabulary,
)
from extractor.text import extract_from_text
from llm.errors import LLMSchemaValidationError
from llm.usage import StructuredLLMResult, TokenUsage

# ─── 헬퍼 ────────────────────────────────────────────────────────────────────


def _make_llm_result(data: RawExtractionResponse) -> StructuredLLMResult[RawExtractionResponse]:
    """테스트용 StructuredLLMResult 생성."""
    return StructuredLLMResult(
        data=data,
        raw_response={"mocked": True},
        usage=TokenUsage(input_tokens=100, output_tokens=300),
        model="claude-sonnet-4-6",
        elapsed_ms=800,
        request_id=uuid.uuid4(),
        parent_request_id=None,
    )


def _make_mock_client(response: RawExtractionResponse) -> AsyncMock:
    """extract_structured 를 mock 하는 LLM 클라이언트."""
    client = AsyncMock()
    client.extract_structured = AsyncMock(return_value=_make_llm_result(response))
    return client


def _simple_passage(text: str = "The fox jumps over the dog.") -> RawPassage:
    return RawPassage(
        body_text=text,
        paragraphs=[text],
        word_count=len(text.split()),
    )


# ─── 빈 입력 테스트 ──────────────────────────────────────────────────────────


class TestEmptyInput:
    """빈 입력 → EmptyInputError."""

    @pytest.mark.asyncio
    async def test_empty_string_raises(self) -> None:
        client = AsyncMock()
        with pytest.raises(EmptyInputError):
            await extract_from_text("", llm_client=client)

    @pytest.mark.asyncio
    async def test_whitespace_only_raises(self) -> None:
        client = AsyncMock()
        with pytest.raises(EmptyInputError):
            await extract_from_text("   \n\t  ", llm_client=client)

    @pytest.mark.asyncio
    async def test_empty_does_not_call_llm(self) -> None:
        """빈 입력 시 LLM 호출하지 않는다."""
        client = AsyncMock()
        client.extract_structured = AsyncMock()
        try:
            await extract_from_text("", llm_client=client)
        except EmptyInputError:
            pass
        client.extract_structured.assert_not_called()


# ─── 정상 추출 테스트 ─────────────────────────────────────────────────────────


class TestExtractFromText:
    """정상 동작 시나리오."""

    @pytest.mark.asyncio
    async def test_english_only_pm6_default(self) -> None:
        """PM-6 default — 영어만 입력, translation=None, vocabulary=[] (정상)."""
        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        results = await extract_from_text("The fox jumps over the dog.", llm_client=client)

        assert len(results) == 1
        assert results[0].translation is None
        assert results[0].vocabulary == []

    @pytest.mark.asyncio
    async def test_returns_list_pm1(self) -> None:
        """PM-1 — 단일 지문 입력도 list 반환 (길이 1)."""
        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        results = await extract_from_text("Some text.", llm_client=client)

        assert isinstance(results, list)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_full_set_pm5(self) -> None:
        """PM-5 — 자료에 한글 해석 + 어휘 있으면 포함."""
        response = RawExtractionResponse(
            items=[
                RawExtractionItem(
                    passage=_simple_passage("The quick fox."),
                    questions=[],
                    translation=RawTranslation(text="빠른 여우."),
                    vocabulary=[
                        RawVocabulary(headword="quick", pos="adj", meaning_ko="빠른"),
                    ],
                )
            ]
        )
        client = _make_mock_client(response)

        results = await extract_from_text("The quick fox. (빠른 여우.)", llm_client=client)

        assert results[0].translation is not None
        assert results[0].translation.text == "빠른 여우."
        assert len(results[0].vocabulary) == 1
        assert results[0].vocabulary[0].word == "quick"

    @pytest.mark.asyncio
    async def test_multiple_passages_pm1(self) -> None:
        """PM-1 — 다중 지문 자료 → list 길이 > 1."""
        response = RawExtractionResponse(
            items=[
                RawExtractionItem(passage=_simple_passage("First passage.")),
                RawExtractionItem(passage=_simple_passage("Second passage.")),
                RawExtractionItem(passage=_simple_passage("Third passage.")),
            ]
        )
        client = _make_mock_client(response)

        results = await extract_from_text(
            "First passage. Second passage. Third passage.",
            llm_client=client,
        )

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_sentinel_uuid_in_output(self) -> None:
        """출력 Passage 의 tenant_id / workspace_id 는 sentinel UUID (ADR-0003 §D-3.6)."""
        from extractor.base import SENTINEL_UUID

        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        results = await extract_from_text("Some text.", llm_client=client)

        assert results[0].passage.tenant_id == SENTINEL_UUID
        assert results[0].passage.workspace_id == SENTINEL_UUID

    @pytest.mark.asyncio
    async def test_llm_client_called_with_correct_purpose(self) -> None:
        """LLM 클라이언트가 purpose='extract_text' 로 호출된다."""
        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        await extract_from_text("Some text.", llm_client=client)

        client.extract_structured.assert_called_once()
        call_kwargs = client.extract_structured.call_args.kwargs
        assert call_kwargs.get("purpose") == "extract_text"

    @pytest.mark.asyncio
    async def test_prompt_template_default(self) -> None:
        """기본 prompt_template_id 가 'extract-text-v0' 이다."""
        from llm.prompt import PromptSpec

        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        await extract_from_text("Some text.", llm_client=client)

        call_kwargs = client.extract_structured.call_args.kwargs
        prompt: PromptSpec = call_kwargs["prompt"]
        assert prompt.template_id == "extract-text-v0"

    @pytest.mark.asyncio
    async def test_custom_prompt_template_id(self) -> None:
        """custom prompt_template_id 가 올바르게 전달된다."""
        import os
        import pathlib
        import tempfile

        from llm.prompt import PromptSpec

        # 임시 프롬프트 파일 생성
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_file = pathlib.Path(tmpdir) / "custom-extract-v1.md"
            prompt_file.write_text("Extract: {{input_text}}", encoding="utf-8")

            response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
            client = _make_mock_client(response)

            os.environ["PROMPTS_DIR"] = tmpdir
            try:
                await extract_from_text(
                    "Some text.",
                    llm_client=client,
                    prompt_template_id="custom-extract-v1",
                )
            finally:
                del os.environ["PROMPTS_DIR"]

        call_kwargs = client.extract_structured.call_args.kwargs
        prompt: PromptSpec = call_kwargs["prompt"]
        assert prompt.template_id == "custom-extract-v1"

    @pytest.mark.asyncio
    async def test_extraction_meta_in_result(self) -> None:
        """ExtractionResult 에 extraction_meta 가 담긴다."""
        response = RawExtractionResponse(items=[RawExtractionItem(passage=_simple_passage())])
        client = _make_mock_client(response)

        results = await extract_from_text("Some text.", llm_client=client)

        assert results[0].extraction_meta is not None
        assert results[0].extraction_meta.model == "claude-sonnet-4-6"
        assert results[0].extraction_meta.prompt_template_id == "extract-text-v0"


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
            await extract_from_text("Some text.", llm_client=client)

    @pytest.mark.asyncio
    async def test_question_type_mapping_failure(self) -> None:
        """LLM 이 24개 유형 외 type 반환 시 ExtractionError."""
        response = RawExtractionResponse(
            items=[
                RawExtractionItem(
                    passage=_simple_passage(),
                    questions=[
                        RawQuestion(
                            type="존재하지_않는_유형_99",
                            stem="문제 발문",
                        )
                    ],
                )
            ]
        )
        client = _make_mock_client(response)

        with pytest.raises(ExtractionError, match="24개 유형"):
            await extract_from_text("Some text.", llm_client=client)
