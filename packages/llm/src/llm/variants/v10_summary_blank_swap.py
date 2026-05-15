"""V10 summary_blank_swap — 요약문 (A)/(B) 이중 빈칸 + 5개 매트릭스 선택지 (Phase 3, 카탈로그 v0.4 §V10).

CLAUDE.md §8.3 강제:
  직접 Anthropic SDK 호출 금지. 모든 LLM 호출은 StructuredLLMClient 를 통한다.

ADR-0013 augment 패턴 준수:
  - sentinel UUID 채움 → 라우트가 실제 ID 주입.
  - PromptSpec 을 통한 프롬프트 로딩.
  - Pydantic 모델로 structured output 검증.

변형 특성 (augment 와의 차이):
  - augment: 기존 row UPDATE (mode 분기).
  - variant: 항상 신규 Question row INSERT (mode 개념 없음).

카탈로그 v0.4 §V10 검증 기준:
  - (A)/(B) 각각 정답 유일성 — 정답 쌍이 유일하고, swap/wrong_a/wrong_b/both_wrong 오답이 명확히 틀려야 함.
  - 요약이 본문 thesis 를 정확히 압축 — verbatim lift 금지, synthesis 강제.
  - summary_text 에 `(A) ______` 와 `(B) ______` 마커가 정확히 존재.
  - distractor_pattern 4개 패턴 완전 집합 (swap / wrong_a / wrong_b / both_wrong).

V6 패턴 + V2 의 매트릭스 선택지 패턴 결합.

에러 처리:
  - choices 5개 미만/초과 → LLMSchemaValidationError (Pydantic validator 강제).
  - choice_matrix rows 5개 미만/초과 → LLMSchemaValidationError.
  - distractor_pattern 'correct' 위치 불일치 → LLMSchemaValidationError.
  - distractor_pattern 4개 패턴 미완전 → LLMSchemaValidationError.
  - summary_text 에 (A)/(B) 마커 미존재 → LLMSchemaValidationError.
  - blank_a_word / blank_b_word 가 choice_matrix 정답 row 와 불일치 → LLMSchemaValidationError.
  - LLM 호출 실패 → llm.errors 계층 그대로 전파.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, model_validator

from llm.client import StructuredLLMClient
from llm.prompt import PromptSpec
from shared.schemas.question import (
    ChoiceFormat,
    ChoiceMatrix,
    Question,
    QuestionType,
    VariantKind,
)

# ─── sentinel UUID (ADR-0003 §D-3.6) ─────────────────────────────────────────
SENTINEL_UUID: uuid.UUID = uuid.UUID(int=0)

# ─── 프롬프트 템플릿 ID ─────────────────────────────────────────────────────
V10_PROMPT_ID = "variant-summary-blank-swap-v0"

# V10 적용 가능 QuestionType (카탈로그 v0.4 §V10 — summary_40 만)
V10_APPLICABLE_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.SUMMARY_40,
    }
)

# distractor_pattern 허용 값 (카탈로그 v0.4 §V10)
_VALID_DISTRACTOR_PATTERNS: frozenset[str] = frozenset(
    {"correct", "swap", "wrong_a", "wrong_b", "both_wrong"}
)

# 비-correct distractor_pattern 4가지 (모두 존재해야 함)
_REQUIRED_DISTRACTOR_PATTERNS: frozenset[str] = frozenset(
    {"swap", "wrong_a", "wrong_b", "both_wrong"}
)

# (A)/(B) 마커 — summary_text 내 존재 강제
_BLANK_A_MARKER = "(A) ______"
_BLANK_B_MARKER = "(B) ______"


# ─── LLM output schema ────────────────────────────────────────────────────────


class V10ChoiceMatrix(BaseModel):
    """V10 LLM 출력 안의 choice_matrix.

    shared.schemas.question.ChoiceMatrix 와 1:1 대응하나 extra='forbid' 없음
    (Gemini API additionalProperties: false 거절 이슈 방지).

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    columns: list[str] = Field(
        ...,
        description="컬럼 라벨 — 반드시 ['(A)', '(B)'].",
    )
    rows: list[list[str]] = Field(
        ...,
        description="행별 셀. 각 행은 [wordA, wordB] 2개.",
    )

    @model_validator(mode="after")
    def _validate_structure(self) -> V10ChoiceMatrix:
        if len(self.columns) != 2:
            raise ValueError(
                f"columns 는 정확히 2개 ['(A)', '(B)'] 여야 한다. 현재: {self.columns}."
            )
        if len(self.rows) != 5:
            raise ValueError(
                f"rows 는 정확히 5개여야 한다. 현재: {len(self.rows)}개."
            )
        for i, row in enumerate(self.rows):
            if len(row) != 2:
                raise ValueError(
                    f"row[{i}] 는 정확히 2개 셀 [wordA, wordB] 이어야 한다. "
                    f"현재: {len(row)}개."
                )
        return self


