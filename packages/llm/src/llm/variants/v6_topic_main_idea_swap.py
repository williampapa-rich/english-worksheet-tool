"""V6 topic_main_idea_swap — 주제·요지·제목 선택지 갱신 (Phase 3, 카탈로그 v0.4 §V6).

CLAUDE.md §8.3 강제:
  직접 Anthropic SDK 호출 금지. 모든 LLM 호출은 StructuredLLMClient 를 통한다.

ADR-0013 augment 패턴 준수:
  - sentinel UUID 채움 → 라우트가 실제 ID 주입.
  - PromptSpec 을 통한 프롬프트 로딩.
  - Pydantic 모델로 structured output 검증.

변형 특성 (augment 와의 차이):
  - augment: 기존 row UPDATE (mode 분기).
  - variant: 항상 신규 Question row INSERT (mode 개념 없음).

카탈로그 v0.4 §V6 검증 기준:
  - 정답이 본문 thesis 정확 일치.
  - sub-type 별 형식 준수 (main_idea_22=한국어 단문, theme_23=영어 명사구, title_24=영어 제목).
  - 오답 4개 패턴 다양성 (too-narrow / too-broad / opposite-conclusion / plausible-unrelated).

에러 처리:
  - choices 5개 미만 → LLMSchemaValidationError (Pydantic validator 강제).
  - answer 범위 (1~5) 벗어남 → LLMSchemaValidationError.
  - choice_pattern 5개 미만 / "correct" 불일치 → LLMSchemaValidationError.
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
V6_PROMPT_ID = "variant-topic-main-idea-swap-v0"

# V6 적용 가능 QuestionType (카탈로그 v0.4 §V6 — 확실)
V6_APPLICABLE_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.GIST_22,
        QuestionType.THEME_23,
        QuestionType.TITLE_24,
    }
)

# variant_metadata.choice_pattern 허용 값
_VALID_CHOICE_PATTERNS: frozenset[str] = frozenset(
    {"correct", "too-narrow", "too-broad", "opposite-conclusion", "plausible-unrelated"}
)


# ─── LLM output schema ────────────────────────────────────────────────────────


class V6VariantMetadata(BaseModel):
    """variant_metadata JSONB 구조 (V6 전용).

    카탈로그 v0.4 §V6 검증 기준 + ADR-0017 D2-c 결정 사항.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
        LLM 이 추가 필드를 반환해도 도메인 변환 시 필요한 필드만 사용.
    """

    sub_type: str = Field(
        ...,
        description=(
            "문제 sub-type 식별자. "
            "'main_idea_22' | 'theme_23' | 'title_24' 중 하나 (호출자 지정과 일치 검증)."
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
    def _validate_choice_pattern(self) -> V6VariantMetadata:
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


class V6Output(BaseModel):
    """V6 LLM structured output schema.

    docs/prompts/variant-topic-main-idea-swap-v0.md 출력 schema 와 1:1 대응.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

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
    variant_metadata: V6VariantMetadata = Field(
        ...,
        description="V6 전용 메타 (sub_type + choice_pattern).",
    )

    @model_validator(mode="after")
    def _validate_choices_length(self) -> V6Output:
        if len(self.choices) != 5:
            raise ValueError(
                f"choices 는 정확히 5개여야 한다. 현재: {len(self.choices)}개."
            )
        return self

    @model_validator(mode="after")
    def _validate_choice_pattern_answer_alignment(self) -> V6Output:
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


async def generate_v6_variant(
    *,
    passage_text: str,
    original_question: Question,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = V6_PROMPT_ID,
) -> Question:
    """V6 topic_main_idea_swap 변형 생성.

    원본 Question 의 passage_text + type 을 기반으로 5개 선택지를 새로 생성하고,
    sentinel UUID 가 채워진 신규 Question 을 반환한다. 라우트가 실제 ID 를 주입.

    ADR-0013 augment 패턴:
      - sentinel UUID 채움 → 라우트가 model_copy 로 실제 tenant_id / workspace_id / id 교체.
      - variant 는 항상 신규 row — mode 정책 없음.

    Args:
        passage_text: 원본 Passage.body_text (LLM 입력).
        original_question: 원본 Question (type 확인 + derived_from_question_id 설정).
        llm_client: StructuredLLMClient 구현체 (CLAUDE.md §8.3 강제).
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``variant-topic-main-idea-swap-v0``.

    Returns:
        sentinel UUID 가 채워진 신규 Question (variant_kind=TOPIC_MAIN_IDEA_SWAP).
        라우트가 tenant_id / workspace_id / passage_id / derived_from_question_id 를
        model_copy 로 주입한다.

    Raises:
        ValueError: original_question.type 이 V6 비적용 type (V6_APPLICABLE_TYPES 외).
        LLMSchemaValidationError: structured output 검증 실패 (재시도 소진 후).
        LLMTimeoutError: 타임아웃 (재시도 소진 후).
        LLMNetworkError / PermanentLLMError: LLM 호출 실패.
    """
    if original_question.type not in V6_APPLICABLE_TYPES:
        raise ValueError(
            f"V6 변형은 main_idea_22 / theme_23 / title_24 type 에만 적용 가능합니다. "
            f"현재 type: {original_question.type}."
        )

    # 원본 선택지 직렬화 — 다양성 회피용 입력 (없으면 빈 배열)
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
        response_model=V6Output,
        purpose="variant_v6_topic_main_idea_swap",
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
        variant_kind=VariantKind.TOPIC_MAIN_IDEA_SWAP,
        question_text=original_question.question_text,
        choices=llm_out.choices,
        answer=llm_out.answer,
        explanation=llm_out.explanation,
        variant_metadata=llm_out.variant_metadata.model_dump(),
    )
