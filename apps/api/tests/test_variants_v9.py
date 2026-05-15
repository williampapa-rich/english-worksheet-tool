"""generate_v9_variant 단위 테스트 — mock LLM client.

커버 케이스:
  - 정상 생성: irrelevant_sentence_35 type.
  - 반환된 Question 의 필드 검증 (variant_kind / choices / answer / variant_metadata 등).
  - sentinel UUID 채움 검증 (라우트가 model_copy 로 교체하는 자리).
  - V9 비적용 type (grammar_29) → ValueError.
  - choices 가 고정 마커 외 값 → Pydantic ValidationError.
  - answer 와 injected_position_index 불일치 → Pydantic ValidationError.
  - body_with_markers 에 마커 미포함 / 중복 → Pydantic ValidationError.
  - injected_sentence_text 가 body_with_markers 에 없음 → Pydantic ValidationError.
  - lexical_similarity_words 비어 있음 → Pydantic ValidationError.
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
from llm.variants.v9_irrelevant_sentence_inject import (
    V9_APPLICABLE_TYPES,
    V9Output,
    V9VariantMetadata,
    generate_v9_variant,
)
from pydantic import ValidationError

from shared.schemas.question import Question, QuestionType, VariantKind

# ─── fixtures ────────────────────────────────────────────────────────────────

_TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_WORKSPACE_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_PASSAGE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_QUESTION_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

# Zero-waste fixture — 무관문장 테스트 지문 (마음챙김 주제)
_ZERO_WASTE_PASSAGE = (
    "Mindfulness practices have been shown to reduce stress levels significantly. "
    "When people focus on the present moment, they interrupt the cycle of anxious thinking "
    "that amplifies stress. "
    "Regular practice rewires neural pathways associated with emotional regulation. "
    "Communities that invest in mindfulness programs report lower burnout rates among employees. "
    "Over time, these benefits extend to physical health outcomes as well."
)

# 주입된 무관 문장 — lexical similarity 보존 (meditation/practice/mindfulness) + 흐름 단절
_INJECTED_SENTENCE = (
    "Ancient meditation traditions in Eastern cultures date back thousands of years "
    "and vary widely in technique and purpose."
)

# ①~⑤ 마커가 부착된 5문장 시퀀스 (③ 위치에 무관 문장 주입)
_BODY_WITH_MARKERS = (
    "① Mindfulness practices have been shown to reduce stress levels significantly. "
    "② When people focus on the present moment, they interrupt the cycle of anxious thinking "
    "that amplifies stress. "
    "③ Ancient meditation traditions in Eastern cultures date back thousands of years "
    "and vary widely in technique and purpose. "
    "④ Communities that invest in mindfulness programs report lower burnout rates among employees. "
    "⑤ Over time, these benefits extend to physical health outcomes as well."
)

_FIXED_CHOICES = ["①", "②", "③", "④", "⑤"]

_EXPLANATION_KO = (
    "이 글은 마음챙김 수련이 스트레스를 줄이고 정서 조절 능력을 향상시킨다는 주제를 다루고 있다. "
    "③번 문장은 '명상'과 관련된 어휘를 사용하지만, 동양 명상의 역사적 기원에 관한 내용으로 "
    "본문의 현대적 스트레스 완화 효과라는 논리 흐름과 무관하다. "
    "앞뒤 문장이 신경 경로 재형성과 직원 소진율 감소로 이어지는 반면, ③번은 역사적 배경으로 흐름을 단절시킨다."
)


def _make_question(
    question_type: QuestionType = QuestionType.IRRELEVANT_SENTENCE_35,
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
        question_text="다음 글에서 전체 흐름과 관계 없는 문장은?",
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_v9_metadata(
    answer: int = 3,
    injected_sentence: str = _INJECTED_SENTENCE,
    body_with_markers: str = _BODY_WITH_MARKERS,
) -> V9VariantMetadata:
    return V9VariantMetadata(
        injected_sentence_text=injected_sentence,
        injected_position_index=answer,
        lexical_similarity_words=["meditation", "practice", "mindfulness"],
        body_with_markers=body_with_markers,
    )


def _make_v9_llm_output(
    answer: int = 3,
    injected_sentence: str = _INJECTED_SENTENCE,
    body_with_markers: str = _BODY_WITH_MARKERS,
    choices: list[str] | None = None,
) -> V9Output:
    if choices is None:
        choices = _FIXED_CHOICES
    return V9Output(
        choices=choices,
        answer=answer,
        explanation=_EXPLANATION_KO,
        variant_metadata=_make_v9_metadata(
            answer=answer,
            injected_sentence=injected_sentence,
            body_with_markers=body_with_markers,
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


# ─── V9Output / V9VariantMetadata Pydantic 검증 ──────────────────────────────


class TestV9OutputValidation:
    def test_valid_irrelevant_35_output(self) -> None:
        """정상 irrelevant_sentence_35 출력 — Pydantic 검증 통과."""
        out = _make_v9_llm_output()
        assert out.choices == _FIXED_CHOICES
        assert out.answer == 3
        assert out.variant_metadata.injected_position_index == 3
        assert out.variant_metadata.injected_sentence_text == _INJECTED_SENTENCE
        assert len(out.variant_metadata.lexical_similarity_words) >= 1
        assert "①" in out.variant_metadata.body_with_markers
        assert _INJECTED_SENTENCE in out.variant_metadata.body_with_markers

    def test_choices_not_fixed_markers_raises(self) -> None:
        """choices 가 고정 마커가 아니면 ValidationError."""
        with pytest.raises(ValidationError, match="항상"):
            V9Output(
                choices=["1", "2", "3", "4", "5"],  # 잘못된 형식
                answer=3,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v9_metadata(answer=3),
            )

    def test_answer_out_of_range_raises(self) -> None:
        """answer 가 1~5 범위를 벗어나면 ValidationError."""
        with pytest.raises(ValidationError):
            V9Output(
                choices=_FIXED_CHOICES,
                answer=6,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v9_metadata(answer=1),
            )

    def test_answer_position_index_mismatch_raises(self) -> None:
        """answer=3 인데 injected_position_index=2 이면 ValidationError."""
        with pytest.raises(ValidationError, match="불일치"):
            V9Output(
                choices=_FIXED_CHOICES,
                answer=3,
                explanation=_EXPLANATION_KO,
                variant_metadata=V9VariantMetadata(
                    injected_sentence_text=_INJECTED_SENTENCE,
                    injected_position_index=2,  # answer=3 와 불일치
                    lexical_similarity_words=["meditation"],
                    body_with_markers=_BODY_WITH_MARKERS,
                ),
            )

    def test_body_missing_marker_raises(self) -> None:
        """body_with_markers 에 마커 ⑤ 가 없으면 ValidationError."""
        body_missing_marker = (
            "① Mindfulness practices reduce stress. "
            "② Focusing on the present moment interrupts anxious thinking. "
            "③ Ancient meditation traditions vary widely in technique. "
            "④ Communities report lower burnout rates."
            # ⑤ 빠짐
        )
        with pytest.raises(ValidationError, match="마커"):
            V9Output(
                choices=_FIXED_CHOICES,
                answer=3,
                explanation=_EXPLANATION_KO,
                variant_metadata=V9VariantMetadata(
                    injected_sentence_text=_INJECTED_SENTENCE,
                    injected_position_index=3,
                    lexical_similarity_words=["meditation"],
                    body_with_markers=body_missing_marker,
                ),
            )

    def test_body_duplicate_marker_raises(self) -> None:
        """body_with_markers 에 마커 ① 이 2개이면 ValidationError."""
        body_duplicate_marker = (
            "① Mindfulness practices reduce stress. "
            "① When people focus, they interrupt anxious thinking. "
            "③ Ancient meditation traditions vary widely. "
            "④ Communities report lower burnout rates. "
            "⑤ Benefits extend to physical health."
        )
        with pytest.raises(ValidationError, match="마커"):
            V9Output(
                choices=_FIXED_CHOICES,
                answer=3,
                explanation=_EXPLANATION_KO,
                variant_metadata=V9VariantMetadata(
                    injected_sentence_text=_INJECTED_SENTENCE,
                    injected_position_index=3,
                    lexical_similarity_words=["meditation"],
                    body_with_markers=body_duplicate_marker,
                ),
            )

    def test_injected_sentence_absent_from_body_raises(self) -> None:
        """injected_sentence_text 가 body_with_markers 에 없으면 ValidationError."""
        body_without_injected = (
            "① Mindfulness practices reduce stress. "
            "② Focusing on the present moment interrupts anxious thinking. "
            "③ Some other completely different sentence here. "
            "④ Communities report lower burnout rates. "
            "⑤ Benefits extend to physical health."
        )
        with pytest.raises(ValidationError, match="포함되어 있지 않다"):
            V9Output(
                choices=_FIXED_CHOICES,
                answer=3,
                explanation=_EXPLANATION_KO,
                variant_metadata=V9VariantMetadata(
                    injected_sentence_text=_INJECTED_SENTENCE,
                    injected_position_index=3,
                    lexical_similarity_words=["meditation"],
                    body_with_markers=body_without_injected,
                ),
            )

    def test_lexical_similarity_words_empty_raises(self) -> None:
        """lexical_similarity_words 가 비어 있으면 ValidationError."""
        with pytest.raises(ValidationError):
            V9VariantMetadata(
                injected_sentence_text=_INJECTED_SENTENCE,
                injected_position_index=3,
                lexical_similarity_words=[],  # 빈 리스트 — min_length=1 위반
                body_with_markers=_BODY_WITH_MARKERS,
            )


# ─── generate_v9_variant 정상 케이스 ─────────────────────────────────────────


class TestGenerateV9Variant:
    @pytest.mark.asyncio
    async def test_irrelevant_35_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """irrelevant_sentence_35 원본 → V9 변형 Question 반환.

        반환된 Question 의 필드 검증:
          - variant_kind == IRRELEVANT_SENTENCE_INJECT
          - derived_from_question_id 는 sentinel UUID (라우트가 교체 예정)
          - choices == ["①", "②", "③", "④", "⑤"]
          - type == IRRELEVANT_SENTENCE_35
          - variant_metadata 에 injected_sentence_text 포함
        """
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.IRRELEVANT_SENTENCE_35)
        llm_out = _make_v9_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v9_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert isinstance(result, Question)
        assert result.variant_kind == VariantKind.IRRELEVANT_SENTENCE_INJECT
        assert result.type == QuestionType.IRRELEVANT_SENTENCE_35
        assert result.choices == _FIXED_CHOICES
        assert result.answer == 3
        # sentinel UUID 채워짐 (라우트가 model_copy 로 교체)
        assert result.derived_from_question_id == uuid.UUID(int=0)
        assert result.tenant_id == uuid.UUID(int=0)
        assert result.workspace_id == uuid.UUID(int=0)

    @pytest.mark.asyncio
    async def test_variant_metadata_stored_correctly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """variant_metadata 가 Question.variant_metadata 에 dict 로 저장된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.IRRELEVANT_SENTENCE_35)
        llm_out = _make_v9_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v9_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.variant_metadata is not None
        assert result.variant_metadata["injected_sentence_text"] == _INJECTED_SENTENCE
        assert result.variant_metadata["injected_position_index"] == 3
        assert len(result.variant_metadata["lexical_similarity_words"]) >= 1
        assert "body_with_markers" in result.variant_metadata
        assert "①" in result.variant_metadata["body_with_markers"]

    @pytest.mark.asyncio
    async def test_answer_position_2_works(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """answer=2 인 시나리오 — 정답 분포 편향 회피 검증."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.IRRELEVANT_SENTENCE_35)

        # answer=2 시나리오용 body_with_markers
        body_answer_2 = (
            "① Mindfulness practices have been shown to reduce stress levels significantly. "
            "② Ancient meditation traditions in Eastern cultures date back thousands of years "
            "and vary widely in technique and purpose. "
            "③ When people focus on the present moment, they interrupt anxious thinking. "
            "④ Communities that invest in mindfulness programs report lower burnout rates. "
            "⑤ Over time, these benefits extend to physical health outcomes as well."
        )
        llm_out = _make_v9_llm_output(
            answer=2,
            body_with_markers=body_answer_2,
        )
        mock_client = _make_mock_client(llm_out)

        result = await generate_v9_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.answer == 2
        assert result.variant_metadata is not None
        assert result.variant_metadata["injected_position_index"] == 2

    @pytest.mark.asyncio
    async def test_llm_client_called_with_correct_purpose(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLM 호출 시 purpose='variant_v9_irrelevant_sentence_inject' 로 로깅."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.IRRELEVANT_SENTENCE_35)
        llm_out = _make_v9_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v9_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        assert call_kwargs["purpose"] == "variant_v9_irrelevant_sentence_inject"

    @pytest.mark.asyncio
    async def test_passage_text_passed_to_prompt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """passage_text 가 프롬프트 변수에 포함되어 LLM 에 전달된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.IRRELEVANT_SENTENCE_35)
        llm_out = _make_v9_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v9_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        prompt = call_kwargs["prompt"]
        rendered = prompt.render()
        assert "Mindfulness" in rendered

    @pytest.mark.asyncio
    async def test_question_text_preserved_from_original(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """원본 question_text 가 그대로 유지된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.IRRELEVANT_SENTENCE_35)
        llm_out = _make_v9_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v9_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.question_text == original.question_text

    @pytest.mark.asyncio
    async def test_question_text_default_when_original_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """원본 question_text 가 None 이면 기본 지시문이 사용된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.IRRELEVANT_SENTENCE_35)
        # question_text 를 None 으로 설정
        original = original.model_copy(update={"question_text": None})
        llm_out = _make_v9_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v9_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.question_text == "다음 글에서 전체 흐름과 관계 없는 문장은?"


