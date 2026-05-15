"""generate_v3_variant 단위 테스트 — mock LLM client.

커버 케이스:
  - 정상 생성: grammar_29 type → V3 변형 Question 반환.
  - 반환된 Question 의 필드 검증
    (variant_kind / type / choices / answer / variant_metadata).
  - sentinel UUID 채움 검증 (라우트가 model_copy 로 교체하는 자리).
  - variant_metadata 에 swapped_position_index / original_phrase /
    swapped_phrase / error_type 저장 확인.
  - V3 비적용 type (vocabulary_30) → ValueError.
  - V3 비적용 type (gist_22) → ValueError.
  - candidates 5개 미만 → Pydantic ValidationError.
  - candidates 5개 초과 → Pydantic ValidationError.
  - is_error 2개 → Pydantic ValidationError.
  - is_error 0개 → Pydantic ValidationError.
  - swapped_position_index ≠ answer → Pydantic ValidationError.
  - choices 5개 미만 → Pydantic ValidationError.
  - answer 범위 벗어남 → Pydantic ValidationError.
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
from llm.variants.v3_grammar_swap import (
    V3_APPLICABLE_TYPES,
    V3CandidateOutput,
    V3Output,
    generate_v3_variant,
)
from pydantic import ValidationError

from shared.schemas.question import Question, QuestionType, VariantKind

# ─── fixtures ────────────────────────────────────────────────────────────────

_TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_WORKSPACE_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_PASSAGE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_QUESTION_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

_GRAMMAR_PASSAGE = (
    "The number of students who choose online learning has grown significantly over the past "
    "decade. Many educators believe this trend, driven by flexible schedules and lower costs, "
    "are likely to continue. Institutions that fail to adapt their curricula risk losing "
    "relevance in an increasingly competitive market. Students are often surprised to find "
    "that flexible programs suit their needs better than traditional ones."
)

_MODIFIED_PASSAGE = (
    "The number of students who choose online learning has grown significantly over the past "
    "decade. Many educators believe this trend, driven by flexible schedules and lower costs, "
    "are likely to continue. Institutions that fail to adapt their curricula risk losing "
    "relevance in an increasingly competitive market. Students are often surprised to find "
    "that flexible programs suit their needs better than traditional ones."
)

_FIVE_CANDIDATES = [
    V3CandidateOutput(
        position_index=1,
        original_phrase="has grown",
        display_phrase="has grown",
        grammar_category="verb_form (tense/aspect)",
        is_error=False,
    ),
    V3CandidateOutput(
        position_index=2,
        original_phrase="is",
        display_phrase="are",
        grammar_category="subject-verb agreement",
        is_error=True,
    ),
    V3CandidateOutput(
        position_index=3,
        original_phrase="to adapt",
        display_phrase="to adapt",
        grammar_category="to-infinitive vs gerund",
        is_error=False,
    ),
    V3CandidateOutput(
        position_index=4,
        original_phrase="surprised",
        display_phrase="surprised",
        grammar_category="participle (active vs passive)",
        is_error=False,
    ),
    V3CandidateOutput(
        position_index=5,
        original_phrase="suit",
        display_phrase="suit",
        grammar_category="subject-verb agreement (relative clause)",
        is_error=False,
    ),
]

_FIVE_CHOICES = [
    "① has grown",
    "② are",
    "③ to adapt",
    "④ surprised",
    "⑤ suit",
]


def _make_question(
    question_type: QuestionType = QuestionType.GRAMMAR_29,
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
        question_text="다음 글의 밑줄 친 부분 중, 어법상 틀린 것은?",
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_v3_llm_output(
    candidates: list[V3CandidateOutput] | None = None,
    choices: list[str] | None = None,
    swapped_position_index: int = 2,
    answer: int = 2,
) -> V3Output:
    if candidates is None:
        candidates = _FIVE_CANDIDATES
    if choices is None:
        choices = _FIVE_CHOICES
    return V3Output(
        modified_passage_text=_MODIFIED_PASSAGE,
        candidates=candidates,
        swapped_position_index=swapped_position_index,
        original_phrase="is",
        swapped_phrase="are",
        error_type="agreement_error",
        choices=choices,
        answer=answer,
        explanation=(
            "② 'are'는 주어-동사 일치 오류다. 주어는 'this trend'(단수)이므로 "
            "단수 동사 'is'가 옳다. 'are'는 복수 주어에 쓰이는 형태로, "
            "주어-동사 일치 규칙을 위반한다."
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


# ─── V3Output / V3CandidateOutput Pydantic 검증 ─────────────────────────────


class TestV3OutputValidation:
    def test_valid_v3_output(self) -> None:
        """정상 V3Output — Pydantic 검증 통과."""
        out = _make_v3_llm_output()
        assert len(out.candidates) == 5
        assert len(out.choices) == 5
        assert out.answer == 2
        assert out.swapped_position_index == 2

    def test_candidates_four_raises(self) -> None:
        """candidates 4개 (범위 미달) → ValidationError."""
        with pytest.raises(ValidationError, match="5개"):
            V3Output(
                modified_passage_text=_MODIFIED_PASSAGE,
                candidates=_FIVE_CANDIDATES[:4],
                swapped_position_index=2,
                original_phrase="is",
                swapped_phrase="are",
                error_type="agreement_error",
                choices=_FIVE_CHOICES,
                answer=2,
                explanation="test",
            )

    def test_candidates_six_raises(self) -> None:
        """candidates 6개 (범위 초과) → ValidationError."""
        extra = V3CandidateOutput(
            position_index=5,
            original_phrase="programs",
            display_phrase="programs",
            grammar_category="subject-verb agreement",
            is_error=False,
        )
        with pytest.raises(ValidationError, match="5개"):
            V3Output(
                modified_passage_text=_MODIFIED_PASSAGE,
                candidates=[*_FIVE_CANDIDATES, extra],
                swapped_position_index=2,
                original_phrase="is",
                swapped_phrase="are",
                error_type="agreement_error",
                choices=_FIVE_CHOICES,
                answer=2,
                explanation="test",
            )

    def test_two_is_error_raises(self) -> None:
        """is_error 가 2개이면 ValidationError."""
        two_errors = [
            V3CandidateOutput(
                position_index=1,
                original_phrase="has grown",
                display_phrase="have grown",
                grammar_category="verb_form",
                is_error=True,
            ),
            V3CandidateOutput(
                position_index=2,
                original_phrase="is",
                display_phrase="are",
                grammar_category="agreement",
                is_error=True,
            ),
            V3CandidateOutput(
                position_index=3,
                original_phrase="to adapt",
                display_phrase="to adapt",
                grammar_category="infinitive",
                is_error=False,
            ),
            V3CandidateOutput(
                position_index=4,
                original_phrase="surprised",
                display_phrase="surprised",
                grammar_category="participle",
                is_error=False,
            ),
            V3CandidateOutput(
                position_index=5,
                original_phrase="suit",
                display_phrase="suit",
                grammar_category="subject-verb",
                is_error=False,
            ),
        ]
        with pytest.raises(ValidationError, match="정확히 1개"):
            V3Output(
                modified_passage_text=_MODIFIED_PASSAGE,
                candidates=two_errors,
                swapped_position_index=1,
                original_phrase="has grown",
                swapped_phrase="have grown",
                error_type="agreement_error",
                choices=_FIVE_CHOICES,
                answer=1,
                explanation="test",
            )

    def test_zero_is_error_raises(self) -> None:
        """is_error 가 0개이면 ValidationError."""
        no_errors = [
            V3CandidateOutput(
                position_index=i + 1,
                original_phrase=f"phrase_{i}",
                display_phrase=f"phrase_{i}",
                grammar_category=f"cat_{i}",
                is_error=False,
            )
            for i in range(5)
        ]
        with pytest.raises(ValidationError, match="정확히 1개"):
            V3Output(
                modified_passage_text=_MODIFIED_PASSAGE,
                candidates=no_errors,
                swapped_position_index=1,
                original_phrase="phrase_0",
                swapped_phrase="wrong_phrase",
                error_type="agreement_error",
                choices=_FIVE_CHOICES,
                answer=1,
                explanation="test",
            )

    def test_swapped_index_not_equal_answer_raises(self) -> None:
        """swapped_position_index ≠ answer → ValidationError."""
        with pytest.raises(ValidationError, match="동일해야"):
            V3Output(
                modified_passage_text=_MODIFIED_PASSAGE,
                candidates=_FIVE_CANDIDATES,
                swapped_position_index=2,
                original_phrase="is",
                swapped_phrase="are",
                error_type="agreement_error",
                choices=_FIVE_CHOICES,
                answer=3,  # swapped_position_index=2 와 불일치
                explanation="test",
            )

    def test_choices_not_five_raises(self) -> None:
        """choices 가 5개 미만이면 ValidationError."""
        with pytest.raises(ValidationError, match="choices 는 정확히 5개"):
            V3Output(
                modified_passage_text=_MODIFIED_PASSAGE,
                candidates=_FIVE_CANDIDATES,
                swapped_position_index=2,
                original_phrase="is",
                swapped_phrase="are",
                error_type="agreement_error",
                choices=["① a", "② b", "③ c"],
                answer=2,
                explanation="test",
            )

    def test_answer_out_of_range_raises(self) -> None:
        """answer 가 1~5 범위를 벗어나면 ValidationError."""
        with pytest.raises(ValidationError):
            V3Output(
                modified_passage_text=_MODIFIED_PASSAGE,
                candidates=_FIVE_CANDIDATES,
                swapped_position_index=6,
                original_phrase="is",
                swapped_phrase="are",
                error_type="agreement_error",
                choices=_FIVE_CHOICES,
                answer=6,
                explanation="test",
            )


# ─── generate_v3_variant 정상 케이스 ─────────────────────────────────────────


class TestGenerateV3Variant:
    @pytest.mark.asyncio
    async def test_grammar_29_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """grammar_29 원본 → V3 변형 Question 반환.

        반환된 Question 의 필드 검증:
          - variant_kind == GRAMMAR_SWAP
          - derived_from_question_id 는 sentinel UUID (라우트가 교체 예정)
          - choices 5개
          - type == GRAMMAR_29
          - answer == 2
        """
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.GRAMMAR_29)
        llm_out = _make_v3_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v3_variant(
            passage_text=_GRAMMAR_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert isinstance(result, Question)
        assert result.variant_kind == VariantKind.GRAMMAR_SWAP
        assert result.type == QuestionType.GRAMMAR_29
        assert len(result.choices) == 5
        assert result.answer == 2
        # sentinel UUID 채워짐 (라우트가 model_copy 로 교체)
        assert result.derived_from_question_id == uuid.UUID(int=0)
        assert result.tenant_id == uuid.UUID(int=0)
        assert result.workspace_id == uuid.UUID(int=0)

    @pytest.mark.asyncio
    async def test_variant_metadata_stored_correctly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """variant_metadata 에 swap 상세 정보가 저장된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.GRAMMAR_29)
        llm_out = _make_v3_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v3_variant(
            passage_text=_GRAMMAR_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.variant_metadata is not None
        assert result.variant_metadata["swapped_position_index"] == 2
        assert result.variant_metadata["original_phrase"] == "is"
        assert result.variant_metadata["swapped_phrase"] == "are"
        assert result.variant_metadata["error_type"] == "agreement_error"
        assert "modified_passage_text" in result.variant_metadata

    @pytest.mark.asyncio
    async def test_llm_client_called_with_correct_purpose(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLM 호출 시 purpose='variant_v3_grammar_swap' 로 로깅."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.GRAMMAR_29)
        llm_out = _make_v3_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v3_variant(
            passage_text=_GRAMMAR_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        assert call_kwargs["purpose"] == "variant_v3_grammar_swap"


# ─── generate_v3_variant 에러 케이스 ─────────────────────────────────────────


class TestGenerateV3VariantErrors:
    @pytest.mark.asyncio
    async def test_non_applicable_type_vocabulary_30_raises_value_error(self) -> None:
        """V3 비적용 type (vocabulary_30) → ValueError."""
        original = _make_question(QuestionType.VOCABULARY_30)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V3 변형은"):
            await generate_v3_variant(
                passage_text=_GRAMMAR_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

        # LLM 호출 없음
        mock_client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_applicable_type_gist_22_raises(self) -> None:
        """V3 비적용 type (gist_22) → ValueError."""
        original = _make_question(QuestionType.GIST_22)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V3 변형은"):
            await generate_v3_variant(
                passage_text=_GRAMMAR_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

    @pytest.mark.asyncio
    async def test_llm_timeout_propagated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLMTimeoutError 그대로 전파."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.GRAMMAR_29)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(side_effect=LLMTimeoutError("timeout"))

        with pytest.raises(LLMTimeoutError):
            await generate_v3_variant(
                passage_text=_GRAMMAR_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

    @pytest.mark.asyncio
    async def test_llm_schema_error_propagated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLMSchemaValidationError 그대로 전파."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.GRAMMAR_29)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMSchemaValidationError(
                "schema fail",
                validation_error="test",
                raw_response={},
            )
        )

        with pytest.raises(LLMSchemaValidationError):
            await generate_v3_variant(
                passage_text=_GRAMMAR_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )


# ─── V3_APPLICABLE_TYPES 커버리지 ────────────────────────────────────────────


class TestV3ApplicableTypes:
    def test_applicable_types_include_grammar_29(self) -> None:
        """V3_APPLICABLE_TYPES 는 카탈로그 v0.4 §V3 의 grammar_29 를 포함한다."""
        assert QuestionType.GRAMMAR_29 in V3_APPLICABLE_TYPES

    def test_applicable_types_excludes_vocabulary_30(self) -> None:
        """vocabulary_30 은 V3 비적용 (V1 대상)."""
        assert QuestionType.VOCABULARY_30 not in V3_APPLICABLE_TYPES

    def test_applicable_types_excludes_blank_phrase_31(self) -> None:
        """blank_phrase_31 은 V3 비적용 (V2/V5 대상)."""
        assert QuestionType.BLANK_PHRASE_31 not in V3_APPLICABLE_TYPES

    def test_applicable_types_has_exactly_one_type(self) -> None:
        """V3 는 grammar_29 만 — 카탈로그 v0.4 §V3 단일 type."""
        assert len(V3_APPLICABLE_TYPES) == 1


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────


def _setup_prompt_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: any) -> None:
    """테스트용 임시 프롬프트 디렉토리 설정.

    실제 docs/prompts/ 파일을 읽지 않도록 tmp_path 에 최소 프롬프트 파일을 생성.
    """
    prompt_file = tmp_path / "variant-grammar-swap-v0.md"
    prompt_file.write_text(
        "---\nversion: 0\n---\nPassage: {{passage_text}}",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
