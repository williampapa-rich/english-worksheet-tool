"""generate_v10_variant 단위 테스트 — mock LLM client.

커버 케이스:
  - 정상 생성: summary_40 type → V10 변형 Question 반환.
  - 반환된 Question 의 필드 검증
    (variant_kind / type / summary / choices / choice_matrix / choice_format / answer).
  - sentinel UUID 채움 검증 (라우트가 model_copy 로 교체하는 자리).
  - variant_metadata 에 summary_text / blank_a_word / blank_b_word 저장 확인.
  - V10 비적용 type (grammar_29) → ValueError.
  - choices 5개 미만 → Pydantic ValidationError.
  - choice_matrix rows 5개 미만 → Pydantic ValidationError.
  - distractor_pattern 'correct' 위치 불일치 → Pydantic ValidationError.
  - distractor_pattern 필수 패턴 누락 → Pydantic ValidationError.
  - summary_text 에 (A) 마커 없음 → Pydantic ValidationError.
  - summary_text 에 (B) 마커 없음 → Pydantic ValidationError.
  - blank_a_word / blank_b_word 와 choice_matrix 정답 row 불일치 → Pydantic ValidationError.
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
from llm.variants.v10_summary_blank_swap import (
    V10_APPLICABLE_TYPES,
    V10ChoiceMatrix,
    V10Output,
    generate_v10_variant,
)
from pydantic import ValidationError

from shared.schemas.question import (
    ChoiceFormat,
    Question,
    QuestionType,
    VariantKind,
)

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

_SUMMARY_TEXT = (
    "Individual (A) ______ of small habits, when shared across a community, "
    "can (B) ______ substantial environmental and economic benefits."
)

_FIVE_CHOICES = [
    "(A) adoption …… (B) generate",
    "(A) generate …… (B) adoption",
    "(A) rejection …… (B) generate",
    "(A) adoption …… (B) eliminate",
    "(A) awareness …… (B) reduce",
]

_CHOICE_MATRIX_ROWS = [
    ["adoption", "generate"],
    ["generate", "adoption"],
    ["rejection", "generate"],
    ["adoption", "eliminate"],
    ["awareness", "reduce"],
]


def _make_question(
    question_type: QuestionType = QuestionType.SUMMARY_40,
    summary: str | None = None,
) -> Question:
    return Question(
        id=_QUESTION_ID,
        tenant_id=_TENANT_ID,
        workspace_id=_WORKSPACE_ID,
        passage_id=_PASSAGE_ID,
        type=question_type,
        variant_kind=VariantKind.ORIGINAL,
        choices=[],
        answer=1,
        question_text=(
            "다음 글의 내용을 한 문장으로 요약하고자 한다. "
            "빈칸 (A), (B)에 들어갈 말로 가장 적절한 것은?"
        ),
        summary=summary,
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_v10_choice_matrix(
    rows: list[list[str]] | None = None,
) -> V10ChoiceMatrix:
    return V10ChoiceMatrix(
        columns=["(A)", "(B)"],
        rows=rows if rows is not None else _CHOICE_MATRIX_ROWS,
    )


def _make_v10_llm_output(
    summary_text: str = _SUMMARY_TEXT,
    blank_a_word: str = "adoption",
    blank_b_word: str = "generate",
    choices: list[str] | None = None,
    answer: int = 1,
    distractor_pattern: list[str] | None = None,
    choice_matrix_rows: list[list[str]] | None = None,
) -> V10Output:
    if choices is None:
        choices = _FIVE_CHOICES
    if distractor_pattern is None:
        # answer=1 → index 0 = "correct"
        distractor_pattern = ["correct", "swap", "wrong_a", "wrong_b", "both_wrong"]
    return V10Output(
        summary_text=summary_text,
        blank_a_word=blank_a_word,
        blank_b_word=blank_b_word,
        choices=choices,
        choice_matrix=_make_v10_choice_matrix(choice_matrix_rows),
        answer=answer,
        explanation="이 글의 핵심 주장은 개인의 작은 습관 실천이 지역 사회 전체로 퍼질 때 효과를 만들어낸다는 것이다.",
        distractor_pattern=distractor_pattern,
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


# ─── V10Output / V10ChoiceMatrix Pydantic 검증 ───────────────────────────────


class TestV10OutputValidation:
    def test_valid_output(self) -> None:
        """정상 V10 출력 — Pydantic 검증 통과."""
        out = _make_v10_llm_output()
        assert out.summary_text == _SUMMARY_TEXT
        assert out.blank_a_word == "adoption"
        assert out.blank_b_word == "generate"
        assert len(out.choices) == 5
        assert out.answer == 1
        assert out.choice_matrix.columns == ["(A)", "(B)"]
        assert len(out.choice_matrix.rows) == 5

    def test_summary_text_missing_blank_a_raises(self) -> None:
        """summary_text 에 (A) ______ 마커가 없으면 ValidationError."""
        bad_summary = "Something (B) ______ without A marker."
        with pytest.raises(ValidationError, match=r"\(A\) ______"):
            _make_v10_llm_output(summary_text=bad_summary)

    def test_summary_text_missing_blank_b_raises(self) -> None:
        """summary_text 에 (B) ______ 마커가 없으면 ValidationError."""
        bad_summary = "Individual (A) ______ of small habits without B marker."
        with pytest.raises(ValidationError, match=r"\(B\) ______"):
            _make_v10_llm_output(summary_text=bad_summary)

    def test_choices_not_five_raises(self) -> None:
        """choices 가 5개 미만이면 ValidationError."""
        with pytest.raises(ValidationError, match="choices 는 정확히 5개"):
            _make_v10_llm_output(choices=["(A) a …… (B) b", "(A) c …… (B) d"])

    def test_choice_matrix_rows_not_five_raises(self) -> None:
        """choice_matrix rows 가 5개 미만이면 ValidationError."""
        bad_rows = [["a", "b"], ["c", "d"]]
        with pytest.raises(ValidationError, match="rows 는 정확히 5개"):
            _make_v10_llm_output(choice_matrix_rows=bad_rows)

    def test_distractor_pattern_correct_position_mismatch_raises(self) -> None:
        """answer=2 인데 distractor_pattern[0]='correct' 이면 ValidationError."""
        # answer=2 → index 1 이 'correct' 여야 하는데 index 0 에 'correct'
        with pytest.raises(ValidationError, match="불일치"):
            _make_v10_llm_output(
                answer=2,
                distractor_pattern=["correct", "swap", "wrong_a", "wrong_b", "both_wrong"],
                choices=[
                    "(A) adoption …… (B) generate",
                    "(A) generate …… (B) adoption",
                    "(A) rejection …… (B) generate",
                    "(A) adoption …… (B) eliminate",
                    "(A) awareness …… (B) reduce",
                ],
                choice_matrix_rows=_CHOICE_MATRIX_ROWS,
            )

    def test_distractor_pattern_missing_required_pattern_raises(self) -> None:
        """distractor_pattern 에 'both_wrong' 이 누락되면 ValidationError."""
        with pytest.raises(ValidationError, match="필수 패턴이 누락"):
            _make_v10_llm_output(
                distractor_pattern=["correct", "swap", "wrong_a", "wrong_b", "wrong_b"],
            )

    def test_blank_a_word_mismatch_choice_matrix_raises(self) -> None:
        """blank_a_word 가 choice_matrix 정답 row[0] 과 다르면 ValidationError."""
        with pytest.raises(ValidationError, match="blank_a_word"):
            _make_v10_llm_output(blank_a_word="WRONG_WORD")

    def test_blank_b_word_mismatch_choice_matrix_raises(self) -> None:
        """blank_b_word 가 choice_matrix 정답 row[1] 과 다르면 ValidationError."""
        with pytest.raises(ValidationError, match="blank_b_word"):
            _make_v10_llm_output(blank_b_word="WRONG_WORD")

    def test_answer_at_position_3_valid(self) -> None:
        """answer=3 + distractor_pattern[2]='correct' — 정상."""
        rows = [
            ["rejection", "generate"],
            ["generate", "adoption"],
            ["adoption", "generate"],  # correct at index 2
            ["adoption", "eliminate"],
            ["awareness", "reduce"],
        ]
        choices = [
            "(A) rejection …… (B) generate",
            "(A) generate …… (B) adoption",
            "(A) adoption …… (B) generate",
            "(A) adoption …… (B) eliminate",
            "(A) awareness …… (B) reduce",
        ]
        out = _make_v10_llm_output(
            answer=3,
            distractor_pattern=["wrong_a", "swap", "correct", "wrong_b", "both_wrong"],
            choices=choices,
            choice_matrix_rows=rows,
        )
        assert out.answer == 3
        assert out.distractor_pattern[2] == "correct"


# ─── generate_v10_variant 정상 케이스 ────────────────────────────────────────


class TestGenerateV10Variant:
    @pytest.mark.asyncio
    async def test_summary_40_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """summary_40 원본 → V10 변형 Question 반환.

        반환된 Question 의 필드 검증:
          - variant_kind == SUMMARY_BLANK_SWAP
          - type == SUMMARY_40
          - derived_from_question_id 는 sentinel UUID (라우트가 교체 예정)
          - choices 5개
          - choice_format == MATRIX_AB
          - choice_matrix 가 NOT NULL
          - summary 에 (A)/(B) 마커 존재
        """
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.SUMMARY_40)
        llm_out = _make_v10_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v10_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert isinstance(result, Question)
        assert result.variant_kind == VariantKind.SUMMARY_BLANK_SWAP
        assert result.type == QuestionType.SUMMARY_40
        assert len(result.choices) == 5
        assert result.answer == 1
        assert result.choice_format == ChoiceFormat.MATRIX_AB
        assert result.choice_matrix is not None
        assert result.choice_matrix.columns == ["(A)", "(B)"]
        assert len(result.choice_matrix.rows) == 5
        assert result.summary is not None
        assert "(A) ______" in result.summary
        assert "(B) ______" in result.summary
        # sentinel UUID 채워짐 (라우트가 model_copy 로 교체)
        assert result.derived_from_question_id == uuid.UUID(int=0)
        assert result.tenant_id == uuid.UUID(int=0)
        assert result.workspace_id == uuid.UUID(int=0)

    @pytest.mark.asyncio
    async def test_variant_metadata_stored_correctly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """variant_metadata 에 summary_text / blank_a_word / blank_b_word 저장."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.SUMMARY_40)
        llm_out = _make_v10_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v10_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.variant_metadata is not None
        assert result.variant_metadata["summary_text"] == _SUMMARY_TEXT
        assert result.variant_metadata["blank_a_word"] == "adoption"
        assert result.variant_metadata["blank_b_word"] == "generate"

    @pytest.mark.asyncio
    async def test_llm_client_called_with_correct_purpose(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """LLM 호출 시 purpose='variant_v10_summary_blank_swap' 로 로깅."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.SUMMARY_40)
        llm_out = _make_v10_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v10_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        assert call_kwargs["purpose"] == "variant_v10_summary_blank_swap"

    @pytest.mark.asyncio
    async def test_original_summary_passed_to_prompt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """원본 요약문이 프롬프트 변수에 포함되어 LLM 에 전달된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(
            QuestionType.SUMMARY_40,
            summary="Awareness leads to (A) ______ habits that (B) ______ community.",
        )
        llm_out = _make_v10_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v10_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        prompt = call_kwargs["prompt"]
        rendered = prompt.render()
        assert "Awareness leads to" in rendered

    @pytest.mark.asyncio
    async def test_no_original_summary_uses_none_placeholder(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """원본 요약문이 없으면 '(none)' 플레이스홀더가 프롬프트에 전달된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.SUMMARY_40, summary=None)
        llm_out = _make_v10_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v10_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        prompt = call_kwargs["prompt"]
        rendered = prompt.render()
        assert "(none)" in rendered


# ─── generate_v10_variant 에러 케이스 ────────────────────────────────────────


class TestGenerateV10VariantErrors:
    @pytest.mark.asyncio
    async def test_non_applicable_type_raises_value_error(self) -> None:
        """V10 비적용 type (grammar_29) → ValueError."""
        original = _make_question(QuestionType.GRAMMAR_29)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V10 변형은"):
            await generate_v10_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

        # LLM 호출 없음
        mock_client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_timeout_propagated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """LLMTimeoutError 그대로 전파."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.SUMMARY_40)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMTimeoutError("timeout")
        )

        with pytest.raises(LLMTimeoutError):
            await generate_v10_variant(
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
        original = _make_question(QuestionType.SUMMARY_40)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMSchemaValidationError(
                "schema fail",
                validation_error="test",
                raw_response={},
            )
        )

        with pytest.raises(LLMSchemaValidationError):
            await generate_v10_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )


