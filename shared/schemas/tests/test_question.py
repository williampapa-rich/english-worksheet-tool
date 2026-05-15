"""Question.variant_metadata + QAValidationResult 단위 테스트.

ADR-0017 D2-c JSONB + D3-c 하이브리드 검증:
  - Question.variant_metadata 신규 필드 — NULLABLE, ORIGINAL 행에서 None.
  - QAValidationResult 신규 모델 생성 / 필드 검증.
  - 기존 Question 동작 BC 유지 확인.
  - variant_kind / derived_from_question_id 정합성 (기존 validator 유지 확인).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from shared.schemas.qa_validation_result import QAValidationResult
from shared.schemas.question import Question, QuestionType, VariantKind

# ─── 공통 픽스처 헬퍼 ────────────────────────────────────────────────────────

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
PASSAGE_ID = uuid.uuid4()


def _make_question(**kwargs) -> Question:
    defaults = {
        "tenant_id": TENANT_ID,
        "workspace_id": WORKSPACE_ID,
        "passage_id": PASSAGE_ID,
        "type": QuestionType.GIST_22,
        "variant_kind": VariantKind.ORIGINAL,
    }
    defaults.update(kwargs)
    return Question(**defaults)


def _make_qa_result(**kwargs) -> QAValidationResult:
    defaults = {
        "tenant_id": TENANT_ID,
        "workspace_id": WORKSPACE_ID,
        "question_id": uuid.uuid4(),
        "passed": True,
    }
    defaults.update(kwargs)
    return QAValidationResult(**defaults)


# ─── Question.variant_metadata 신규 필드 테스트 ───────────────────────────────


class TestQuestionVariantMetadata:
    """ADR-0017 D2-c: variant_metadata JSONB nullable 필드 검증."""

    def test_variant_metadata_default_none(self):
        """variant_metadata 기본값 None — 기존 Question 생성 영향 없음 (BC 유지)."""
        q = _make_question()
        assert q.variant_metadata is None

    def test_variant_metadata_none_for_original(self):
        """ORIGINAL 문제는 variant_metadata = None (의미 없는 값)."""
        q = _make_question(
            variant_kind=VariantKind.ORIGINAL,
            variant_metadata=None,
        )
        assert q.variant_metadata is None

    def test_variant_metadata_dict_for_variant(self):
        """변형 문제는 variant_metadata 에 dict 설정 가능."""
        origin_id = uuid.uuid4()
        q = _make_question(
            variant_kind=VariantKind.VOCABULARY_SWAP,
            derived_from_question_id=origin_id,
            variant_metadata={
                "llm_candidate_words": ["strive", "attempt"],
                "generation_attempt": 2,
            },
        )
        assert q.variant_metadata is not None
        assert q.variant_metadata["generation_attempt"] == 2
        assert "strive" in q.variant_metadata["llm_candidate_words"]

    def test_variant_metadata_empty_dict_allowed(self):
        """빈 dict 도 허용 — Phase 3 에서 구조 보강."""
        origin_id = uuid.uuid4()
        q = _make_question(
            variant_kind=VariantKind.GRAMMAR_SWAP,
            derived_from_question_id=origin_id,
            variant_metadata={},
        )
        assert q.variant_metadata == {}

    def test_original_with_metadata_not_blocked_by_pydantic(self):
        """ORIGINAL 에 variant_metadata 설정해도 Pydantic 에서 에러 없음.

        정책 강제 (variant 만 metadata) 는 application 레이어 책임.
        """
        q = _make_question(
            variant_kind=VariantKind.ORIGINAL,
            variant_metadata={"note": "unused"},
        )
        assert q.variant_metadata == {"note": "unused"}


# ─── 기존 Question BC 유지 테스트 ────────────────────────────────────────────


class TestQuestionBackwardCompatibility:
    """기존 Question 필드 / 검증 로직 변경 없음 확인 (BC 유지)."""

    def test_existing_validator_variant_consistency_still_works(self):
        """기존 _validate_variant_consistency — ORIGINAL 에 derived_from_question_id 있으면 에러."""
        with pytest.raises(ValidationError, match="derived_from_question_id"):
            _make_question(
                variant_kind=VariantKind.ORIGINAL,
                derived_from_question_id=uuid.uuid4(),  # ORIGINAL 이면 None 이어야 함
            )

    def test_existing_validator_variant_needs_origin_id(self):
        """기존 validator — variant_kind != ORIGINAL 이면 derived_from_question_id 필수."""
        with pytest.raises(ValidationError, match="derived_from_question_id"):
            _make_question(
                variant_kind=VariantKind.VOCABULARY_SWAP,
                derived_from_question_id=None,  # NOT NULL 이어야 함
            )

    def test_create_original_question_minimal(self):
        """기존 최소 필드 생성 그대로 동작 (variant_metadata 없이)."""
        q = _make_question()
        assert q.variant_kind == VariantKind.ORIGINAL
        assert q.derived_from_question_id is None
        assert q.variant_metadata is None

    def test_uniqueness_validated_default_false(self):
        """uniqueness_validated 기본값 False — 변경 없음."""
        q = _make_question()
        assert q.uniqueness_validated is False
        assert q.uniqueness_validator_note is None

    def test_extra_fields_forbidden(self):
        """extra="forbid" — 알 수 없는 필드 거부."""
        with pytest.raises(ValidationError):
            _make_question(unknown_field="oops")


# ─── QAValidationResult 신규 모델 테스트 ──────────────────────────────────────


class TestQAValidationResultCreate:
    """ADR-0017 D3-c: QAValidationResult history 모델 생성 / 필드 검증."""

    def test_create_minimal_passed(self):
        """최소 필드 (passed=True) 로 생성 가능."""
        result = _make_qa_result(passed=True)
        assert result.passed is True
        assert result.validator_note is None
        assert result.validator_model is None
        assert result.validator_version is None

    def test_create_minimal_failed(self):
        """passed=False 로 생성 가능."""
        result = _make_qa_result(passed=False, validator_note="정답 외 선택지도 정답 가능")
        assert result.passed is False
        assert result.validator_note == "정답 외 선택지도 정답 가능"

    def test_validated_at_default_utc_now(self):
        """validated_at 기본값 = UTC now (timezone-aware)."""
        before = datetime.now(UTC)
        result = _make_qa_result()
        after = datetime.now(UTC)
        assert result.validated_at.tzinfo is not None
        assert before <= result.validated_at <= after

    def test_validator_model_and_version(self):
        """validator_model / validator_version 설정 가능."""
        result = _make_qa_result(
            passed=True,
            validator_model="claude-sonnet-4-5",
            validator_version="v0.1",
        )
        assert result.validator_model == "claude-sonnet-4-5"
        assert result.validator_version == "v0.1"

    def test_question_id_required(self):
        """question_id 누락 시 ValidationError."""
        with pytest.raises(ValidationError):
            QAValidationResult(
                tenant_id=TENANT_ID,
                workspace_id=WORKSPACE_ID,
                passed=True,
                # question_id 누락
            )

    def test_passed_required(self):
        """passed 누락 시 ValidationError."""
        with pytest.raises(ValidationError):
            QAValidationResult(
                tenant_id=TENANT_ID,
                workspace_id=WORKSPACE_ID,
                question_id=uuid.uuid4(),
                # passed 누락
            )

    def test_tenant_workspace_id_required(self):
        """tenant_id / workspace_id 누락 시 ValidationError."""
        with pytest.raises(ValidationError):
            QAValidationResult(
                question_id=uuid.uuid4(),
                passed=True,
            )

    def test_extra_fields_forbidden(self):
        """extra="forbid" — 알 수 없는 필드 거부."""
        with pytest.raises(ValidationError):
            _make_qa_result(unknown_field="oops")

    def test_from_attributes(self):
        """ORM-style attribute 접근으로 model_validate 가능 (from_attributes=True)."""
        result = _make_qa_result(passed=True, validator_note="OK")
        revalidated = QAValidationResult.model_validate(result.model_dump())
        assert revalidated.passed == result.passed
        assert revalidated.question_id == result.question_id

    def test_workspace_scoped_entity_base(self):
        """WorkspaceScopedEntity 베이스 — id / tenant_id / workspace_id / created_at 포함."""
        result = _make_qa_result()
        assert result.id is not None
        assert result.tenant_id == TENANT_ID
        assert result.workspace_id == WORKSPACE_ID
        assert result.created_at is not None
