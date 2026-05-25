"""Question(문제) 도메인 모델.

CLAUDE.md v0.3 §6.2 정정 반영:
  - **변형 유형은 별 카테고리가 아니라 기존 24개 유형의 sub-form / 파생**.
  - exam-generator 의 24개 활성 유형 (`ACTIVE_TYPES`) 을 ``QuestionType`` enum 으로
    그대로 흡수.
  - 변형문제는 같은 ``type`` 안에서 ``variant_kind`` + ``derived_from_question_id``
    필드로 표현 (단일 테이블 + discriminator 방향, audit §4-5 권고).
  - 새 type 은 도입하지 않는다 — 기존 24개로 표현 불가능한 케이스는 PM 결정.

Sub-form 표현 (CLAUDE.md §6.2 + audit §3.1 / §3.2 / audit-review-domain §3.1 / §3.2):
  - **Gap A 본문 내장형 어휘 선택**: ``inline_choices: Optional[list[InlineChoice]]``.
  - **Gap B 다중 선택지 매트릭스**: ``choice_format`` 디스크리미네이터 +
    ``choice_matrix: Optional[ChoiceMatrix]`` (audit-review-domain §3.2 권고:
    평탄화-우선 + 매트릭스-옵트인).

Open Question (별 ADR 예정):
  - §4-5 Question vs VariantQuestion 단일 테이블 vs 별 테이블 — **ADR-0017 Accepted
    (2026-05-15)**: 권장안 (a) 단일 ``Question`` 테이블 + ``variant_kind``
    discriminator + ``derived_from_question_id`` self-FK NULLABLE 채택.
  - §4-8 inline_choices 도입 시점 — Phase 3 진입 전 ADR.
  - ``VariantKind`` enum 보강 — **v0.4 (2026-05-15) 카탈로그 v0.4 와 동시 보강
    완료** (V1~V10 모두 enum 멤버 추가, THEME_REWORD → TOPIC_MAIN_IDEA_SWAP 통합).
    ADR-0017 D2-b 결정 사항.

audit-review-domain §4.1 권고:
  qa-validator 가 Phase 3 에서 채울 ``uniqueness_validated`` / ``uniqueness_validator_note``
  필드 자리 마련 ("AI 자동 ≠ 완성").
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.schemas.common import EntityId, WorkspaceScopedEntity


# ─── Question 유형 enum (24개 활성 + 1개 비활성) ────────────────────────────
class QuestionType(StrEnum):
    """exam-generator ``ACTIVE_TYPES`` (24개) + ``DISABLED_TYPES`` (1개) 흡수.

    enum value 는 영문 snake_case + 평가원 문항 번호. 한국어 라벨 (예: '빈칸-구(31)')
    은 ``LAYOUT_PATTERN`` / ``GROUP_LABEL_TEMPLATES`` 등의 후처리 어댑터에서 매핑한다
    (renderer / parser 관심사).

    enum value 명명 규칙:
      - 평가원 분류명 (영문 snake_case) + ``_<문항번호>``.
      - 같은 분류 다른 번호는 별 enum 멤버 (예: ``BLANK_CLAUSE_32`` / ``_33`` / ``_34``).
      - 장문 세트는 번호 범위 (``LONG_SET_41_42`` / ``LONG_SET_43_45``).
    """

    # reasoning 계열
    PURPOSE_18 = "purpose_18"
    MOOD_19 = "mood_19"
    ASSERTION_20 = "assertion_20"
    UNDERLINE_IMPLICATION_21 = "underline_implication_21"
    GIST_22 = "gist_22"
    THEME_23 = "theme_23"
    TITLE_24 = "title_24"

    # 비활성 — DISABLED_TYPES (이미지 생성 미지원)
    CHART_25 = "chart_25"

    FIGURE_MATCH_26 = "figure_match_26"
    NOTICE_27 = "notice_27"
    NOTICE_28 = "notice_28"

    # marker_inline 계열 (어법/어휘)
    GRAMMAR_29 = "grammar_29"
    VOCABULARY_30 = "vocabulary_30"

    # blank_inline 계열
    BLANK_PHRASE_31 = "blank_phrase_31"
    BLANK_CLAUSE_32 = "blank_clause_32"
    BLANK_CLAUSE_33 = "blank_clause_33"
    BLANK_CLAUSE_34 = "blank_clause_34"

    # marker_inline 계열 (무관문장 / 문장삽입)
    IRRELEVANT_SENTENCE_35 = "irrelevant_sentence_35"

    # passage_segments 계열
    ORDER_36 = "order_36"
    ORDER_37 = "order_37"

    INSERTION_38 = "insertion_38"
    INSERTION_39 = "insertion_39"

    SUMMARY_40 = "summary_40"

    # long_set 계열
    LONG_SET_41_42 = "long_set_41_42"
    LONG_SET_43_45 = "long_set_43_45"


class VariantKind(StrEnum):
    """변형 유형 (CLAUDE.md §6.2 정정 — 같은 ``type`` 안에서의 파생).

    v0.4 (2026-05-15) — 카탈로그 v0.4 (`docs/variant-type-catalog.md` §3.2) 의
    V1~V10 모두 흡수. ADR-0017 D2-b 결정 (variant_kind enum 보강 시점) — 본 enum
    값은 카탈로그 v0.4 와 동시 보강.

    카탈로그 ID 정합 (snake_case + 카탈로그 ID — `docs/variant-type-catalog.md` §3.2):

    | enum 멤버 | 카탈로그 ID | 적용 가능 type (확실) | 우선순위 |
    |---|---|---|---|
    | ``ORIGINAL`` | -    | 모든 type | - |
    | ``VOCABULARY_SWAP`` | V1 | vocabulary_30 / long_set_41_42 | 2순위 |
    | ``VOCABULARY_INLINE`` | V2 | vocabulary_30 / blank_phrase_31 | **1순위** |
    | ``GRAMMAR_SWAP`` | V3 | grammar_29 | 2순위 |
    | ``GRAMMAR_INLINE`` | V4 | grammar_29 | **1순위** |
    | ``BLANK_INFERENCE`` | V5 | blank_phrase_31 / blank_clause_32~34 | **1순위** |
    | ``TOPIC_MAIN_IDEA_SWAP`` | V6 | main_idea_22 / topic_23 / title_24 | **1순위** |
    | ``ORDER_SHUFFLE`` | V7 | paragraph_order_36 / _37 | **1순위** |
    | ``SENTENCE_INSERTION_SHIFT`` | V8 | sentence_insertion_38 / _39 | 2순위 |
    | ``IRRELEVANT_SENTENCE_INJECT`` | V9 | irrelevant_sentence_35 | 2순위 |
    | ``SUMMARY_BLANK_SWAP`` | V10 | summary_40 | 2순위 |

    Phase 3 진입 시 1순위 5개 (V2/V4/V5/V6/V7) 부터 LLM 변형 프롬프트 작성.

    Breaking change 주의 — v0.3 (~v0.10.1) 의 ``THEME_REWORD = "theme_reword"`` 는
    카탈로그 v0.4 의 V6 ``TOPIC_MAIN_IDEA_SWAP`` 으로 통합 (이전 enum value 는
    영속 데이터에서 사용된 적 없음 — 단순 교체).
    """

    ORIGINAL = "original"

    # V1~V10 (docs/variant-type-catalog.md v0.4 §3.2 정합)
    VOCABULARY_SWAP = "vocabulary_swap"  # V1
    VOCABULARY_INLINE = "vocabulary_inline"  # V2 — Gap A 어휘형 sub-form 변환
    GRAMMAR_SWAP = "grammar_swap"  # V3
    GRAMMAR_INLINE = "grammar_inline"  # V4 — Gap A 어법형 sub-form 변환
    BLANK_INFERENCE = "blank_inference"  # V5
    TOPIC_MAIN_IDEA_SWAP = "topic_main_idea_swap"  # V6 — THEME_REWORD 통합
    ORDER_SHUFFLE = "order_shuffle"  # V7
    SENTENCE_INSERTION_SHIFT = "sentence_insertion_shift"  # V8
    IRRELEVANT_SENTENCE_INJECT = "irrelevant_sentence_inject"  # V9
    SUMMARY_BLANK_SWAP = "summary_blank_swap"  # V10

    # Cross-type variant (카탈로그 v0.5 — 이종 유형 간 변환)
    CROSS_TYPE = "cross_type"


# ─── Choices / InlineChoice / ChoiceMatrix (Gap A / B sub-form) ─────────────
class ChoiceFormat(StrEnum):
    """선택지 형태 디스크리미네이터 (audit-review-domain §3.2 권고).

    v0.1 은 평탄화-우선 + 매트릭스-옵트인 구조:
      - ``FLAT``: ``choices: list[str]`` 만 사용 (기본). exam-generator 의 5개 원문자
        ``["①", "②", "③", "④", "⑤"]`` 케이스 + 요약문(40) 의 lossy 평탄화 케이스.
      - ``MATRIX_AB``: 2컬럼 (예: 요약문(40) ``(A) word1 …… (B) word2``).
      - ``MATRIX_ABC``: 3컬럼 (Gap B 본문 내장 (A)/(B)/(C) 매트릭스).
    """

    FLAT = "flat"
    MATRIX_AB = "matrix_AB"
    MATRIX_ABC = "matrix_ABC"


class ChoiceMatrix(BaseModel):
    """매트릭스 형태 선택지 (Gap B sub-form).

    ``ChoiceFormat == MATRIX_AB / MATRIX_ABC`` 일 때 ``Question.choice_matrix`` 에
    채운다. 평탄화 ``Question.choices`` 와의 관계: 평탄화는 보통 표면형 ("①", ...)
    유지, 매트릭스는 컬럼/행 구조 보존. 렌더러가 분기.
    """

    model_config = ConfigDict(extra="forbid")

    columns: list[str] = Field(
        ...,
        min_length=2,
        max_length=3,
        description="컬럼 라벨 (예: ['(A)', '(B)'] 또는 ['(A)', '(B)', '(C)']).",
    )
    rows: list[list[str]] = Field(
        ...,
        description="행별 셀. 각 행 길이는 ``columns`` 길이와 일치해야 함.",
    )

    @model_validator(mode="after")
    def _validate_row_widths(self) -> ChoiceMatrix:
        col_count = len(self.columns)
        for i, row in enumerate(self.rows):
            if len(row) != col_count:
                raise ValueError(f"row[{i}] 길이 {len(row)} 가 columns 길이 {col_count} 와 불일치.")
        return self


class InlineChoiceKind(StrEnum):
    """본문 내장 선택지의 출제 의도 (audit-review-domain §3.1 권고).

    같은 표면 형태라도 어휘형/어법형은 변별 포인트가 다르다 — 보강 메타.
    """

    VOCABULARY = "vocabulary"  # 어휘형
    GRAMMAR = "grammar"  # 어법형
    MIXED = "mixed"  # 혼합


class InlineChoice(BaseModel):
    """본문 내장형 선택지 1개 (Gap A sub-form).

    ``Question.inline_choices`` 에 N개 (보통 2~3개) 들어간다. 학생은 각 박스마다
    options 중 하나를 고른 후, 그 조합을 ``Question.choices`` (5지선다) 에서 매칭.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        ...,
        max_length=16,
        description="박스 라벨 (예: '(A)', '(B)', '(C)').",
    )
    options: list[str] = Field(
        ...,
        min_length=2,
        max_length=3,
        description="선택지 단어/구 리스트 (보통 2개, 어휘형은 3개도 가능).",
    )
    answer_index: int = Field(
        ...,
        ge=0,
        description="0-based 정답 위치 (``options`` 인덱스).",
    )
    position_marker: str | None = Field(
        default=None,
        description=(
            "본문 내 위치 식별자. 식별 방식은 ADR-0003 (Annotation span) 결정에 합류 "
            "예정 — v0.1 은 자유 문자열 placeholder."
        ),
    )
    kind: InlineChoiceKind = Field(
        default=InlineChoiceKind.MIXED,
        description="출제 의도 (어휘형/어법형/혼합).",
    )


