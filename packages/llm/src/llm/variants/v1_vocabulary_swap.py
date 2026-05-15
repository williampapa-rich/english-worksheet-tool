"""V1 vocabulary_swap — 어휘 교체 변형 (Phase 3, 카탈로그 v0.4 §V1).

CLAUDE.md §8.3 강제:
  직접 Anthropic SDK 호출 금지. 모든 LLM 호출은 StructuredLLMClient 를 통한다.

ADR-0013 augment 패턴 준수:
  - sentinel UUID 채움 → 라우트가 실제 ID 주입.
  - PromptSpec 을 통한 프롬프트 로딩.
  - Pydantic 모델로 structured output 검증.

변형 특성:
  - 입력: 원본 Question (vocabulary_30 또는 long_set_41_42) 또는 원본 Passage.
  - 본문에서 5개 어휘 후보 위치 선택.
  - 5개 중 1개를 의미 부적절 단어(반의어 또는 문맥 어긋남)로 swap.
  - ①~⑤ 마커가 인라인으로 삽입된 body_with_markers 생성.
  - choices 는 5개 마커 위치의 단어들 (정답 위치 = 부적절 단어).
  - answer 는 부적절 단어의 위치 (1-based, 1~5).

카탈로그 v0.4 §V1 검증 기준:
  - 부적절 단어가 본문 의미를 명확히 어긋나게 만듦.
  - 4개 적절 단어가 dictionary 동의어 swap 검증 회피되는 변별 가치 위치.
  - body_with_markers 에 ①~⑤ 마커 정확히 5개 (각 1회씩) 포함.
  - answer == variant_metadata.swapped_position_index.
  - swapped_word 가 original_word 와 동일 품사.

에러 처리:
  - choices 5개 미만 → LLMSchemaValidationError (Pydantic validator 강제).
  - answer 범위 (1~5) 벗어남 → LLMSchemaValidationError.
  - answer != swapped_position_index → LLMSchemaValidationError.
  - body_with_markers 에 마커 5개 미포함 → LLMSchemaValidationError.
  - swap_reason 허용 값 외 → LLMSchemaValidationError.
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
V1_PROMPT_ID = "variant-vocabulary-swap-v0"

# V1 적용 가능 QuestionType (카탈로그 v0.4 §V1 — 확실)
V1_APPLICABLE_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.VOCABULARY_30,
        QuestionType.LONG_SET_41_42,
    }
)

# ①~⑤ 유니코드 마커
_POSITION_MARKERS: tuple[str, ...] = ("①", "②", "③", "④", "⑤")

# swap_reason 허용 값
_VALID_SWAP_REASONS: frozenset[str] = frozenset({"antonym", "context_mismatch"})


# ─── LLM output schema ────────────────────────────────────────────────────────


class V1VariantMetadata(BaseModel):
    """variant_metadata JSONB 구조 (V1 전용).

    카탈로그 v0.4 §V1 검증 기준 + ADR-0017 D2-c 결정 사항.
    variant_metadata 명세: ``docs/prompts/variant-vocabulary-swap-v0.md``.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    sub_type: str = Field(
        ...,
        description=(
            "문제 sub-type 식별자. "
            "'vocabulary_30' | 'long_set_41_42' 중 하나 (호출자 지정과 일치 검증)."
        ),
    )
    swapped_position_index: int = Field(
        ...,
        ge=1,
        le=5,
        description="부적절 단어가 삽입된 위치 (1-based, ①=1 … ⑤=5). answer 와 일치해야 함.",
    )
    original_word: str = Field(
        ...,
        description="교체되기 전의 원본 단어 (적절한 단어 — 정답 복원용).",
    )
    swapped_word: str = Field(
        ...,
        description="삽입된 부적절한 단어 (본문에 실제로 포함된 틀린 단어).",
    )
    swap_reason: Literal["antonym", "context_mismatch"] = Field(
        ...,
        description=("교체 유형. 'antonym' = 반의어 swap. 'context_mismatch' = 문맥 어긋남 단어."),
    )


