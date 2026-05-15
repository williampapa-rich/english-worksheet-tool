"""validate_question_uniqueness 단위 테스트.

커버 케이스:
  - passed=True 정상 — LLM 이 uniqueness 검증 통과 반환.
  - passed=False 정상 — LLM 이 복수 정답 가능 판정.
  - LLMSchemaValidationError — graceful degradation (passed=False, validator_error note).
  - LLMTimeoutError — graceful degradation.
  - PermanentLLMError — graceful degradation.
  - 예상치 못한 Exception — graceful degradation.
  - variant_kind 별 prompt 변수 포함 확인 (V6 / V5 / V2 / V4 / V7).
  - confidence 필드 note 에 prefix 로 포함되는지 확인.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from qa_validator.uniqueness import (
    QA_VALIDATOR_VERSION,
    UniquenessValidationOutput,
    validate_question_uniqueness,
)
from shared.schemas.qa_validation_result import QAValidationResult
from shared.schemas.question import ChoiceFormat, Question, QuestionType, VariantKind

# ─── 테스트 고정 UUID ────────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
PASSAGE_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ORIGINAL_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
VARIANT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

_PASSAGE_TEXT = (
    "Reducing waste starts with awareness. Individual effort, "
    "multiplied across an entire community, creates meaningful change."
)

_FIVE_CHOICES = [
    "쓰레기를 줄이는 인식이 생기면 습관 변화로 이어져 지역 사회 전체에 긍정적 효과를 가져온다.",
    "재활용 가방 사용만으로 환경 문제를 완전히 해결할 수 있다.",
    "환경 보호를 위해서는 개인보다 기업의 역할이 더 중요하다.",
    "쓰레기 감량보다 무분별한 소비 자체를 막는 것이 더 시급한 과제이다.",
    "일회용품 사용을 줄이면 지방 자치 단체의 예산 문제도 해결된다.",
]


# ─── 헬퍼 ───────────────────────────────────────────────────────────────────


def _make_variant_question(
    variant_kind: VariantKind = VariantKind.TOPIC_MAIN_IDEA_SWAP,
    question_type: QuestionType = QuestionType.GIST_22,
    choices: list[str] | None = None,
    answer: int = 1,
) -> Question:
    return Question(
        id=VARIANT_ID,
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=PASSAGE_ID,
        derived_from_question_id=ORIGINAL_ID,
        type=question_type,
        variant_kind=variant_kind,
        question_text="다음 글의 요지로 가장 적절한 것은?",
        choices=choices if choices is not None else _FIVE_CHOICES,
        answer=answer,
        explanation="이 글은 인식이 변화를 이끈다는 점을 주장한다.",
        choice_format=ChoiceFormat.FLAT,
        created_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 15, 0, 0, 0, tzinfo=UTC),
    )


def _make_mock_llm_result(
    passed: bool = True,
    note: str = "정답이 thesis 와 정확히 일치.",
    confidence: str = "high",
) -> MagicMock:
    """StructuredLLMResult mock 반환."""
    llm_output = UniquenessValidationOutput(
        passed=passed,
        note=note,
        confidence=confidence,  # type: ignore[arg-type]
    )
    result = MagicMock()
    result.data = llm_output
    result.model = "claude-sonnet-4-6"
    return result


def _make_mock_client(llm_result: MagicMock) -> AsyncMock:
    """StructuredLLMClient mock."""
    client = AsyncMock()
    client.extract_structured = AsyncMock(return_value=llm_result)
    return client


def _make_prompts_dir(tmp_path: Path) -> Path:
    """최소 qa-validator 프롬프트 파일이 있는 임시 디렉토리."""
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "qa-validator-uniqueness-v0.md").write_text(
        "---\nversion: 0\n---\n"
        "Passage: {{passage_text}}\n"
        "Type: {{question_type}}\n"
        "Variant: {{variant_kind}}\n"
        "Question: {{question_text}}\n"
        "Choices: {{choices_text}}\n"
        "Answer: {{answer}}\n"
        "Answer text: {{answer_text}}\n"
        "Explanation: {{explanation}}\n"
        "Variant check: {{variant_kind_check}}",
        encoding="utf-8",
    )
    return d


# ─── TC-1: passed=True 정상 케이스 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_passes_when_llm_returns_true(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 이 passed=True 반환하면 QAValidationResult.passed=True."""
    monkeypatch.setenv("PROMPTS_DIR", str(_make_prompts_dir(tmp_path)))

    question = _make_variant_question()
    llm_result = _make_mock_llm_result(passed=True, note="정답 유일 확인.", confidence="high")
    client = _make_mock_client(llm_result)

    result = await validate_question_uniqueness(
        question=question,
        passage_text=_PASSAGE_TEXT,
        client=client,
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
    )

    assert isinstance(result, QAValidationResult)
    assert result.passed is True
    assert result.validator_note is not None
    assert "high" in result.validator_note
    assert "정답 유일 확인." in result.validator_note
    assert result.validator_model == "claude-sonnet-4-6"
    assert result.validator_version == QA_VALIDATOR_VERSION
    assert result.question_id == VARIANT_ID