# ─── generate_v9_variant 에러 케이스 ─────────────────────────────────────────


class TestGenerateV9VariantErrors:
    @pytest.mark.asyncio
    async def test_non_applicable_type_raises_value_error(self) -> None:
        """V9 비적용 type (grammar_29) → ValueError."""
        original = _make_question(QuestionType.GRAMMAR_29)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V9 변형은"):
            await generate_v9_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

        # LLM 호출 없음
        mock_client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_insertion_38_not_applicable_raises_value_error(self) -> None:
        """insertion_38 도 V9 비적용 type (V8 대상)."""
        original = _make_question(QuestionType.INSERTION_38)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V9 변형은"):
            await generate_v9_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

    @pytest.mark.asyncio
    async def test_llm_timeout_propagated(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLMTimeoutError 그대로 전파."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.IRRELEVANT_SENTENCE_35)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(side_effect=LLMTimeoutError("timeout"))

        with pytest.raises(LLMTimeoutError):
            await generate_v9_variant(
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
        original = _make_question(QuestionType.IRRELEVANT_SENTENCE_35)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMSchemaValidationError(
                "schema fail",
                validation_error="test",
                raw_response={},
            )
        )

        with pytest.raises(LLMSchemaValidationError):
            await generate_v9_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )


# ─── V9_APPLICABLE_TYPES 커버리지 ────────────────────────────────────────────


