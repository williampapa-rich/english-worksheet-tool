"""V3 grammar_swap — 어법 오류 swap (Phase 3, 카탈로그 v0.4 §V3).

CLAUDE.md §8.3 강제:
  직접 Anthropic SDK 호출 금지. 모든 LLM 호출은 StructuredLLMClient 를 통한다.

ADR-0013 augment 패턴 준수:
  - sentinel UUID 채움 → 라우트가 실제 ID 주입.
  - PromptSpec 을 통한 프롬프트 로딩.
  - Pydantic 모델로 structured output 검증.

변형 특성 (augment 와의 차이):
  - augment: 기존 row UPDATE (mode 분기).
  - variant: 항상 신규 Question row INSERT (mode 개념 없음).

카탈로그 v0.4 §V3 검증 기준:
  - candidates 5개 정확히 (어법 후보 위치).
  - is_error == True 인 candidate 가 정확히 1개.
  - swapped_position_index 가 is_error candidate 의 position_index 와 일치.
  - choices 5개 (①~⑤).
  - answer == swapped_position_index (1-based).
  - error_type 이 허용된 값 중 하나.

에러 처리:
  - candidates 5개 미만/초과 → LLMSchemaValidationError (Pydantic validator 강제).
  - is_error candidate 0개 또는 2개 이상 → LLMSchemaValidationError.
  - swapped_position_index ≠ answer → LLMSchemaValidationError.
  - choices 5개 미만/초과 → LLMSchemaValidationError.
  - answer 범위 (1~5) 벗어남 → LLMSchemaValidationError.
  - LLM 호출 실패 → llm.errors 계층 그대로 전파.
"""

from __future__ import annotations

import uuid
from typing import Literal

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
V3_PROMPT_ID = "variant-grammar-swap-v0"

# V3 적용 가능 QuestionType (카탈로그 v0.4 §V3 — grammar_29 만)
V3_APPLICABLE_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.GRAMMAR_29,
    }
)

# 허용된 error_type 값 (카탈로그 v0.4 §V3 — 어법 카테고리)
_ALLOWED_ERROR_TYPES: frozenset[str] = frozenset(
    {
        "verb_form_error",
        "agreement_error",
        "infinitive_gerund_error",
        "relative_pronoun_error",
        "preposition_error",
        "participle_error",
        "pronoun_error",
    }
)


# ─── LLM output schema ────────────────────────────────────────────────────────


class V3CandidateOutput(BaseModel):
    """V3 LLM structured output 안의 개별 어법 후보 항목.

    docs/prompts/variant-grammar-swap-v0.md 의 candidates 배열 원소.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    position_index: int = Field(
        ...,
        ge=1,
        le=5,
        description="후보 위치 인덱스 (1-based, 1~5, 본문 등장 순서).",
    )
    original_phrase: str = Field(
        ...,
        description="원본 본문에서의 올바른 어법 형태.",
    )
    display_phrase: str = Field(
        ...,
        description="선택지에 표시되는 구문. 오류 위치는 swapped 형태, 나머지는 original.",
    )
    grammar_category: str = Field(
        ...,
        description="테스트되는 어법 카테고리 (예: 'subject-verb agreement').",
    )
    is_error: bool = Field(
        ...,
        description="True = 이 위치가 어법 오류로 swap 된 위치. 정확히 1개만 True.",
    )


class V3Output(BaseModel):
    """V3 LLM structured output schema.

    docs/prompts/variant-grammar-swap-v0.md 출력 schema 와 1:1 대응.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    modified_passage_text: str = Field(
        ...,
        description="어법 오류 1개가 삽입된 수정 본문.",
    )
    candidates: list[V3CandidateOutput] = Field(
        ...,
        description="어법 후보 5개 배열 (본문 등장 순서).",
    )
    swapped_position_index: int = Field(
        ...,
        ge=1,
        le=5,
        description="오류로 swap 된 후보 위치 (1-based, 1~5). answer 와 동일해야 함.",
    )
    original_phrase: str = Field(
        ...,
        description="swap 된 위치의 원본 올바른 형태.",
    )
    swapped_phrase: str = Field(
        ...,
        description="swap 된 위치에 삽입된 어법 오류 형태.",
    )
    error_type: Literal[
        "verb_form_error",
        "agreement_error",
        "infinitive_gerund_error",
        "relative_pronoun_error",
        "preposition_error",
        "participle_error",
        "pronoun_error",
    ] = Field(
        ...,
        description="어법 오류 유형 레이블.",
    )
    choices: list[str] = Field(
        ...,
        description="5개 선택지 (①~⑤, 각각 후보 위치의 구문).",
    )
    answer: int = Field(
        ...,
        ge=1,
        le=5,
        description="정답 인덱스 (1-based, 1~5). swapped_position_index 와 동일해야 함.",
    )
    explanation: str = Field(
        ...,
        description="정답 사유 (한국어, 2~3문장) — 어법 규칙 위반 설명.",
    )

    @model_validator(mode="after")
    def _validate_candidates_count(self) -> V3Output:
        if len(self.candidates) != 5:
            raise ValueError(f"candidates 는 정확히 5개여야 한다. 현재: {len(self.candidates)}개.")
        return self

    @model_validator(mode="after")
    def _validate_exactly_one_error(self) -> V3Output:
        error_count = sum(1 for c in self.candidates if c.is_error)
        if error_count != 1:
            raise ValueError(
                f"is_error == True 인 candidate 는 정확히 1개여야 한다. 현재: {error_count}개."
            )
        return self

    @model_validator(mode="after")
    def _validate_swapped_index_matches_answer(self) -> V3Output:
        if self.swapped_position_index != self.answer:
            raise ValueError(
                f"swapped_position_index ({self.swapped_position_index}) 는 "
                f"answer ({self.answer}) 와 동일해야 한다."
            )
        return self

    @model_validator(mode="after")
    def _validate_swapped_index_matches_is_error(self) -> V3Output:
        error_candidates = [c for c in self.candidates if c.is_error]
        if error_candidates and error_candidates[0].position_index != self.swapped_position_index:
            raise ValueError(
                f"is_error candidate 의 position_index ({error_candidates[0].position_index}) 가 "
                f"swapped_position_index ({self.swapped_position_index}) 와 불일치한다."
            )
        return self

    @model_validator(mode="after")
    def _validate_choices_length(self) -> V3Output:
        if len(self.choices) != 5:
            raise ValueError(f"choices 는 정확히 5개여야 한다. 현재: {len(self.choices)}개.")
        return self


