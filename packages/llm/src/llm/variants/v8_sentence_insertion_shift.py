"""V8 sentence_insertion_shift — 문장삽입 위치 변형 (Phase 3, 카탈로그 v0.4 §V8).

CLAUDE.md §8.3 강제:
  직접 Anthropic SDK 호출 금지. 모든 LLM 호출은 StructuredLLMClient 를 통한다.

ADR-0013 augment 패턴 준수:
  - sentinel UUID 채움 → 라우트가 실제 ID 주입.
  - PromptSpec 을 통한 프롬프트 로딩.
  - Pydantic 모델로 structured output 검증.

변형 특성 (V7 와의 유사점):
  - 입력: 원본 Passage (body_text).
  - 본문에서 결정적 문장 1개 추출 → given_sentence.
  - 본문 안 ①~⑤ 위치 마커 5개 부착 → body_with_markers.
  - choices 는 항상 ["①", "②", "③", "④", "⑤"] 고정 (위치 마커 선택).
  - answer 는 정답 위치 인덱스 (1-based, 1~5).

카탈로그 v0.4 §V8 검증 기준:
  - 추출 문장이 인접 문장과 응결 단서 (대명사 referent / 접속사 / 결론 흐름) 로 연결.
  - 다른 4개 위치에서 문맥 흐름이 깨짐 (정답 유일성).
  - body_with_markers 에 ①~⑤ 마커 정확히 5개 (각 1회씩) 포함.
  - given_sentence 가 body_with_markers 에 없음 (완전 제거).

에러 처리:
  - choices 가 ["①", "②", "③", "④", "⑤"] 와 불일치 → LLMSchemaValidationError.
  - answer 범위 (1~5) 벗어남 → LLMSchemaValidationError.
  - original_position_index != answer → LLMSchemaValidationError.
  - removed_sentence_text != given_sentence → LLMSchemaValidationError.
  - body_with_markers 에 마커 5개 미포함 → LLMSchemaValidationError.
  - given_sentence 가 body_with_markers 에 남아 있음 → LLMSchemaValidationError.
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
V8_PROMPT_ID = "variant-sentence-insertion-shift-v0"

# V8 적용 가능 QuestionType (카탈로그 v0.4 §V8 — 확실)
V8_APPLICABLE_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.INSERTION_38,
        QuestionType.INSERTION_39,
    }
)

# 고정 선택지 — 항상 위치 마커 (문장 내용 아님)
_FIXED_CHOICES: list[str] = ["①", "②", "③", "④", "⑤"]

# ①~⑤ 유니코드 마커
_POSITION_MARKERS: tuple[str, ...] = ("①", "②", "③", "④", "⑤")


# ─── LLM output schema ────────────────────────────────────────────────────────


class V8VariantMetadata(BaseModel):
    """variant_metadata JSONB 구조 (V8 전용).

    카탈로그 v0.4 §V8 검증 기준 + ADR-0017 D2-c 결정 사항.
    variant_metadata 명세: ``docs/prompts/variant-sentence-insertion-shift-v0.md``.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    sub_type: str = Field(
        ...,
        description=(
            "문제 sub-type 식별자. 'insertion_38' | 'insertion_39' 중 하나 (호출자 지정과 일치 검증)."
        ),
    )
    original_position_index: int = Field(
        ...,
        ge=1,
        le=5,
        description="추출된 문장의 원본 위치 (1-based, ①=1 … ⑤=5). answer 와 일치해야 함.",
    )
    removed_sentence_text: str = Field(
        ...,
        description="제거된 문장 텍스트. given_sentence 와 정확히 동일해야 함.",
    )
    cohesion_cues: list[str] = Field(
        ...,
        min_length=1,
        description="응결 단서 설명 리스트 (최소 1개). 대명사 referent / 접속사 / 논리 흐름.",
    )


