"""``shared.schemas.extraction`` 단위 테스트.

P0-0 PR (`docs/phase-0-task-breakdown.md` §6) 의 DoD 충족 검증:
  - ``ExtractionResult`` 정상 생성 — 빈 questions / translation None / vocabulary [].
  - 풀세트 (translation 존재 + vocabulary 1건) 정상 생성.
  - 잘못된 타입 (translation dict / vocabulary None / naive datetime) 거절.
  - ``ExtractionRequest`` kind 별 정합성 강제 (image 의 media_type 누락 거절,
    pdf 의 force_vision default False 등).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from shared.schemas.common import utc_now
from shared.schemas.extraction import (
    ExtractionMetaRef,
    ExtractionRequest,
    ExtractionResult,
)
from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade
from shared.schemas.question import Question, QuestionType, VariantKind
from shared.schemas.translation import Translation, TranslationCreatedBy
from shared.schemas.vocabulary import Vocabulary, VocabularySelectedBy

# ─── 공통 fixture 헬퍼 ────────────────────────────────────────────────────


def _sentinel_uuid() -> UUID:
    """ADR-0003 §D-3.6 의 sentinel UUID."""
    return UUID(int=0)


def _make_passage() -> Passage:
    """최소 valid Passage (sentinel UUID 사용 — extractor 단계 가정)."""
    return Passage(
        tenant_id=_sentinel_uuid(),
        workspace_id=_sentinel_uuid(),
        body_text="The quick brown fox jumps over the lazy dog.",
        word_count=9,
        source=SourceMeta(provider=SourceProvider.USER_INPUT),
        target_grade=TargetGrade.OTHER,
    )


def _make_question(passage_id: UUID) -> Question:
    """최소 valid Question (passage 와 동일 sentinel scope)."""
    return Question(
        tenant_id=_sentinel_uuid(),
        workspace_id=_sentinel_uuid(),
        passage_id=passage_id,
        type=QuestionType.GIST_22,
        variant_kind=VariantKind.ORIGINAL,
        question_text="다음 글의 요지로 가장 적절한 것은?",
        choices=["①", "②", "③", "④", "⑤"],
        answer=1,
    )


def _make_translation(passage_id: UUID) -> Translation:
    """최소 valid Translation."""
    return Translation(
        tenant_id=_sentinel_uuid(),
        workspace_id=_sentinel_uuid(),
        passage_id=passage_id,
        text="빠른 갈색 여우가 게으른 개 위로 뛰어넘는다.",
        created_by=TranslationCreatedBy.LLM,
    )


def _make_vocabulary(passage_id: UUID) -> Vocabulary:
    """최소 valid Vocabulary."""
    return Vocabulary(
        tenant_id=_sentinel_uuid(),
        workspace_id=_sentinel_uuid(),
        passage_id=passage_id,
        word="quick",
        headword_normalized="quick",
        meaning_ko="빠른",
        selected_by=VocabularySelectedBy.LLM,
    )


def _make_meta() -> ExtractionMetaRef:
    """최소 valid ExtractionMetaRef."""
    return ExtractionMetaRef(
        request_id=uuid4(),
        model="claude-sonnet-4-20250514",
        prompt_template_id="extract-text-v0",
        extracted_at=utc_now(),
    )


# ─── ExtractionResult — 정상 케이스 ────────────────────────────────────────


class TestExtractionResultHappyPath:
    """정상 생성 — PM-5 / PM-6 가정 검증."""

    def test_default_minimal_translation_none_vocabulary_empty(self) -> None:
        """PM-6 default — translation=None, vocabulary=[] 인 게 정상."""
        passage = _make_passage()
        result = ExtractionResult(
            passage=passage,
            questions=[_make_question(passage.id)],
            extraction_meta=_make_meta(),
        )
        assert result.translation is None
        assert result.vocabulary == []
        assert len(result.questions) == 1

    def test_empty_questions_is_valid(self) -> None:
        """questions 빈 list 도 valid (지문만 있는 자료 케이스)."""
        passage = _make_passage()
        result = ExtractionResult(
            passage=passage,
            extraction_meta=_make_meta(),
        )
        assert result.questions == []
        assert result.translation is None
        assert result.vocabulary == []

    def test_full_set_translation_and_vocabulary(self) -> None:
        """풀세트 (아잉카 자료) — translation + vocabulary 양쪽 채움."""
        passage = _make_passage()
        result = ExtractionResult(
            passage=passage,
            questions=[_make_question(passage.id)],
            translation=_make_translation(passage.id),
            vocabulary=[_make_vocabulary(passage.id)],
            extraction_meta=_make_meta(),
        )
        assert result.translation is not None
        assert result.translation.text.startswith("빠른")
        assert len(result.vocabulary) == 1
        assert result.vocabulary[0].word == "quick"


# ─── ExtractionResult — 거절 케이스 ────────────────────────────────────────


class TestExtractionResultRejection:
    """잘못된 타입 / 가정 위반 거절."""

    def test_translation_dict_is_rejected(self) -> None:
        """translation 이 Translation 객체가 아닌 dict (잘못된 타입) 거절.

        Pydantic 은 dict 도 자동으로 모델 변환을 시도하지만, 필드 누락이면
        ValidationError. 본 케이스는 빈 dict — Translation 의 NOT NULL 필드
        (passage_id / text / created_by) 누락으로 거절되어야 함.
        """
        passage = _make_passage()
        with pytest.raises(ValidationError):
            ExtractionResult(
                passage=passage,
                translation={},  # type: ignore[arg-type]
                extraction_meta=_make_meta(),
            )

    def test_translation_wrong_type_is_rejected(self) -> None:
        """translation 이 완전히 다른 타입 (str) 이면 거절."""
        passage = _make_passage()
        with pytest.raises(ValidationError):
            ExtractionResult(
                passage=passage,
                translation="not a translation",  # type: ignore[arg-type]
                extraction_meta=_make_meta(),
            )

    def test_vocabulary_none_is_rejected(self) -> None:
        """vocabulary=None 거절 — 빈 list 가 default, None 은 의미 다름.

        PM-6 가정: 자료에 어휘 박스 없으면 빈 list. None 은 "데이터 없음 vs 비었음"
        혼동 유발 — 거절.
        """
        passage = _make_passage()
        with pytest.raises(ValidationError):
            ExtractionResult(
                passage=passage,
                vocabulary=None,  # type: ignore[arg-type]
                extraction_meta=_make_meta(),
            )

    def test_passage_missing_is_rejected(self) -> None:
        """passage 누락 거절 — NOT NULL."""
        with pytest.raises(ValidationError):
            ExtractionResult(  # type: ignore[call-arg]
                extraction_meta=_make_meta(),
            )

    def test_extraction_meta_missing_is_rejected(self) -> None:
        """extraction_meta 누락 거절 — NOT NULL (G-1)."""
        passage = _make_passage()
        with pytest.raises(ValidationError):
            ExtractionResult(  # type: ignore[call-arg]
                passage=passage,
            )

    def test_extra_field_is_rejected(self) -> None:
        """extra='forbid' — 알 수 없는 필드 거절 (LLM silent drift 방지)."""
        passage = _make_passage()
        with pytest.raises(ValidationError):
            ExtractionResult(
                passage=passage,
                extraction_meta=_make_meta(),
                unknown_field="oops",  # type: ignore[call-arg]
            )


# ─── ExtractionMetaRef — timezone 강제 ────────────────────────────────────


class TestExtractionMetaRefTimezone:
    """``extracted_at`` 의 timezone-aware 강제."""

    def test_naive_datetime_is_rejected(self) -> None:
        """naive datetime (tzinfo=None) 거절."""
        with pytest.raises(ValidationError) as excinfo:
            ExtractionMetaRef(
                request_id=uuid4(),
                model="claude-sonnet-4-20250514",
                extracted_at=datetime(2026, 5, 2, 12, 0, 0),  # naive
            )
        assert "timezone-aware" in str(excinfo.value)

    def test_utc_aware_datetime_is_accepted(self) -> None:
        """timezone-aware UTC datetime 통과."""
        meta = ExtractionMetaRef(
            request_id=uuid4(),
            model="claude-sonnet-4-20250514",
            extracted_at=datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC),
        )
        assert meta.extracted_at.tzinfo is not None

    def test_utc_now_helper_is_accepted(self) -> None:
        """common.utc_now() 산출물 통과 (회귀 가드)."""
        meta = ExtractionMetaRef(
            request_id=uuid4(),
            model="claude-sonnet-4-20250514",
            extracted_at=utc_now(),
        )
        assert meta.extracted_at.tzinfo is not None

    def test_prompt_template_id_optional(self) -> None:
        """prompt_template_id 는 None 허용 (직접 텍스트 주입 호출 케이스)."""
        meta = ExtractionMetaRef(
            request_id=uuid4(),
            model="claude-sonnet-4-20250514",
            prompt_template_id=None,
            extracted_at=utc_now(),
        )
        assert meta.prompt_template_id is None


# ─── ExtractionRequest — kind 별 정합성 ───────────────────────────────────


class TestExtractionRequestKindConsistency:
    """``kind`` 디스크리미네이터별 payload / media_type / force_vision 정합성."""

    def test_text_kind_minimal(self) -> None:
        """kind=text — payload str, media_type None, force_vision False."""
        req = ExtractionRequest(
            kind="text",
            payload="The quick brown fox.",
        )
        assert req.kind == "text"
        assert req.media_type is None
        assert req.force_vision is False

    def test_text_kind_rejects_bytes_payload(self) -> None:
        """kind=text 에 bytes payload 거절."""
        with pytest.raises(ValidationError):
            ExtractionRequest(
                kind="text",
                payload=b"raw bytes",
            )

    def test_text_kind_rejects_media_type(self) -> None:
        """kind=text 에 media_type 지정 거절 (str payload 에 무의미)."""
        with pytest.raises(ValidationError):
            ExtractionRequest(
                kind="text",
                payload="hello",
                media_type="text/plain",
            )

    def test_image_kind_requires_media_type(self) -> None:
        """kind=image 에 media_type 누락 → ValidationError."""
        with pytest.raises(ValidationError) as excinfo:
            ExtractionRequest(
                kind="image",
                payload=b"\x89PNG\r\n\x1a\n",
            )
        assert "media_type" in str(excinfo.value)

    def test_image_kind_with_media_type_ok(self) -> None:
        """kind=image + media_type 정상."""
        req = ExtractionRequest(
            kind="image",
            payload=b"\x89PNG\r\n\x1a\n",
            media_type="image/png",
        )
        assert req.media_type == "image/png"

    def test_image_kind_rejects_str_payload(self) -> None:
        """kind=image 에 str payload 거절."""
        with pytest.raises(ValidationError):
            ExtractionRequest(
                kind="image",
                payload="not bytes",
                media_type="image/png",
            )

    def test_pdf_kind_default_force_vision_false(self) -> None:
        """kind=pdf — force_vision default False (PM-3)."""
        req = ExtractionRequest(
            kind="pdf",
            payload=b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n",
        )
        assert req.kind == "pdf"
        assert req.force_vision is False

    def test_pdf_kind_force_vision_true(self) -> None:
        """kind=pdf + force_vision=True 정상 (PyMuPDF 우회 신호)."""
        req = ExtractionRequest(
            kind="pdf",
            payload=b"%PDF-1.4\n",
            force_vision=True,
        )
        assert req.force_vision is True

    def test_pdf_kind_rejects_str_payload(self) -> None:
        """kind=pdf 에 str payload 거절."""
        with pytest.raises(ValidationError):
            ExtractionRequest(
                kind="pdf",
                payload="not bytes",
            )

    def test_invalid_kind_is_rejected(self) -> None:
        """알 수 없는 kind 거절 (Literal 강제)."""
        with pytest.raises(ValidationError):
            ExtractionRequest(
                kind="audio",  # type: ignore[arg-type]
                payload=b"...",
            )

    def test_extra_field_is_rejected(self) -> None:
        """extra='forbid' — 알 수 없는 필드 거절."""
        with pytest.raises(ValidationError):
            ExtractionRequest(
                kind="text",
                payload="hello",
                unknown="oops",  # type: ignore[call-arg]
            )