# ─── SubQuestion / QuestionPlan (exam-generator 흡수) ─────────────────────
class SubQuestion(BaseModel):
    """장문 세트 (41-42, 43-45) 안의 부속 문항.

    exam-generator ``SubQuestion`` 1:1 흡수.
    """

    model_config = ConfigDict(extra="forbid")

    question_text: str = Field(..., description="문항 지시문.")
    choices: list[str] = Field(..., description="선택지.")
    answer: int = Field(..., ge=1, le=5, description="정답 인덱스 (1-based).")


class QuestionPlan(BaseModel):
    """LLM 자기 계획 메타 (exam-generator ``QuestionPlan`` 흡수).

    LLM 호출에서 passage 작성 전에 강제 채워지는 메타. parser/renderer 는 무시.
    영속화하되 도메인 출력에는 영향 없음 (audit Gap N).
    """

    model_config = ConfigDict(extra="forbid")

    topic_scope: str = Field(..., description="이 글이 다룰 주제 한 문장 (영어).")
    thesis_sentence: str = Field(..., description="이 글이 도달할 결론 한 문장 (영어).")
    structure_plan: str = Field(..., description="도입-전개-결론 구조 계획.")
    target_word_count: int = Field(
        ...,
        ge=50,
        le=400,
        description="목표 영어 단어 수 (자기 인식용).",
    )


