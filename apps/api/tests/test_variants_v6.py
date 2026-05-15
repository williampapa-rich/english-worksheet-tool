"""generate_v6_variant 단위 테스트 — mock LLM client.

커버 케이스:
  - 정상 생성: main_idea_22 / theme_23 / title_24 각 type.
  - 반환된 Question 의 필드 검증 (variant_kind / derived_from_question_id / choices 등).
  - sentinel UUID 채움 검증 (라우트가 model_copy 로 교체하는 자리).
  - V6 비적용 type (grammar_29) → ValueError.
  - choices 5개 미만 → LLMSchemaValidationError (Pydantic validator).
  - answer 범위 벗어남 → LLMSchemaValidationError.
  - choice_pattern 'correct' 위치 불일치 → LLMSchemaValidationError.
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
from llm.variants.v6_topic_main_idea_swap import (
    V6_APPLICABLE_TYPES,
    V6Output,
    V6VariantMetadata,
    generate_v6_variant,
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

_FIVE_CHOICES_MAIN_IDEA = [
    "쓰레기를 줄이는 인식이 생기면 습관 변화로 이어져 지역 사회 전체에 긍정적 효과를 가져온다.",
    "재활용 가방 사용만으로 환경 문제를 완전히 해결할 수 있다.",
    "환경 보호를 위해서는 개인보다 기업의 역할이 더 중요하다.",
    "쓰레기 감량보다 무분별한 소비 자체를 막는 것이 더 시급한 과제이다.",
    "일회용품 사용을 줄이면 지방 자치 단체의 예산 문제도 해결된다.",
]


def _make_question(
    question_type: QuestionType = QuestionType.GIST_22,
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
        question_text="다음 글의 요지로 가장 적절한 것은?",
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_v6_llm_output(
    choices: list[str] | None = None,
    answer: int = 1,
    sub_type: str = "main_idea_22",
    choice_pattern: list[str] | None = None,
) -> V6Output:
    if choices is None:
        choices = _FIVE_CHOICES_MAIN_IDEA
    if choice_pattern is None:
        # answer=1 → index 0 = "correct"
        choice_pattern = [
            "correct",
            "too-narrow",
            "too-broad",
            "opposite-conclusion",
            "plausible-unrelated",
        ]
    return V6Output(
        choices=choices,
        answer=answer,
        explanation="이 글은 인식 → 개인 행동 → 공동체 효과로 이어지는 논리를 주장한다.",
        variant_metadata=V6VariantMetadata(
            sub_type=sub_type,
            choice_pattern=choice_pattern,
        ),
    )


def _make_llm_result(data: Any) -> StructuredLLMResult[Any]:
    return StructuredLLMResult(
        data=data,
        raw_response={},
        usage=TokenUsage(input_tokens=300, output_tokens=150, cache_read_tokens=0),
        model="claude-sonnet-4-6",
        elapsed_ms=1200,
    )


def _make_mock_client(return_data: Any) -> AsyncMock:
    """mock StructuredLLMClient — extract_structured 가 return_data 를 반환."""
    mock = AsyncMock()
    mock.extract_structured = AsyncMock(return_value=_make_llm_result(return_data))
    return mock


# ─── V6Output / V6VariantMetadata Pydantic 검증 ──────────────────────────────


class TestV6OutputValidation:
    def test_valid_main_idea_output(self) -> None:
        """정상 main_idea_22 출력 — Pydantic 검증 통과."""
        out = _make_v6_llm_output()
        assert len(out.choices) == 5
        assert out.answer == 1
        assert out.variant_metadata.sub_type == "main_idea_22"

    def test_choices_not_five_raises(self) -> None:
        """choices 가 5개 미만이면 ValidationError."""
        with pytest.raises(ValidationError, match="choices 는 정확히 5개"):
            V6Output(
                choices=["a", "b", "c"],
                answer=1,
                explanation="test",
                variant_metadata=V6VariantMetadata(
                    sub_type="main_idea_22",
                    choice_pattern=[
                        "correct",
                        "too-narrow",
                        "too-broad",
                        "opposite-conclusion",
                        "plausible-unrelated",
                    ],
                ),
            )

    def test_answer_out_of_range_raises(self) -> None:
        """answer 가 1~5 범위를 벗어나면 ValidationError."""
        with pytest.raises(ValidationError):
            V6Output(
                choices=_FIVE_CHOICES_MAIN_IDEA,
                answer=6,
                explanation="test",
                variant_metadata=V6VariantMetadata(
                    sub_type="main_idea_22",
                    choice_pattern=[
                        "correct",
                        "too-narrow",
                        "too-broad",
                        "opposite-conclusion",
                        "plausible-unrelated",
                    ],
                ),
            )

    def test_choice_pattern_answer_mismatch_raises(self) -> None:
        """answer=2 인데 choice_pattern[0]='correct' 이면 ValidationError."""
        with pytest.raises(ValidationError, match="불일치"):
            V6Output(
                choices=_FIVE_CHOICES_MAIN_IDEA,
                answer=2,
                explanation="test",
                variant_metadata=V6VariantMetadata(
                    sub_type="main_idea_22",
                    # answer=2 → index=1 이 "correct" 여야 하는데 index=0 이 "correct"
                    choice_pattern=[
                        "correct",
                        "too-narrow",
                        "too-broad",
                        "opposite-conclusion",
                        "plausible-unrelated",
                    ],
                ),
            )

    def test_invalid_choice_pattern_value_raises(self) -> None:
        """허용되지 않은 choice_pattern 값이면 ValidationError."""
        with pytest.raises(ValidationError, match="허용되지 않은"):
            V6VariantMetadata(
                sub_type="main_idea_22",
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
            V6VariantMetadata(
                sub_type="main_idea_22",
                choice_pattern=[
                    "correct",
                    "correct",
                    "too-broad",
                    "opposite-conclusion",
                    "plausible-unrelated",
                ],
            )


# ─── generate_v6_variant 정상 케이스 ─────────────────────────────────────────


class TestGenerateV6Variant:
    @pytest.mark.asyncio
    async def test_main_idea_22_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """main_idea_22 원본 → V6 변형 Question 반환.

        반환된 Question 의 필드 검증:
          - variant_kind == TOPIC_MAIN_IDEA_SWAP
          - derived_from_question_id 는 sentinel UUID (라우트가 교체 예정)
          - choices 5개
          - type == GIST_22 (원본과 동일)
        """
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.GIST_22)
        llm_out = _make_v6_llm_output(sub_type="main_idea_22")
        mock_client = _make_mock_client(llm_out)

        result = await generate_v6_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert isinstance(result, Question)
        assert result.variant_kind == VariantKind.TOPIC_MAIN_IDEA_SWAP
        assert result.type == QuestionType.GIST_22
        assert len(result.choices) == 5
        assert result.answer == 1
        # sentinel UUID 채워짐 (라우트가 model_copy 로 교체)
        assert result.derived_from_question_id == uuid.UUID(int=0)
        assert result.tenant_id == uuid.UUID(int=0)
        assert result.workspace_id == uuid.UUID(int=0)

    @pytest.mark.asyncio
    async def test_theme_23_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """theme_23 원본 → V6 변형 Question 반환."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.THEME_23)
        llm_out = _make_v6_llm_output(
            choices=[
                "the role of individual awareness in reducing community waste",
                "the importance of recycling programs in schools",
                "global efforts to eliminate single-use plastics",
                "government policies reducing municipal waste costs",
                "corporate responsibility for environmental sustainability",
            ],
            sub_type="theme_23",
        )
        mock_client = _make_mock_client(llm_out)

        result = await generate_v6_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.type == QuestionType.THEME_23
        assert result.variant_kind == VariantKind.TOPIC_MAIN_IDEA_SWAP

    @pytest.mark.asyncio
    async def test_title_24_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """title_24 원본 → V6 변형 Question 반환."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.TITLE_24)
        llm_out = _make_v6_llm_output(
            choices=[
                "Small Acts, Big Environmental Impact",
                "Recycling: The Only Solution",
                "Why Governments Must Lead Green Initiatives",
                "Composting: A Minor Step in Waste Reduction",
                "How Plastic Bans Transform Society",
            ],
            sub_type="title_24",
        )
        mock_client = _make_mock_client(llm_out)

        result = await generate_v6_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.type == QuestionType.TITLE_24
        assert result.variant_kind == VariantKind.TOPIC_MAIN_IDEA_SWAP

    @pytest.mark.asyncio
    async def test_variant_metadata_stored_correctly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """variant_metadata 가 Question.variant_metadata 에 dict 로 저장된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.GIST_22)
        llm_out = _make_v6_llm_output(sub_type="main_idea_22")
        mock_client = _make_mock_client(llm_out)

        result = await generate_v6_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.variant_metadata is not None
        assert result.variant_metadata["sub_type"] == "main_idea_22"
        assert len(result.variant_metadata["choice_pattern"]) == 5
        assert "correct" in result.variant_metadata["choice_pattern"]

    @pytest.mark.asyncio
    async def test_original_choices_passed_to_prompt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """원본 선택지가 프롬프트 변수에 포함되어 LLM 에 전달된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(
            QuestionType.GIST_22,
            choices=["개인의 노력이 중요하다.", "기업의 역할이 더 크다."],
        )
        llm_out = _make_v6_llm_output(sub_type="main_idea_22")
        mock_client = _make_mock_client(llm_out)

        await generate_v6_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        prompt = call_kwargs["prompt"]
        rendered = prompt.render()
        assert "개인의 노력이 중요하다." in rendered

    @pytest.mark.asyncio
    async def test_llm_client_called_with_correct_purpose(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLM 호출 시 purpose='variant_v6_topic_main_idea_swap' 로 로깅."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.GIST_22)
        llm_out = _make_v6_llm_output(sub_type="main_idea_22")
        mock_client = _make_mock_client(llm_out)

        await generate_v6_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        assert call_kwargs["purpose"] == "variant_v6_topic_main_idea_swap"


# ─── generate_v6_variant 에러 케이스 ─────────────────────────────────────────


class TestGenerateV6VariantErrors:
    @pytest.mark.asyncio
    async def test_non_applicable_type_raises_value_error(self) -> None:
        """V6 비적용 type (grammar_29) → ValueError."""
        original = _make_question(QuestionType.GRAMMAR_29)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V6 변형은"):
            await generate_v6_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

        # LLM 호출 없음
        mock_client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_timeout_propagated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLMTimeoutError 그대로 전파."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.GIST_22)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMTimeoutError("timeout")
        )

        with pytest.raises(LLMTimeoutError):
            await generate_v6_variant(
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
        original = _make_question(QuestionType.GIST_22)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMSchemaValidationError(
                "schema fail",
                validation_error="test",
                raw_response={},
            )
        )

        with pytest.raises(LLMSchemaValidationError):
            await generate_v6_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )


# ─── V6_APPLICABLE_TYPES 커버리지 ────────────────────────────────────────────


class TestV6ApplicableTypes:
    def test_applicable_types_include_required(self) -> None:
        """V6_APPLICABLE_TYPES 는 카탈로그 v0.4 §V6 의 3개 type 을 포함한다."""
        assert QuestionType.GIST_22 in V6_APPLICABLE_TYPES
        assert QuestionType.THEME_23 in V6_APPLICABLE_TYPES
        assert QuestionType.TITLE_24 in V6_APPLICABLE_TYPES

    def test_applicable_types_excludes_grammar(self) -> None:
        """grammar_29 는 V6 비적용."""
        assert QuestionType.GRAMMAR_29 not in V6_APPLICABLE_TYPES

    def test_applicable_types_excludes_blank(self) -> None:
        """blank_phrase_31 은 V6 비적용 (V5 대상)."""
        assert QuestionType.BLANK_PHRASE_31 not in V6_APPLICABLE_TYPES


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────


def _setup_prompt_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: any) -> None:
    """테스트용 임시 프롬프트 디렉토리 설정.

    실제 docs/prompts/ 파일을 읽지 않도록 tmp_path 에 최소 프롬프트 파일을 생성.
    """
    prompt_file = tmp_path / "variant-topic-main-idea-swap-v0.md"
    prompt_file.write_text(
        "---\nversion: 0\n---\n"
        "Passage: {{passage_text}}\nType: {{question_type}}\n"
        "Original choices: {{original_choices}}",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