# ─── V10_APPLICABLE_TYPES 커버리지 ───────────────────────────────────────────


class TestV10ApplicableTypes:
    def test_applicable_types_include_summary_40(self) -> None:
        """V10_APPLICABLE_TYPES 는 summary_40 을 포함한다."""
        assert QuestionType.SUMMARY_40 in V10_APPLICABLE_TYPES

    def test_applicable_types_excludes_grammar_29(self) -> None:
        """grammar_29 는 V10 비적용."""
        assert QuestionType.GRAMMAR_29 not in V10_APPLICABLE_TYPES

    def test_applicable_types_excludes_blank_phrase_31(self) -> None:
        """blank_phrase_31 은 V10 비적용 (V5 대상)."""
        assert QuestionType.BLANK_PHRASE_31 not in V10_APPLICABLE_TYPES

    def test_applicable_types_excludes_gist_22(self) -> None:
        """gist_22 는 V10 비적용 (V6 대상)."""
        assert QuestionType.GIST_22 not in V10_APPLICABLE_TYPES


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────


def _setup_prompt_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """테스트용 임시 프롬프트 디렉토리 설정.

    실제 docs/prompts/ 파일을 읽지 않도록 tmp_path 에 최소 프롬프트 파일을 생성.
    """
    prompt_file = tmp_path / "variant-summary-blank-swap-v0.md"
    prompt_file.write_text(
        "---\nversion: 0\n---\n"
        "Passage: {{passage_text}}\n"
        "Original summary: {{original_summary}}",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