# ─── Question (메인 모델) ────────────────────────────────────────────────
class Question(WorkspaceScopedEntity):
    """문제 1건 (원본 또는 변형).

    Pydantic v2 + WorkspaceScopedEntity 베이스. ``passage_id`` 로 Passage 참조.

    변형 vs 원본 (CLAUDE.md §6.2):
      - ``variant_kind == ORIGINAL`` 이면 입력에서 추출된 원본 — ``derived_from_question_id``
        는 None.
      - ``variant_kind != ORIGINAL`` 이면 변형 — ``derived_from_question_id`` 가 NOT NULL
        (validator 강제).

    Sub-form 필드 (CLAUDE.md §6.2 + audit Gap A/B):
      - ``inline_choices``: 본문 내장형 선택지 (Gap A).
      - ``choice_format`` + ``choice_matrix``: 매트릭스 선택지 (Gap B).
    """

    # ─── 출처 / 분류 ────────────────────────────────────────────────────
    passage_id: EntityId = Field(
        ...,
        description="참조 Passage ID (FK → passages.id).",
    )
    type: QuestionType = Field(
        ...,
        description=(
            "exam-generator 24개 활성 유형 중 하나 (CLAUDE.md §6.2 — 변형도 같은 type "
            "안에서 ``variant_kind`` 로 표현). 새 type 은 도입하지 않는다."
        ),
    )
    variant_kind: VariantKind = Field(
        default=VariantKind.ORIGINAL,
        description=(
            "변형 유형 (default = ORIGINAL). variant_kind != ORIGINAL 이면 "
            "``derived_from_question_id`` 가 NOT NULL."
        ),
    )
    derived_from_question_id: EntityId | None = Field(
        default=None,
        description=(
            "원본 Question ID — ``variant_kind != ORIGINAL`` 일 때 NOT NULL "
            "(model_validator 가 강제)."
        ),
    )

    # ─── 시험지 메타 ─────────────────────────────────────────────────────
    number: int | None = Field(
        default=None,
        ge=1,
        le=45,
        description="시험지 안에서의 번호 (parser 추출 실패 시 None).",
    )
    points: float | None = Field(
        default=None,
        description="배점.",
    )
    group_label: str | None = Field(
        default=None,
        description="동일 대분류 연속 출제 시 시스템이 부착하는 그룹 라벨.",
    )

    # ─── 문항 본체 ───────────────────────────────────────────────────────
    question_text: str = Field(
        default="",
        description="문항 지시문.",
    )
    choices: list[str] = Field(
        default_factory=list,
        description=(
            "5지선다 선택지 (기본은 평탄). 평탄 list[str] 케이스는 그대로, 매트릭스 "
            "케이스는 ``choice_format`` + ``choice_matrix`` 에 추가 표현."
        ),
    )
    choice_format: ChoiceFormat = Field(
        default=ChoiceFormat.FLAT,
        description="선택지 표면 형태 디스크리미네이터 (audit-review-domain §3.2).",
    )
    choice_matrix: ChoiceMatrix | None = Field(
        default=None,
        description=(
            "매트릭스 선택지 (Gap B). ``choice_format != FLAT`` 일 때 NOT NULL "
            "(model_validator 가 강제)."
        ),
    )
    answer: int = Field(
        default=1,
        ge=1,
        le=5,
        description="정답 인덱스 (1-based, 5지선다 기준).",
    )
    explanation: str = Field(
        default="",
        description="해설.",
    )

    # ─── 유형별 부가 필드 (exam-generator 1:1 흡수) ───────────────────────
    given_sentence: str | None = Field(
        default=None,
        description="문장삽입 (38, 39) 의 주어진 문장.",
    )
    sub_passages: list[list[str]] | None = Field(
        default=None,
        description="순서배열(36, 37) (A)/(B)/(C) 단락 / 장문독해(43-45) (B)/(C)/(D).",
    )
    summary: str | None = Field(
        default=None,
        description="요약문(40) 의 요약 문장 ((A) ______ ... (B) ______).",
    )
    sub_questions: list[SubQuestion] | None = Field(
        default=None,
        description="장문 세트(41-42, 43-45) 안의 부속 문항.",
    )

    # ─── 본문 내장형 sub-form (Gap A) ────────────────────────────────────
    inline_choices: list[InlineChoice] | None = Field(
        default=None,
        description=(
            "본문 내장형 선택지 (Gap A — 와이프의 1차 변형 유형). 와이프 본인 확인 "
            "전 1차 안 — 작업 #5 후속 PR 에서 보강 가능."
        ),
    )

    # ─── LLM 자가검증 / 자가계획 메타 (영속화, 렌더러 무시) ──────────────
    plan: QuestionPlan | None = Field(
        default=None,
        description="LLM 자기 계획 메타 (audit Gap N 권고 — 영속화하되 렌더러 무시).",
    )
    naturalness_check: (
        Literal[
            "OK",
            "REWRITE_SCOPE_TOO_BROAD",
            "REWRITE_ABRUPT_ENDING",
            "REWRITE_REPETITIVE",
            "REWRITE_FORCED_BREVITY",
        ]
        | None
    ) = Field(
        default=None,
        description="LLM 자가검증 결과 (exam-generator 1:1 흡수).",
    )
    referent_assignments: list[str] | None = Field(
        default=None,
        description=("장문독해(43-45) 전용. (a)~(e) 5개 라벨이 가리키는 인물명 — 4:1 분포 강제."),
    )

    # ─── parser 메타 (LLM/renderer 무시 가능) ──────────────────────────
    has_passage_box: bool = Field(default=False)
    has_inline_markers: bool = Field(default=False)
    has_blanks: bool = Field(default=False)
    raw_paragraphs: list[str] = Field(default_factory=list)
    paragraph_indices: list[int] = Field(default_factory=list)

    # ─── 변형 전용 메타 (ADR-0017 D2-c JSONB) ────────────────────────────────
    variant_metadata: dict[str, Any] | None = Field(
        default=None,
        description=(
            "변형만의 추가 메타 (JSONB). variant_kind != ORIGINAL 일 때 의미 있는 값. "
            "원본 행에서는 항상 None. "
            "v0.1 구조 미정 — Phase 3 첫 변형 생성 PR 에서 보강. "
            "예: {'llm_candidate_words': [...], 'generation_attempt': 3}. "
            "물리 매핑 정책 (ADR-0017 권장 안 (a)): 단일 questions 테이블, "
            "derived_from_question_id self-FK NULLABLE, variant_metadata JSONB NULLABLE. "
            "variant 의 variant 허용 — derived_from chain 은 depth 5 제한 (application 레이어). "
        ),
    )

    # ─── qa-validator 메타 (Phase 3 — audit-review-domain §4.1) ────────
    uniqueness_validated: bool = Field(
        default=False,
        description=(
            "qa-validator 가 정답 유일성 검증을 통과했는지 (Phase 3 활성). v0.1 은 "
            "자리만 — 기본 False. "
            "ADR-0017 D3-c 하이브리드: 본 필드는 최신 상태 캐시, "
            "history 는 QAValidationResult 테이블 (shared/schemas/qa_validation_result.py)."
        ),
    )
    uniqueness_validator_note: str | None = Field(
        default=None,
        description="qa-validator 의 검증 메모 (실패 사유 등). 최신 검증 결과 캐시.",
    )

    # ─── 검증 ─────────────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _validate_variant_consistency(self) -> Question:
        """``variant_kind`` 와 ``derived_from_question_id`` 정합성 강제.

        - ``ORIGINAL`` 이면 ``derived_from_question_id`` 는 None 이어야 함.
        - ``ORIGINAL`` 이 아니면 ``derived_from_question_id`` 가 NOT NULL 이어야 함.
        """
        if self.variant_kind == VariantKind.ORIGINAL:
            if self.derived_from_question_id is not None:
                raise ValueError(
                    "variant_kind == ORIGINAL 일 때 derived_from_question_id 는 None 이어야 한다."
                )
        else:
            if self.derived_from_question_id is None:
                raise ValueError(
                    "variant_kind != ORIGINAL 일 때 derived_from_question_id 는 "
                    "NOT NULL 이어야 한다."
                )
        return self

    @model_validator(mode="after")
    def _validate_choice_format_matrix(self) -> Question:
        """``choice_format`` 과 ``choice_matrix`` 정합성 강제.

        - ``FLAT`` 이면 ``choice_matrix`` 는 None.
        - ``MATRIX_*`` 이면 ``choice_matrix`` 가 NOT NULL.
        """
        if self.choice_format == ChoiceFormat.FLAT:
            if self.choice_matrix is not None:
                raise ValueError("choice_format == FLAT 일 때 choice_matrix 는 None 이어야 한다.")
        else:
            if self.choice_matrix is None:
                raise ValueError(
                    f"choice_format == {self.choice_format} 일 때 choice_matrix 는 "
                    "NOT NULL 이어야 한다."
                )
        return self
