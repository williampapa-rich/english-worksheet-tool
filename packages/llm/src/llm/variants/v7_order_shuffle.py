"""V7 order_shuffle — 순서배열 변형 (Phase 3, 카탈로그 v0.4 §V7).

CLAUDE.md §8.3 강제:
  직접 Anthropic SDK 호출 금지. 모든 LLM 호출은 StructuredLLMClient 를 통한다.

ADR-0013 augment 패턴 준수:
  - sentinel UUID 채움 → 라우트가 실제 ID 주입.
  - PromptSpec 을 통한 프롬프트 로딩.
  - Pydantic 모델로 structured output 검증.

변형 특성 (V6 와의 차이):
  - 입력: 원본 Passage (body_text).
  - 출력: sub_passages 채움 (A/B/C 단락별 문장 리스트) + 순서 조합 선택지 5개.
  - choices 는 "(A) - (B) - (C)" 형식 문자열 (번호 기반 아님).

카탈로그 v0.4 §V7 검증 기준:
  - 단락 분할이 의미 단위 (문장 중간 자르기 금지 → 각 inner list ≥ 1개 문장).
  - 응결 단서 (접속사 / 대명사 / 정관사) 충분 → split_categories ≥ 1개.
  - 단락 길이 균형 → 각 sub_passage 길이 검증.
  - 정답 분포 편향 회피 (exam-generator Hotfix 17-2 정합) — answer 1~5 범위.

에러 처리:
  - sub_passages 가 3개 미만 → LLMSchemaValidationError (Pydantic validator 강제).
  - choices 가 5개 미만 → LLMSchemaValidationError.
  - choice_pattern 5개 미만 / "correct" 불일치 → LLMSchemaValidationError.
  - answer 범위 (1~5) 벗어남 → LLMSchemaValidationError.
  - choices 형식 "(X) - (Y) - (Z)" 미준수 → LLMSchemaValidationError.
  - LLM 호출 실패 → llm.errors 계층 그대로 전파.
"""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field, model_validator

from llm.client import StructuredLLMClient
from llm.prompt import PromptSpec
from shared.schemas.question import (
    Question,
    QuestionType,
    VariantKind,
)

# ─── sentinel UUID (ADR-0003 §D-3.6) ─────────────────────────────────────────
SENTINEL_UUID: uuid.UUID = uuid.UUID(int=0)

# ─── 프롬프트 템플릿 ID ─────────────────────────────────────────────────────
V7_PROMPT_ID = "variant-order-shuffle-v0"

# V7 적용 가능 QuestionType (카탈로그 v0.4 §V7 — 확실)
V7_APPLICABLE_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.ORDER_36,
        QuestionType.ORDER_37,
    }
)

# choices 형식 검증 패턴 "(A) - (B) - (C)" 등
_CHOICE_LABEL_PATTERN: re.Pattern[str] = re.compile(
    r"^\([ABC]\) - \([ABC]\) - \([ABC]\)$"
)

# variant_metadata.split_categories 허용 값
_VALID_SPLIT_CATEGORIES: frozenset[str] = frozenset(
    {
        "conjunction",
        "anaphoric_pronoun",
        "definite_article",
        "lexical_cohesion",
    }
)


# ─── LLM output schema ────────────────────────────────────────────────────────


