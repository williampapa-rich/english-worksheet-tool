"""NoOpValidator + ValidationResult 단위 테스트.

Phase 0 stub 검증:
  - NoOpValidator 가 모든 Question 에 대해 항상 통과 반환.
  - ValidationResult schema 적합성 (extra="forbid").
  - Validator 프로토콜 conformance.
  - PM-6 가정 (translation is None / vocabulary == [] 는 에러가 아님) 반영 — 다양한
    Question 입력이 모두 통과하는지 확인.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from qa_validator import NoOpValidator, ValidationResult, Validator

from shared.schemas.question import ChoiceFormat, Question, QuestionType, VariantKind

# ─── 헬퍼 ───────────────────────────────────────────────────────────────────


def _make_question(**overrides: object) -> Question:
    """테스트용 최소 Question 을 생성한다.

    WorkspaceScopedEntity 필수 필드 (tenant_id, workspace_id, passage_id) 를 채운다.
    """
    base = {
        "tenant_id": uuid.uuid4(),
        "workspace_id": uuid.uuid4(),
        "passage_id": uuid.uuid4(),
        "type": QuestionType.GIST_22,
        "variant_kind": VariantKind.ORIGINAL,
        "choices": ["①", "②", "③", "④", "⑤"],
        "answer": 1,
        "choice_format": ChoiceFormat.FLAT,
    }
    base.update(overrides)
    return Question.model_validate(base)


# ─── TC-1: 기본 동작 ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_noop_validator_returns_pass_basic() -> None:
    """NoOpValidator 가 기본 Question 에 대해 통과 결과를 반환한다."""
    validator = NoOpValidator()
    question = _make_question()
    result = await validator.validate(question)

    assert result.uniqueness_validated is True
    assert result.validator_note is None


# ─── TC-2: 선지 없는 Question ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_noop_validator_passes_question_without_choices() -> None:
    """선택지가 없는 Question (빈 list) 도 통과한다.

    PM-6 가정: 영어만 / 선택지 없는 케이스도 Phase 0 에서는 정상 처리.
    """
    validator = NoOpValidator()
    question = _make_question(choices=[])
    result = await validator.validate(question)

    assert result.uniqueness_validated is True
    assert result.validator_note is None


# ─── TC-3: 정답 인덱스 극단값 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_noop_validator_passes_answer_at_boundary() -> None:
    """정답 인덱스가 경계값(1, 5) 인 Question 도 통과한다."""
    validator = NoOpValidator()

    for answer_idx in [1, 5]:
        question = _make_question(answer=answer_idx)
        result = await validator.validate(question)
        assert result.uniqueness_validated is True, f"answer={answer_idx} 에서 실패"
        assert result.validator_note is None


# ─── TC-4: ValidationResult extra="forbid" ──────────────────────────────────


def test_validation_result_rejects_unknown_fields() -> None:
    """ValidationResult 는 알 수 없는 필드를 거부한다 (extra="forbid")."""
    with pytest.raises(ValidationError):
        ValidationResult.model_validate(
            {
                "uniqueness_validated": True,
                "validator_note": None,
                "unknown_field": "이 필드는 허용되지 않는다",
            }
        )


# ─── TC-5: Validator 프로토콜 conformance ────────────────────────────────────


def test_noop_validator_satisfies_validator_protocol() -> None:
    """NoOpValidator 가 Validator 프로토콜을 만족한다.

    isinstance 체크는 @runtime_checkable Protocol 로 가능하다.
    """
    validator = NoOpValidator()
    assert isinstance(validator, Validator)


# ─── TC-6: 복수 호출 — 결과 일관성 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_noop_validator_consistent_across_multiple_calls() -> None:
    """동일 validator 를 여러 Question 에 대해 호출해도 결과가 일관된다."""
    validator = NoOpValidator()
    questions = [
        _make_question(type=QuestionType.GIST_22),
        _make_question(type=QuestionType.VOCABULARY_30),
        _make_question(type=QuestionType.BLANK_PHRASE_31),
        _make_question(type=QuestionType.GRAMMAR_29),
        _make_question(type=QuestionType.TITLE_24),
    ]

    for q in questions:
        result = await validator.validate(q)
        assert result.uniqueness_validated is True
        assert result.validator_note is None


# ─── TC-7: ValidationResult 기본값 검증 ─────────────────────────────────────


def test_validation_result_default_values() -> None:
    """ValidationResult 를 인자 없이 생성하면 기본값이 올바르다."""
    result = ValidationResult()

    assert result.uniqueness_validated is True
    assert result.validator_note is None
