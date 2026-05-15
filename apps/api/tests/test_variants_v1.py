"""generate_v1_variant 단위 테스트 — mock LLM client.

커버 케이스:
  - 정상 생성: vocabulary_30 / long_set_41_42 각 type.
  - 반환된 Question 의 필드 검증 (variant_kind / choices / answer / derived_from 등).
  - sentinel UUID 채움 검증 (라우트가 model_copy 로 교체하는 자리).
  - variant_metadata 에 body_with_markers + swapped_position_index + original_word +
    swapped_word + swap_reason 저장 검증.
  - V1 비적용 type (grammar_29) → ValueError.
  - choices 5개 미만 → Pydantic ValidationError.
  - answer 와 swapped_position_index 불일치 → Pydantic ValidationError.
  - body_with_markers 에 마커 미포함 / 중복 → Pydantic ValidationError.
  - LLM 호출 실패 → 에러 그대로 전파.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from llm.errors import LLMSchemaValidationError, LLMTimeoutError
from llm.usage import StructuredLLMResult, TokenUsage
from llm.variants.v1_vocabulary_swap import (
    V1_APPLICABLE_TYPES,
    V1Output,
    V1VariantMetadata,
    generate_v1_variant,
)
from pydantic import ValidationError

from shared.schemas.question import Question, QuestionType, VariantKind

# ─── fixtures ────────────────────────────────────────────────────────────────

_TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_WORKSPACE_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_PASSAGE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_QUESTION_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

# Zero-waste fixture — 어휘 교체 테스트 지문
_ZERO_WASTE_PASSAGE = (
    "Reducing waste starts with awareness. "
    "When people understand how much they throw away each day, "
    "they become more motivated to change their habits. "
    "Small actions — bringing reusable bags, refusing single-use plastics, "
    "and composting food scraps — add up to significant environmental benefits. "
    "Communities that adopt these practices report not only cleaner surroundings "
    "but also lower costs for municipal waste management. "
    "Individual effort, multiplied across an entire community, creates meaningful change."
)

# ①~⑤ 마커가 인라인 삽입된 수정 본문 (⑤ 위치 단어가 부적절 swap)
_BODY_WITH_MARKERS = (
    "Reducing waste starts with ①awareness. "
    "When people understand how much they throw away each day, "
    "they become more ②motivated to change their habits. "
    "Small actions add up to ③significant environmental benefits. "
    "Communities that adopt these practices report not only ④cleaner surroundings "
    "but also lower costs for municipal waste management. "
    "Individual effort, multiplied across an entire community, creates ⑤meaningless change."
)

_CHOICES = ["awareness", "motivated", "significant", "cleaner", "meaningless"]
_ANSWER = 5  # ⑤ 위치 = 부적절 단어

_EXPLANATION_KO = (
    "지문은 개인의 노력이 커뮤니티 전체에 걸쳐 '의미 있는(meaningful)' 변화를 "
    "만들어낸다고 결론짓고 있다. 그러나 ⑤번 위치에는 'meaningless(의미 없는)'가 삽입되어 "
    "글 전체가 긍정적 행동의 가치를 강조하는 맥락과 정면으로 모순된다."
)


def _make_question(
    question_type: QuestionType = QuestionType.VOCABULARY_30,
) -> Question:
    return Question(
        id=_QUESTION_ID,
        tenant_id=_TENANT_ID,
        workspace_id=_WORKSPACE_ID,
        passage_id=_PASSAGE_ID,
        type=question_type,
        variant_kind=VariantKind.ORIGINAL,
        choices=["increase", "positive", "helpful", "active", "significant"],
        answer=3,
        question_text="다음 밑줄 친 단어 중, 문맥상 낱말의 쓰임이 적절하지 않은 것은?",
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_v1_metadata(
    answer: int = _ANSWER,
    sub_type: str = "vocabulary_30",
    original_word: str = "meaningful",
    swapped_word: str = "meaningless",
    swap_reason: str = "antonym",
) -> V1VariantMetadata:
    return V1VariantMetadata(
        sub_type=sub_type,
        swapped_position_index=answer,
        original_word=original_word,
        swapped_word=swapped_word,
        swap_reason=swap_reason,  # type: ignore[arg-type]
    )


def _make_v1_llm_output(
    answer: int = _ANSWER,
    sub_type: str = "vocabulary_30",
    choices: list[str] | None = None,
    body_with_markers: str = _BODY_WITH_MARKERS,
) -> V1Output:
    if choices is None:
        choices = _CHOICES
    return V1Output(
        body_with_markers=body_with_markers,
        choices=choices,
        answer=answer,
        explanation=_EXPLANATION_KO,
        variant_metadata=_make_v1_metadata(answer=answer, sub_type=sub_type),
    )


def _make_llm_result(data: Any) -> StructuredLLMResult[Any]:
    return StructuredLLMResult(
        data=data,
        raw_response={},
        usage=TokenUsage(input_tokens=350, output_tokens=180, cache_read_tokens=0),
        model="claude-sonnet-4-6",
        elapsed_ms=1200,
    )


def _make_mock_client(return_data: Any) -> AsyncMock:
    """mock StructuredLLMClient — extract_structured 가 return_data 를 반환."""
    mock = AsyncMock()
    mock.extract_structured = AsyncMock(return_value=_make_llm_result(return_data))
    return mock


# ─── V1Output / V1VariantMetadata Pydantic 검증 ──────────────────────────────


class TestV1OutputValidation:
    def test_valid_vocabulary_30_output(self) -> None:
        """정상 vocabulary_30 출력 — Pydantic 검증 통과."""
        out = _make_v1_llm_output()
        assert out.choices == _CHOICES
        assert out.answer == _ANSWER
        assert out.variant_metadata.swapped_position_index == _ANSWER
        assert out.variant_metadata.sub_type == "vocabulary_30"
        assert out.variant_metadata.original_word == "meaningful"
        assert out.variant_metadata.swapped_word == "meaningless"
        assert out.variant_metadata.swap_reason == "antonym"

    def test_choices_too_few_raises(self) -> None:
        """choices 가 4개이면 ValidationError."""
        with pytest.raises(ValidationError, match="5개"):
            V1Output(
                body_with_markers=_BODY_WITH_MARKERS,
                choices=["awareness", "motivated", "significant", "cleaner"],  # 4개
                answer=4,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v1_metadata(answer=4),
            )

    def test_answer_out_of_range_raises(self) -> None:
        """answer 가 1~5 범위를 벗어나면 ValidationError."""
        with pytest.raises(ValidationError):
            V1Output(
                body_with_markers=_BODY_WITH_MARKERS,
                choices=_CHOICES,
                answer=6,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v1_metadata(answer=5),
            )

    def test_answer_swapped_position_mismatch_raises(self) -> None:
        """answer=5 인데 swapped_position_index=3 이면 ValidationError."""
        with pytest.raises(ValidationError, match="불일치"):
            V1Output(
                body_with_markers=_BODY_WITH_MARKERS,
                choices=_CHOICES,
                answer=5,
                explanation=_EXPLANATION_KO,
                variant_metadata=V1VariantMetadata(
                    sub_type="vocabulary_30",
                    swapped_position_index=3,  # answer=5 와 불일치
                    original_word="meaningful",
                    swapped_word="meaningless",
                    swap_reason="antonym",
                ),
            )

    def test_body_missing_marker_raises(self) -> None:
        """body_with_markers 에 마커 ⑤ 가 없으면 ValidationError."""
        body_missing_marker = (
            "Reducing waste starts with ①awareness. "
            "They become more ②motivated to change their habits. "
            "Add up to ③significant environmental benefits. "
            "④cleaner surroundings."
            # ⑤ 빠짐
        )
        with pytest.raises(ValidationError, match="마커"):
            V1Output(
                body_with_markers=body_missing_marker,
                choices=_CHOICES,
                answer=_ANSWER,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v1_metadata(),
            )

    def test_body_duplicate_marker_raises(self) -> None:
        """body_with_markers 에 마커 ① 이 2개이면 ValidationError."""
        body_duplicate_marker = (
            "Reducing waste starts with ①awareness. ①again. "
            "They become more ②motivated. "
            "③significant environmental benefits. "
            "④cleaner surroundings. "
            "⑤meaningless change."
        )
        with pytest.raises(ValidationError, match="마커"):
            V1Output(
                body_with_markers=body_duplicate_marker,
                choices=_CHOICES,
                answer=_ANSWER,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v1_metadata(),
            )

    def test_invalid_swap_reason_raises(self) -> None:
        """swap_reason 이 허용 값 외이면 ValidationError."""
        with pytest.raises(ValidationError):
            V1VariantMetadata(
                sub_type="vocabulary_30",
                swapped_position_index=5,
                original_word="meaningful",
                swapped_word="meaningless",
                swap_reason="synonym",  # 허용 값 아님
            )

    def test_context_mismatch_reason_valid(self) -> None:
        """swap_reason='context_mismatch' 도 유효."""
        meta = V1VariantMetadata(
            sub_type="vocabulary_30",
            swapped_position_index=3,
            original_word="significant",
            swapped_word="trivial",
            swap_reason="context_mismatch",
        )
        assert meta.swap_reason == "context_mismatch"


# ─── generate_v1_variant 정상 케이스 ─────────────────────────────────────────


class TestGenerateV1Variant:
    @pytest.mark.asyncio
    async def test_vocabulary_30_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """vocabulary_30 원본 → V1 변형 Question 반환.

        반환된 Question 의 필드 검증:
          - variant_kind == VOCABULARY_SWAP
          - derived_from_question_id 는 sentinel UUID (라우트가 교체 예정)
          - choices == 5개 단어
          - answer == _ANSWER (부적절 단어 위치)
          - type == VOCABULARY_30 (원본과 동일)
        """
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        llm_out = _make_v1_llm_output(sub_type="vocabulary_30")
        mock_client = _make_mock_client(llm_out)

        result = await generate_v1_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert isinstance(result, Question)
        assert result.variant_kind == VariantKind.VOCABULARY_SWAP
        assert result.type == QuestionType.VOCABULARY_30
        assert result.choices == _CHOICES
        assert result.answer == _ANSWER
        # sentinel UUID 채워짐 (라우트가 model_copy 로 교체)
        assert result.derived_from_question_id == uuid.UUID(int=0)
        assert result.tenant_id == uuid.UUID(int=0)
        assert result.workspace_id == uuid.UUID(int=0)

    @pytest.mark.asyncio
    async def test_long_set_41_42_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """long_set_41_42 원본 → V1 변형 Question 반환."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.LONG_SET_41_42)
        llm_out = _make_v1_llm_output(sub_type="long_set_41_42")
        mock_client = _make_mock_client(llm_out)

        result = await generate_v1_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.type == QuestionType.LONG_SET_41_42
        assert result.variant_kind == VariantKind.VOCABULARY_SWAP

    @pytest.mark.asyncio
    async def test_variant_metadata_stored_correctly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """variant_metadata 가 Question.variant_metadata 에 dict 로 저장된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        llm_out = _make_v1_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v1_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.variant_metadata is not None
        assert result.variant_metadata["sub_type"] == "vocabulary_30"
        assert result.variant_metadata["swapped_position_index"] == _ANSWER
        assert result.variant_metadata["original_word"] == "meaningful"
        assert result.variant_metadata["swapped_word"] == "meaningless"
        assert result.variant_metadata["swap_reason"] == "antonym"
        # body_with_markers 도 variant_metadata 에 저장됨
        assert "body_with_markers" in result.variant_metadata
        assert "⑤" in result.variant_metadata["body_with_markers"]

    @pytest.mark.asyncio
    async def test_llm_client_called_with_correct_purpose(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """LLM 호출 시 purpose='variant_v1_vocabulary_swap' 로 로깅."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        llm_out = _make_v1_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v1_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        assert call_kwargs["purpose"] == "variant_v1_vocabulary_swap"

    @pytest.mark.asyncio
    async def test_passage_text_passed_to_prompt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """passage_text 가 프롬프트 변수에 포함되어 LLM 에 전달된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        llm_out = _make_v1_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v1_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        prompt = call_kwargs["prompt"]
        rendered = prompt.render()
        assert "Reducing waste" in rendered

    @pytest.mark.asyncio
    async def test_answer_varied_position(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """answer 가 2일 때 정상 처리된다 (정답 분포 편향 회피 검증)."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)

        # answer=2 시나리오 — ② 위치가 부적절 단어
        body_answer_2 = (
            "Reducing waste starts with ①awareness. "
            "They become more ②discouraged to change their habits. "
            "Add up to ③significant environmental benefits. "
            "④cleaner surroundings. "
            "Creates ⑤meaningful change."
        )
        choices_answer_2 = ["awareness", "discouraged", "significant", "cleaner", "meaningful"]
        llm_out = V1Output(
            body_with_markers=body_answer_2,
            choices=choices_answer_2,
            answer=2,
            explanation="② 위치의 'discouraged' 는 긍정적 맥락과 모순된다.",
            variant_metadata=V1VariantMetadata(
                sub_type="vocabulary_30",
                swapped_position_index=2,
                original_word="motivated",
                swapped_word="discouraged",
                swap_reason="antonym",
            ),
        )
        mock_client = _make_mock_client(llm_out)

        result = await generate_v1_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.answer == 2
        assert result.variant_metadata is not None
        assert result.variant_metadata["swapped_position_index"] == 2
        assert result.variant_metadata["original_word"] == "motivated"
        assert result.variant_metadata["swapped_word"] == "discouraged"

    @pytest.mark.asyncio
    async def test_question_text_preserved_from_original(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """원본 question_text 가 그대로 유지된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        llm_out = _make_v1_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v1_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.question_text == original.question_text


# ─── generate_v1_variant 에러 케이스 ─────────────────────────────────────────


class TestGenerateV1VariantErrors:
    @pytest.mark.asyncio
    async def test_non_applicable_type_raises_value_error(self) -> None:
        """V1 비적용 type (grammar_29) → ValueError."""
        original = _make_question(QuestionType.GRAMMAR_29)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V1 변형은"):
            await generate_v1_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

        # LLM 호출 없음
        mock_client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_blank_inference_not_applicable_raises_value_error(self) -> None:
        """blank_phrase_31 도 V1 비적용 type (V2/V5 대상)."""
        original = _make_question(QuestionType.BLANK_PHRASE_31)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V1 변형은"):
            await generate_v1_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

    @pytest.mark.asyncio
    async def test_llm_timeout_propagated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """LLMTimeoutError 그대로 전파."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(side_effect=LLMTimeoutError("timeout"))

        with pytest.raises(LLMTimeoutError):
            await generate_v1_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

    @pytest.mark.asyncio
    async def test_llm_schema_error_propagated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """LLMSchemaValidationError 그대로 전파."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMSchemaValidationError(
                "schema fail",
                validation_error="test",
                raw_response={},
            )
        )

        with pytest.raises(LLMSchemaValidationError):
            await generate_v1_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )


# ─── V1_APPLICABLE_TYPES 커버리지 ────────────────────────────────────────────


class TestV1ApplicableTypes:
    def test_applicable_types_include_required(self) -> None:
        """V1_APPLICABLE_TYPES 는 카탈로그 v0.4 §V1 의 2개 type 을 포함한다."""
        assert QuestionType.VOCABULARY_30 in V1_APPLICABLE_TYPES
        assert QuestionType.LONG_SET_41_42 in V1_APPLICABLE_TYPES

    def test_applicable_types_excludes_grammar(self) -> None:
        """grammar_29 는 V1 비적용."""
        assert QuestionType.GRAMMAR_29 not in V1_APPLICABLE_TYPES

    def test_applicable_types_excludes_blank(self) -> None:
        """blank_phrase_31 는 V1 비적용 (V2/V5 대상)."""
        assert QuestionType.BLANK_PHRASE_31 not in V1_APPLICABLE_TYPES

    def test_applicable_types_excludes_gist(self) -> None:
        """gist_22 는 V1 비적용 (V6 대상)."""
        assert QuestionType.GIST_22 not in V1_APPLICABLE_TYPES

    def test_applicable_types_count(self) -> None:
        """V1 적용 type 은 정확히 2개."""
        assert len(V1_APPLICABLE_TYPES) == 2


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────


def _setup_prompt_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """테스트용 임시 프롬프트 디렉토리 설정.

    실제 docs/prompts/ 파일을 읽지 않도록 tmp_path 에 최소 프롬프트 파일을 생성.
    """
    prompt_file = tmp_path / "variant-vocabulary-swap-v0.md"
    prompt_file.write_text(
        "---\nversion: 0\n---\n"
        "Passage: {{passage_text}}\nType: {{question_type}}\nOriginal: {{original_choices}}",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
