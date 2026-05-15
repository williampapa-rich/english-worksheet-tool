"""V4 grammar_inline — 어법 인라인화 (Phase 3, 카탈로그 v0.4 §V4).

CLAUDE.md §8.3 강제:
  직접 Anthropic SDK 호출 금지. 모든 LLM 호출은 StructuredLLMClient 를 통한다.

ADR-0013 augment 패턴 준수:
  - sentinel UUID 채움 → 라우트가 실제 ID 주입.
  - PromptSpec 을 통한 프롬프트 로딩.
  - Pydantic 모델로 structured output 검증.

변형 특성 (augment 와의 차이):
  - augment: 기존 row UPDATE (mode 분기).
  - variant: 항상 신규 Question row INSERT (mode 개념 없음).

카탈로그 v0.4 §V4 검증 기준:
  - inline_choices 2~3개 (박스 개수 범위 강제).
  - 각 박스 answer_index == 0 (options[0] = 정답).
  - choices 5개.
  - 오답 옵션이 grammatically incorrect form (프롬프트 가이드 반영, Pydantic 에서
    구조만 검증 — 문법 정확성은 qa-validator 별도).

에러 처리:
  - inline_choices 범위 벗어남 → LLMSchemaValidationError (Pydantic validator 강제).
  - choices 5개 미만/초과 → LLMSchemaValidationError.
  - answer 범위 (1~5) 벗어남 → LLMSchemaValidationError.
  - LLM 호출 실패 → llm.errors 계층 그대로 전파.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, model_validator

from llm.client import StructuredLLMClient
from llm.prompt import PromptSpec
from shared.schemas.question import (
    InlineChoice,
    InlineChoiceKind,
    Question,
    QuestionType,
    VariantKind,
)

# ─── sentinel UUID (ADR-0003 §D-3.6) ─────────────────────────────────────────
SENTINEL_UUID: uuid.UUID = uuid.UUID(int=0)

# ─── 프롬프트 템플릿 ID ─────────────────────────────────────────────────────
V4_PROMPT_ID = "variant-grammar-inline-v0"

# V4 적용 가능 QuestionType (카탈로그 v0.4 §V4 — grammar_29 만)
V4_APPLICABLE_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.GRAMMAR_29,
    }
)

# 인라인 박스 개수 범위 (카탈로그 v0.4 §V4 — 2~3개)
_MIN_BOX_COUNT = 2
_MAX_BOX_COUNT = 3

# 기본 박스 개수
_DEFAULT_BOX_COUNT = 2


# ─── LLM output schema ────────────────────────────────────────────────────────


class V4InlineChoiceOutput(BaseModel):
    """V4 LLM structured output 안의 개별 inline_choice 항목.

    docs/prompts/variant-grammar-inline-v0.md 의 inline_choices 배열 원소.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    label: str = Field(
        ...,
        description="박스 라벨 (예: '(A)', '(B)', '(C)').",
    )
    options: list[str] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="[correct_form, incorrect_form] — options[0] 이 항상 정답.",
    )
    answer_index: int = Field(
        ...,
        ge=0,
        le=0,
        description="항상 0 — options[0] 이 정답.",
    )
    position_marker: str | None = Field(
        default=None,
        description="본문 내 위치 식별자 (박스가 속한 문장의 첫 5~8 단어).",
    )
    kind: str = Field(
        default="grammar",
        description="출제 의도 — V4 는 항상 'grammar'.",
    )

    @model_validator(mode="after")
    def _validate_options_length(self) -> V4InlineChoiceOutput:
        if len(self.options) != 2:
            raise ValueError(
                f"options 는 정확히 2개여야 한다 (correct + incorrect). "
                f"현재: {len(self.options)}개."
            )
        return self


