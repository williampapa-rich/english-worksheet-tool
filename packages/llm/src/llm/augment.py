"""Translation / Vocabulary 보강 어댑터 — ADR-0013 D5 구현.

CLAUDE.md §8.3 / ADR-0013 D5:
  모든 LLM 호출은 packages/llm/ 경유. 보강 라우트는 본 모듈의 augment_translation /
  augment_vocabulary 만 호출하고, Anthropic SDK 직접 호출 금지.

ADR-0013 D5-0 — target_grade enum → 한국어 라벨 매핑:
  shared/schemas/passage.TargetGrade 의 snake_case enum 값 (`high_2` 등) 을
  프롬프트가 기대하는 한국어 라벨 ("고2" 등) 로 변환. None / OTHER → "고등" fallback.

ADR-0013 D5-1 — 어댑터 함수 시그니처:
  augment_translation(passage, llm_client) -> Translation (sentinel UUID 채워짐)
  augment_vocabulary(passage, llm_client, count) -> list[Vocabulary] (sentinel UUID)
  라우트가 sentinel UUID → 실제 tenant_id / workspace_id / passage_id model_copy 주입.

PM-6 가정:
  실유저 지문 default 는 영어만. 보강은 사용자가 명시적으로 트리거 (extract 와
  분리 — D1).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from llm.client import StructuredLLMClient
from llm.prompt import PromptSpec
from shared.schemas.passage import Passage, TargetGrade
from shared.schemas.translation import Translation, TranslationCreatedBy
from shared.schemas.vocabulary import Vocabulary, VocabularySelectedBy

# ADR-0003 §D-3.6 — sentinel UUID. 라우트가 model_copy 로 실제 tenant_id /
# workspace_id / passage_id 로 교체. extractor 도 동일 sentinel (packages/extractor
# 와 cross-package 의존 회피 위해 자체 정의).
SENTINEL_UUID: uuid.UUID = uuid.UUID(int=0)

# ─── 프롬프트 템플릿 ID ──────────────────────────────────────────────────────

TRANSLATION_PROMPT_ID = "augment-translation-v0"
VOCABULARY_PROMPT_ID = "augment-vocabulary-v0"

# 어휘 보강 default count — ADR-0013 D5 (라우트 default).
# domain-expert review B3: 학년별 default 는 라우트 / UI 책임. 본 어댑터 default 는 10.
DEFAULT_VOCABULARY_COUNT = 10

# ─── target_grade 매핑 (ADR-0013 D5-0) ──────────────────────────────────────

GRADE_LABELS_KO: dict[TargetGrade, str] = {
    TargetGrade.MIDDLE_1: "중1",
    TargetGrade.MIDDLE_2: "중2",
    TargetGrade.MIDDLE_3: "중3",
    TargetGrade.HIGH_1: "고1",
    TargetGrade.HIGH_2: "고2",
    TargetGrade.HIGH_3: "고3",
    TargetGrade.SUNEUNG: "수능",
}


def grade_label_for_prompt(grade: TargetGrade | None) -> str:
    """`target_grade` → 프롬프트용 한국어 라벨.

    None 또는 ``OTHER`` 는 ``"고등"`` 로 fallback (한국 학원 default 학년 추정).
    """
    if grade is None or grade == TargetGrade.OTHER:
        return "고등"
    return GRADE_LABELS_KO[grade]


# ─── LLM output schema (ADR-0013 D5-a) ──────────────────────────────────────


class TranslationLLMOutput(BaseModel):
    """LLM 이 채울 수 있는 Translation 필드만 (subset).

    시스템 메타 (tenant_id / workspace_id / passage_id / created_by) 는 라우트
    책임. LLM 이 만들면 안 되는 필드라 schema 자체에 포함 안 함.

    Note: ``extra="forbid"`` 미적용 — Gemini API 가 schema 의 ``additionalProperties:
    false`` 를 거절 (INVALID_ARGUMENT). LLM 이 추가 필드를 반환하면 무시 (도메인
    모델 변환 시 필요한 필드만 사용).
    """

    text: str = Field(..., description="전체 한국어 해석.")


class VocabularyItemLLMOutput(BaseModel):
    """LLM 이 채울 수 있는 Vocabulary 항목 필드 (subset)."""

    word: str = Field(..., max_length=255)
    headword_normalized: str = Field(..., max_length=255)
    pos: str | None = Field(default=None, max_length=64)
    meaning_ko: str = Field(..., max_length=512)
    level_label: str | None = Field(default=None, max_length=64)


class VocabularyLLMOutput(BaseModel):
    """LLM 어휘 보강 응답 컨테이너."""

    items: list[VocabularyItemLLMOutput] = Field(default_factory=list)


# ─── 어댑터 함수 ────────────────────────────────────────────────────────────


async def augment_translation(
    passage: Passage,
    *,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = TRANSLATION_PROMPT_ID,
) -> Translation:
    """LLM 으로 Translation 생성. sentinel UUID 채움 — 라우트가 실제 ID 주입.

    ADR-0013 D5-1.

    Args:
        passage: 보강 대상 Passage. body_text + target_grade 만 사용.
        llm_client: StructuredLLMClient 구현체.
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``augment-translation-v0``.

    Returns:
        sentinel UUID 로 채워진 Translation. ``created_by=LLM``.

    Raises:
        LLMSchemaValidationError / LLMTimeoutError / PermanentLLMError 등 packages/llm/
        에러 계층 (ADR-0003 §D-3.5) 그대로 전파.
    """
    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={
            "passage_text": passage.body_text,
            "target_grade": grade_label_for_prompt(passage.target_grade),
        },
    )
    result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=TranslationLLMOutput,
        purpose="augment_translation",
        tenant_id=passage.tenant_id,
        workspace_id=passage.workspace_id,
    )
    return Translation(
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        passage_id=SENTINEL_UUID,
        text=result.data.text,
        created_by=TranslationCreatedBy.LLM,
    )


async def augment_vocabulary(
    passage: Passage,
    *,
    llm_client: StructuredLLMClient,
    count: int = DEFAULT_VOCABULARY_COUNT,
    prompt_template_id: str = VOCABULARY_PROMPT_ID,
) -> list[Vocabulary]:
    """LLM 으로 Vocabulary list 생성. sentinel UUID — 라우트가 실제 ID 주입.

    ADR-0013 D5-1.

    Args:
        passage: 보강 대상 Passage.
        llm_client: StructuredLLMClient 구현체.
        count: 요청 어휘 개수. 프롬프트가 \"target {{count}} items\" 로 사용. LLM 이
            지문 길이에 따라 적게 반환 가능 (프롬프트 가이드).
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``augment-vocabulary-v0``.

    Returns:
        sentinel UUID 로 채워진 Vocabulary list. 각 항목 ``selected_by=LLM`` /
        ``user_edited=False``. PM-6 — 빈 list 도 정상 (LLM 이 0개 반환 가능).

    Raises:
        LLM* 에러 (ADR-0003 §D-3.5) 그대로 전파.
    """
    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={
            "passage_text": passage.body_text,
            "target_grade": grade_label_for_prompt(passage.target_grade),
            "count": str(count),
        },
    )
    result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=VocabularyLLMOutput,
        purpose="augment_vocabulary",
        tenant_id=passage.tenant_id,
        workspace_id=passage.workspace_id,
    )
    return [
        Vocabulary(
            tenant_id=SENTINEL_UUID,
            workspace_id=SENTINEL_UUID,
            passage_id=SENTINEL_UUID,
            word=item.word,
            headword_normalized=item.headword_normalized,
            pos=item.pos,
            meaning_ko=item.meaning_ko,
            level_label=item.level_label,
            selected_by=VocabularySelectedBy.LLM,
            user_edited=False,
        )
        for item in result.data.items
    ]
