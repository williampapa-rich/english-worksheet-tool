"""generate_v8_variant 단위 테스트 — mock LLM client.

커버 케이스:
  - 정상 생성: insertion_38 / insertion_39 각 type.
  - 반환된 Question 의 필드 검증 (variant_kind / given_sentence / choices / derived_from 등).
  - sentinel UUID 채움 검증 (라우트가 model_copy 로 교체하는 자리).
  - V8 비적용 type (grammar_29) → ValueError.
  - choices 가 고정 마커 외 값 → Pydantic ValidationError.
  - answer 와 original_position_index 불일치 → Pydantic ValidationError.
  - removed_sentence_text 와 given_sentence 불일치 → Pydantic ValidationError.
  - body_with_markers 에 마커 미포함 / 중복 → Pydantic ValidationError.
  - given_sentence 가 body_with_markers 에 잔류 → Pydantic ValidationError.
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
from llm.variants.v8_sentence_insertion_shift import (
    V8_APPLICABLE_TYPES,
    V8Output,
    V8VariantMetadata,
    generate_v8_variant,
)
from pydantic import ValidationError

from shared.schemas.question import Question, QuestionType, VariantKind

# ─── fixtures ────────────────────────────────────────────────────────────────

_TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_WORKSPACE_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_PASSAGE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_QUESTION_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

# Zero-waste fixture — 문장삽입 테스트 지문
_ZERO_WASTE_PASSAGE = (
    "Reducing waste starts with awareness. "
    "When people understand how much they throw away each day, "
    "they become more motivated to change their habits. "
    "Small actions add up to significant environmental benefits. "
    "Communities that adopt these practices report not only cleaner surroundings "
    "but also lower costs for municipal waste management. "
    "Individual effort, multiplied across an entire community, creates meaningful change."
)

# 추출 대상 문장 (본문 중간 — 3번째 문장)
_GIVEN_SENTENCE = "Small actions add up to significant environmental benefits."

# ①~⑤ 마커가 삽입된 수정 본문 (마커 5개 모두 포함, 추출 문장 제거)
_BODY_WITH_MARKERS = (
    "Reducing waste starts with awareness. "
    "① When people understand how much they throw away each day, "
    "they become more motivated to change their habits. "
    "② Communities that adopt these practices report not only cleaner surroundings "
    "but also lower costs for municipal waste management. "
    "③ Individual effort, multiplied across an entire community, creates meaningful change. "
    "④ ⑤"
)

_FIXED_CHOICES = ["①", "②", "③", "④", "⑤"]

_EXPLANATION_KO = (
    "주어진 문장은 '작은 행동들이 상당한 환경적 이익으로 이어진다'는 내용으로, "
    "앞 문장의 '습관 변화 동기'의 결과를 나타낸다. "
    "뒤 문장의 'these practices'는 주어진 문장에서 암시한 구체적 행동들을 가리켜 "
    "② 위치에서 자연스럽게 연결된다."
)


def _make_question(
    question_type: QuestionType = QuestionType.INSERTION_38,
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
        question_text="글의 흐름으로 보아, 주어진 문장이 들어가기에 가장 적절한 곳은?",
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_v8_metadata(
    answer: int = 2,
    sub_type: str = "insertion_38",
) -> V8VariantMetadata:
    return V8VariantMetadata(
        sub_type=sub_type,
        original_position_index=answer,
        removed_sentence_text=_GIVEN_SENTENCE,
        cohesion_cues=[
            "앞 문장의 '습관 변화(change their habits)' → 주어진 문장의 '작은 행동들(Small actions)' 논리 연결",
            "뒤 문장의 'these practices'가 주어진 문장의 행동을 지시",
        ],
    )


def _make_v8_llm_output(
    answer: int = 2,
    sub_type: str = "insertion_38",
    given_sentence: str = _GIVEN_SENTENCE,
    body_with_markers: str = _BODY_WITH_MARKERS,
    choices: list[str] | None = None,
) -> V8Output:
    if choices is None:
        choices = _FIXED_CHOICES
    return V8Output(
        given_sentence=given_sentence,
        body_with_markers=body_with_markers,
        choices=choices,
        answer=answer,
        explanation=_EXPLANATION_KO,
        variant_metadata=_make_v8_metadata(answer=answer, sub_type=sub_type),
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


# ─── V8Output / V8VariantMetadata Pydantic 검증 ──────────────────────────────


class TestV8OutputValidation:
    def test_valid_insertion_38_output(self) -> None:
        """정상 insertion_38 출력 — Pydantic 검증 통과."""
        out = _make_v8_llm_output()
        assert out.given_sentence == _GIVEN_SENTENCE
        assert out.choices == _FIXED_CHOICES
        assert out.answer == 2
        assert out.variant_metadata.original_position_index == 2
        assert out.variant_metadata.sub_type == "insertion_38"

    def test_choices_not_fixed_markers_raises(self) -> None:
        """choices 가 고정 마커가 아니면 ValidationError."""
        with pytest.raises(ValidationError, match="항상"):
            V8Output(
                given_sentence=_GIVEN_SENTENCE,
                body_with_markers=_BODY_WITH_MARKERS,
                choices=["1", "2", "3", "4", "5"],  # 잘못된 형식
                answer=2,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v8_metadata(answer=2),
            )

    def test_answer_out_of_range_raises(self) -> None:
        """answer 가 1~5 범위를 벗어나면 ValidationError."""
        with pytest.raises(ValidationError):
            V8Output(
                given_sentence=_GIVEN_SENTENCE,
                body_with_markers=_BODY_WITH_MARKERS,
                choices=_FIXED_CHOICES,
                answer=6,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v8_metadata(answer=1),
            )

    def test_answer_position_index_mismatch_raises(self) -> None:
        """answer=2 인데 original_position_index=3 이면 ValidationError."""
        with pytest.raises(ValidationError, match="불일치"):
            V8Output(
                given_sentence=_GIVEN_SENTENCE,
                body_with_markers=_BODY_WITH_MARKERS,
                choices=_FIXED_CHOICES,
                answer=2,
                explanation=_EXPLANATION_KO,
                variant_metadata=V8VariantMetadata(
                    sub_type="insertion_38",
                    original_position_index=3,  # answer=2 와 불일치
                    removed_sentence_text=_GIVEN_SENTENCE,
                    cohesion_cues=["test cue"],
                ),
            )

    def test_removed_sentence_mismatch_given_raises(self) -> None:
        """removed_sentence_text 가 given_sentence 와 다르면 ValidationError."""
        with pytest.raises(ValidationError, match="불일치"):
            V8Output(
                given_sentence=_GIVEN_SENTENCE,
                body_with_markers=_BODY_WITH_MARKERS,
                choices=_FIXED_CHOICES,
                answer=2,
                explanation=_EXPLANATION_KO,
                variant_metadata=V8VariantMetadata(
                    sub_type="insertion_38",
                    original_position_index=2,
                    removed_sentence_text="Different sentence text.",  # 불일치
                    cohesion_cues=["test cue"],
                ),
            )

    def test_body_missing_marker_raises(self) -> None:
        """body_with_markers 에 마커 ⑤ 가 없으면 ValidationError."""
        body_missing_marker = (
            "Reducing waste starts with awareness. "
            "① When people understand, they change habits. "
            "② Communities adopt practices. "
            "③ Individual effort creates change. "
            "④"
            # ⑤ 빠짐
        )
        with pytest.raises(ValidationError, match="마커"):
            V8Output(
                given_sentence=_GIVEN_SENTENCE,
                body_with_markers=body_missing_marker,
                choices=_FIXED_CHOICES,
                answer=2,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v8_metadata(answer=2),
            )

    def test_body_duplicate_marker_raises(self) -> None:
        """body_with_markers 에 마커 ① 이 2개이면 ValidationError."""
        body_duplicate_marker = (
            "Reducing waste starts with awareness. "
            "① When people understand, ① they change habits. "
            "② Communities adopt practices. "
            "③ Individual effort creates change. "
            "④ ⑤"
        )
        with pytest.raises(ValidationError, match="마커"):
            V8Output(
                given_sentence=_GIVEN_SENTENCE,
                body_with_markers=body_duplicate_marker,
                choices=_FIXED_CHOICES,
                answer=2,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v8_metadata(answer=2),
            )

    def test_given_sentence_remains_in_body_raises(self) -> None:
        """given_sentence 가 body_with_markers 에 그대로 남아 있으면 ValidationError."""
        body_with_sentence_remaining = (
            "Reducing waste starts with awareness. "
            "① When people understand how much they throw away each day, "
            "they become more motivated to change their habits. "
            "Small actions add up to significant environmental benefits. "  # 남아있음
            "② Communities that adopt these practices report not only cleaner surroundings "
            "but also lower costs for municipal waste management. "
            "③ Individual effort, multiplied across an entire community, creates meaningful change. "
            "④ ⑤"
        )
        with pytest.raises(ValidationError, match="완전히 제거"):
            V8Output(
                given_sentence=_GIVEN_SENTENCE,
                body_with_markers=body_with_sentence_remaining,
                choices=_FIXED_CHOICES,
                answer=2,
                explanation=_EXPLANATION_KO,
                variant_metadata=_make_v8_metadata(answer=2),
            )

    def test_cohesion_cues_empty_raises(self) -> None:
        """cohesion_cues 가 비어 있으면 ValidationError."""
        with pytest.raises(ValidationError):
            V8VariantMetadata(
                sub_type="insertion_38",
                original_position_index=2,
                removed_sentence_text=_GIVEN_SENTENCE,
                cohesion_cues=[],  # 빈 리스트 — min_length=1 위반
            )


# ─── generate_v8_variant 정상 케이스 ─────────────────────────────────────────


class TestGenerateV8Variant:
    @pytest.mark.asyncio
    async def test_insertion_38_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """insertion_38 원본 → V8 변형 Question 반환.

        반환된 Question 의 필드 검증:
          - variant_kind == SENTENCE_INSERTION_SHIFT
          - derived_from_question_id 는 sentinel UUID (라우트가 교체 예정)
          - given_sentence 채워짐
          - choices == ["①", "②", "③", "④", "⑤"]
          - type == INSERTION_38 (원본과 동일)
        """
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.INSERTION_38)
        llm_out = _make_v8_llm_output(sub_type="insertion_38")
        mock_client = _make_mock_client(llm_out)

        result = await generate_v8_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert isinstance(result, Question)
        assert result.variant_kind == VariantKind.SENTENCE_INSERTION_SHIFT
        assert result.type == QuestionType.INSERTION_38
        assert result.given_sentence == _GIVEN_SENTENCE
        assert result.choices == _FIXED_CHOICES
        assert result.answer == 2
        # sentinel UUID 채워짐 (라우트가 model_copy 로 교체)
        assert result.derived_from_question_id == uuid.UUID(int=0)
        assert result.tenant_id == uuid.UUID(int=0)
        assert result.workspace_id == uuid.UUID(int=0)

    @pytest.mark.asyncio
    async def test_insertion_39_returns_variant_question(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """insertion_39 원본 → V8 변형 Question 반환."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.INSERTION_39)
        llm_out = _make_v8_llm_output(sub_type="insertion_39")
        mock_client = _make_mock_client(llm_out)

        result = await generate_v8_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.type == QuestionType.INSERTION_39
        assert result.variant_kind == VariantKind.SENTENCE_INSERTION_SHIFT

    @pytest.mark.asyncio
    async def test_variant_metadata_stored_correctly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """variant_metadata 가 Question.variant_metadata 에 dict 로 저장된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.INSERTION_38)
        llm_out = _make_v8_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v8_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.variant_metadata is not None
        assert result.variant_metadata["sub_type"] == "insertion_38"
        assert result.variant_metadata["original_position_index"] == 2
        assert result.variant_metadata["removed_sentence_text"] == _GIVEN_SENTENCE
        assert len(result.variant_metadata["cohesion_cues"]) >= 1

    @pytest.mark.asyncio
    async def test_answer_varied_position(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """answer 가 4일 때 정상 처리된다 (정답 분포 편향 회피 검증)."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.INSERTION_38)

        # answer=4 인 시나리오용 body_with_markers
        body_answer_4 = (
            "Reducing waste starts with awareness. "
            "① When people understand how much they throw away each day, "
            "they become more motivated to change their habits. "
            "② Communities that adopt these practices report not only cleaner surroundings "
            "but also lower costs for municipal waste management. "
            "③ Individual effort, multiplied across an entire community, creates meaningful change. "
            "④ ⑤"
        )
        llm_out = _make_v8_llm_output(
            answer=4,
            body_with_markers=body_answer_4,
        )
        mock_client = _make_mock_client(llm_out)

        result = await generate_v8_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.answer == 4
        assert result.variant_metadata is not None
        assert result.variant_metadata["original_position_index"] == 4

    @pytest.mark.asyncio
    async def test_llm_client_called_with_correct_purpose(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """LLM 호출 시 purpose='variant_v8_sentence_insertion_shift' 로 로깅."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.INSERTION_38)
        llm_out = _make_v8_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v8_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        assert call_kwargs["purpose"] == "variant_v8_sentence_insertion_shift"

    @pytest.mark.asyncio
    async def test_passage_text_passed_to_prompt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """passage_text 가 프롬프트 변수에 포함되어 LLM 에 전달된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.INSERTION_38)
        llm_out = _make_v8_llm_output()
        mock_client = _make_mock_client(llm_out)

        await generate_v8_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        call_kwargs = mock_client.extract_structured.call_args.kwargs
        prompt = call_kwargs["prompt"]
        rendered = prompt.render()
        assert "Reducing waste" in rendered

    @pytest.mark.asyncio
    async def test_question_text_preserved_from_original(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: any
    ) -> None:
        """원본 question_text 가 그대로 유지된다."""
        _setup_prompt_dir(monkeypatch, tmp_path)
        original = _make_question(QuestionType.INSERTION_38)
        llm_out = _make_v8_llm_output()
        mock_client = _make_mock_client(llm_out)

        result = await generate_v8_variant(
            passage_text=_ZERO_WASTE_PASSAGE,
            original_question=original,
            llm_client=mock_client,
        )

        assert result.question_text == original.question_text