class V1Output(BaseModel):
    """V1 LLM structured output schema.

    docs/prompts/variant-vocabulary-swap-v0.md 출력 schema 와 1:1 대응.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    body_with_markers: str = Field(
        ...,
        description=(
            "①~⑤ 마커가 인라인 삽입된 본문. "
            "1개 단어가 부적절 단어로 swap됨. "
            "각 마커는 해당 후보 단어 바로 앞에 위치."
        ),
    )
    choices: list[str] = Field(
        ...,
        description="5개 선택지. 각 마커 위치의 단어. choices[answer-1] = 부적절 단어.",
    )
    answer: int = Field(
        ...,
        ge=1,
        le=5,
        description="정답 인덱스 (1-based, 1~5). 부적절 단어의 위치. ①=1, ②=2, ③=3, ④=4, ⑤=5.",
    )
    explanation: str = Field(
        ...,
        description="정답 사유 (한국어, 2~4문장). 본문 문맥에서 왜 부적절한지 설명.",
    )
    variant_metadata: V1VariantMetadata = Field(
        ...,
        description=(
            "V1 전용 메타 "
            "(sub_type + swapped_position_index + original_word + swapped_word + swap_reason)."
        ),
    )

    @model_validator(mode="after")
    def _validate_choices_length(self) -> V1Output:
        """choices 가 정확히 5개인지 검증."""
        if len(self.choices) != 5:
            raise ValueError(f"choices 는 정확히 5개여야 한다. 현재: {len(self.choices)}개.")
        return self

    @model_validator(mode="after")
    def _validate_answer_matches_swapped_position(self) -> V1Output:
        """answer 와 variant_metadata.swapped_position_index 가 일치하는지 검증."""
        if self.answer != self.variant_metadata.swapped_position_index:
            raise ValueError(
                f"answer={self.answer} 과 "
                f"variant_metadata.swapped_position_index="
                f"{self.variant_metadata.swapped_position_index} "
                "가 불일치. 두 값은 동일해야 한다."
            )
        return self

    @model_validator(mode="after")
    def _validate_body_markers(self) -> V1Output:
        """body_with_markers 에 ①~⑤ 마커가 각 정확히 1회씩 포함되는지 검증."""
        for marker in _POSITION_MARKERS:
            count = self.body_with_markers.count(marker)
            if count != 1:
                raise ValueError(
                    f"body_with_markers 에 마커 '{marker}' 가 정확히 1개여야 한다. 현재: {count}개."
                )
        return self


# ─── 어댑터 함수 ──────────────────────────────────────────────────────────────


async def generate_v1_variant(
    *,
    passage_text: str,
    original_question: Question,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = V1_PROMPT_ID,
) -> Question:
    """V1 vocabulary_swap 변형 생성.

    원본 Passage.body_text 에서 5개 어휘 후보 위치를 선택하고 1개를 의미 부적절
    단어로 swap 한다. ①~⑤ 마커가 인라인 삽입된 body_with_markers 와 5개 choices
    (정답 = 부적절 단어 위치)를 반환. sentinel UUID 가 채워진 신규 Question 반환.
    라우트가 실제 ID 를 주입.

    ADR-0013 augment 패턴:
      - sentinel UUID 채움 → 라우트가 model_copy 로 실제 tenant_id / workspace_id / id 교체.
      - variant 는 항상 신규 row — mode 정책 없음.

    Args:
        passage_text: 원본 Passage.body_text (LLM 입력).
        original_question: 원본 Question (type 확인 + derived_from_question_id 설정).
        llm_client: StructuredLLMClient 구현체 (CLAUDE.md §8.3 강제).
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``variant-vocabulary-swap-v0``.

    Returns:
        sentinel UUID 가 채워진 신규 Question (variant_kind=VOCABULARY_SWAP).
        body_with_markers 는 variant_metadata["body_with_markers"] 에 저장.
        choices 에 5개 후보 단어 (정답 위치 = 부적절 단어).
        variant_metadata 에 sub_type / swapped_position_index / original_word /
        swapped_word / swap_reason 이 채워진다.
        라우트가 tenant_id / workspace_id / passage_id / derived_from_question_id 를
        model_copy 로 주입한다.

    Raises:
        ValueError: original_question.type 이 V1 비적용 type (V1_APPLICABLE_TYPES 외).
        LLMSchemaValidationError: structured output 검증 실패 (재시도 소진 후).
        LLMTimeoutError: 타임아웃 (재시도 소진 후).
        LLMNetworkError / PermanentLLMError: LLM 호출 실패.
    """
    if original_question.type not in V1_APPLICABLE_TYPES:
        raise ValueError(
            f"V1 변형은 vocabulary_30 / long_set_41_42 type 에만 적용 가능합니다. "
            f"현재 type: {original_question.type}."
        )

    # 원본 선택지 직렬화 — 위치 다양성 회피용 입력 (없으면 빈 배열)
    original_choices_repr = str(original_question.choices) if original_question.choices else "[]"

    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={
            "passage_text": passage_text,
            "question_type": str(original_question.type),
            "original_choices": original_choices_repr,
        },
    )

    result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=V1Output,
        purpose="variant_v1_vocabulary_swap",
        tenant_id=original_question.tenant_id,
        workspace_id=original_question.workspace_id,
    )

    llm_out = result.data

    # question_text — 어휘(30) 표준 지시문
    question_text = original_question.question_text or (
        "다음 밑줄 친 단어 중, 문맥상 낱말의 쓰임이 적절하지 않은 것은?"
    )

    # LLM 출력 → Question 도메인 모델 변환
    # body_with_markers 를 variant_metadata 에 포함시켜 저장
    # sentinel UUID 채움 — 라우트가 model_copy 로 실제 ID 주입 (ADR-0003 §D-3.6)
    metadata_dict = llm_out.variant_metadata.model_dump()
    metadata_dict["body_with_markers"] = llm_out.body_with_markers

    return Question(
        id=SENTINEL_UUID,
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        passage_id=SENTINEL_UUID,
        derived_from_question_id=SENTINEL_UUID,  # 라우트가 실제 question_id 로 교체
        type=original_question.type,
        variant_kind=VariantKind.VOCABULARY_SWAP,
        question_text=question_text,
        choices=llm_out.choices,
        answer=llm_out.answer,
        explanation=llm_out.explanation,
        variant_metadata=metadata_dict,
    )