class V10Output(BaseModel):
    """V10 LLM structured output schema.

    docs/prompts/variant-summary-blank-swap-v0.md 출력 schema 와 1:1 대응.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    summary_text: str = Field(
        ...,
        description=(
            "본문 thesis 를 압축한 1문장 요약. "
            "'(A) ______' 와 '(B) ______' 마커를 각각 1개씩 포함해야 한다."
        ),
    )
    blank_a_word: str = Field(
        ...,
        description="(A) 빈칸의 정답 단어 (단일 단어).",
    )
    blank_b_word: str = Field(
        ...,
        description="(B) 빈칸의 정답 단어 (단일 단어).",
    )
    choices: list[str] = Field(
        ...,
        description=(
            "5개 평탄 선택지 (표면형). 형식: '(A) wordA …… (B) wordB'. "
            "정답 인덱스 기준 순서."
        ),
    )
    choice_matrix: V10ChoiceMatrix = Field(
        ...,
        description="매트릭스 선택지 — columns=['(A)', '(B)'], rows 5개.",
    )
    answer: int = Field(
        ...,
        ge=1,
        le=5,
        description="정답 인덱스 (1-based, 1~5).",
    )
    explanation: str = Field(
        ...,
        description="정답 사유 (한국어, 2~4문장).",
    )
    distractor_pattern: list[str] = Field(
        ...,
        description=(
            "5개 선택지 각각의 패턴 라벨. "
            "answer-1 index 는 반드시 'correct'. "
            "나머지 4개는 swap / wrong_a / wrong_b / both_wrong (각각 1개씩)."
        ),
    )

    @model_validator(mode="after")
    def _validate_summary_markers(self) -> V10Output:
        """summary_text 에 (A)/(B) 마커가 정확히 존재하는지 검증."""
        if _BLANK_A_MARKER not in self.summary_text:
            raise ValueError(
                f"summary_text 에 '{_BLANK_A_MARKER}' 마커가 없다. "
                f"현재 summary_text: {self.summary_text!r}."
            )
        if _BLANK_B_MARKER not in self.summary_text:
            raise ValueError(
                f"summary_text 에 '{_BLANK_B_MARKER}' 마커가 없다. "
                f"현재 summary_text: {self.summary_text!r}."
            )
        a_pos = self.summary_text.index(_BLANK_A_MARKER)
        b_pos = self.summary_text.index(_BLANK_B_MARKER)
        if a_pos >= b_pos:
            raise ValueError(
                "(A) ______ 마커가 (B) ______ 마커보다 앞에 나타나야 한다. "
                f"현재 a_pos={a_pos}, b_pos={b_pos}."
            )
        return self

    @model_validator(mode="after")
    def _validate_choices_length(self) -> V10Output:
        if len(self.choices) != 5:
            raise ValueError(
                f"choices 는 정확히 5개여야 한다. 현재: {len(self.choices)}개."
            )
        return self

    @model_validator(mode="after")
    def _validate_distractor_pattern(self) -> V10Output:
        """distractor_pattern 완전성 + 'correct' 위치 검증."""
        if len(self.distractor_pattern) != 5:
            raise ValueError(
                f"distractor_pattern 은 정확히 5개여야 한다. "
                f"현재: {len(self.distractor_pattern)}개."
            )
        for pattern in self.distractor_pattern:
            if pattern not in _VALID_DISTRACTOR_PATTERNS:
                raise ValueError(
                    f"허용되지 않은 distractor_pattern 값: '{pattern}'. "
                    f"허용 값: {sorted(_VALID_DISTRACTOR_PATTERNS)}."
                )
        # 'correct' 는 정확히 1개, answer-1 위치
        correct_count = self.distractor_pattern.count("correct")
        if correct_count != 1:
            raise ValueError(
                f"distractor_pattern 안에 'correct' 가 정확히 1개여야 한다. "
                f"현재: {correct_count}개."
            )
        expected_correct_idx = self.answer - 1
        actual_correct_idx = self.distractor_pattern.index("correct")
        if expected_correct_idx != actual_correct_idx:
            raise ValueError(
                f"answer={self.answer} (0-based index={expected_correct_idx}) 과 "
                f"distractor_pattern 의 'correct' 위치(index={actual_correct_idx}) 가 불일치."
            )
        # swap / wrong_a / wrong_b / both_wrong 모두 존재해야 함
        actual_patterns = set(self.distractor_pattern) - {"correct"}
        missing = _REQUIRED_DISTRACTOR_PATTERNS - actual_patterns
        if missing:
            raise ValueError(
                f"distractor_pattern 에 필수 패턴이 누락됐다: {sorted(missing)}. "
                "swap / wrong_a / wrong_b / both_wrong 4개 모두 존재해야 한다."
            )
        return self

    @model_validator(mode="after")
    def _validate_blank_words_match_matrix(self) -> V10Output:
        """blank_a_word / blank_b_word 가 choice_matrix 정답 row 와 일치하는지 검증."""
        correct_row = self.choice_matrix.rows[self.answer - 1]
        if correct_row[0] != self.blank_a_word:
            raise ValueError(
                f"blank_a_word='{self.blank_a_word}' 가 "
                f"choice_matrix 정답 row[0]='{correct_row[0]}' 와 불일치."
            )
        if correct_row[1] != self.blank_b_word:
            raise ValueError(
                f"blank_b_word='{self.blank_b_word}' 가 "
                f"choice_matrix 정답 row[1]='{correct_row[1]}' 와 불일치."
            )
        return self


# ─── 어댑터 함수 ──────────────────────────────────────────────────────────────


async def generate_v10_variant(
    *,
    passage_text: str,
    original_question: Question,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = V10_PROMPT_ID,
) -> Question:
    """V10 summary_blank_swap 변형 생성.

    원본 Passage.body_text 를 기반으로 요약 1문장 + (A)/(B) 이중 빈칸 +
    5개 매트릭스 선택지를 생성하고, sentinel UUID 가 채워진 신규 Question 을 반환한다.
    라우트가 실제 ID 를 주입.

    ADR-0013 augment 패턴:
      - sentinel UUID 채움 → 라우트가 model_copy 로 실제 tenant_id / workspace_id / id 교체.
      - variant 는 항상 신규 row — mode 정책 없음.

    Args:
        passage_text: 원본 Passage.body_text (LLM 입력).
        original_question: 원본 Question (type 확인 + derived_from_question_id 설정).
        llm_client: StructuredLLMClient 구현체 (CLAUDE.md §8.3 강제).
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``variant-summary-blank-swap-v0``.

    Returns:
        sentinel UUID 가 채워진 신규 Question (variant_kind=SUMMARY_BLANK_SWAP).
        라우트가 tenant_id / workspace_id / passage_id / derived_from_question_id 를
        model_copy 로 주입한다.

    Raises:
        ValueError: original_question.type 이 V10 비적용 type (V10_APPLICABLE_TYPES 외).
        LLMSchemaValidationError: structured output 검증 실패 (재시도 소진 후).
        LLMTimeoutError: 타임아웃 (재시도 소진 후).
        LLMNetworkError / PermanentLLMError: LLM 호출 실패.
    """
    if original_question.type not in V10_APPLICABLE_TYPES:
        raise ValueError(
            f"V10 변형은 summary_40 type 에만 적용 가능합니다. "
            f"현재 type: {original_question.type}."
        )

    # 원본 요약문 직렬화 — 다양성 회피용 입력 (없으면 "(none)")
    original_summary = original_question.summary or "(none)"

    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={
            "passage_text": passage_text,
            "original_summary": original_summary,
        },
    )

    result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=V10Output,
        purpose="variant_v10_summary_blank_swap",
        tenant_id=original_question.tenant_id,
        workspace_id=original_question.workspace_id,
    )

    llm_out = result.data

    # V10ChoiceMatrix → shared.schemas.question.ChoiceMatrix 변환
    choice_matrix = ChoiceMatrix(
        columns=llm_out.choice_matrix.columns,
        rows=llm_out.choice_matrix.rows,
    )

    # LLM 출력 → Question 도메인 모델 변환
    # sentinel UUID 채움 — 라우트가 model_copy 로 실제 ID 주입 (ADR-0003 §D-3.6)
    return Question(
        id=SENTINEL_UUID,
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        passage_id=SENTINEL_UUID,
        derived_from_question_id=SENTINEL_UUID,  # 라우트가 실제 question_id 로 교체
        type=QuestionType.SUMMARY_40,
        variant_kind=VariantKind.SUMMARY_BLANK_SWAP,
        question_text=(
            original_question.question_text
            or "다음 글의 내용을 한 문장으로 요약하고자 한다. 빈칸 (A), (B)에 들어갈 말로 가장 적절한 것은?"
        ),
        summary=llm_out.summary_text,
        choices=llm_out.choices,
        choice_format=ChoiceFormat.MATRIX_AB,
        choice_matrix=choice_matrix,
        answer=llm_out.answer,
        explanation=llm_out.explanation,
        variant_metadata={
            "summary_text": llm_out.summary_text,
            "blank_a_word": llm_out.blank_a_word,
            "blank_b_word": llm_out.blank_b_word,
        },
    )