# ─── 어댑터 함수 ──────────────────────────────────────────────────────────────


async def generate_v3_variant(
    *,
    passage_text: str,
    original_question: Question,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = V3_PROMPT_ID,
) -> Question:
    """V3 grammar_swap 변형 생성.

    원본 Passage.body_text 를 기반으로 어법 후보 5곳 중 1곳을 오류로 swap 하고,
    sentinel UUID 가 채워진 신규 Question 을 반환한다. 라우트가 실제 ID 를 주입.

    ADR-0013 augment 패턴:
      - sentinel UUID 채움 → 라우트가 model_copy 로 실제 tenant_id / workspace_id / id 교체.
      - variant 는 항상 신규 row — mode 정책 없음.

    Args:
        passage_text: 원본 Passage.body_text (LLM 입력).
        original_question: 원본 Question (type 확인 + derived_from_question_id 설정).
        llm_client: StructuredLLMClient 구현체 (CLAUDE.md §8.3 강제).
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``variant-grammar-swap-v0``.

    Returns:
        sentinel UUID 가 채워진 신규 Question (variant_kind=GRAMMAR_SWAP).
        라우트가 tenant_id / workspace_id / passage_id / derived_from_question_id 를
        model_copy 로 주입한다.

    Raises:
        ValueError: original_question.type 이 V3 비적용 type (V3_APPLICABLE_TYPES 외).
        LLMSchemaValidationError: structured output 검증 실패 (재시도 소진 후).
        LLMTimeoutError: 타임아웃 (재시도 소진 후).
        LLMNetworkError / PermanentLLMError: LLM 호출 실패.
    """
    if original_question.type not in V3_APPLICABLE_TYPES:
        raise ValueError(
            f"V3 변형은 grammar_29 type 에만 적용 가능합니다. 현재 type: {original_question.type}."
        )

    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={
            "passage_text": passage_text,
        },
    )

    result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=V3Output,
        purpose="variant_v3_grammar_swap",
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
        type=QuestionType.GRAMMAR_29,  # V3 는 grammar_29 로 통일 (카탈로그 v0.4)
        variant_kind=VariantKind.GRAMMAR_SWAP,
        question_text=(
            original_question.question_text or "다음 글의 밑줄 친 부분 중, 어법상 틀린 것은?"
        ),
        choices=llm_out.choices,
        answer=llm_out.answer,
        explanation=llm_out.explanation,
        variant_metadata={
            "modified_passage_text": llm_out.modified_passage_text,
            "swapped_position_index": llm_out.swapped_position_index,
            "original_phrase": llm_out.original_phrase,
            "swapped_phrase": llm_out.swapped_phrase,
            "error_type": llm_out.error_type,
        },
    )