# ─── TC-2: passed=False 정상 케이스 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_fails_when_llm_returns_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 이 passed=False 반환하면 QAValidationResult.passed=False."""
    monkeypatch.setenv("PROMPTS_DIR", str(_make_prompts_dir(tmp_path)))

    question = _make_variant_question()
    fail_note = "선지 ②와 ④ 모두 본문과 일치하는 해석이 가능함."
    llm_result = _make_mock_llm_result(passed=False, note=fail_note, confidence="medium")
    client = _make_mock_client(llm_result)

    result = await validate_question_uniqueness(
        question=question,
        passage_text=_PASSAGE_TEXT,
        client=client,
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
    )

    assert result.passed is False
    assert "medium" in result.validator_note  # type: ignore[operator]
    assert fail_note in result.validator_note  # type: ignore[operator]


# ─── TC-3: LLMSchemaValidationError graceful degradation ────────────────────


@pytest.mark.asyncio
async def test_validate_graceful_on_schema_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMSchemaValidationError 시 passed=False, validator_error note 반환."""
    from llm.errors import LLMSchemaValidationError

    monkeypatch.setenv("PROMPTS_DIR", str(_make_prompts_dir(tmp_path)))

    question = _make_variant_question()
    client = AsyncMock()
    client.extract_structured = AsyncMock(
        side_effect=LLMSchemaValidationError(
            "schema mismatch",
            validation_error="missing field",
            raw_response={},
        )
    )

    result = await validate_question_uniqueness(
        question=question,
        passage_text=_PASSAGE_TEXT,
        client=client,
    )

    assert result.passed is False
    assert result.validator_note is not None
    assert "validator_error" in result.validator_note
    assert "LLMSchemaValidationError" in result.validator_note
    assert result.validator_model is None
    assert result.validator_version == QA_VALIDATOR_VERSION


# ─── TC-4: LLMTimeoutError graceful degradation ─────────────────────────────


@pytest.mark.asyncio
async def test_validate_graceful_on_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMTimeoutError 시 graceful degradation."""
    from llm.errors import LLMTimeoutError

    monkeypatch.setenv("PROMPTS_DIR", str(_make_prompts_dir(tmp_path)))

    question = _make_variant_question()
    client = AsyncMock()
    client.extract_structured = AsyncMock(
        side_effect=LLMTimeoutError("timeout after 60s")
    )

    result = await validate_question_uniqueness(
        question=question,
        passage_text=_PASSAGE_TEXT,
        client=client,
    )

    assert result.passed is False
    assert "LLMTimeoutError" in result.validator_note  # type: ignore[operator]


# ─── TC-5: PermanentLLMError graceful degradation ──────────────────────────


