"""V5 blank_inference — 빈칸 추론 변형 (Phase 3, 카탈로그 v0.4 §V5).

CLAUDE.md §8.3 강제:
  직접 Anthropic SDK 호출 금지. 모든 LLM 호출은 StructuredLLMClient 를 통한다.

ADR-0013 augment 패턴 준수:
  - sentinel UUID 채움 → 라우트가 실제 ID 주입.
  - PromptSpec 을 통한 프롬프트 로딩.
  - Pydantic 모델로 structured output 검증.

변형 특성 (V6 와의 차이):
  - V6: 본문 유지 + 선택지만 갱신 (body_with_blank 없음).
  - V5: thesis 핵심 어구/절을 `______` 로 가린 body_with_blank 추가 생성.
  - variant_metadata 에 blank_position [start, end] (char offset) 추가.

카탈로그 v0.4 §V5 검증 기준:
  - 빈칸 위치가 본문 thesis 핵심.
  - 정답이 본문 다른 곳에 그대로 등장 금지 (literal repetition 회피).
  - 오답 4개 패턴 다양성 (too-narrow / too-broad / opposite-conclusion / plausible-unrelated).

에러 처리:
  - choices 5개 미만 → LLMSchemaValidationError (Pydantic validator 강제).
  - answer 범위 (1~5) 벗어남 → LLMSchemaValidationError.
  - choice_pattern 5개 미만 / "correct" 불일치 → LLMSchemaValidationError.
  - body_with_blank 에 `______` 없음 → LLMSchemaValidationError.
  - blank_position 길이 불일치 → LLMSchemaValidationError.
  - LLM 호출 실패 → llm.errors 계층 그대로 전파.
"""

from __future__ import annotations

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
V5_PROMPT_ID = "variant-blank-inference-v0"

# V5 적용 가능 QuestionType (카탈로그 v0.4 §V5 — 확실)
V5_APPLICABLE_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.BLANK_PHRASE_31,
        QuestionType.BLANK_CLAUSE_32,
        QuestionType.BLANK_CLAUSE_33,
        QuestionType.BLANK_CLAUSE_34,
    }
)

# variant_metadata.choice_pattern 허용 값
_VALID_CHOICE_PATTERNS: frozenset[str] = frozenset(
    {"correct", "too-narrow", "too-broad", "opposite-conclusion", "plausible-unrelated"}
)

# 빈칸 표기 (6개 언더스코어 — 수능 표준)
_BLANK_MARKER = "______"


# ─── LLM output schema ────────────────────────────────────────────────────────


class V5VariantMetadata(BaseModel):
    """variant_metadata JSONB 구조 (V5 전용).

    카탈로그 v0.4 §V5 검증 기준 + ADR-0017 D2-c 결정 사항.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
        LLM 이 추가 필드를 반환해도 도메인 변환 시 필요한 필드만 사용.
    """

    sub_type: str = Field(
        ...,
        description=(
            "문제 sub-type 식별자. "
            "'blank_phrase_31' | 'blank_clause_32' | 'blank_clause_33' | 'blank_clause_34' 중 하나."
        ),
    )
    blank_position: list[int] = Field(
        ...,
        description=(
            "빈칸 위치 [start, end] (0-based, end exclusive). "
            "원본 joined passage text 기준 character offset."
        ),
    )
    choice_pattern: list[str] = Field(
        ...,
        description=(
            "5개 선택지 각각의 패턴 라벨. "
            "answer-1 index 는 반드시 'correct'. "
            "나머지 4개는 too-narrow / too-broad / opposite-conclusion / plausible-unrelated."
        ),
    )

    @model_validator(mode="after")
    def _validate_blank_position(self) -> V5VariantMetadata:
        if len(self.blank_position) != 2:
            raise ValueError(
                f"blank_position 은 정확히 [start, end] 2개 정수여야 한다. "
                f"현재: {len(self.blank_position)}개."
            )
        start, end = self.blank_position
        if start < 0:
            raise ValueError(f"blank_position[0] (start) 은 0 이상이어야 한다. 현재: {start}.")
        if end <= start:
            raise ValueError(
                f"blank_position[1] (end) 은 start({start}) 보다 커야 한다. 현재: {end}."
            )
        return self

    @model_validator(mode="after")
    def _validate_choice_pattern(self) -> V5VariantMetadata:
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
            if pattern not in _VALID_CHOICE_PATTERNS:
                raise ValueError(
                    f"허용되지 않은 choice_pattern 값: '{pattern}'. "
                    f"허용 값: {sorted(_VALID_CHOICE_PATTERNS)}."
                )
        return self


