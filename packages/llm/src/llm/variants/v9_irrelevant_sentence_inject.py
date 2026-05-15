"""V9 irrelevant_sentence_inject — 무관문장 주입 변형 (Phase 3, 카탈로그 v0.4 §V9).

CLAUDE.md §8.3 강제:
  직접 Anthropic SDK 호출 금지. 모든 LLM 호출은 StructuredLLMClient 를 통한다.

ADR-0013 augment 패턴 준수:
  - sentinel UUID 채움 → 라우트가 실제 ID 주입.
  - PromptSpec 을 통한 프롬프트 로딩.
  - Pydantic 모델로 structured output 검증.

변형 특성 (V8 와의 유사점 — ①~⑤ 마커 패턴):
  - 입력: 원본 Passage (body_text).
  - 본문에서 무관 문장 *주입 위치* 선택 (시작/끝 제외, 본문 중간).
  - 무관 문장 1개 생성 — 어휘 유사성 보존 + 논리 흐름 단절.
  - 주입된 무관 문장 포함 5문장 시퀀스에 ①~⑤ 마커 부착.
  - choices 는 항상 ["①", "②", "③", "④", "⑤"] 고정.
  - answer 는 주입된 무관 문장 위치 (1-based, 1~5).

카탈로그 v0.4 §V9 검증 기준:
  - 무관 문장이 명백히 흐름 단절 (애매한 case 회피).
  - 주변 문장과 lexical similarity 보존 (단순 어휘 차이로 안 잡힘 회피).
  - 나머지 4개 문장은 본문 흐름에 자연스러워야 함.
  - body_with_markers 에 ①~⑤ 마커 정확히 5개 (각 1회씩) 포함.
  - injected_sentence 가 body_with_markers 에 포함됨 (주입 위치에서 확인).

에러 처리:
  - choices 가 ["①", "②", "③", "④", "⑤"] 와 불일치 → LLMSchemaValidationError.
  - answer 범위 (1~5) 벗어남 → LLMSchemaValidationError.
  - injected_position_index != answer → LLMSchemaValidationError.
  - body_with_markers 에 마커 5개 미포함 → LLMSchemaValidationError.
  - lexical_similarity_words 비어 있음 → LLMSchemaValidationError.
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
V9_PROMPT_ID = "variant-irrelevant-sentence-inject-v0"

# V9 적용 가능 QuestionType (카탈로그 v0.4 §V9 — 확실)
V9_APPLICABLE_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.IRRELEVANT_SENTENCE_35,
    }
)

# 고정 선택지 — 항상 위치 마커 (문장 내용 아님)
_FIXED_CHOICES: list[str] = ["①", "②", "③", "④", "⑤"]

# ①~⑤ 유니코드 마커
_POSITION_MARKERS: tuple[str, ...] = ("①", "②", "③", "④", "⑤")


# ─── LLM output schema ────────────────────────────────────────────────────────


class V9VariantMetadata(BaseModel):
    """variant_metadata JSONB 구조 (V9 전용).

    카탈로그 v0.4 §V9 검증 기준 + ADR-0017 D2-c 결정 사항.
    variant_metadata 명세: ``docs/prompts/variant-irrelevant-sentence-inject-v0.md``.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    injected_sentence_text: str = Field(
        ...,
        description=(
            "주입된 무관 문장 텍스트. 본문 주제와 어휘 유사성은 있으나 논리 흐름을 단절시키는 문장."
        ),
    )
    injected_position_index: int = Field(
        ...,
        ge=1,
        le=5,
        description="주입된 무관 문장의 위치 (1-based, ①=1 … ⑤=5). answer 와 일치해야 함.",
    )
    lexical_similarity_words: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "주변 문장과 lexical similarity 를 공유하는 단어 리스트 (최소 1개). "
            "무관 문장이 완전히 어색하지 않게 만드는 어휘 연결 증거."
        ),
    )
    body_with_markers: str = Field(
        ...,
        description=(
            "①~⑤ 마커가 붙은 5문장 시퀀스. "
            "각 마커는 해당 문장 앞에 인라인으로 삽입됨. "
            "렌더러가 이 필드를 사용하여 문제 본문을 표시한다."
        ),
    )


