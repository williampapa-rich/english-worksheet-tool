"""LLM 출력(RawExtractionResponse) → 정식 도메인 모델(ExtractionResult) 정규화.

ADR-0003 §D-3.1 의 normalizer.py 역할:
  - LLM 의 structured output 표면을 단순화/안정화하는 RawExtractionResponse 를
    공식 shared/schemas 도메인 모델로 변환.
  - LLM 자유 문자열(grade, source, question type 등) → enum 정규화.
  - sentinel UUID 채움 (ADR-0003 §D-3.6).

PM-5: 자료에 보이는 것만 추출 — translation / vocabulary 가 자료에 있으면 포함.
PM-6: 자료에 없으면 translation=None / vocabulary=[] (정상, 에러 아님).

RawExtractionResponse 는 extractor 패키지 내부 스키마 — shared/schemas/ 와 별개.
architect 영역(shared/schemas/) 침범 없이 LLM 출력 표면만 담당.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from extractor.base import SENTINEL_UUID
from extractor.errors import ExtractionError
from shared.schemas.extraction import ExtractionMetaRef, ExtractionResult
from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade
from shared.schemas.question import Question, QuestionType, VariantKind
from shared.schemas.translation import Translation, TranslationCreatedBy
from shared.schemas.vocabulary import Vocabulary, VocabularySelectedBy

# ─── Raw 스키마 (LLM 출력 표면) ──────────────────────────────────────────────
# extractor 패키지 내부 스키마. shared/schemas/ 와 별개.
# LLM 이 실제로 출력하는 단순화/안정화된 형태 — 정식 도메인 모델보다 필드가 적고
# 타입이 느슨하다. normalizer 가 이를 정식 모델로 변환.


class RawPassage(BaseModel):
    """LLM 이 출력하는 지문 표현."""

    body_text: str = Field(..., description="영어 본문 텍스트 (마커 inline 보존).")
    paragraphs: list[str] = Field(
        default_factory=list,
        description="단락 분할. LLM 이 분리 못하면 빈 list — normalizer 가 body_text 로 재구성.",
    )
    word_count: int | None = Field(
        default=None,
        description="단어 수. LLM 이 빠뜨리면 normalizer 가 body_text 로 계산.",
    )
    target_grade: str | None = Field(
        default=None,
        description="학년 자유 문자열 (예: '고2', 'high_2', '2학년'). enum 정규화는 normalizer.",
    )
    topic_tags: list[str] = Field(
        default_factory=list,
        description="주제 키워드 (자유 문자열).",
    )
    source_provider: str | None = Field(
        default=None,
        description="출처 제공자 자유 문자열 (예: '아잉카', 'aingka', '평가원'). enum 정규화는 normalizer.",
    )


class RawQuestion(BaseModel):
    """LLM 이 출력하는 문제 표현."""

    type: str = Field(
        ...,
        description=(
            "exam-generator 24개 유형 중 하나 (자유 문자열). "
            "정규화에서 QuestionType enum 으로 변환. 매핑 실패 시 ExtractionError."
        ),
    )
    stem: str = Field(default="", description="문제 발문.")
    choices: list[str] = Field(default_factory=list, description="선택지 목록.")
    correct_answer: str | None = Field(default=None, description="정답 (있으면).")
    explanation: str | None = Field(default=None, description="해설 (있으면).")
    sub_form: str | None = Field(
        default=None,
        description="CLAUDE.md §6.2 sub-form (예: 'inline_choice', 'matrix_ab').",
    )
    number: int | None = Field(default=None, ge=1, le=45, description="시험지 문항 번호.")


class RawTranslation(BaseModel):
    """LLM 이 출력하는 한글 해석 표현."""

    text: str = Field(..., description="전체 한글 해석 본문.")


class RawVocabulary(BaseModel):
    """LLM 이 출력하는 어휘 항목 표현."""

    headword: str = Field(..., description="어휘 표제어 (사용자 입력 표면형).")
    pos: str | None = Field(default=None, description="품사 (예: 'verb', 'noun').")
    meaning_ko: str | None = Field(default=None, description="한국어 뜻.")
    examples: list[str] = Field(default_factory=list, description="예문 (있으면).")


class RawExtractionItem(BaseModel):
    """1개 지문 단위 — passage + 그에 속한 questions / translation / vocabulary.

    PM-1: 한 자료에 N개 지문이 있으면 N개의 RawExtractionItem.
    """

    passage: RawPassage
    questions: list[RawQuestion] = Field(default_factory=list)
    translation: RawTranslation | None = Field(
        default=None,
        description="PM-5: 자료에 한글 해석이 있으면 채움. 없으면 None (PM-6 — 정상).",
    )
    vocabulary: list[RawVocabulary] = Field(
        default_factory=list,
        description="PM-5: 자료에 어휘 박스가 있으면 채움. 없으면 빈 list (PM-6 — 정상).",
    )


class RawExtractionResponse(BaseModel):
    """LLM 의 최상위 출력 — N개의 passage 단위를 포함.

    PM-1: 단일 지문 입력도 items 에 1개 항목으로.
    """

    items: list[RawExtractionItem] = Field(..., description="추출된 지문 단위 목록 (최소 1개).")


# ─── 정규화 헬퍼 ─────────────────────────────────────────────────────────────

# TargetGrade 정규화 매핑 — LLM 자유 문자열 → enum
# 한국어 / 영어 표현 / 다양한 변형을 허용.
_GRADE_MAP: dict[str, TargetGrade] = {
    # 중학교
    "중1": TargetGrade.MIDDLE_1,
    "중학교 1학년": TargetGrade.MIDDLE_1,
    "middle_1": TargetGrade.MIDDLE_1,
    "middle 1": TargetGrade.MIDDLE_1,
    "m1": TargetGrade.MIDDLE_1,
    "중2": TargetGrade.MIDDLE_2,
    "중학교 2학년": TargetGrade.MIDDLE_2,
    "middle_2": TargetGrade.MIDDLE_2,
    "middle 2": TargetGrade.MIDDLE_2,
    "m2": TargetGrade.MIDDLE_2,
    "중3": TargetGrade.MIDDLE_3,
    "중학교 3학년": TargetGrade.MIDDLE_3,
    "middle_3": TargetGrade.MIDDLE_3,
    "middle 3": TargetGrade.MIDDLE_3,
    "m3": TargetGrade.MIDDLE_3,
    # 고등학교
    "고1": TargetGrade.HIGH_1,
    "고등학교 1학년": TargetGrade.HIGH_1,
    "high_1": TargetGrade.HIGH_1,
    "high 1": TargetGrade.HIGH_1,
    "1학년": TargetGrade.HIGH_1,
    "h1": TargetGrade.HIGH_1,
    "고2": TargetGrade.HIGH_2,
    "고등학교 2학년": TargetGrade.HIGH_2,
    "high_2": TargetGrade.HIGH_2,
    "high 2": TargetGrade.HIGH_2,
    "2학년": TargetGrade.HIGH_2,
    "h2": TargetGrade.HIGH_2,
    "고3": TargetGrade.HIGH_3,
    "고등학교 3학년": TargetGrade.HIGH_3,
    "high_3": TargetGrade.HIGH_3,
    "high 3": TargetGrade.HIGH_3,
    "3학년": TargetGrade.HIGH_3,
    "h3": TargetGrade.HIGH_3,
    # 수능
    "수능": TargetGrade.SUNEUNG,
    "csat": TargetGrade.SUNEUNG,
    "수학능력시험": TargetGrade.SUNEUNG,
    "suneung": TargetGrade.SUNEUNG,
}

# SourceProvider 정규화 매핑
_SOURCE_MAP: dict[str, SourceProvider] = {
    "아잉카": SourceProvider.AINGKA,
    "aingka": SourceProvider.AINGKA,
    "평가원": SourceProvider.EVALUATOR,
    "evaluator": SourceProvider.EVALUATOR,
    "수능": SourceProvider.EVALUATOR,
    "모평": SourceProvider.EVALUATOR,
    "ebsi": SourceProvider.EBSI,
    "ebs": SourceProvider.EBSI,
    "school_internal": SourceProvider.SCHOOL_INTERNAL,
    "학교": SourceProvider.SCHOOL_INTERNAL,
    "내신": SourceProvider.SCHOOL_INTERNAL,
    "user_input": SourceProvider.USER_INPUT,
    "직접입력": SourceProvider.USER_INPUT,
    "user": SourceProvider.USER_INPUT,
}

# QuestionType 정규화 매핑 — LLM 자유 문자열 → enum
# exam-generator 24개 유형 기반 (CLAUDE.md §6.2)
_QUESTION_TYPE_MAP: dict[str, QuestionType] = {
    # 공식 enum 값 그대로
    "purpose_18": QuestionType.PURPOSE_18,
    "mood_19": QuestionType.MOOD_19,
    "assertion_20": QuestionType.ASSERTION_20,
    "underline_implication_21": QuestionType.UNDERLINE_IMPLICATION_21,
    "gist_22": QuestionType.GIST_22,
    "theme_23": QuestionType.THEME_23,
    "title_24": QuestionType.TITLE_24,
    "chart_25": QuestionType.CHART_25,
    "figure_match_26": QuestionType.FIGURE_MATCH_26,
    "notice_27": QuestionType.NOTICE_27,
    "notice_28": QuestionType.NOTICE_28,
    "grammar_29": QuestionType.GRAMMAR_29,
    "vocabulary_30": QuestionType.VOCABULARY_30,
    "blank_phrase_31": QuestionType.BLANK_PHRASE_31,
    "blank_clause_32": QuestionType.BLANK_CLAUSE_32,
    "blank_clause_33": QuestionType.BLANK_CLAUSE_33,
    "blank_clause_34": QuestionType.BLANK_CLAUSE_34,
    "irrelevant_sentence_35": QuestionType.IRRELEVANT_SENTENCE_35,
    "order_36": QuestionType.ORDER_36,
    "order_37": QuestionType.ORDER_37,
    "insertion_38": QuestionType.INSERTION_38,
    "insertion_39": QuestionType.INSERTION_39,
    "summary_40": QuestionType.SUMMARY_40,
    "long_set_41_42": QuestionType.LONG_SET_41_42,
    "long_set_43_45": QuestionType.LONG_SET_43_45,
    # 한국어 별칭
    "목적": QuestionType.PURPOSE_18,
    "심경": QuestionType.MOOD_19,
    "주장": QuestionType.ASSERTION_20,
    "밑줄 함의": QuestionType.UNDERLINE_IMPLICATION_21,
    "요지": QuestionType.GIST_22,
    "주제": QuestionType.THEME_23,
    "제목": QuestionType.TITLE_24,
    "도표": QuestionType.CHART_25,
    "그림": QuestionType.FIGURE_MATCH_26,
    "안내문1": QuestionType.NOTICE_27,
    "안내문2": QuestionType.NOTICE_28,
    "어법": QuestionType.GRAMMAR_29,
    "어휘": QuestionType.VOCABULARY_30,
    "빈칸31": QuestionType.BLANK_PHRASE_31,
    "빈칸32": QuestionType.BLANK_CLAUSE_32,
    "빈칸33": QuestionType.BLANK_CLAUSE_33,
    "빈칸34": QuestionType.BLANK_CLAUSE_34,
    "무관문장": QuestionType.IRRELEVANT_SENTENCE_35,
    "순서36": QuestionType.ORDER_36,
    "순서37": QuestionType.ORDER_37,
    "삽입38": QuestionType.INSERTION_38,
    "삽입39": QuestionType.INSERTION_39,
    "요약": QuestionType.SUMMARY_40,
    "장문41_42": QuestionType.LONG_SET_41_42,
    "장문43_45": QuestionType.LONG_SET_43_45,
}


def _count_words(text: str) -> int:
    """영어 텍스트의 단어 수 계산.

    공백 기준 분리. 빈 토큰 제외.
    """
    return len(text.split())


def _normalize_grade(raw: str | None) -> TargetGrade:
    """LLM 자유 문자열 학년 → TargetGrade enum.

    Args:
        raw: LLM 출력 학년 문자열 (예: '고2', 'high_2', None).

    Returns:
        TargetGrade enum. 매핑 실패 또는 None 이면 TargetGrade.OTHER.
    """
    if raw is None:
        return TargetGrade.OTHER
    normalized = raw.strip().lower().replace("  ", " ")
    result = _GRADE_MAP.get(normalized)
    if result is not None:
        return result
    # 원본(대소문자 보존) 도 시도
    result = _GRADE_MAP.get(raw.strip())
    return result if result is not None else TargetGrade.OTHER


def _normalize_source(raw: str | None) -> SourceProvider:
    """LLM 자유 문자열 출처 → SourceProvider enum.

    Args:
        raw: LLM 출력 출처 문자열 (예: '아잉카', 'evaluator', None).

    Returns:
        SourceProvider enum. 매핑 실패 또는 None 이면 SourceProvider.USER_INPUT.
    """
    if raw is None:
        return SourceProvider.USER_INPUT
    normalized = raw.strip().lower()
    result = _SOURCE_MAP.get(normalized)
    if result is not None:
        return result
    result = _SOURCE_MAP.get(raw.strip())
    return result if result is not None else SourceProvider.USER_INPUT


def _normalize_question_type(raw: str) -> QuestionType:
    """LLM 자유 문자열 유형 → QuestionType enum.

    Args:
        raw: LLM 출력 유형 문자열 (예: 'purpose_18', '목적', 'vocabulary_30').

    Returns:
        QuestionType enum.

    Raises:
        ExtractionError: 24개 유형 중 매핑 실패 시. LLM 이 schema 외 유형 반환은
            schema validation error 수준으로 취급.
    """
    normalized = raw.strip().lower()
    result = _QUESTION_TYPE_MAP.get(normalized)
    if result is not None:
        return result
    result = _QUESTION_TYPE_MAP.get(raw.strip())
    if result is not None:
        return result
    raise ExtractionError(
        f"LLM 이 반환한 question type '{raw}' 를 24개 유형 enum 으로 매핑할 수 없습니다. "
        "exam-generator 24개 유형 중 하나이어야 합니다 (CLAUDE.md §6.2). "
        "프롬프트에 유형 목록이 명시되어 있는지 확인하세요."
    )


def _parse_answer_index(raw: str | None) -> int:
    """정답 문자열 → 1-based 인덱스.

    '1', '①', '②', ... → 1, 2, ...
    파싱 실패 시 기본값 1.
    """
    if raw is None:
        return 1
    stripped = raw.strip()
    # 원문자 변환 (①②③④⑤)
    circled = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5}
    if stripped in circled:
        return circled[stripped]
    # 숫자 직접 파싱
    match = re.search(r"\d", stripped)
    if match:
        val = int(match.group())
        if 1 <= val <= 5:
            return val
    return 1


def _normalize_question(
    raw: RawQuestion,
    *,
    passage_id: uuid.UUID,
    sentinel: uuid.UUID,
) -> Question:
    """RawQuestion → Question 도메인 모델.

    Args:
        raw: LLM 출력 문제 표현.
        passage_id: 귀속 Passage ID.
        sentinel: sentinel UUID (tenant_id / workspace_id 에 채움).

    Returns:
        Question 인스턴스.

    Raises:
        ExtractionError: question type 매핑 실패.
    """
    q_type = _normalize_question_type(raw.type)
    answer_idx = _parse_answer_index(raw.correct_answer)

    return Question(
        tenant_id=sentinel,
        workspace_id=sentinel,
        passage_id=passage_id,
        type=q_type,
        variant_kind=VariantKind.ORIGINAL,
        derived_from_question_id=None,
        number=raw.number,
        question_text=raw.stem,
        choices=raw.choices,
        answer=answer_idx,
        explanation=raw.explanation or "",
    )


def _normalize_vocabulary(
    raw: RawVocabulary,
    *,
    passage_id: uuid.UUID,
    sentinel: uuid.UUID,
) -> Vocabulary:
    """RawVocabulary → Vocabulary 도메인 모델.

    Args:
        raw: LLM 출력 어휘 항목.
        passage_id: 귀속 Passage ID.
        sentinel: sentinel UUID.

    Returns:
        Vocabulary 인스턴스.
    """
    headword_normalized = raw.headword.strip().lower()
    return Vocabulary(
        tenant_id=sentinel,
        workspace_id=sentinel,
        passage_id=passage_id,
        word=raw.headword,
        headword_normalized=headword_normalized,
        pos=raw.pos,
        meaning_ko=raw.meaning_ko or "",
        selected_by=VocabularySelectedBy.LLM,
        user_edited=False,
    )


def _normalize_item(
    item: RawExtractionItem,
    *,
    llm_meta: ExtractionMetaRef,
) -> ExtractionResult:
    """RawExtractionItem → ExtractionResult.

    sentinel UUID 를 사용해 tenant_id / workspace_id 를 채운다.
    API 레이어가 model_copy 로 실제 값 주입.

    Args:
        item: LLM 출력 지문 단위.
        llm_meta: LLM 호출 메타 참조.

    Returns:
        ExtractionResult 인스턴스.
    """
    sentinel = SENTINEL_UUID

    raw_passage = item.passage
    # 단락이 비어있으면 body_text 를 단일 단락으로
    paragraphs = raw_passage.paragraphs if raw_passage.paragraphs else [raw_passage.body_text]
    word_count = raw_passage.word_count or _count_words(raw_passage.body_text)

    passage = Passage(
        tenant_id=sentinel,
        workspace_id=sentinel,
        body_text=raw_passage.body_text,
        paragraphs=paragraphs,
        word_count=word_count,
        target_grade=_normalize_grade(raw_passage.target_grade),
        topic_tags=raw_passage.topic_tags,
        source=SourceMeta(
            provider=_normalize_source(raw_passage.source_provider),
        ),
    )

    questions = [
        _normalize_question(q, passage_id=passage.id, sentinel=sentinel) for q in item.questions
    ]

    translation: Translation | None = None
    if item.translation is not None:
        translation = Translation(
            tenant_id=sentinel,
            workspace_id=sentinel,
            passage_id=passage.id,
            language="ko",
            text=item.translation.text,
            created_by=TranslationCreatedBy.LLM,
        )

    vocabulary = [
        _normalize_vocabulary(v, passage_id=passage.id, sentinel=sentinel) for v in item.vocabulary
    ]

    return ExtractionResult(
        passage=passage,
        questions=questions,
        translation=translation,
        vocabulary=vocabulary,
        extraction_meta=llm_meta,
    )


def normalize(
    raw: RawExtractionResponse,
    *,
    llm_meta: ExtractionMetaRef,
) -> list[ExtractionResult]:
    """RawExtractionResponse → list[ExtractionResult].

    각 RawExtractionItem 1개당 ExtractionResult 1개 생성 (PM-1).

    Args:
        raw: LLM 최상위 출력.
        llm_meta: LLM 호출 메타 참조 (ExtractionMetaRef).

    Returns:
        list[ExtractionResult]: PM-1 — 다중 지문 결과.
    """
    return [_normalize_item(item, llm_meta=llm_meta) for item in raw.items]


def make_llm_meta(
    *,
    request_id: uuid.UUID,
    model: str,
    prompt_template_id: str | None = None,
) -> ExtractionMetaRef:
    """LLM 호출 결과에서 ExtractionMetaRef 생성.

    Args:
        request_id: LLM 호출 request_id (StructuredLLMResult.request_id).
        model: 실제 사용 모델 ID.
        prompt_template_id: 사용한 프롬프트 템플릿 ID.

    Returns:
        ExtractionMetaRef 인스턴스 (extracted_at = 현재 UTC).
    """
    return ExtractionMetaRef(
        request_id=request_id,
        model=model,
        prompt_template_id=prompt_template_id,
        extracted_at=datetime.now(UTC),
    )