# ─── generate_v8_variant 에러 케이스 ─────────────────────────────────────────


class TestGenerateV8VariantErrors:
    @pytest.mark.asyncio
    async def test_non_applicable_type_raises_value_error(self) -> None:
        """V8 비적용 type (grammar_29) → ValueError."""
        original = _make_question(QuestionType.GRAMMAR_29)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V8 변형은"):
            await generate_v8_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )

        # LLM 호출 없음
        mock_client.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_order_36_not_applicable_raises_value_error(self) -> None:
        """order_36 도 V8 비적용 type (V7 대상)."""
        original = _make_question(QuestionType.ORDER_36)
        mock_client = AsyncMock()

        with pytest.raises(ValueError, match="V8 변형은"):
            await generate_v8_variant(
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
        original = _make_question(QuestionType.INSERTION_38)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMTimeoutError("timeout")
        )

        with pytest.raises(LLMTimeoutError):
            await generate_v8_variant(
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
        original = _make_question(QuestionType.INSERTION_38)
        mock_client = AsyncMock()
        mock_client.extract_structured = AsyncMock(
            side_effect=LLMSchemaValidationError(
                "schema fail",
                validation_error="test",
                raw_response={},
            )
        )

        with pytest.raises(LLMSchemaValidationError):
            await generate_v8_variant(
                passage_text=_ZERO_WASTE_PASSAGE,
                original_question=original,
                llm_client=mock_client,
            )


# ─── V8_APPLICABLE_TYPES 커버리지 ────────────────────────────────────────────


class TestV8ApplicableTypes:
    def test_applicable_types_include_required(self) -> None:
        """V8_APPLICABLE_TYPES 는 카탈로그 v0.4 §V8 의 2개 type 을 포함한다."""
        assert QuestionType.INSERTION_38 in V8_APPLICABLE_TYPES
        assert QuestionType.INSERTION_39 in V8_APPLICABLE_TYPES

    def test_applicable_types_excludes_grammar(self) -> None:
        """grammar_29 는 V8 비적용."""
        assert QuestionType.GRAMMAR_29 not in V8_APPLICABLE_TYPES

    def test_applicable_types_excludes_order(self) -> None:
        """order_36 / order_37 은 V8 비적용 (V7 대상)."""
        assert QuestionType.ORDER_36 not in V8_APPLICABLE_TYPES
        assert QuestionType.ORDER_37 not in V8_APPLICABLE_TYPES

    def test_applicable_types_excludes_gist(self) -> None:
        """gist_22 는 V8 비적용 (V6 대상)."""
        assert QuestionType.GIST_22 not in V8_APPLICABLE_TYPES

    def test_applicable_types_count(self) -> None:
        """V8 적용 type 은 정확히 2개."""
        assert len(V8_APPLICABLE_TYPES) == 2


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────


def _setup_prompt_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: any) -> None:
    """테스트용 임시 프롬프트 디렉토리 설정.

    실제 docs/prompts/ 파일을 읽지 않도록 tmp_path 에 최소 프롬프트 파일을 생성.
    """
    prompt_file = tmp_path / "variant-sentence-insertion-shift-v0.md"
    prompt_file.write_text(
        "---\nversion: 0\n---\n"
        "Passage: {{passage_text}}\nType: {{question_type}}",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