class V9Output(BaseModel):
    """V9 LLM structured output schema.

    docs/prompts/variant-irrelevant-sentence-inject-v0.md 출력 schema 와 1:1 대응.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    choices: list[str] = Field(
        ...,
        description="5개 선택지. 항상 ['①', '②', '③', '④', '⑤'] 고정.",
    )
    answer: int = Field(
        ...,
        ge=1,
        le=5,
        description="정답 인덱스 (1-based, 1~5). 주입된 무관 문장 위치. ①=1, ②=2, ③=3, ④=4, ⑤=5.",
    )
    explanation: str = Field(
        ...,
        description="정답 사유 (한국어, 2~4문장). 흐름 단절 이유와 lexical similarity 보존 근거 언급.",
    )
    variant_metadata: V9VariantMetadata = Field(
        ...,
        description=(
            "V9 전용 메타 (injected_sentence_text + injected_position_index + "
            "lexical_similarity_words + body_with_markers)."
        ),
    )

    @model_validator(mode="after")
    def _validate_choices_fixed(self) -> V9Output:
        """choices 가 고정 마커 리스트 ['①'~'⑤'] 와 일치하는지 검증."""
        if self.choices != _FIXED_CHOICES:
            raise ValueError(f"choices 는 항상 {_FIXED_CHOICES} 여야 한다. 현재: {self.choices}.")
        return self

    @model_validator(mode="after")
    def _validate_answer_matches_position_index(self) -> V9Output:
        """answer 와 variant_metadata.injected_position_index 가 일치하는지 검증."""
        if self.answer != self.variant_metadata.injected_position_index:
            raise ValueError(
                f"answer={self.answer} 과 "
                f"variant_metadata.injected_position_index="
                f"{self.variant_metadata.injected_position_index} "
                "가 불일치. 두 값은 동일해야 한다."
            )
        return self

    @model_validator(mode="after")
    def _validate_body_markers(self) -> V9Output:
        """variant_metadata.body_with_markers 에 ①~⑤ 마커가 각 정확히 1회씩 포함되는지 검증."""
        for marker in _POSITION_MARKERS:
            count = self.variant_metadata.body_with_markers.count(marker)
            if count != 1:
                raise ValueError(
                    f"variant_metadata.body_with_markers 에 마커 '{marker}' 가 정확히 1개여야 한다. "
                    f"현재: {count}개."
                )
        return self

    @model_validator(mode="after")
    def _validate_injected_sentence_in_body(self) -> V9Output:
        """injected_sentence_text 가 body_with_markers 에 포함되어 있는지 검증."""
        injected = self.variant_metadata.injected_sentence_text
        body = self.variant_metadata.body_with_markers
        if injected not in body:
            raise ValueError(
                "variant_metadata.injected_sentence_text 가 "
                "variant_metadata.body_with_markers 에 "
                "포함되어 있지 않다. 주입된 무관 문장은 body_with_markers 에 존재해야 한다."
            )
        return self


# ─── 어댑터 함수 ──────────────────────────────────────────────────────────────


async def generate_v9_variant(
    *,
    passage_text: str,
    original_question: Question,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = V9_PROMPT_ID,
) -> Question:
    """V9 irrelevant_sentence_inject 변형 생성.

    원본 Passage.body_text 에서 무관 문장 주입 위치를 선정하고,
    lexical similarity 를 보존하면서 논리 흐름을 단절시키는 무관 문장 1개를 생성한다.
    5문장 시퀀스에 ①~⑤ 마커를 부착하여 반환한다.
    sentinel UUID 가 채워진 신규 Question 반환. 라우트가 실제 ID 를 주입.

    ADR-0013 augment 패턴:
      - sentinel UUID 채움 → 라우트가 model_copy 로 실제 tenant_id / workspace_id / id 교체.
      - variant 는 항상 신규 row — mode 정책 없음.

    Args:
        passage_text: 원본 Passage.body_text (LLM 입력).
        original_question: 원본 Question (type 확인 + derived_from_question_id 설정).
        llm_client: StructuredLLMClient 구현체 (CLAUDE.md §8.3 강제).
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``variant-irrelevant-sentence-inject-v0``.

    Returns:
        sentinel UUID 가 채워진 신규 Question (variant_kind=IRRELEVANT_SENTENCE_INJECT).
        choices 에 고정 마커 ["①", "②", "③", "④", "⑤"] 가 채워진다.
        variant_metadata 에 injected_sentence_text / injected_position_index /
        lexical_similarity_words 가 채워진다.
        라우트가 tenant_id / workspace_id / passage_id / derived_from_question_id 를
        model_copy 로 주입한다.

    Raises:
        ValueError: original_question.type 이 V9 비적용 type (V9_APPLICABLE_TYPES 외).
        LLMSchemaValidationError: structured output 검증 실패 (재시도 소진 후).
        LLMTimeoutError: 타임아웃 (재시도 소진 후).
        LLMNetworkError / PermanentLLMError: LLM 호출 실패.
    """
    if original_question.type not in V9_APPLICABLE_TYPES:
        raise ValueError(
            f"V9 변형은 irrelevant_sentence_35 type 에만 적용 가능합니다. "
            f"현재 type: {original_question.type}."
        )

    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={
            "passage_text": passage_text,
        },
    )

    result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=V9Output,
        purpose="variant_v9_irrelevant_sentence_inject",
        tenant_id=original_question.tenant_id,
        workspace_id=original_question.workspace_id,
    )

    llm_out = result.data

    # question_text 는 원본 유지 (무관문장 지시문) 또는 기본 지시문 생성
    question_text = original_question.question_text or ("다음 글에서 전체 흐름과 관계 없는 문장은?")

    # LLM 출력 → Question 도메인 모델 변환
    # sentinel UUID 채움 — 라우트가 model_copy 로 실제 ID 주입 (ADR-0003 §D-3.6)
    # body_with_markers 는 variant_metadata.body_with_markers 에 저장됨
    # (V8 패턴 — body_with_markers 는 variant_metadata 에만 저장, Question 별도 필드 없음)
    return Question(
        id=SENTINEL_UUID,
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        passage_id=SENTINEL_UUID,
        derived_from_question_id=SENTINEL_UUID,  # 라우트가 실제 question_id 로 교체
        type=QuestionType.IRRELEVANT_SENTENCE_35,
        variant_kind=VariantKind.IRRELEVANT_SENTENCE_INJECT,
        question_text=question_text,
        choices=llm_out.choices,
        answer=llm_out.answer,
        explanation=llm_out.explanation,
        variant_metadata=llm_out.variant_metadata.model_dump(),
    )