class V4Output(BaseModel):
    """V4 LLM structured output schema.

    docs/prompts/variant-grammar-inline-v0.md 출력 schema 와 1:1 대응.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    modified_passage_text: str = Field(
        ...,
        description="(A) [opt1 / opt2] 박스가 삽입된 수정 본문.",
    )
    inline_choices: list[V4InlineChoiceOutput] = Field(
        ...,
        description="박스 2~3개의 인라인 선택지 배열 (본문 등장 순서).",
    )
    choices: list[str] = Field(
        ...,
        description="5개 매트릭스 선택지 (1-based answer index 기준 순서).",
    )
    answer: int = Field(
        ...,
        ge=1,
        le=5,
        description="정답 인덱스 (1-based, 1~5).",
    )
    explanation: str = Field(
        ...,
        description="정답 사유 (한국어, 2~3문장) — 각 박스의 어법 규칙 설명.",
    )

    @model_validator(mode="after")
    def _validate_inline_choices_count(self) -> V4Output:
        count = len(self.inline_choices)
        if not (_MIN_BOX_COUNT <= count <= _MAX_BOX_COUNT):
            raise ValueError(
                f"inline_choices 는 {_MIN_BOX_COUNT}~{_MAX_BOX_COUNT}개여야 한다. 현재: {count}개."
            )
        return self

    @model_validator(mode="after")
    def _validate_choices_length(self) -> V4Output:
        if len(self.choices) != 5:
            raise ValueError(f"choices 는 정확히 5개여야 한다. 현재: {len(self.choices)}개.")
        return self


# ─── 어댑터 함수 ──────────────────────────────────────────────────────────────


async def generate_v4_variant(
    *,
    passage_text: str,
    original_question: Question,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = V4_PROMPT_ID,
    box_count: int = _DEFAULT_BOX_COUNT,
) -> Question:
    """V4 grammar_inline 변형 생성.

    원본 Passage.body_text 를 기반으로 2~3개 어법 인라인 박스를 삽입하고,
    sentinel UUID 가 채워진 신규 Question 을 반환한다. 라우트가 실제 ID 를 주입.

    ADR-0013 augment 패턴:
      - sentinel UUID 채움 → 라우트가 model_copy 로 실제 tenant_id / workspace_id / id 교체.
      - variant 는 항상 신규 row — mode 정책 없음.

    Args:
        passage_text: 원본 Passage.body_text (LLM 입력).
        original_question: 원본 Question (type 확인 + derived_from_question_id 설정).
        llm_client: StructuredLLMClient 구현체 (CLAUDE.md §8.3 강제).
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``variant-grammar-inline-v0``.
        box_count: 인라인 박스 개수 (2~3). 기본 2.

    Returns:
        sentinel UUID 가 채워진 신규 Question (variant_kind=GRAMMAR_INLINE).
        라우트가 tenant_id / workspace_id / passage_id / derived_from_question_id 를
        model_copy 로 주입한다.

    Raises:
        ValueError: original_question.type 이 V4 비적용 type (V4_APPLICABLE_TYPES 외).
        ValueError: box_count 가 2~3 범위 벗어남.
        LLMSchemaValidationError: structured output 검증 실패 (재시도 소진 후).
        LLMTimeoutError: 타임아웃 (재시도 소진 후).
        LLMNetworkError / PermanentLLMError: LLM 호출 실패.
    """
    if original_question.type not in V4_APPLICABLE_TYPES:
        raise ValueError(
            f"V4 변형은 grammar_29 type 에만 적용 가능합니다. 현재 type: {original_question.type}."
        )

    if not (_MIN_BOX_COUNT <= box_count <= _MAX_BOX_COUNT):
        raise ValueError(
            f"box_count 는 {_MIN_BOX_COUNT}~{_MAX_BOX_COUNT} 사이여야 합니다. 현재: {box_count}."
        )

    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={
            "passage_text": passage_text,
            "box_count": str(box_count),
        },
    )

    result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=V4Output,
        purpose="variant_v4_grammar_inline",
        tenant_id=original_question.tenant_id,
        workspace_id=original_question.workspace_id,
    )

    llm_out = result.data

    # V4InlineChoiceOutput → shared.schemas.question.InlineChoice 변환
    inline_choices: list[InlineChoice] = [
        InlineChoice(
            label=ic.label,
            options=ic.options,
            answer_index=ic.answer_index,
            position_marker=ic.position_marker,
            kind=InlineChoiceKind.GRAMMAR,
        )
        for ic in llm_out.inline_choices
    ]

    # LLM 출력 → Question 도메인 모델 변환
    # sentinel UUID 채움 — 라우트가 model_copy 로 실제 ID 주입 (ADR-0003 §D-3.6)
    return Question(
        id=SENTINEL_UUID,
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        passage_id=SENTINEL_UUID,
        derived_from_question_id=SENTINEL_UUID,  # 라우트가 실제 question_id 로 교체
        type=QuestionType.GRAMMAR_29,  # V4 는 grammar_29 로 통일 (카탈로그 v0.4)
        variant_kind=VariantKind.GRAMMAR_INLINE,
        question_text=(
            original_question.question_text or "밑줄 친 (A), (B)에 들어갈 말로 어법에 맞는 것은?"
        ),
        inline_choices=inline_choices,
        choices=llm_out.choices,
        answer=llm_out.answer,
        explanation=llm_out.explanation,
        variant_metadata={
            "modified_passage_text": llm_out.modified_passage_text,
            "box_count": box_count,
        },
    )
