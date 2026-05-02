"""normalizer.py — Raw → 도메인 모델 정규화 테스트.

_normalize_grade / _normalize_source / _normalize_question_type 의 매핑 정확성 검증.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from extractor.errors import ExtractionError
from extractor.normalizer import (
    RawExtractionItem,
    RawExtractionResponse,
    RawPassage,
    RawQuestion,
    RawTranslation,
    RawVocabulary,
    _normalize_grade,
    _normalize_question_type,
    _normalize_source,
    make_llm_meta,
    normalize,
)

from shared.schemas.extraction import ExtractionMetaRef
from shared.schemas.passage import SourceProvider, TargetGrade
from shared.schemas.question import QuestionType

# ─── fixture ─────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_meta() -> ExtractionMetaRef:
    return ExtractionMetaRef(
        request_id=uuid.uuid4(),
        model="claude-sonnet-4-6",
        prompt_template_id="extract-text-v0",
        extracted_at=datetime.now(UTC),
    )


@pytest.fixture
def minimal_raw_passage() -> RawPassage:
    return RawPassage(
        body_text="The quick brown fox jumps over the lazy dog.",
        paragraphs=["The quick brown fox jumps over the lazy dog."],
        word_count=9,
    )


# ─── _normalize_grade 테스트 ─────────────────────────────────────────────────


class TestNormalizeGrade:
    """LLM 자유 문자열 학년 → TargetGrade enum 매핑."""

    def test_korean_high_2(self) -> None:
        assert _normalize_grade("고2") == TargetGrade.HIGH_2

    def test_korean_high_2_verbose(self) -> None:
        assert _normalize_grade("고등학교 2학년") == TargetGrade.HIGH_2

    def test_english_underscore_high_2(self) -> None:
        assert _normalize_grade("high_2") == TargetGrade.HIGH_2

    def test_english_space_high_2(self) -> None:
        assert _normalize_grade("high 2") == TargetGrade.HIGH_2

    def test_korean_year_high_2(self) -> None:
        assert _normalize_grade("2학년") == TargetGrade.HIGH_2

    def test_korean_middle_1(self) -> None:
        assert _normalize_grade("중1") == TargetGrade.MIDDLE_1

    def test_english_middle_3(self) -> None:
        assert _normalize_grade("middle_3") == TargetGrade.MIDDLE_3

    def test_high_1(self) -> None:
        assert _normalize_grade("고1") == TargetGrade.HIGH_1

    def test_high_3(self) -> None:
        assert _normalize_grade("고3") == TargetGrade.HIGH_3

    def test_suneung_korean(self) -> None:
        assert _normalize_grade("수능") == TargetGrade.SUNEUNG

    def test_suneung_english(self) -> None:
        assert _normalize_grade("csat") == TargetGrade.SUNEUNG

    def test_none_returns_other(self) -> None:
        """None 입력 시 OTHER 반환 (PM-6 — 자료에 없으면 정상)."""
        assert _normalize_grade(None) == TargetGrade.OTHER

    def test_unknown_string_returns_other(self) -> None:
        """매핑 실패 시 OTHER 반환 (에러 raise 안 함)."""
        assert _normalize_grade("알 수 없는 학년") == TargetGrade.OTHER

    def test_empty_string_returns_other(self) -> None:
        assert _normalize_grade("") == TargetGrade.OTHER

    def test_whitespace_stripped(self) -> None:
        """앞뒤 공백은 strip 후 매핑."""
        assert _normalize_grade("  고2  ") == TargetGrade.HIGH_2


# ─── _normalize_source 테스트 ────────────────────────────────────────────────


class TestNormalizeSource:
    """LLM 자유 문자열 출처 → SourceProvider enum 매핑."""

    def test_korean_aingka(self) -> None:
        assert _normalize_source("아잉카") == SourceProvider.AINGKA

    def test_english_aingka(self) -> None:
        assert _normalize_source("aingka") == SourceProvider.AINGKA

    def test_korean_evaluator(self) -> None:
        assert _normalize_source("평가원") == SourceProvider.EVALUATOR

    def test_korean_suneung_maps_to_evaluator(self) -> None:
        assert _normalize_source("수능") == SourceProvider.EVALUATOR

    def test_korean_mopyeong_maps_to_evaluator(self) -> None:
        assert _normalize_source("모평") == SourceProvider.EVALUATOR

    def test_ebsi(self) -> None:
        assert _normalize_source("ebsi") == SourceProvider.EBSI

    def test_school_internal(self) -> None:
        assert _normalize_source("내신") == SourceProvider.SCHOOL_INTERNAL

    def test_none_returns_user_input(self) -> None:
        """None 입력 시 USER_INPUT 반환."""
        assert _normalize_source(None) == SourceProvider.USER_INPUT

    def test_unknown_returns_user_input(self) -> None:
        """매핑 실패 시 USER_INPUT fallback."""
        assert _normalize_source("알 수 없는 출처") == SourceProvider.USER_INPUT


# ─── _normalize_question_type 테스트 ─────────────────────────────────────────


class TestNormalizeQuestionType:
    """LLM 자유 문자열 유형 → QuestionType enum 매핑 + 실패 시 raise."""

    def test_purpose_18_exact(self) -> None:
        assert _normalize_question_type("purpose_18") == QuestionType.PURPOSE_18

    def test_purpose_18_korean(self) -> None:
        assert _normalize_question_type("목적") == QuestionType.PURPOSE_18

    def test_mood_19(self) -> None:
        assert _normalize_question_type("mood_19") == QuestionType.MOOD_19

    def test_vocabulary_30(self) -> None:
        assert _normalize_question_type("vocabulary_30") == QuestionType.VOCABULARY_30

    def test_blank_phrase_31(self) -> None:
        assert _normalize_question_type("blank_phrase_31") == QuestionType.BLANK_PHRASE_31

    def test_blank_clause_32(self) -> None:
        assert _normalize_question_type("blank_clause_32") == QuestionType.BLANK_CLAUSE_32

    def test_order_36(self) -> None:
        assert _normalize_question_type("order_36") == QuestionType.ORDER_36

    def test_insertion_38(self) -> None:
        assert _normalize_question_type("insertion_38") == QuestionType.INSERTION_38

    def test_summary_40(self) -> None:
        assert _normalize_question_type("summary_40") == QuestionType.SUMMARY_40

    def test_long_set_41_42(self) -> None:
        assert _normalize_question_type("long_set_41_42") == QuestionType.LONG_SET_41_42

    def test_unknown_raises_extraction_error(self) -> None:
        """24개 유형 외 매핑 실패 시 ExtractionError raise."""
        with pytest.raises(ExtractionError, match="24개 유형"):
            _normalize_question_type("알_수_없는_유형")

    def test_case_insensitive(self) -> None:
        """대소문자 무관 매핑 (lowercase 정규화)."""
        assert _normalize_question_type("VOCABULARY_30") == QuestionType.VOCABULARY_30


# ─── normalize (최상위) 테스트 ───────────────────────────────────────────────


class TestNormalize:
    """RawExtractionResponse → list[ExtractionResult] 통합 정규화 테스트."""

    def test_single_passage_english_only(
        self, sample_meta: ExtractionMetaRef, minimal_raw_passage: RawPassage
    ) -> None:
        """PM-6 default — 영어만 입력, translation=None, vocabulary=[] (정상)."""
        raw = RawExtractionResponse(
            items=[
                RawExtractionItem(
                    passage=minimal_raw_passage,
                    questions=[],
                    translation=None,
                    vocabulary=[],
                )
            ]
        )
        results = normalize(raw, llm_meta=sample_meta)

        assert len(results) == 1
        result = results[0]
        assert result.translation is None
        assert result.vocabulary == []
        assert result.passage.body_text == minimal_raw_passage.body_text

    def test_sentinel_uuid_in_passage(
        self, sample_meta: ExtractionMetaRef, minimal_raw_passage: RawPassage
    ) -> None:
        """Passage.tenant_id / workspace_id 는 sentinel UUID (ADR-0003 §D-3.6)."""
        from extractor.base import SENTINEL_UUID

        raw = RawExtractionResponse(items=[RawExtractionItem(passage=minimal_raw_passage)])
        results = normalize(raw, llm_meta=sample_meta)

        assert results[0].passage.tenant_id == SENTINEL_UUID
        assert results[0].passage.workspace_id == SENTINEL_UUID

    def test_with_translation_and_vocabulary(
        self, sample_meta: ExtractionMetaRef, minimal_raw_passage: RawPassage
    ) -> None:
        """PM-5 — 자료에 한글 해석 + 어휘 있으면 추출."""
        raw = RawExtractionResponse(
            items=[
                RawExtractionItem(
                    passage=minimal_raw_passage,
                    questions=[],
                    translation=RawTranslation(text="빠른 갈색 여우가 게으른 개 위로 점프한다."),
                    vocabulary=[
                        RawVocabulary(headword="fox", pos="noun", meaning_ko="여우"),
                        RawVocabulary(headword="lazy", pos="adj", meaning_ko="게으른"),
                    ],
                )
            ]
        )
        results = normalize(raw, llm_meta=sample_meta)

        assert results[0].translation is not None
        assert results[0].translation.text == "빠른 갈색 여우가 게으른 개 위로 점프한다."
        assert len(results[0].vocabulary) == 2
        assert results[0].vocabulary[0].word == "fox"
        assert results[0].vocabulary[1].headword_normalized == "lazy"

    def test_multiple_passages_pm1(self, sample_meta: ExtractionMetaRef) -> None:
        """PM-1 — 한 자료에 N개 지문이 있으면 N개의 ExtractionResult."""
        passage_a = RawPassage(
            body_text="First passage text here.", paragraphs=["First passage text here."]
        )
        passage_b = RawPassage(
            body_text="Second passage text here.", paragraphs=["Second passage text here."]
        )
        raw = RawExtractionResponse(
            items=[
                RawExtractionItem(passage=passage_a),
                RawExtractionItem(passage=passage_b),
            ]
        )
        results = normalize(raw, llm_meta=sample_meta)

        assert len(results) == 2
        assert results[0].passage.body_text == "First passage text here."
        assert results[1].passage.body_text == "Second passage text here."

    def test_word_count_auto_calculated(self, sample_meta: ExtractionMetaRef) -> None:
        """LLM 이 word_count 빠뜨리면 normalizer 가 자동 계산."""
        passage = RawPassage(
            body_text="One two three four five",
            paragraphs=["One two three four five"],
            word_count=None,  # LLM 이 빠뜨린 경우
        )
        raw = RawExtractionResponse(items=[RawExtractionItem(passage=passage)])
        results = normalize(raw, llm_meta=sample_meta)

        assert results[0].passage.word_count == 5

    def test_empty_paragraphs_auto_filled(self, sample_meta: ExtractionMetaRef) -> None:
        """LLM 이 paragraphs 를 빈 list 로 주면 body_text 로 단일 단락 구성."""
        passage = RawPassage(
            body_text="Single paragraph text.",
            paragraphs=[],  # LLM 이 분리 못한 경우
        )
        raw = RawExtractionResponse(items=[RawExtractionItem(passage=passage)])
        results = normalize(raw, llm_meta=sample_meta)

        assert results[0].passage.paragraphs == ["Single paragraph text."]

    def test_question_with_type_mapping(
        self, sample_meta: ExtractionMetaRef, minimal_raw_passage: RawPassage
    ) -> None:
        """문제 type 이 올바르게 QuestionType enum 으로 매핑된다."""
        from shared.schemas.question import QuestionType

        raw = RawExtractionResponse(
            items=[
                RawExtractionItem(
                    passage=minimal_raw_passage,
                    questions=[
                        RawQuestion(
                            type="vocabulary_30",
                            stem="다음 글의 밑줄 친 단어 중 문맥상 낱말의 쓰임이 적절하지 않은 것은?",
                            choices=["①", "②", "③", "④", "⑤"],
                            correct_answer="②",
                        )
                    ],
                )
            ]
        )
        results = normalize(raw, llm_meta=sample_meta)

        assert len(results[0].questions) == 1
        assert results[0].questions[0].type == QuestionType.VOCABULARY_30
        assert results[0].questions[0].answer == 2  # "②" → 2

    def test_extraction_meta_preserved(
        self, sample_meta: ExtractionMetaRef, minimal_raw_passage: RawPassage
    ) -> None:
        """ExtractionMetaRef 가 ExtractionResult 에 그대로 담긴다."""
        raw = RawExtractionResponse(items=[RawExtractionItem(passage=minimal_raw_passage)])
        results = normalize(raw, llm_meta=sample_meta)

        assert results[0].extraction_meta.request_id == sample_meta.request_id
        assert results[0].extraction_meta.model == sample_meta.model

    def test_make_llm_meta_creates_valid_meta(self) -> None:
        """make_llm_meta 가 유효한 ExtractionMetaRef 를 생성한다."""
        request_id = uuid.uuid4()
        meta = make_llm_meta(
            request_id=request_id,
            model="claude-sonnet-4-6",
            prompt_template_id="extract-text-v0",
        )

        assert meta.request_id == request_id
        assert meta.model == "claude-sonnet-4-6"
        assert meta.prompt_template_id == "extract-text-v0"
        assert meta.extracted_at.tzinfo is not None  # timezone-aware

    def test_vocabulary_headword_normalized(
        self, sample_meta: ExtractionMetaRef, minimal_raw_passage: RawPassage
    ) -> None:
        """headword_normalized 는 소문자 변환된 headword."""
        raw = RawExtractionResponse(
            items=[
                RawExtractionItem(
                    passage=minimal_raw_passage,
                    vocabulary=[
                        RawVocabulary(headword="QuickLY", meaning_ko="빠르게"),
                    ],
                )
            ]
        )
        results = normalize(raw, llm_meta=sample_meta)

        assert results[0].vocabulary[0].word == "QuickLY"
        assert results[0].vocabulary[0].headword_normalized == "quickly"