class V5Output(BaseModel):
    """V5 LLM structured output schema.

    docs/prompts/variant-blank-inference-v0.md 출력 schema 와 1:1 대응.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    question_type: str = Field(
        ...,
        description="문제 sub-type (blank_phrase_31 | blank_clause_32 | _33 | _34).",
    )
    body_with_blank: str = Field(
        ...,
        description="본문에 `______` 1개 박힌 형태 (joined passage text + blank 치환).",
    )
    choices: list[str] = Field(
        ...,
        description="5개 선택지 (1-based answer index 기준 순서).",
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
    variant_metadata: V5VariantMetadata = Field(
        ...,
        description="V5 전용 메타 (sub_type + blank_position + choice_pattern).",
    )

    @model_validator(mode="after")
    def _validate_choices_length(self) -> V5Output:
        if len(self.choices) != 5:
            raise ValueError(
                f"choices 는 정확히 5개여야 한다. 현재: {len(self.choices)}개."
            )
        return self

    @model_validator(mode="after")
    def _validate_body_with_blank(self) -> V5Output:
        """body_with_blank 에 `______` 가 정확히 1개 있어야 한다."""
        count = self.body_with_blank.count(_BLANK_MARKER)
        if count != 1:
            raise ValueError(
                f"body_with_blank 에 `______` 가 정확히 1개여야 한다. 현재: {count}개."
            )
        return self

    @model_validator(mode="after")
    def _validate_choice_pattern_answer_alignment(self) -> V5Output:
        """answer index 와 choice_pattern 의 'correct' 위치가 일치하는지 검증."""
        pattern = self.variant_metadata.choice_pattern
        # answer 는 1-based, list index 는 0-based
        expected_correct_idx = self.answer - 1
        actual_correct_idx = pattern.index("correct")
        if expected_correct_idx != actual_correct_idx:
            raise ValueError(
                f"answer={self.answer} (0-based index={expected_correct_idx}) 과 "
                f"choice_pattern 의 'correct' 위치(index={actual_correct_idx}) 가 불일치."
            )
        return self


# ─── 어댑터 함수 ──────────────────────────────────────────────────────────────


async def generate_v5_variant(
    *,
    passage_text: str,
    original_question: Question,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = V5_PROMPT_ID,
    blank_position_hint: str = "",
) -> Question:
    """V5 blank_inference 변형 생성.

    원본 Question 의 passage_text + type 을 기반으로 빈칸 위치를 선정하고
    5개 선택지를 생성한 뒤, sentinel UUID 가 채워진 신규 Question 을 반환한다.
    라우트가 실제 ID 를 주입.

    ADR-0013 augment 패턴:
      - sentinel UUID 채움 → 라우트가 model_copy 로 실제 tenant_id / workspace_id / id 교체.
      - variant 는 항상 신규 row — mode 정책 없음.

    Args:
        passage_text: 원본 Passage.body_text (LLM 입력).
        original_question: 원본 Question (type 확인 + derived_from_question_id 설정).
        llm_client: StructuredLLMClient 구현체 (CLAUDE.md §8.3 강제).
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``variant-blank-inference-v0``.
        blank_position_hint: 빈칸 위치 힌트 (선택 — 빈 문자열이면 LLM 이 자동 선택).

    Returns:
        sentinel UUID 가 채워진 신규 Question (variant_kind=BLANK_INFERENCE).
        라우트가 tenant_id / workspace_id / passage_id / derived_from_question_id 를
        model_copy 로 주입한다.

    Raises:
        ValueError: original_question.type 이 V5 비적용 type (V5_APPLICABLE_TYPES 외).
        LLMSchemaValidationError: structured output 검증 실패 (재시도 소진 후).
        LLMTimeoutError: 타임아웃 (재시도 소진 후).
        LLMNetworkError / PermanentLLMError: LLM 호출 실패.
    """
    if original_question.type not in V5_APPLICABLE_TYPES:
        raise ValueError(
            f"V5 변형은 blank_phrase_31 / blank_clause_32 / _33 / _34 type 에만 적용 가능합니다. "
            f"현재 type: {original_question.type}."
        )

    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={
            "passage_text": passage_text,
            "question_type": str(original_question.type),
            "blank_position_hint": blank_position_hint,
        },
    )

    result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=V5Output,
        purpose="variant_v5_blank_inference",
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
        variant_kind=VariantKind.BLANK_INFERENCE,
        question_text=original_question.question_text,
        choices=llm_out.choices,
        answer=llm_out.answer,
        explanation=llm_out.explanation,
        has_blanks=True,
        variant_metadata={
            **llm_out.variant_metadata.model_dump(),
            "body_with_blank": llm_out.body_with_blank,
        },
    )
