"""augment_translation / augment_vocabulary 단위 테스트 (mock LLM client).

ADR-0013 D5 어댑터 검증:
  - target_grade 한국어 매핑 (D5-0)
  - sentinel UUID 채움 (D5-1)
  - PromptSpec 변수 바인딩 (passage_text / target_grade / count)
  - LLM output schema → domain schema 변환
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from llm.augment import (
    GRADE_LABELS_KO,
    SENTINEL_UUID,
    TranslationLLMOutput,
    VocabularyItemLLMOutput,
    VocabularyLLMOutput,
    augment_translation,
    augment_vocabulary,
    grade_label_for_prompt,
)
from llm.usage import StructuredLLMResult, TokenUsage

from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade
from shared.schemas.translation import TranslationCreatedBy
from shared.schemas.vocabulary import VocabularySelectedBy


def _make_passage(
    target_grade: TargetGrade | None = TargetGrade.HIGH_2,
    body_text: str = "The economy is growing steadily.",
) -> Passage:
    return Passage(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        workspace_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        body_text=body_text,
        word_count=5,
        source=SourceMeta(provider=SourceProvider.EVALUATOR),
        target_grade=target_grade,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )


def _make_llm_result(data: Any) -> StructuredLLMResult[Any]:
    return StructuredLLMResult(
        data=data,
        raw_response={},
        usage=TokenUsage(input_tokens=100, output_tokens=50, cache_read_tokens=0),
        model="claude-sonnet-4-6",
        elapsed_ms=500,
    )


# ─── grade_label_for_prompt — D5-0 ───────────────────────────────────────────


def test_grade_label_all_enum_values_mapped() -> None:
    """TargetGrade 의 모든 값 (OTHER 포함) 이 fallback 없이 처리되어야."""
    assert grade_label_for_prompt(TargetGrade.MIDDLE_1) == "중1"
    assert grade_label_for_prompt(TargetGrade.MIDDLE_3) == "중3"
    assert grade_label_for_prompt(TargetGrade.HIGH_1) == "고1"
    assert grade_label_for_prompt(TargetGrade.HIGH_3) == "고3"
    assert grade_label_for_prompt(TargetGrade.SUNEUNG) == "수능"


def test_grade_label_none_fallback_to_고등() -> None:
    """target_grade=None → "고등" fallback (domain-expert review C1)."""
    assert grade_label_for_prompt(None) == "고등"


def test_grade_label_other_fallback_to_고등() -> None:
    """target_grade=OTHER → "고등" fallback (D5-0 도메인 검토 반영)."""
    assert grade_label_for_prompt(TargetGrade.OTHER) == "고등"


def test_grade_labels_dict_complete() -> None:
    """GRADE_LABELS_KO 가 OTHER 외 모든 enum 값을 cover."""
    expected_keys = set(TargetGrade) - {TargetGrade.OTHER}
    assert set(GRADE_LABELS_KO.keys()) == expected_keys


# ─── augment_translation ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_augment_translation_returns_sentinel_uuid_translation() -> None:
    """LLM 결과 → sentinel UUID 채워진 Translation."""
    passage = _make_passage()
    llm_client = AsyncMock()
    llm_client.extract_structured = AsyncMock(
        return_value=_make_llm_result(TranslationLLMOutput(text="LLM 한국어 해석"))
    )

    result = await augment_translation(passage, llm_client=llm_client)

    assert result.tenant_id == SENTINEL_UUID
    assert result.workspace_id == SENTINEL_UUID
    assert result.passage_id == SENTINEL_UUID
    assert result.text == "LLM 한국어 해석"
    assert result.created_by == TranslationCreatedBy.LLM


@pytest.mark.asyncio
async def test_augment_translation_passes_target_grade_label() -> None:
    """프롬프트 변수에 한국어 라벨 ("고2") 이 들어가야."""
    passage = _make_passage(target_grade=TargetGrade.HIGH_2)
    llm_client = AsyncMock()
    llm_client.extract_structured = AsyncMock(
        return_value=_make_llm_result(TranslationLLMOutput(text="해석"))
    )

    await augment_translation(passage, llm_client=llm_client)

    call_kwargs = llm_client.extract_structured.await_args.kwargs
    spec = call_kwargs["prompt"]
    assert spec.template_id == "augment-translation-v0"
    assert spec.variables["target_grade"] == "고2"
    assert spec.variables["passage_text"] == passage.body_text


@pytest.mark.asyncio
async def test_augment_translation_other_grade_fallback() -> None:
    """target_grade=OTHER → 프롬프트에 "고등" 으로 전달."""
    passage = _make_passage(target_grade=TargetGrade.OTHER)
    llm_client = AsyncMock()
    llm_client.extract_structured = AsyncMock(
        return_value=_make_llm_result(TranslationLLMOutput(text="해석"))
    )

    await augment_translation(passage, llm_client=llm_client)

    spec = llm_client.extract_structured.await_args.kwargs["prompt"]
    assert spec.variables["target_grade"] == "고등"


@pytest.mark.asyncio
async def test_augment_translation_purpose_recorded() -> None:
    """LLM 호출 purpose='augment_translation' 기록 (비용 추적, ADR-0013 D8)."""
    passage = _make_passage()
    llm_client = AsyncMock()
    llm_client.extract_structured = AsyncMock(
        return_value=_make_llm_result(TranslationLLMOutput(text="해석"))
    )

    await augment_translation(passage, llm_client=llm_client)

    call_kwargs = llm_client.extract_structured.await_args.kwargs
    assert call_kwargs["purpose"] == "augment_translation"
    assert call_kwargs["tenant_id"] == passage.tenant_id
    assert call_kwargs["workspace_id"] == passage.workspace_id


# ─── augment_vocabulary ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_augment_vocabulary_empty_list_ok() -> None:
    """LLM 이 빈 list 반환 → 빈 list 반환 (PM-6 가정)."""
    passage = _make_passage()
    llm_client = AsyncMock()
    llm_client.extract_structured = AsyncMock(
        return_value=_make_llm_result(VocabularyLLMOutput(items=[]))
    )

    result = await augment_vocabulary(passage, llm_client=llm_client)

    assert result == []


@pytest.mark.asyncio
async def test_augment_vocabulary_maps_all_fields() -> None:
    """LLM output → Vocabulary 도메인 모델 매핑. sentinel UUID, selected_by=LLM."""
    passage = _make_passage()
    llm_client = AsyncMock()
    llm_client.extract_structured = AsyncMock(
        return_value=_make_llm_result(
            VocabularyLLMOutput(
                items=[
                    VocabularyItemLLMOutput(
                        word="unprecedented",
                        headword_normalized="unprecedented",
                        pos="adj",
                        meaning_ko="전례 없는",
                        level_label="수능 필수",
                    ),
                    VocabularyItemLLMOutput(
                        word="long-held",
                        headword_normalized="long-held",
                        pos="adj",
                        meaning_ko="오랫동안 지녀 온",
                        level_label=None,
                    ),
                ]
            )
        )
    )

    result = await augment_vocabulary(passage, llm_client=llm_client, count=10)

    assert len(result) == 2
    assert result[0].tenant_id == SENTINEL_UUID
    assert result[0].word == "unprecedented"
    assert result[0].pos == "adj"
    assert result[0].meaning_ko == "전례 없는"
    assert result[0].level_label == "수능 필수"
    assert result[0].selected_by == VocabularySelectedBy.LLM
    assert result[0].user_edited is False
    # level_label 이 None 인 항목도 정상 매핑
    assert result[1].level_label is None


@pytest.mark.asyncio
async def test_augment_vocabulary_passes_count_and_grade() -> None:
    """count + target_grade 둘 다 프롬프트 변수에 들어가야."""
    passage = _make_passage(target_grade=TargetGrade.MIDDLE_3)
    llm_client = AsyncMock()
    llm_client.extract_structured = AsyncMock(
        return_value=_make_llm_result(VocabularyLLMOutput(items=[]))
    )

    await augment_vocabulary(passage, llm_client=llm_client, count=15)

    spec = llm_client.extract_structured.await_args.kwargs["prompt"]
    assert spec.template_id == "augment-vocabulary-v0"
    assert spec.variables["count"] == "15"
    assert spec.variables["target_grade"] == "중3"


@pytest.mark.asyncio
async def test_augment_vocabulary_purpose_recorded() -> None:
    """LLM 호출 purpose='augment_vocabulary' 기록."""
    passage = _make_passage()
    llm_client = AsyncMock()
    llm_client.extract_structured = AsyncMock(
        return_value=_make_llm_result(VocabularyLLMOutput(items=[]))
    )

    await augment_vocabulary(passage, llm_client=llm_client)

    assert llm_client.extract_structured.await_args.kwargs["purpose"] == "augment_vocabulary"
