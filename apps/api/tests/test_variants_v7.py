"""generate_v7_variant 단위 테스트 — mock LLM client.

커버 케이스:
  - 정상 생성: paragraph_order_36 / paragraph_order_37 각 type.
  - 반환된 Question 의 필드 검증 (variant_kind / sub_passages / choices / derived_from 등).
  - sentinel UUID 채움 검증 (라우트가 model_copy 로 교체하는 자리).
  - V7 비적용 type (grammar_29) → ValueError.
  - sub_passages 가 3개 미만 → Pydantic ValidationError.
  - choices 가 5개 미만 → Pydantic ValidationError.
  - choices 형식 오류 → Pydantic ValidationError.
  - choice_pattern 'correct' 위치 불일치 → Pydantic ValidationError.
  - choices 중복 → Pydantic ValidationError.
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
from llm.variants.v7_order_shuffle import (
    V7_APPLICABLE_TYPES,
    V7Output,
    V7VariantMetadata,
    generate_v7_variant,
)
from pydantic import ValidationError

from shared.schemas.question import Question, QuestionType, VariantKind

# ─── fixtures ────────────────────────────────────────────────────────────────

_TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_WORKSPACE_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_PASSAGE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_QUESTION_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

_URBAN_CYCLING_PASSAGE = (
    "Over the past decade, urban cycling has transformed from a niche hobby into a mainstream "
    "mode of transportation. "
    "City planners began investing in dedicated bike lanes and secure parking facilities, "
    "making cycling safer and more convenient for commuters. "
    "As a result, ridership numbers climbed steadily each year. "
    "However, this growth brought new challenges. "
    "The increased number of cyclists created congestion at popular intersections and raised "
    "concerns about conflicts with pedestrians. "
    "Consequently, city authorities introduced stricter traffic regulations and updated "
    "signage to manage the new dynamics."
)

_INTRO = (
    "Over the past decade, urban cycling has transformed from a niche hobby into a mainstream "
    "mode of transportation."
)

_SUB_PASSAGES = [
    [
        "City planners began investing in dedicated bike lanes and secure parking facilities, "
        "making cycling safer and more convenient for commuters.",
        "As a result, ridership numbers climbed steadily each year.",
    ],
    [
        "However, this growth brought new challenges.",
        "The increased number of cyclists created congestion at popular intersections and "
        "raised concerns about conflicts with pedestrians.",
    ],
    [
        "Consequently, city authorities introduced stricter traffic regulations and updated "
        "signage to manage the new dynamics."
    ],
]

_FIVE_ORDER_CHOICES = [
    "(A) - (B) - (C)",
    "(B) - (A) - (C)",
    "(C) - (A) - (B)",
    "(A) - (C) - (B)",
    "(B) - (C) - (A)",
]

_EXPLANATION_KO = (
    "(A)는 도시 인프라 투자를 소개하며 자전거 이용자 증가로 연결되고, "
    "(B)는 'However'로 역접 전환하여 혼잡 문제를 제기한다. "
    "(C)는 'Consequently'로 (B)의 문제에 대한 당국의 대응을 결론짓는다."
)


def _make_question(
    question_type: QuestionType = QuestionType.ORDER_36,
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
        question_text="주어진 글 다음에 이어질 글의 순서로 가장 적절한 것은?",
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_v7_metadata(
    answer: int = 1,
) -> V7VariantMetadata:
    choice_pattern = ["distractor"] * 5
    choice_pattern[answer - 1] = "correct"
    return V7VariantMetadata(
        intro_paragraph=_INTRO,
        split_categories=["conjunction", "anaphoric_pronoun"],
        choice_pattern=choice_pattern,
    )


def _make_v7_llm_output(
    choices: list[str] | None = None,
    answer: int = 1,
    sub_passages: list[list[str]] | None = None,
) -> V7Output:
    if choices is None:
        choices = _FIVE_ORDER_CHOICES
    if sub_passages is None:
        sub_passages = _SUB_PASSAGES
    return V7Output(
        intro_paragraph=_INTRO,
        sub_passages=sub_passages,
        choices=choices,
        answer=answer,
        explanation=_EXPLANATION_KO,
        variant_metadata=_make_v7_metadata(answer=answer),
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


# ─── V7Output / V7VariantMetadata Pydantic 검증 ──────────────────────────────


class TestV7OutputValidation:
    def test_valid_order_36_output(self) -> None:
        """정상 paragraph_order_36 출력 — Pydantic 검증 통과."""
        out = _make_v7_llm_output()
        assert len(out.sub_passages) == 3
        assert len(out.choices) == 5
        assert out.answer == 1
        assert out.variant_metadata.intro_paragraph == _INTRO

    def test_sub_passages_not_three_raises(self) -> None:
        """sub_passages 가 3개 미만이면 ValidationError."""
        with pytest.raises(ValidationError, match="sub_passages 는 정확히 3개"):
            V7Output(
                intro_paragraph=_INTRO,
                sub_passages=[["sentence A"], ["sentence B"]],  # 2개 — 부족
                choices=_FIVE_ORDER_CHOICES,
                answer=1,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v7_metadata(),
            )

    def test_sub_passages_empty_inner_raises(self) -> None:
        """sub_passages inner list 가 비어 있으면 ValidationError."""
        with pytest.raises(ValidationError, match="최소 1개 문장"):
            V7Output(
                intro_paragraph=_INTRO,
                sub_passages=[["sentence A"], [], ["sentence C"]],  # (B) 비어 있음
                choices=_FIVE_ORDER_CHOICES,
                answer=1,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v7_metadata(),
            )

    def test_choices_not_five_raises(self) -> None:
        """choices 가 5개 미만이면 ValidationError."""
        with pytest.raises(ValidationError, match="choices 는 정확히 5개"):
            V7Output(
                intro_paragraph=_INTRO,
                sub_passages=_SUB_PASSAGES,
                choices=["(A) - (B) - (C)", "(B) - (A) - (C)", "(C) - (A) - (B)"],
                answer=1,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v7_metadata(),
            )

    def test_choice_format_invalid_raises(self) -> None:
        """choices 형식 오류 (예: 번호 형식) 이면 ValidationError."""
        with pytest.raises(ValidationError, match="형식 오류"):
            V7Output(
                intro_paragraph=_INTRO,
                sub_passages=_SUB_PASSAGES,
                choices=[
                    "A-B-C",  # 잘못된 형식
                    "(B) - (A) - (C)",
                    "(C) - (A) - (B)",
                    "(A) - (C) - (B)",
                    "(B) - (C) - (A)",
                ],
                answer=1,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v7_metadata(),
            )

    def test_choices_duplicate_raises(self) -> None:
        """choices 에 중복 순서 조합이 있으면 ValidationError."""
        with pytest.raises(ValidationError, match="고유해야"):
            V7Output(
                intro_paragraph=_INTRO,
                sub_passages=_SUB_PASSAGES,
                choices=[
                    "(A) - (B) - (C)",
                    "(A) - (B) - (C)",  # 중복
                    "(C) - (A) - (B)",
                    "(A) - (C) - (B)",
                    "(B) - (C) - (A)",
                ],
                answer=1,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v7_metadata(),
            )

    def test_answer_out_of_range_raises(self) -> None:
        """answer 가 1~5 범위를 벗어나면 ValidationError."""
        with pytest.raises(ValidationError):
            V7Output(
                intro_paragraph=_INTRO,
                sub_passages=_SUB_PASSAGES,
                choices=_FIVE_ORDER_CHOICES,
                answer=6,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v7_metadata(answer=1),  # answer 는 V7Output 레벨에서 6 → 검증
            )

    def test_choice_pattern_answer_mismatch_raises(self) -> None:
        """answer=2 인데 choice_pattern[0]='correct' 이면 ValidationError."""
        with pytest.raises(ValidationError, match="불일치"):
            V7Output(
                intro_paragraph=_INTRO,
                sub_passages=_SUB_PASSAGES,
                choices=_FIVE_ORDER_CHOICES,
                answer=2,
                explanation=_EXPLANATION_KO,
                variant_metadata=V7VariantMetadata(
                    intro_paragraph=_INTRO,
                    split_categories=["conjunction"],
                    # answer=2 → index=1 이 "correct" 여야 하는데 index=0 이 "correct"
                    choice_pattern=["correct", "distractor", "distractor", "distractor", "distractor"],
                ),
            )

    def test_invalid_split_category_raises(self) -> None:
        """허용되지 않은 split_categories 값이면 ValidationError."""
        with pytest.raises(ValidationError, match="허용되지 않은 split_categories"):
            V7VariantMetadata(
                intro_paragraph=_INTRO,
                split_categories=["conjunction", "INVALID_CATEGORY"],
                choice_pattern=["correct", "distractor", "distractor", "distractor", "distractor"],
            )

    def test_choice_pattern_wrong_correct_count_raises(self) -> None:
        """choice_pattern 에 'correct' 가 2개이면 ValidationError."""
        with pytest.raises(ValidationError, match="'correct' 가 정확히 1개"):
            V7VariantMetadata(
                intro_paragraph=_INTRO,
                split_categories=["conjunction"],
                choice_pattern=["correct", "correct", "distractor", "distractor", "distractor"],
            )

    def test_choice_pattern_invalid_value_raises(self) -> None:
        """choice_pattern 에 'correct' / 'distractor' 외 값이면 ValidationError."""
        with pytest.raises(ValidationError, match="허용되지 않은 choice_pattern"):
            V7VariantMetadata(
                intro_paragraph=_INTRO,
                split_categories=["conjunction"],
                choice_pattern=["correct", "distractor", "distractor", "distractor", "INVALID"],
            )


# ─── generate_v7_variant 정상 케이스 ─────────────────────────────────────────


class TestGenerateV7Variant:
    @pytest.mark.asyncio
    async def test_order_36_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """paragraph_order_36 원본 → V7 변형 Question 반환.

        반환된 Question 의 필드 검증:
          - variant_kind == ORDER_SHUFFLE
          - derived_from_question_id 는 sentinel UUID (라우트가 교체 예정)
          - sub_passages 3개 inner list
          - choices 5개 순서 조합 문자열
          - type == ORDER_36 (원본과 동일)
        """
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.ORDER_36)
        llm_out = _make_v7_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v7_variant(
            passage_text=_URBAN_CYCLING_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert isinstance(result, Question)
        assert result.variant_kind == VariantKind.ORDER_SHUFFLE
        assert result.type == QuestionType.ORDER_36
        assert result.sub_passages is not None
        assert len(result.sub_passages) == 3
        assert all(len(para) >= 1 for para in result.sub_passages)
        assert len(result.choices) == 5
        assert result.answer == 1
        # sentinel UUID 채워짐 (라우트가 model_copy 로 교체)
        assert result.derived_from_question_id == uuid.UUID(int=0)
        assert result.tenant_id == uuid.UUID(int=0)
        assert result.workspace_id == uuid.UUID(int=0)

    @pytest.mark.asyncio
    async def test_order_37_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """paragraph_order_37 원본 → V7 변형 Question 반환."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.ORDER_37)
        llm_out = _make_v7_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v7_variant(
            passage_text=_URBAN_CYCLING_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.type == QuestionType.ORDER_37
        assert result.variant_kind == VariantKind.ORDER_SHUFFLE

    @pytest.mark.asyncio
    async def test_choices_are_order_combination_strings(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """choices 가 '(X) - (Y) - (Z)' 형식 문자열 5개인지 확인."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.ORDER_36)
        llm_out = _make_v7_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v7_variant(
            passage_text=_URBAN_CYCLING_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        import re

        pattern = re.compile(r"^\([ABC]\) - \([ABC]\) - \([ABC]\)$")
        for choice in result.choices:
            assert pattern.match(choice), f"choice 형식 오류: '{choice}'"

    @pytest.mark.asyncio
    async def test_sub_passages_stored_in_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """sub_passages 가 Question.sub_passages 에 저장된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.ORDER_36)
        llm_out = _make_v7_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v7_variant(
            passage_text=_URBAN_CYCLING_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.sub_passages == _SUB_PASSAGES

    @pytest.mark.asyncio
    async def test_variant_metadata_stored_correctly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """variant_metadata 가 Question.variant_metadata 에 dict 로 저장된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.ORDER_36)
        llm_out = _make_v7_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v7_variant(
            passage_text=_URBAN_CYCLING_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.variant_metadata is not None
        assert result.variant_metadata["intro_paragraph"] == _INTRO
        assert len(result.variant_metadata["split_categories"]) >= 1
        assert len(result.variant_metadata["choice_pattern"]) == 5
        assert "correct" in result.variant_metadata["choice_pattern"]

    @pytest.mark.asyncio
    async def test_answer_varied_position(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """answer 가 3일 때 정상적으로 처리된다 (정답 분포 편향 회피 검증)."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.ORDER_36)
        # 정답을 3번 위치에 배치
        choices = [
            "(B) - (A) - (C)",
            "(C) - (A) - (B)",
            "(A) - (B) - (C)",  # 정답 (3번)
            "(A) - (C) - (B)",
            "(B) - (C) - (A)",
        ]
        llm_out = _make_v7_llm_output(choices=choices, answer=3)
        mock_client = _make_mock_client(llm_out)

        result = await generate_v7_variant(
            passage_text=_URBAN_CYCLING_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.answer == 3
        assert result.choices[2] == "(A) - (B) - (C)"

    @pytest.mark.asyncio
    async def test_llm_client_called_with_correct_purpose(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLM 호출 시 purpose='variant_v7_order_shuffle' 로 로깅."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.ORDER_36)
        llm_out = _make_v7_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v7_variant(
            passage_text=_URBAN_CYCLING_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        assert call_kwargs["purpose"] == "variant_v7_order_shuffle"

    @pytest.mark.asyncio
    async def test_passage_text_passed_to_prompt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """passage_text 가 프롬프트 변수에 포함되어 LLM 에 전달된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.ORDER_36)
        llm_out = _make_v7_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v7_variant(
            passage_text=_URBAN_CYCLING_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        prompt = call_kwargs["prompt"]
        rendered = prompt.render()
        assert "urban cycling" in rendered


# ─── generate_v7_variant 에러 케이스 ─────────────────────────────────────────


class TestGenerateV7VariantErrors:
    @pytest.mark.asyncio
    async def test_non_applicable_type_raises_value_error(self) -> None:
        """V7 비적용 type (grammar_29) → ValueError."""
        original = _make_question(QuestionType.GRAMMAR_29)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V7 변형은"):
            await generate_v7_variant(
                passage_text=_URBAN_CYCLING_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

        # LLM 호출 없음
        mock_client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_gist_22_not_applicable_raises_value_error(self) -> None:
        """gist_22 도 V7 비적용 type."""
        original = _make_question(QuestionType.GIST_22)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V7 변형은"):
            await generate_v7_variant(
                passage_text=_URBAN_CYCLING_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

    @pytest.mark.asyncio
    async def test_llm_timeout_propagated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLMTimeoutError 그대로 전파."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.ORDER_36)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMTimeoutError("timeout")
        )

        with pytest.raises(LLMTimeoutError):
            await generate_v7_variant(
                passage_text=_URBAN_CYCLING_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

    @pytest.mark.asyncio
    async def test_llm_schema_error_propagated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLMSchemaValidationError 그대로 전파."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.ORDER_36)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMSchemaValidationError(
                "schema fail",
                validation_error="test",
                raw_response={},
            )
        )

        with pytest.raises(LLMSchemaValidationError):
            await generate_v7_variant(
                passage_text=_URBAN_CYCLING_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )


# ─── V7_APPLICABLE_TYPES 커버리지 ────────────────────────────────────────────


class TestV7ApplicableTypes:
    def test_applicable_types_include_required(self) -> None:
        """V7_APPLICABLE_TYPES 는 카탈로그 v0.4 §V7 의 2개 type 을 포함한다."""
        assert QuestionType.ORDER_36 in V7_APPLICABLE_TYPES
        assert QuestionType.ORDER_37 in V7_APPLICABLE_TYPES

    def test_applicable_types_excludes_grammar(self) -> None:
        """grammar_29 는 V7 비적용."""
        assert QuestionType.GRAMMAR_29 not in V7_APPLICABLE_TYPES

    def test_applicable_types_excludes_gist(self) -> None:
        """gist_22 는 V7 비적용 (V6 대상)."""
        assert QuestionType.GIST_22 not in V7_APPLICABLE_TYPES

    def test_applicable_types_excludes_blank(self) -> None:
        """blank_phrase_31 은 V7 비적용 (V5 대상)."""
        assert QuestionType.BLANK_PHRASE_31 not in V7_APPLICABLE_TYPES

    def test_applicable_types_count(self) -> None:
        """V7 적용 type 은 정확히 2개."""
        assert len(V7_APPLICABLE_TYPES) == 2


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────


def _setup_prompt_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: any) -> None:
    """테스트용 임시 프롬프트 디렉토리 설정.

    실제 docs/prompts/ 파일을 읽지 않도록 tmp_path 에 최소 프롬프트 파일을 생성.
    """
    prompt_file = tmp_path / "variant-order-shuffle-v0.md"
    prompt_file.write_text(
        "---\nversion: 0\n---\n"
        "Passage: {{passage_text}}\nType: {{question_type}}",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