class TestV9ApplicableTypes:
    def test_applicable_types_include_required(self) -> None:
        """V9_APPLICABLE_TYPES 는 카탈로그 v0.4 §V9 의 1개 type 을 포함한다."""
        assert QuestionType.IRRELEVANT_SENTENCE_35 in V9_APPLICABLE_TYPES

    def test_applicable_types_excludes_grammar(self) -> None:
        """grammar_29 는 V9 비적용."""
        assert QuestionType.GRAMMAR_29 not in V9_APPLICABLE_TYPES

    def test_applicable_types_excludes_insertion(self) -> None:
        """insertion_38 / insertion_39 는 V9 비적용 (V8 대상)."""
        assert QuestionType.INSERTION_38 not in V9_APPLICABLE_TYPES
        assert QuestionType.INSERTION_39 not in V9_APPLICABLE_TYPES

    def test_applicable_types_excludes_order(self) -> None:
        """order_36 / order_37 은 V9 비적용 (V7 대상)."""
        assert QuestionType.ORDER_36 not in V9_APPLICABLE_TYPES
        assert QuestionType.ORDER_37 not in V9_APPLICABLE_TYPES

    def test_applicable_types_count(self) -> None:
        """V9 적용 type 은 정확히 1개."""
        assert len(V9_APPLICABLE_TYPES) == 1


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────


def _setup_prompt_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: any) -> None:
    """테스트용 임시 프롬프트 디렉토리 설정.

    실제 docs/prompts/ 파일을 읽지 않도록 tmp_path 에 최소 프롬프트 파일을 생성.
    """
    prompt_file = tmp_path / "variant-irrelevant-sentence-inject-v0.md"
    prompt_file.write_text(
        "---\nversion: 0\n---\nPassage: {{passage_text}}",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