class V7VariantMetadata(BaseModel):
    """variant_metadata JSONB 구조 (V7 전용).

    카탈로그 v0.4 §V7 검증 기준 + V7 특수 필드.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    intro_paragraph: str = Field(
        ...,
        description="도입 단락 텍스트 (주어진 글 — 순서배열 문제의 고정 파트).",
    )
    split_categories: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "사용된 응결 단서 카테고리 리스트. "
            "허용 값: conjunction / anaphoric_pronoun / definite_article / lexical_cohesion."
        ),
    )
    choice_pattern: list[str] = Field(
        ...,
        description=(
            "5개 선택지 각각의 패턴 라벨. "
            "answer-1 index 는 반드시 'correct'. "
            "나머지 4개는 'distractor'."
        ),
    )

    @model_validator(mode="after")
    def _validate_split_categories(self) -> V7VariantMetadata:
        for cat in self.split_categories:
            if cat not in _VALID_SPLIT_CATEGORIES:
                raise ValueError(
                    f"허용되지 않은 split_categories 값: '{cat}'. "
                    f"허용 값: {sorted(_VALID_SPLIT_CATEGORIES)}."
                )
        return self

    @model_validator(mode="after")
    def _validate_choice_pattern(self) -> V7VariantMetadata:
        if len(self.choice_pattern) != 5:
            raise ValueError(
                f"choice_pattern 은 정확히 5개여야 한다. 현재: {len(self.choice_pattern)}개."
            )
        correct_count = self.choice_pattern.count("correct")
        if correct_count != 1:
            raise ValueError(
                f"choice_pattern 안에 'correct' 가 정확히 1개여야 한다. 현재: {correct_count}개."
            )
        for pattern in self.choice_pattern:
            if pattern not in {"correct", "distractor"}:
                raise ValueError(
                    f"허용되지 않은 choice_pattern 값: '{pattern}'. "
                    "허용 값: 'correct', 'distractor'."
                )
        return self


class V7Output(BaseModel):
    """V7 LLM structured output schema.

    docs/prompts/variant-order-shuffle-v0.md 출력 schema 와 1:1 대응.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    intro_paragraph: str = Field(
        ...,
        description="도입 단락 텍스트 (주어진 글).",
    )
    sub_passages: list[list[str]] = Field(
        ...,
        description="(A)/(B)/(C) 3개 단락 각각의 문장 리스트. 정확히 3개 inner list.",
    )
    choices: list[str] = Field(
        ...,
        description="5개 순서 조합 선택지. 각 문자열 형식: '(X) - (Y) - (Z)'.",
    )
    answer: int = Field(
        ...,
        ge=1,
        le=5,
        description="정답 인덱스 (1-based, 1~5).",
    )
    explanation: str = Field(
        ...,
        description="정답 사유 (한국어, 2~4문장). 응결 단서를 구체적으로 언급.",
    )
    variant_metadata: V7VariantMetadata = Field(
        ...,
        description="V7 전용 메타 (intro_paragraph + split_categories + choice_pattern).",
    )

    @model_validator(mode="after")
    def _validate_sub_passages_count(self) -> V7Output:
        if len(self.sub_passages) != 3:
            raise ValueError(
                f"sub_passages 는 정확히 3개 inner list 여야 한다. 현재: {len(self.sub_passages)}개."
            )
        return self

    @model_validator(mode="after")
    def _validate_sub_passages_non_empty(self) -> V7Output:
        for i, para in enumerate(self.sub_passages):
            if len(para) == 0:
                raise ValueError(
                    f"sub_passages[{i}] 가 비어 있다. 각 단락은 최소 1개 문장이어야 한다."
                )
        return self

    @model_validator(mode="after")
    def _validate_choices_length(self) -> V7Output:
        if len(self.choices) != 5:
            raise ValueError(
                f"choices 는 정확히 5개여야 한다. 현재: {len(self.choices)}개."
            )
        return self

    @model_validator(mode="after")
    def _validate_choices_format(self) -> V7Output:
        for i, choice in enumerate(self.choices):
            if not _CHOICE_LABEL_PATTERN.match(choice):
                raise ValueError(
                    f"choices[{i}] 형식 오류: '{choice}'. "
                    "올바른 형식 예시: '(A) - (B) - (C)'."
                )
        return self

    @model_validator(mode="after")
    def _validate_choices_unique(self) -> V7Output:
        if len(set(self.choices)) != len(self.choices):
            raise ValueError("choices 5개가 모두 고유해야 한다 — 중복 순서 조합 금지.")
        return self

    @model_validator(mode="after")
    def _validate_choice_pattern_answer_alignment(self) -> V7Output:
        """answer index 와 choice_pattern 의 'correct' 위치가 일치하는지 검증."""
        pattern = self.variant_metadata.choice_pattern
        expected_correct_idx = self.answer - 1
        actual_correct_idx = pattern.index("correct")
        if expected_correct_idx != actual_correct_idx:
            raise ValueError(
                f"answer={self.answer} (0-based index={expected_correct_idx}) 과 "
                f"choice_pattern 의 'correct' 위치(index={actual_correct_idx}) 가 불일치."
            )
        return self


# ─── 어댑터 함수 ──────────────────────────────────────────────────────────────


async def generate_v7_variant(
    *,
    passage_text: str,
    original_question: Question,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = V7_PROMPT_ID,
) -> Question:
    """V7 order_shuffle 변형 생성.

    원본 Passage.body_text 를 도입 1단락 + (A)/(B)/(C) 3단락으로 분할하고
    5개 순서 조합 선택지를 생성한다. sentinel UUID 가 채워진 신규 Question 반환.
    라우트가 실제 ID 를 주입.

    ADR-0013 augment 패턴:
      - sentinel UUID 채움 → 라우트가 model_copy 로 실제 tenant_id / workspace_id / id 교체.
      - variant 는 항상 신규 row — mode 정책 없음.

    Args:
        passage_text: 원본 Passage.body_text (LLM 입력).
        original_question: 원본 Question (type 확인 + derived_from_question_id 설정).
        llm_client: StructuredLLMClient 구현체 (CLAUDE.md §8.3 강제).
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``variant-order-shuffle-v0``.

    Returns:
        sentinel UUID 가 채워진 신규 Question (variant_kind=ORDER_SHUFFLE).
        sub_passages 에 (A)/(B)/(C) 단락별 문장 리스트가 채워진다.
        choices 에 5개 순서 조합 문자열 (예: "(A) - (B) - (C)") 이 채워진다.
        라우트가 tenant_id / workspace_id / passage_id / derived_from_question_id 를
        model_copy 로 주입한다.

    Raises:
        ValueError: original_question.type 이 V7 비적용 type (V7_APPLICABLE_TYPES 외).
        LLMSchemaValidationError: structured output 검증 실패 (재시도 소진 후).
        LLMTimeoutError: 타임아웃 (재시도 소진 후).
        LLMNetworkError / PermanentLLMError: LLM 호출 실패.
    """
    if original_question.type not in V7_APPLICABLE_TYPES:
        raise ValueError(
            f"V7 변형은 paragraph_order_36 / paragraph_order_37 type 에만 적용 가능합니다. "
            f"현재 type: {original_question.type}."
        )

    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={
            "passage_text": passage_text,
            "question_type": str(original_question.type),
        },
    )

    result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=V7Output,
        purpose="variant_v7_order_shuffle",
        tenant_id=original_question.tenant_id,
        workspace_id=original_question.workspace_id,
    )

    llm_out = result.data

    # LLM 출력 → Question 도메인 모델 변환
    # sentinel UUID 채움 — 라우트가 model_copy 로 실제 ID 주입 (ADR-0003 §D-3.6)
    return Question(
        id=SENTINEL_UUID,
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        passage_id=SENTINEL_UUID,
        derived_from_question_id=SENTINEL_UUID,  # 라우트가 실제 question_id 로 교체
        type=original_question.type,
        variant_kind=VariantKind.ORDER_SHUFFLE,
        question_text=original_question.question_text,
        choices=llm_out.choices,
        answer=llm_out.answer,
        explanation=llm_out.explanation,
        sub_passages=llm_out.sub_passages,
        variant_metadata=llm_out.variant_metadata.model_dump(),
    )