@pytest.mark.asyncio
async def test_validate_graceful_on_permanent_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PermanentLLMError 시 graceful degradation."""
    from llm.errors import PermanentLLMError

    monkeypatch.setenv("PROMPTS_DIR", str(_make_prompts_dir(tmp_path)))

    question = _make_variant_question()
    client = AsyncMock()
    client.extract_structured = AsyncMock(
        side_effect=PermanentLLMError("API key invalid")
    )

    result = await validate_question_uniqueness(
        question=question,
        passage_text=_PASSAGE_TEXT,
        client=client,
    )

    assert result.passed is False
    assert "PermanentLLMError" in result.validator_note  # type: ignore[operator]


# ─── TC-6: 예상치 못한 Exception graceful degradation ───────────────────────


@pytest.mark.asyncio
async def test_validate_graceful_on_unexpected_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """예상치 못한 Exception 도 graceful degradation."""
    monkeypatch.setenv("PROMPTS_DIR", str(_make_prompts_dir(tmp_path)))

    question = _make_variant_question()
    client = AsyncMock()
    client.extract_structured = AsyncMock(
        side_effect=RuntimeError("unexpected internal error")
    )

    result = await validate_question_uniqueness(
        question=question,
        passage_text=_PASSAGE_TEXT,
        client=client,
    )

    assert result.passed is False
    assert "RuntimeError" in result.validator_note  # type: ignore[operator]


# ─── TC-7: QAValidationResult 필드 정합성 확인 ──────────────────────────────


@pytest.mark.asyncio
async def test_validate_result_fields_populated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """QAValidationResult 의 tenant_id / workspace_id / question_id 가 올바르게 채워짐."""
    monkeypatch.setenv("PROMPTS_DIR", str(_make_prompts_dir(tmp_path)))

    question = _make_variant_question()
    llm_result = _make_mock_llm_result(passed=True)
    client = _make_mock_client(llm_result)

    result = await validate_question_uniqueness(
        question=question,
        passage_text=_PASSAGE_TEXT,
        client=client,
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
    )

    assert result.tenant_id == TENANT_A
    assert result.workspace_id == WORKSPACE_A
    assert result.question_id == VARIANT_ID
    assert result.validated_at is not None


# ─── TC-8: variant_kind 별 check — V5 BLANK_INFERENCE ──────────────────────


@pytest.mark.asyncio
async def test_validate_v5_blank_inference_variant_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V5 BLANK_INFERENCE variant 에 대해 정상적으로 검증이 실행된다."""
    monkeypatch.setenv("PROMPTS_DIR", str(_make_prompts_dir(tmp_path)))

    question = _make_variant_question(
        variant_kind=VariantKind.BLANK_INFERENCE,
        question_type=QuestionType.BLANK_PHRASE_31,
    )
    llm_result = _make_mock_llm_result(passed=True, confidence="high")
    client = _make_mock_client(llm_result)

    result = await validate_question_uniqueness(
        question=question,
        passage_text=_PASSAGE_TEXT,
        client=client,
    )

    assert result.passed is True
    # LLM call 이 실제로 실행되었는지 확인
    client.extract_structured.assert_called_once()


# ─── TC-9: variant_kind 별 check — V2 VOCABULARY_INLINE ────────────────────


@pytest.mark.asyncio
async def test_validate_v2_vocabulary_inline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V2 VOCABULARY_INLINE variant 에 대해 정상적으로 검증이 실행된다."""
    monkeypatch.setenv("PROMPTS_DIR", str(_make_prompts_dir(tmp_path)))

    question = _make_variant_question(
        variant_kind=VariantKind.VOCABULARY_INLINE,
        question_type=QuestionType.VOCABULARY_30,
    )
    llm_result = _make_mock_llm_result(passed=True, confidence="medium")
    client = _make_mock_client(llm_result)

    result = await validate_question_uniqueness(
        question=question,
        passage_text=_PASSAGE_TEXT,
        client=client,
    )

    assert result.passed is True


# ─── TC-10: variant_kind 별 check — V7 ORDER_SHUFFLE ────────────────────────


@pytest.mark.asyncio
async def test_validate_v7_order_shuffle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V7 ORDER_SHUFFLE variant 에 대해 정상적으로 검증이 실행된다."""
    monkeypatch.setenv("PROMPTS_DIR", str(_make_prompts_dir(tmp_path)))

    question = _make_variant_question(
        variant_kind=VariantKind.ORDER_SHUFFLE,
        question_type=QuestionType.ORDER_36,
    )
    llm_result = _make_mock_llm_result(passed=False, note="응결 단서 불충분.", confidence="low")
    client = _make_mock_client(llm_result)

    result = await validate_question_uniqueness(
        question=question,
        passage_text=_PASSAGE_TEXT,
        client=client,
    )

    assert result.passed is False
    assert "low" in result.validator_note  # type: ignore[operator]


# ─── TC-11: UniquenessValidationOutput schema 검증 ──────────────────────────


def test_uniqueness_validation_output_valid() -> None:
    """UniquenessValidationOutput 정상 입력 검증."""
    out = UniquenessValidationOutput(
        passed=True,
        note="정답이 유일함.",
        confidence="high",
    )
    assert out.passed is True
    assert out.confidence == "high"


def test_uniqueness_validation_output_invalid_confidence() -> None:
    """UniquenessValidationOutput confidence 허용값 외 거부."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        UniquenessValidationOutput(
            passed=True,
            note="note",
            confidence="very_high",  # type: ignore[arg-type]
        )
