"""generate_v5_variant 단위 테스트 — mock LLM client.

커버 케이스:
  - 정상 생성: blank_phrase_31 type.
  - 정상 생성: blank_clause_32 type.
  - 반환된 Question 의 필드 검증 (variant_kind / derived_from_question_id /
    choices / has_blanks / variant_metadata.blank_position 등).
  - sentinel UUID 채움 검증 (라우트가 model_copy 로 교체하는 자리).
  - V5 비적용 type (grammar_29) → ValueError.
  - choices 5개 미만 → ValidationError (Pydantic validator).
  - answer 범위 벗어남 → ValidationError.
  - body_with_blank 에 `______` 없음 → ValidationError.
  - blank_position 길이 불일치 → ValidationError.
  - choice_pattern 'correct' 위치 불일치 → ValidationError.
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
from llm.variants.v5_blank_inference import (
    V5_APPLICABLE_TYPES,
    V5Output,
    V5VariantMetadata,
    generate_v5_variant,
)
from pydantic import ValidationError

from shared.schemas.question import Question, QuestionType, VariantKind

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

_BODY_WITH_BLANK = (
    "Reducing waste starts with ______. When people understand how much they throw away "
    "each day, they become more motivated to change their habits. Small actions — bringing "
    "reusable bags, refusing single-use plastics, and composting food scraps — add up to "
    "significant environmental benefits. Communities that adopt these practices report not "
    "only cleaner surroundings but also lower costs for municipal waste management. "
    "Individual effort, multiplied across an entire community, creates meaningful change."
)

_FIVE_CHOICES_PHRASE = [
    "awareness of personal consumption habits",
    "access to recycling infrastructure",
    "complete elimination of single-use products",
    "indifference to environmental consequences",
    "stricter government regulation of industry",
]


def _make_question(
    question_type: QuestionType = QuestionType.BLANK_PHRASE_31,
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
        question_text="다음 빈칸에 들어갈 말로 가장 적절한 것은?",
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_v5_metadata(
    sub_type: str = "blank_phrase_31",
    blank_position: list[int] | None = None,
    choice_pattern: list[str] | None = None,
) -> V5VariantMetadata:
    if blank_position is None:
        blank_position = [24, 33]
    if choice_pattern is None:
        # answer=1 → index 0 = "correct"
        choice_pattern = [
            "correct",
            "too-narrow",
            "too-broad",
            "opposite-conclusion",
            "plausible-unrelated",
        ]
    return V5VariantMetadata(
        sub_type=sub_type,
        blank_position=blank_position,
        choice_pattern=choice_pattern,
    )


def _make_v5_llm_output(
    choices: list[str] | None = None,
    answer: int = 1,
    sub_type: str = "blank_phrase_31",
    blank_position: list[int] | None = None,
    choice_pattern: list[str] | None = None,
    body_with_blank: str | None = None,
) -> V5Output:
    if choices is None:
        choices = _FIVE_CHOICES_PHRASE
    if body_with_blank is None:
        body_with_blank = _BODY_WITH_BLANK
    return V5Output(
        question_type=sub_type,
        body_with_blank=body_with_blank,
        choices=choices,
        answer=answer,
        explanation="이 글은 쓰레기 감소의 출발점이 개인 인식임을 주장한다. 1번 선택지가 이를 정확히 재진술한다.",
        variant_metadata=_make_v5_metadata(
            sub_type=sub_type,
            blank_position=blank_position,
            choice_pattern=choice_pattern,
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


# ─── V5Output / V5VariantMetadata Pydantic 검증 ──────────────────────────────


class TestV5OutputValidation:
    def test_valid_blank_phrase_31_output(self) -> None:
        """정상 blank_phrase_31 출력 — Pydantic 검증 통과."""
        out = _make_v5_llm_output()
        assert len(out.choices) == 5
        assert out.answer == 1
        assert out.variant_metadata.sub_type == "blank_phrase_31"
        assert "______" in out.body_with_blank
        assert out.variant_metadata.blank_position == [24, 33]

    def test_choices_not_five_raises(self) -> None:
        """choices 가 5개 미만이면 ValidationError."""
        with pytest.raises(ValidationError, match="choices 는 정확히 5개"):
            V5Output(
                question_type="blank_phrase_31",
                body_with_blank=_BODY_WITH_BLANK,
                choices=["a", "b", "c"],
                answer=1,
                explanation="test",
                variant_metadata=_make_v5_metadata(),
            )

    def test_answer_out_of_range_raises(self) -> None:
        """answer 가 1~5 범위를 벗어나면 ValidationError."""
        with pytest.raises(ValidationError):
            V5Output(
                question_type="blank_phrase_31",
                body_with_blank=_BODY_WITH_BLANK,
                choices=_FIVE_CHOICES_PHRASE,
                answer=6,
                explanation="test",
                variant_metadata=_make_v5_metadata(),
            )

    def test_body_with_blank_missing_marker_raises(self) -> None:
        """body_with_blank 에 `______` 가 없으면 ValidationError."""
        with pytest.raises(ValidationError, match="______"):
            V5Output(
                question_type="blank_phrase_31",
                body_with_blank="No blank marker here.",
                choices=_FIVE_CHOICES_PHRASE,
                answer=1,
                explanation="test",
                variant_metadata=_make_v5_metadata(),
            )

    def test_body_with_blank_multiple_markers_raises(self) -> None:
        """body_with_blank 에 `______` 가 2개이면 ValidationError."""
        with pytest.raises(ValidationError, match="______"):
            V5Output(
                question_type="blank_phrase_31",
                body_with_blank="First ______ and second ______.",
                choices=_FIVE_CHOICES_PHRASE,
                answer=1,
                explanation="test",
                variant_metadata=_make_v5_metadata(),
            )

    def test_choice_pattern_answer_mismatch_raises(self) -> None:
        """answer=2 인데 choice_pattern[0]='correct' 이면 ValidationError."""
        with pytest.raises(ValidationError, match="불일치"):
            V5Output(
                question_type="blank_phrase_31",
                body_with_blank=_BODY_WITH_BLANK,
                choices=_FIVE_CHOICES_PHRASE,
                answer=2,
                explanation="test",
                variant_metadata=_make_v5_metadata(
                    choice_pattern=[
                        "correct",  # answer=2 → index=1 이 "correct" 여야 하는데 index=0 이 "correct"
                        "too-narrow",
                        "too-broad",
                        "opposite-conclusion",
                        "plausible-unrelated",
                    ]
                ),
            )

    def test_blank_position_not_two_elements_raises(self) -> None:
        """blank_position 이 2개가 아니면 ValidationError."""
        with pytest.raises(ValidationError, match="blank_position 은 정확히"):
            V5VariantMetadata(
                sub_type="blank_phrase_31",
                blank_position=[24],  # 1개만 — 오류
                choice_pattern=[
                    "correct",
                    "too-narrow",
                    "too-broad",
                    "opposite-conclusion",
                    "plausible-unrelated",
                ],
            )

    def test_blank_position_end_not_greater_than_start_raises(self) -> None:
        """blank_position[1] <= blank_position[0] 이면 ValidationError."""
        with pytest.raises(ValidationError, match="end.*start"):
            V5VariantMetadata(
                sub_type="blank_phrase_31",
                blank_position=[24, 24],  # end == start — 오류
                choice_pattern=[
                    "correct",
                    "too-narrow",
                    "too-broad",
                    "opposite-conclusion",
                    "plausible-unrelated",
                ],
            )

    def test_invalid_choice_pattern_value_raises(self) -> None:
        """허용되지 않은 choice_pattern 값이면 ValidationError."""
        with pytest.raises(ValidationError, match="허용되지 않은"):
            V5VariantMetadata(
                sub_type="blank_phrase_31",
                blank_position=[24, 33],
                choice_pattern=[
                    "correct",
                    "too-narrow",
                    "too-broad",
                    "opposite-conclusion",
                    "INVALID_PATTERN",
                ],
            )

    def test_choice_pattern_wrong_correct_count_raises(self) -> None:
        """choice_pattern 에 'correct' 가 2개이면 ValidationError."""
        with pytest.raises(ValidationError, match="'correct' 가 정확히 1개"):
            V5VariantMetadata(
                sub_type="blank_phrase_31",
                blank_position=[24, 33],
                choice_pattern=[
                    "correct",
                    "correct",
                    "too-broad",
                    "opposite-conclusion",
                    "plausible-unrelated",
                ],
            )


# ─── generate_v5_variant 정상 케이스 ─────────────────────────────────────────


class TestGenerateV5Variant:
    @pytest.mark.asyncio
    async def test_blank_phrase_31_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """blank_phrase_31 원본 → V5 변형 Question 반환.

        반환된 Question 의 필드 검증:
          - variant_kind == BLANK_INFERENCE
          - derived_from_question_id 는 sentinel UUID (라우트가 교체 예정)
          - choices 5개
          - has_blanks == True
          - type == BLANK_PHRASE_31 (원본과 동일)
          - variant_metadata 에 blank_position + body_with_blank 포함
        """
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.BLANK_PHRASE_31)
        llm_out = _make_v5_llm_output(sub_type="blank_phrase_31")
        mock_client = _make_mock_client(llm_out)

        result = await generate_v5_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert isinstance(result, Question)
        assert result.variant_kind == VariantKind.BLANK_INFERENCE
        assert result.type == QuestionType.BLANK_PHRASE_31
        assert len(result.choices) == 5
        assert result.answer == 1
        assert result.has_blanks is True
        # sentinel UUID 채워짐 (라우트가 model_copy 로 교체)
        assert result.derived_from_question_id == uuid.UUID(int=0)
        assert result.tenant_id == uuid.UUID(int=0)
        assert result.workspace_id == uuid.UUID(int=0)

    @pytest.mark.asyncio
    async def test_blank_clause_32_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """blank_clause_32 원본 → V5 변형 Question 반환."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.BLANK_CLAUSE_32)
        llm_out = _make_v5_llm_output(
            choices=[
                "individual habits drive collective change",
                "recycling bins reduce municipal costs",
                "governments must enforce strict waste policies",
                "people are naturally indifferent to waste",
                "corporate pollution outweighs personal impact",
            ],
            sub_type="blank_clause_32",
            body_with_blank=(
                "Research confirms that ______. Small actions add up to significant benefits."
            ),
        )
        mock_client = _make_mock_client(llm_out)

        result = await generate_v5_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.type == QuestionType.BLANK_CLAUSE_32
        assert result.variant_kind == VariantKind.BLANK_INFERENCE
        assert result.has_blanks is True

    @pytest.mark.asyncio
    async def test_variant_metadata_stored_correctly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """variant_metadata 가 Question.variant_metadata 에 dict 로 저장된다.

        V5 전용 필드 blank_position + body_with_blank 포함 검증.
        """
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.BLANK_PHRASE_31)
        llm_out = _make_v5_llm_output(
            sub_type="blank_phrase_31",
            blank_position=[24, 33],
        )
        mock_client = _make_mock_client(llm_out)

        result = await generate_v5_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.variant_metadata is not None
        assert result.variant_metadata["sub_type"] == "blank_phrase_31"
        assert result.variant_metadata["blank_position"] == [24, 33]
        assert "______" in result.variant_metadata["body_with_blank"]
        assert len(result.variant_metadata["choice_pattern"]) == 5
        assert "correct" in result.variant_metadata["choice_pattern"]

    @pytest.mark.asyncio
    async def test_llm_client_called_with_correct_purpose(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLM 호출 시 purpose='variant_v5_blank_inference' 로 로깅."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.BLANK_PHRASE_31)
        llm_out = _make_v5_llm_output(sub_type="blank_phrase_31")
        mock_client = _make_mock_client(llm_out)

        await generate_v5_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        assert call_kwargs["purpose"] == "variant_v5_blank_inference"

    @pytest.mark.asyncio
    async def test_blank_position_hint_passed_to_prompt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """blank_position_hint 가 프롬프트 변수에 포함되어 LLM 에 전달된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.BLANK_PHRASE_31)
        llm_out = _make_v5_llm_output(sub_type="blank_phrase_31")
        mock_client = _make_mock_client(llm_out)

        await generate_v5_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
            blank_position_hint="thesis sentence first phrase",
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        prompt = call_kwargs["prompt"]
        rendered = prompt.render()
        assert "thesis sentence first phrase" in rendered


# ─── generate_v5_variant 에러 케이스 ─────────────────────────────────────────


class TestGenerateV5VariantErrors:
    @pytest.mark.asyncio
    async def test_non_applicable_type_raises_value_error(self) -> None:
        """V5 비적용 type (grammar_29) → ValueError."""
        original = _make_question(QuestionType.GRAMMAR_29)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V5 변형은"):
            await generate_v5_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

        # LLM 호출 없음
        mock_client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_gist_22_not_applicable_raises_value_error(self) -> None:
        """gist_22 (V6 type) 는 V5 비적용 → ValueError."""
        original = _make_question(QuestionType.GIST_22)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V5 변형은"):
            await generate_v5_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

        mock_client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_timeout_propagated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLMTimeoutError 그대로 전파."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.BLANK_PHRASE_31)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMTimeoutError("timeout")
        )

        with pytest.raises(LLMTimeoutError):
            await generate_v5_variant(
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
        original = _make_question(QuestionType.BLANK_PHRASE_31)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMSchemaValidationError(
                "schema fail",
                validation_error="test",
                raw_response={},
            )
        )

        with pytest.raises(LLMSchemaValidationError):
            await generate_v5_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )


# ─── V5_APPLICABLE_TYPES 커버리지 ────────────────────────────────────────────


class TestV5ApplicableTypes:
    def test_applicable_types_include_all_blank_types(self) -> None:
        """V5_APPLICABLE_TYPES 는 카탈로그 v0.4 §V5 의 4개 type 을 포함한다."""
        assert QuestionType.BLANK_PHRASE_31 in V5_APPLICABLE_TYPES
        assert QuestionType.BLANK_CLAUSE_32 in V5_APPLICABLE_TYPES
        assert QuestionType.BLANK_CLAUSE_33 in V5_APPLICABLE_TYPES
        assert QuestionType.BLANK_CLAUSE_34 in V5_APPLICABLE_TYPES

    def test_applicable_types_excludes_grammar(self) -> None:
        """grammar_29 는 V5 비적용."""
        assert QuestionType.GRAMMAR_29 not in V5_APPLICABLE_TYPES

    def test_applicable_types_excludes_gist(self) -> None:
        """gist_22 (V6 대상) 는 V5 비적용."""
        assert QuestionType.GIST_22 not in V5_APPLICABLE_TYPES

    def test_applicable_types_excludes_topic(self) -> None:
        """theme_23 (V6 대상) 는 V5 비적용."""
        assert QuestionType.THEME_23 not in V5_APPLICABLE_TYPES


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────


def _setup_prompt_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: any) -> None:
    """테스트용 임시 프롬프트 디렉토리 설정.

    실제 docs/prompts/ 파일을 읽지 않도록 tmp_path 에 최소 프롬프트 파일을 생성.
    """
    prompt_file = tmp_path / "variant-blank-inference-v0.md"
    prompt_file.write_text(
        "---\nversion: 0\n---\n"
        "Passage: {{passage_text}}\nType: {{question_type}}\n"
        "Blank hint: {{blank_position_hint}}",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
