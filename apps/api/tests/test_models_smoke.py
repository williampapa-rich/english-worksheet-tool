"""ORM 모델 smoke 테스트 (DB 없이) — ADR-0005 §D-5.7.

DB 연결 없이 ORM 클래스 인스턴스화 + 필드 정의를 검증한다.
JSONB / PostgreSQL 전용 기능 검증은 test_migrations.py 의 통합 테스트에서 수행.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from worksheet_api.models.base import SENTINEL_UUID
from worksheet_api.models.llm_usage_log import LlmUsageLogORM
from worksheet_api.models.passage import PassageORM
from worksheet_api.models.question import QuestionORM
from worksheet_api.models.syntax_annotation import SyntaxAnnotationORM
from worksheet_api.models.translation import TranslationORM
from worksheet_api.models.vocabulary import VocabularyORM

# ─── 픽스처 ──────────────────────────────────────────────────────────────────

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
PASSAGE_ID = uuid.uuid4()
NOW = datetime.now(UTC)


def _make_passage(**kwargs: object) -> PassageORM:
    defaults = dict(
        tenant_id=TENANT_ID,
        workspace_id=WORKSPACE_ID,
        body_text="The world is changing rapidly.",
        word_count=5,
        source={"provider": "evaluator"},
        target_grade="high_3",
        paragraphs=[],
        topic_tags=[],
    )
    defaults.update(kwargs)
    return PassageORM(**defaults)


def _make_question(**kwargs: object) -> QuestionORM:
    defaults = dict(
        tenant_id=TENANT_ID,
        workspace_id=WORKSPACE_ID,
        passage_id=PASSAGE_ID,
        type="gist_22",
        variant_kind="original",
        choices=["①", "②", "③", "④", "⑤"],
        answer=1,
    )
    defaults.update(kwargs)
    return QuestionORM(**defaults)


def _make_vocabulary(**kwargs: object) -> VocabularyORM:
    defaults = dict(
        tenant_id=TENANT_ID,
        workspace_id=WORKSPACE_ID,
        passage_id=PASSAGE_ID,
        word="rapidly",
        headword_normalized="rapidly",
        meaning_ko="빠르게",
        selected_by="llm",
    )
    defaults.update(kwargs)
    return VocabularyORM(**defaults)


def _make_translation(**kwargs: object) -> TranslationORM:
    defaults = dict(
        tenant_id=TENANT_ID,
        workspace_id=WORKSPACE_ID,
        passage_id=PASSAGE_ID,
        text="세계가 빠르게 변하고 있다.",
        created_by="llm",
    )
    defaults.update(kwargs)
    return TranslationORM(**defaults)


def _make_syntax_annotation(**kwargs: object) -> SyntaxAnnotationORM:
    defaults = dict(
        tenant_id=TENANT_ID,
        workspace_id=WORKSPACE_ID,
        passage_id=PASSAGE_ID,
        kind="highlight",
        # P1-3: AnnotationSpan v0.2 — start/end 1급 필드 (data dict placeholder 폐기).
        span={"span_format": "character_offset_v1", "start": 0, "end": 3},
    )
    defaults.update(kwargs)
    return SyntaxAnnotationORM(**defaults)


# ─── PassageORM ───────────────────────────────────────────────────────────────


class TestPassageORM:
    def test_instantiate(self) -> None:
        """PassageORM 인스턴스화 성공."""
        passage = _make_passage()
        assert passage.body_text == "The world is changing rapidly."
        assert passage.word_count == 5
        assert passage.target_grade == "high_3"

    def test_id_auto_generated(self) -> None:
        """id 가 자동 생성된다."""
        p1 = _make_passage()
        p2 = _make_passage()
        assert p1.id != p2.id
        assert isinstance(p1.id, uuid.UUID)

    def test_tablename(self) -> None:
        assert PassageORM.__tablename__ == "passages"

    def test_has_workspace_scoped_fields(self) -> None:
        passage = _make_passage()
        assert passage.tenant_id == TENANT_ID
        assert passage.workspace_id == WORKSPACE_ID


# ─── QuestionORM ─────────────────────────────────────────────────────────────


class TestQuestionORM:
    def test_instantiate(self) -> None:
        """QuestionORM 인스턴스화 성공."""
        q = _make_question()
        assert q.type == "gist_22"
        assert q.variant_kind == "original"
        assert q.answer == 1

    def test_derived_from_nullable(self) -> None:
        """derived_from_question_id 는 nullable."""
        q = _make_question()
        assert q.derived_from_question_id is None

    def test_variant_with_derived(self) -> None:
        """변형 문제는 derived_from_question_id 가 있다."""
        original_id = uuid.uuid4()
        q = _make_question(
            variant_kind="vocabulary_swap",
            derived_from_question_id=original_id,
        )
        assert q.variant_kind == "vocabulary_swap"
        assert q.derived_from_question_id == original_id

    def test_tablename(self) -> None:
        assert QuestionORM.__tablename__ == "questions"


# ─── VocabularyORM ────────────────────────────────────────────────────────────


class TestVocabularyORM:
    def test_instantiate(self) -> None:
        v = _make_vocabulary()
        assert v.word == "rapidly"
        assert v.meaning_ko == "빠르게"

    def test_passage_id_nullable(self) -> None:
        """passage_id 는 nullable (Phase 2/3 글로벌화 여지)."""
        v = _make_vocabulary(passage_id=None)
        assert v.passage_id is None

    def test_tablename(self) -> None:
        assert VocabularyORM.__tablename__ == "vocabulary"


# ─── TranslationORM ───────────────────────────────────────────────────────────


class TestTranslationORM:
    def test_instantiate(self) -> None:
        t = _make_translation()
        assert t.text == "세계가 빠르게 변하고 있다."
        assert t.language == "ko"
        assert t.created_by == "llm"

    def test_tablename(self) -> None:
        assert TranslationORM.__tablename__ == "translations"

    def test_unique_constraint_declared(self) -> None:
        """UniqueConstraint(passage_id) 가 테이블 정의에 포함된다."""
        from sqlmodel import SQLModel

        # SQLModel.metadata 에서 translations 테이블 확인
        table = SQLModel.metadata.tables.get("translations")
        assert table is not None
        unique_cols = [
            c.name
            for uc in table.constraints
            if hasattr(uc, "columns")
            for c in uc.columns
            if uc.__class__.__name__ == "UniqueConstraint"
        ]
        assert "passage_id" in unique_cols, (
            "translations.passage_id UNIQUE 제약이 없다 (PM 결정 D-2 위반)"
        )


# ─── SyntaxAnnotationORM ──────────────────────────────────────────────────────


class TestSyntaxAnnotationORM:
    def test_instantiate(self) -> None:
        ann = _make_syntax_annotation()
        assert ann.kind == "highlight"
        assert ann.category is None

    def test_with_category(self) -> None:
        ann = _make_syntax_annotation(category="sentence_role")
        assert ann.category == "sentence_role"

    def test_tablename(self) -> None:
        assert SyntaxAnnotationORM.__tablename__ == "syntax_annotations"


# ─── LlmUsageLogORM ──────────────────────────────────────────────────────────


class TestLlmUsageLogORM:
    def test_instantiate(self) -> None:
        log = LlmUsageLogORM(
            model="claude-sonnet-4-6",
            purpose="extract_text",
            input_tokens=100,
            output_tokens=200,
            latency_ms=500,
            status="success",
        )
        assert log.model == "claude-sonnet-4-6"
        assert log.tenant_id is None  # nullable — PM-4
        assert log.workspace_id is None  # nullable — PM-4

    def test_tablename(self) -> None:
        assert LlmUsageLogORM.__tablename__ == "llm_usage_logs"

    def test_tenant_id_nullable(self) -> None:
        """LlmUsageLogORM 의 tenant_id / workspace_id 는 nullable (PM-4 명세)."""
        log = LlmUsageLogORM(
            model="claude-sonnet-4-6",
            purpose="extract_pdf_vision",
            input_tokens=500,
            output_tokens=800,
            latency_ms=1200,
            status="success",
            tenant_id=None,
            workspace_id=None,
        )
        assert log.tenant_id is None
        assert log.workspace_id is None

    def test_with_tenant_id(self) -> None:
        """tenant_id 가 있는 경우도 허용된다."""
        log = LlmUsageLogORM(
            tenant_id=TENANT_ID,
            model="claude-sonnet-4-6",
            purpose="extract_text",
            input_tokens=100,
            output_tokens=200,
            latency_ms=400,
            status="success",
        )
        assert log.tenant_id == TENANT_ID


# ─── sentinel UUID 상수 ───────────────────────────────────────────────────────


class TestSentinelUUID:
    def test_sentinel_is_zero(self) -> None:
        """SENTINEL_UUID 는 UUID(int=0) 다."""
        assert SENTINEL_UUID == uuid.UUID(int=0)
        assert str(SENTINEL_UUID) == "00000000-0000-0000-0000-000000000000"

    def test_sentinel_distinct_from_normal_uuid(self) -> None:
        """일반 uuid.uuid4() 는 sentinel 과 다르다."""
        normal = uuid.uuid4()
        assert normal != SENTINEL_UUID


# ─── 메타데이터 등록 확인 ──────────────────────────────────────────────────────


class TestMetadataRegistration:
    def test_all_tables_in_sqlmodel_metadata(self) -> None:
        """6개 도메인 테이블이 모두 SQLModel.metadata 에 등록된다."""
        from sqlmodel import SQLModel

        expected = {
            "passages",
            "questions",
            "vocabulary",
            "translations",
            "syntax_annotations",
            "llm_usage_logs",
        }
        registered = set(SQLModel.metadata.tables.keys())
        missing = expected - registered
        assert not missing, f"SQLModel.metadata 에 등록 누락된 테이블: {missing}"

    def test_tenant_workspace_in_base_metadata(self) -> None:
        """tenants / workspaces 테이블은 Base.metadata 에 등록된다."""
        from worksheet_api.db import Base

        expected = {"tenants", "workspaces"}
        registered = set(Base.metadata.tables.keys())
        missing = expected - registered
        assert not missing, f"Base.metadata 에 등록 누락된 테이블: {missing}"
