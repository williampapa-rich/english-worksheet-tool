"""generate_v2_variant 단위 테스트 — mock LLM client.

커버 케이스:
  - 정상 생성: vocabulary_30 type.
  - 정상 생성: blank_phrase_31 type.
  - 반환된 Question 의 필드 검증 (variant_kind / derived_from_question_id /
    choices / inline_choices 등).
  - sentinel UUID 채움 검증 (라우트가 model_copy 로 교체하는 자리).
  - V2 비적용 type (grammar_29) → ValueError.
  - box_count 범위 벗어남 → ValueError.
  - inline_choices 범위 벗어남 (1개) → LLMSchemaValidationError (Pydantic validator).
  - choices 5개 미만 → LLMSchemaValidationError.
  - answer 범위 벗어남 → LLMSchemaValidationError.
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
from llm.variants.v2_vocabulary_inline import (
    V2_APPLICABLE_TYPES,
    V2InlineChoiceOutput,
    V2Output,
    generate_v2_variant,
)
from pydantic import ValidationError

from shared.schemas.question import InlineChoiceKind, Question, QuestionType, VariantKind

# ─── fixtures ────────────────────────────────────────────────────────────────

_TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_WORKSPACE_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_PASSAGE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_QUESTION_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

_ZERO_WASTE_PASSAGE = (
    "Reducing waste starts with awareness. When people understand how much they throw away "
    "each day, they become more motivated to change their habits. Small actions — bringing "
    "reusable bags, refusing single-use plastics, and composting food scraps — add up to "
    "significant environmental benefits. Communities that adopt these practices report not "
    "only cleaner surroundings but also lower costs for municipal waste management. "
    "Individual effort, multiplied across an entire community, creates meaningful change."
)

_MODIFIED_PASSAGE = (
    "Reducing waste starts with awareness. When people understand how much they throw away "
    "each day, they become more (A) [motivated / discouraged] to change their habits. "
    "Small actions — bringing reusable bags, refusing single-use plastics, and composting "
    "food scraps — add up to (B) [significant / negligible] environmental benefits. "
    "Communities that adopt these practices report not only cleaner surroundings but also "
    "lower costs for municipal waste management. Individual effort, multiplied across an "
    "entire community, creates meaningful change."
)

_FIVE_CHOICES = [
    "(A) motivated, (B) significant",
    "(A) discouraged, (B) negligible",
    "(A) motivated, (B) negligible",
    "(A) discouraged, (B) significant",
    "(A) discouraged, (B) negligible",
]

_TWO_INLINE_CHOICES = [
    V2InlineChoiceOutput(
        label="(A)",
        options=["motivated", "discouraged"],
        answer_index=0,
        position_marker="they become more (A)",
        kind="vocabulary",
    ),
    V2InlineChoiceOutput(
        label="(B)",
        options=["significant", "negligible"],
        answer_index=0,
        position_marker="add up to (B) environmental",
        kind="vocabulary",
    ),
]


def _make_question(
    question_type: QuestionType = QuestionType.VOCABULARY_30,
    choices: list[str] | None = None,
) -> Question:
    return Question(
        id=_QUESTION_ID,
        tenant_id=_TENANT_ID,
        workspace_id=_WORKSPACE_ID,
        passage_id=_PASSAGE_ID,
        type=question_type,
        variant_kind=VariantKind.ORIGINAL,
        choices=choices or [],
        answer=1,
        question_text="밑줄 친 (A), (B)에 들어갈 말로 가장 적절한 것은?",
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_v2_llm_output(
    inline_choices: list[V2InlineChoiceOutput] | None = None,
    choices: list[str] | None = None,
    answer: int = 1,
) -> V2Output:
    if inline_choices is None:
        inline_choices = _TWO_INLINE_CHOICES
    if choices is None:
        choices = _FIVE_CHOICES
    return V2Output(
        modified_passage_text=_MODIFIED_PASSAGE,
        inline_choices=inline_choices,
        choices=choices,
        answer=answer,
        explanation=(
            "글에서 사람들은 인식이 생기면 습관을 바꾸려는 동기(motivated)가 생긴다고 했으므로 "
            "(A)는 motivated가 적절하다. 작은 실천들이 significant한 환경 이점을 가져온다고 했으므로 "
            "(B)는 significant가 맞다."
        ),
    )


def _make_llm_result(data: Any) -> StructuredLLMResult[Any]:
    return StructuredLLMResult(
        data=data,
        raw_response={},
        usage=TokenUsage(input_tokens=400, output_tokens=200, cache_read_tokens=0),
        model="claude-sonnet-4-6",
        elapsed_ms=1500,
    )


def _make_mock_client(return_data: Any) -> AsyncMock:
    """mock StructuredLLMClient — extract_structured 가 return_data 를 반환."""
    mock = AsyncMock()
    mock.extract_structured = AsyncMock(return_value=_make_llm_result(return_data))
    return mock


# ─── V2Output / V2InlineChoiceOutput Pydantic 검증 ───────────────────────────


class TestV2OutputValidation:
    def test_valid_v2_output(self) -> None:
        """정상 V2Output — Pydantic 검증 통과."""
        out = _make_v2_llm_output()
        assert len(out.inline_choices) == 2
        assert len(out.choices) == 5
        assert out.answer == 1

    def test_inline_choices_one_raises(self) -> None:
        """inline_choices 가 1개 (범위 미달) 이면 ValidationError."""
        with pytest.raises(ValidationError, match="2~3개"):
            V2Output(
                modified_passage_text=_MODIFIED_PASSAGE,
                inline_choices=[_TWO_INLINE_CHOICES[0]],
                choices=_FIVE_CHOICES,
                answer=1,
                explanation="test",
            )

    def test_inline_choices_four_raises(self) -> None:
        """inline_choices 가 4개 (범위 초과) 이면 ValidationError."""
        extra_choice = V2InlineChoiceOutput(
            label="(D)",
            options=["extra", "wrong"],
            answer_index=0,
            kind="vocabulary",
        )
        with pytest.raises(ValidationError, match="2~3개"):
            V2Output(
                modified_passage_text=_MODIFIED_PASSAGE,
                inline_choices=[*_TWO_INLINE_CHOICES, extra_choice, extra_choice],
                choices=_FIVE_CHOICES,
                answer=1,
                explanation="test",
            )

    def test_choices_not_five_raises(self) -> None:
        """choices 가 5개 미만이면 ValidationError."""
        with pytest.raises(ValidationError, match="choices 는 정확히 5개"):
            V2Output(
                modified_passage_text=_MODIFIED_PASSAGE,
                inline_choices=_TWO_INLINE_CHOICES,
                choices=["a", "b", "c"],
                answer=1,
                explanation="test",
            )

    def test_answer_out_of_range_raises(self) -> None:
        """answer 가 1~5 범위를 벗어나면 ValidationError."""
        with pytest.raises(ValidationError):
            V2Output(
                modified_passage_text=_MODIFIED_PASSAGE,
                inline_choices=_TWO_INLINE_CHOICES,
                choices=_FIVE_CHOICES,
                answer=6,
                explanation="test",
            )

    def test_inline_choice_options_not_two_raises(self) -> None:
        """options 가 2개 미만이면 ValidationError (Pydantic min_length 강제)."""
        with pytest.raises(ValidationError):
            V2InlineChoiceOutput(
                label="(A)",
                options=["only_one"],
                answer_index=0,
                kind="vocabulary",
            )

    def test_inline_choice_answer_index_nonzero_raises(self) -> None:
        """answer_index 가 0 이 아니면 ValidationError."""
        with pytest.raises(ValidationError):
            V2InlineChoiceOutput(
                label="(A)",
                options=["correct", "wrong"],
                answer_index=1,  # 0만 허용
                kind="vocabulary",
            )

    def test_three_boxes_valid(self) -> None:
        """inline_choices 3개 — 정상 케이스."""
        third = V2InlineChoiceOutput(
            label="(C)",
            options=["adopt", "abandon"],
            answer_index=0,
            kind="vocabulary",
        )
        out = V2Output(
            modified_passage_text=_MODIFIED_PASSAGE,
            inline_choices=[*_TWO_INLINE_CHOICES, third],
            choices=_FIVE_CHOICES,
            answer=1,
            explanation="test",
        )
        assert len(out.inline_choices) == 3


# ─── generate_v2_variant 정상 케이스 ─────────────────────────────────────────


class TestGenerateV2Variant:
    @pytest.mark.asyncio
    async def test_vocabulary_30_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """vocabulary_30 원본 → V2 변형 Question 반환.

        반환된 Question 의 필드 검증:
          - variant_kind == VOCABULARY_INLINE
          - derived_from_question_id 는 sentinel UUID (라우트가 교체 예정)
          - choices 5개
          - inline_choices 2개
          - type == VOCABULARY_30
        """
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        llm_out = _make_v2_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v2_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert isinstance(result, Question)
        assert result.variant_kind == VariantKind.VOCABULARY_INLINE
        assert result.type == QuestionType.VOCABULARY_30
        assert len(result.choices) == 5
        assert result.answer == 1
        assert result.inline_choices is not None
        assert len(result.inline_choices) == 2
        # sentinel UUID 채워짐 (라우트가 model_copy 로 교체)
        assert result.derived_from_question_id == uuid.UUID(int=0)
        assert result.tenant_id == uuid.UUID(int=0)
        assert result.workspace_id == uuid.UUID(int=0)

    @pytest.mark.asyncio
    async def test_blank_phrase_31_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """blank_phrase_31 원본 → V2 변형 Question 반환 (type 은 vocabulary_30 으로 통일)."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.BLANK_PHRASE_31)
        llm_out = _make_v2_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v2_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.variant_kind == VariantKind.VOCABULARY_INLINE
        # V2 는 vocabulary_30 으로 출력 type 통일 (카탈로그 v0.4 §V2)
        assert result.type == QuestionType.VOCABULARY_30

    @pytest.mark.asyncio
    async def test_inline_choices_converted_to_domain_model(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """inline_choices 가 InlineChoice 도메인 모델로 변환된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        llm_out = _make_v2_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v2_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.inline_choices is not None
        first = result.inline_choices[0]
        assert first.label == "(A)"
        assert first.options == ["motivated", "discouraged"]
        assert first.answer_index == 0
        assert first.kind == InlineChoiceKind.VOCABULARY

    @pytest.mark.asyncio
    async def test_variant_metadata_stored_correctly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """variant_metadata 가 Question.variant_metadata 에 dict 로 저장된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        llm_out = _make_v2_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v2_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.variant_metadata is not None
        assert "modified_passage_text" in result.variant_metadata
        assert result.variant_metadata["box_count"] == 2

    @pytest.mark.asyncio
    async def test_three_boxes_variant(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """box_count=3 으로 호출 시 inline_choices 3개 반환."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        third = V2InlineChoiceOutput(
            label="(C)",
            options=["adopt", "abandon"],
            answer_index=0,
            kind="vocabulary",
        )
        llm_out = _make_v2_llm_output(
            inline_choices=[*_TWO_INLINE_CHOICES, third],
        )
        mock_client = _make_mock_client(llm_out)

        result = await generate_v2_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
            box_count=3,
        )

        assert result.inline_choices is not None
        assert len(result.inline_choices) == 3
        assert result.variant_metadata is not None
        assert result.variant_metadata["box_count"] == 3

    @pytest.mark.asyncio
    async def test_llm_client_called_with_correct_purpose(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLM 호출 시 purpose='variant_v2_vocabulary_inline' 로 로깅."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        llm_out = _make_v2_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v2_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        assert call_kwargs["purpose"] == "variant_v2_vocabulary_inline"


# ─── generate_v2_variant 에러 케이스 ─────────────────────────────────────────


class TestGenerateV2VariantErrors:
    @pytest.mark.asyncio
    async def test_non_applicable_type_raises_value_error(self) -> None:
        """V2 비적용 type (grammar_29) → ValueError."""
        original = _make_question(QuestionType.GRAMMAR_29)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V2 변형은"):
            await generate_v2_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

        # LLM 호출 없음
        mock_client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_applicable_type_gist_22_raises(self) -> None:
        """V2 비적용 type (gist_22) → ValueError."""
        original = _make_question(QuestionType.GIST_22)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V2 변형은"):
            await generate_v2_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

    @pytest.mark.asyncio
    async def test_box_count_out_of_range_raises(self) -> None:
        """box_count 가 1 이면 ValueError."""
        original = _make_question(QuestionType.VOCABULARY_30)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="box_count"):
            await generate_v2_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
                box_count=1,
            )

        mock_client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_box_count_four_raises(self) -> None:
        """box_count 가 4 이면 ValueError."""
        original = _make_question(QuestionType.VOCABULARY_30)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="box_count"):
            await generate_v2_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
                box_count=4,
            )

    @pytest.mark.asyncio
    async def test_llm_timeout_propagated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLMTimeoutError 그대로 전파."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.VOCABULARY_30)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(side_effect=LLMTimeoutError("timeout"))

        with pytest.raises(LLMTimeoutError):
            await generate_v2_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

    @pytest.mark.asyncio
    async def test_llm_schema_error_propagated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
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
            await generate_v2_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )


# ─── V2_APPLICABLE_TYPES 커버리지 ────────────────────────────────────────────


class TestV2ApplicableTypes:
    def test_applicable_types_include_required(self) -> None:
        """V2_APPLICABLE_TYPES 는 카탈로그 v0.4 §V2 의 2개 type 을 포함한다."""
        assert QuestionType.VOCABULARY_30 in V2_APPLICABLE_TYPES
        assert QuestionType.BLANK_PHRASE_31 in V2_APPLICABLE_TYPES

    def test_applicable_types_excludes_grammar(self) -> None:
        """grammar_29 는 V2 비적용."""
        assert QuestionType.GRAMMAR_29 not in V2_APPLICABLE_TYPES

    def test_applicable_types_excludes_gist_22(self) -> None:
        """gist_22 는 V2 비적용 (V6 대상)."""
        assert QuestionType.GIST_22 not in V2_APPLICABLE_TYPES

    def test_applicable_types_excludes_blank_clause(self) -> None:
        """blank_clause_32 는 V2 비적용 (V5 대상)."""
        assert QuestionType.BLANK_CLAUSE_32 not in V2_APPLICABLE_TYPES


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────


def _setup_prompt_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: any) -> None:
    """테스트용 임시 프롬프트 디렉토리 설정.

    실제 docs/prompts/ 파일을 읽지 않도록 tmp_path 에 최소 프롬프트 파일을 생성.
    """
    prompt_file = tmp_path / "variant-vocabulary-inline-v0.md"
    prompt_file.write_text(
        "---\nversion: 0\n---\nPassage: {{passage_text}}\nBox count: {{box_count}}",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