class V8Output(BaseModel):
    """V8 LLM structured output schema.

    docs/prompts/variant-sentence-insertion-shift-v0.md 출력 schema 와 1:1 대응.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    given_sentence: str = Field(
        ...,
        description="추출된 문장 (주어진 문장). 원본 Passage 에서 verbatim 추출.",
    )
    body_with_markers: str = Field(
        ...,
        description="①~⑤ 마커가 삽입된 수정 본문 (추출 문장 제거 + 위치 마커 5개 삽입).",
    )
    choices: list[str] = Field(
        ...,
        description="5개 선택지. 항상 ['①', '②', '③', '④', '⑤'] 고정.",
    )
    answer: int = Field(
        ...,
        ge=1,
        le=5,
        description="정답 인덱스 (1-based, 1~5). ①=1, ②=2, ③=3, ④=4, ⑤=5.",
    )
    explanation: str = Field(
        ...,
        description="정답 사유 (한국어, 2~4문장). 응결 단서를 구체적으로 언급.",
    )
    variant_metadata: V8VariantMetadata = Field(
        ...,
        description="V8 전용 메타 (sub_type + original_position_index + removed_sentence_text + cohesion_cues).",
    )

    @model_validator(mode="after")
    def _validate_choices_fixed(self) -> V8Output:
        """choices 가 고정 마커 리스트 ['①'~'⑤'] 와 일치하는지 검증."""
        if self.choices != _FIXED_CHOICES:
            raise ValueError(
                f"choices 는 항상 {_FIXED_CHOICES} 여야 한다. 현재: {self.choices}."
            )
        return self

    @model_validator(mode="after")
    def _validate_answer_matches_position_index(self) -> V8Output:
        """answer 와 variant_metadata.original_position_index 가 일치하는지 검증."""
        if self.answer != self.variant_metadata.original_position_index:
            raise ValueError(
                f"answer={self.answer} 과 "
                f"variant_metadata.original_position_index={self.variant_metadata.original_position_index} "
                "가 불일치. 두 값은 동일해야 한다."
            )
        return self

    @model_validator(mode="after")
    def _validate_removed_sentence_matches_given(self) -> V8Output:
        """removed_sentence_text 가 given_sentence 와 동일한지 검증."""
        if self.variant_metadata.removed_sentence_text != self.given_sentence:
            raise ValueError(
                "variant_metadata.removed_sentence_text 와 given_sentence 가 불일치. "
                "두 필드는 동일한 문장이어야 한다."
            )
        return self

    @model_validator(mode="after")
    def _validate_body_markers(self) -> V8Output:
        """body_with_markers 에 ①~⑤ 마커가 각 정확히 1회씩 포함되는지 검증."""
        for marker in _POSITION_MARKERS:
            count = self.body_with_markers.count(marker)
            if count != 1:
                raise ValueError(
                    f"body_with_markers 에 마커 '{marker}' 가 정확히 1개여야 한다. "
                    f"현재: {count}개."
                )
        return self

    @model_validator(mode="after")
    def _validate_given_sentence_removed(self) -> V8Output:
        """given_sentence 가 body_with_markers 에 남아있지 않은지 검증."""
        if self.given_sentence in self.body_with_markers:
            raise ValueError(
                "given_sentence 가 body_with_markers 에 그대로 남아 있다. "
                "추출 문장은 body_with_markers 에서 완전히 제거되어야 한다."
            )
        return self


# ─── 어댑터 함수 ──────────────────────────────────────────────────────────────


async def generate_v8_variant(
    *,
    passage_text: str,
    original_question: Question,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = V8_PROMPT_ID,
) -> Question:
    """V8 sentence_insertion_shift 변형 생성.

    원본 Passage.body_text 에서 결정적 문장 1개를 추출하여 given_sentence 로 만들고,
    본문 안 ①~⑤ 위치 마커를 삽입한다. sentinel UUID 가 채워진 신규 Question 반환.
    라우트가 실제 ID 를 주입.

    ADR-0013 augment 패턴:
      - sentinel UUID 채움 → 라우트가 model_copy 로 실제 tenant_id / workspace_id / id 교체.
      - variant 는 항상 신규 row — mode 정책 없음.

    Args:
        passage_text: 원본 Passage.body_text (LLM 입력).
        original_question: 원본 Question (type 확인 + derived_from_question_id 설정).
        llm_client: StructuredLLMClient 구현체 (CLAUDE.md §8.3 강제).
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``variant-sentence-insertion-shift-v0``.

    Returns:
        sentinel UUID 가 채워진 신규 Question (variant_kind=SENTENCE_INSERTION_SHIFT).
        given_sentence 에 추출된 문장이 채워진다.
        choices 에 고정 마커 ["①", "②", "③", "④", "⑤"] 가 채워진다.
        variant_metadata 에 sub_type / original_position_index / removed_sentence_text /
        cohesion_cues 가 채워진다.
        라우트가 tenant_id / workspace_id / passage_id / derived_from_question_id 를
        model_copy 로 주입한다.

    Raises:
        ValueError: original_question.type 이 V8 비적용 type (V8_APPLICABLE_TYPES 외).
        LLMSchemaValidationError: structured output 검증 실패 (재시도 소진 후).
        LLMTimeoutError: 타임아웃 (재시도 소진 후).
        LLMNetworkError / PermanentLLMError: LLM 호출 실패.
    """
    if original_question.type not in V8_APPLICABLE_TYPES:
        raise ValueError(
            f"V8 변형은 insertion_38 / insertion_39 type 에만 적용 가능합니다. "
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
        response_model=V8Output,
        purpose="variant_v8_sentence_insertion_shift",
        tenant_id=original_question.tenant_id,
        workspace_id=original_question.workspace_id,
    )

    llm_out = result.data

    # question_text 는 원본 유지 (문장삽입 지시문) 또는 기본 지시문 생성
    question_text = original_question.question_text or (
        "글의 흐름으로 보아, 주어진 문장이 들어가기에 가장 적절한 곳은?"
    )

    # LLM 출력 → Question 도메인 모델 변환
    # sentinel UUID 채움 — 라우트가 model_copy 로 실제 ID 주입 (ADR-0003 §D-3.6)
    return Question(
        id=SENTINEL_UUID,
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        passage_id=SENTINEL_UUID,
        derived_from_question_id=SENTINEL_UUID,  # 라우트가 실제 question_id 로 교체
        type=original_question.type,
        variant_kind=VariantKind.SENTENCE_INSERTION_SHIFT,
        question_text=question_text,
        given_sentence=llm_out.given_sentence,
        choices=llm_out.choices,
        answer=llm_out.answer,
        explanation=llm_out.explanation,
        variant_metadata=llm_out.variant_metadata.model_dump(),
    )
