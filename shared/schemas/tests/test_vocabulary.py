"""VocabularyMaster + Vocabulary.master_id 단위 테스트.

ADR-0016 D2-a/-b/-c/-d 검증:
  - VocabularyMaster 모델 생성 / 필드 검증.
  - Vocabulary.master_id NULLABLE 필드 추가 확인.
  - master_id link 시 headword_normalized sync 정책 (ADR-0016 D2-b).
  - passage-specific override 정책 (ADR-0016 D2-c).
  - model_config extra="forbid" 위반 감지.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from shared.schemas.vocabulary import Vocabulary, VocabularySelectedBy
from shared.schemas.vocabulary_master import VocabularyMaster, VocabularyMasterCreatedBy

# ─── 공통 픽스처 헬퍼 ────────────────────────────────────────────────────────

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
PASSAGE_ID = uuid.uuid4()


def _make_vocabulary(**kwargs) -> Vocabulary:
    defaults = {
        "tenant_id": TENANT_ID,
        "workspace_id": WORKSPACE_ID,
        "passage_id": PASSAGE_ID,
        "word": "endeavor",
        "headword_normalized": "endeavor",
        "meaning_ko": "노력하다",
        "selected_by": VocabularySelectedBy.LLM,
    }
    defaults.update(kwargs)
    return Vocabulary(**defaults)


def _make_master(**kwargs) -> VocabularyMaster:
    defaults = {
        "tenant_id": TENANT_ID,
        "workspace_id": WORKSPACE_ID,
        "headword_normalized": "endeavor",
        "word_canonical": "endeavor",
        "default_meaning_ko": "노력하다",
        "created_by": VocabularyMasterCreatedBy.LLM,
    }
    defaults.update(kwargs)
    return VocabularyMaster(**defaults)


# ─── VocabularyMaster 생성 테스트 ─────────────────────────────────────────────


class TestVocabularyMasterCreate:
    """VocabularyMaster 모델 생성 / 필드 기본값 검증."""

    def test_create_minimal(self):
        """필수 필드만으로 생성 가능."""
        master = _make_master()
        assert master.headword_normalized == "endeavor"
        assert master.word_canonical == "endeavor"
        assert master.default_meaning_ko == "노력하다"
        assert master.created_by == VocabularyMasterCreatedBy.LLM

    def test_default_usage_count_zero(self):
        """usage_count 기본값 = 0."""
        master = _make_master()
        assert master.usage_count == 0

    def test_optional_fields_none(self):
        """선택 필드 (default_pos / default_level_label) 기본값 None."""
        master = _make_master()
        assert master.default_pos is None
        assert master.default_level_label is None

    def test_create_with_all_fields(self):
        """모든 필드를 채워 생성."""
        master = _make_master(
            default_pos="verb",
            default_level_label="수능 필수",
            usage_count=5,
            created_by=VocabularyMasterCreatedBy.USER,
        )
        assert master.default_pos == "verb"
        assert master.default_level_label == "수능 필수"
        assert master.usage_count == 5
        assert master.created_by == VocabularyMasterCreatedBy.USER

    def test_created_by_enum_values(self):
        """created_by enum — LLM / USER / IMPORT 모두 유효."""
        for val in VocabularyMasterCreatedBy:
            master = _make_master(created_by=val)
            assert master.created_by == val

    def test_usage_count_non_negative(self):
        """usage_count 는 0 이상이어야 한다."""
        with pytest.raises(ValidationError):
            _make_master(usage_count=-1)

    def test_extra_fields_forbidden(self):
        """extra="forbid" — 알 수 없는 필드 거부."""
        with pytest.raises(ValidationError):
            _make_master(unknown_field="oops")

    def test_tenant_workspace_id_required(self):
        """tenant_id / workspace_id 누락 시 ValidationError."""
        with pytest.raises(ValidationError):
            VocabularyMaster(
                headword_normalized="endeavor",
                word_canonical="endeavor",
                default_meaning_ko="노력하다",
                created_by=VocabularyMasterCreatedBy.LLM,
            )

    def test_from_attributes(self):
        """ORM-style attribute 접근으로 model_validate 가능 (from_attributes=True)."""
        master = _make_master()
        revalidated = VocabularyMaster.model_validate(master.model_dump())
        assert revalidated.headword_normalized == master.headword_normalized


# ─── Vocabulary.master_id 필드 테스트 ────────────────────────────────────────


class TestVocabularyMasterId:
    """Vocabulary.master_id NULLABLE 필드 + sync 정책 (ADR-0016 D2-b) 검증."""

    def test_master_id_default_none(self):
        """master_id 기본값 None — 기존 Vocabulary 생성 영향 없음 (BC 유지)."""
        vocab = _make_vocabulary()
        assert vocab.master_id is None

    def test_master_id_can_be_uuid(self):
        """master_id 에 UUID 값 설정 가능."""
        master_id = uuid.uuid4()
        vocab = _make_vocabulary(master_id=master_id)
        assert vocab.master_id == master_id

    def test_master_id_link_requires_nonempty_headword(self):
        """ADR-0016 D2-b: master_id 있을 때 headword_normalized 가 비어있으면 에러."""
        with pytest.raises(ValidationError, match="headword_normalized"):
            _make_vocabulary(
                master_id=uuid.uuid4(),
                headword_normalized="",  # 비어있음
            )

    def test_master_id_link_with_headword_ok(self):
        """master_id link 시 headword_normalized 있으면 OK."""
        vocab = _make_vocabulary(
            master_id=uuid.uuid4(),
            headword_normalized="endeavor",
        )
        assert vocab.master_id is not None
        assert vocab.headword_normalized == "endeavor"

    def test_master_id_none_with_empty_headword_allowed(self):
        """master_id = None 이면 headword_normalized 빈 문자열도 허용 (validator 비활성)."""
        # headword_normalized max_length=255, min_length 없음 — 빈 문자열 허용
        vocab = _make_vocabulary(master_id=None, headword_normalized="")
        assert vocab.master_id is None

    def test_existing_vocabulary_fields_unchanged(self):
        """기존 Vocabulary 필드 (word, meaning_ko 등) 변경 없음 (BC 유지)."""
        vocab = _make_vocabulary(
            word="Endeavored",
            headword_normalized="endeavor",
            pos="verb",
            meaning_ko="노력했다",
            level_label="수능 필수",
            selected_by=VocabularySelectedBy.USER,
            user_edited=True,
        )
        assert vocab.word == "Endeavored"
        assert vocab.meaning_ko == "노력했다"
        assert vocab.pos == "verb"
        assert vocab.level_label == "수능 필수"
        assert vocab.user_edited is True


# ─── passage-specific override 정책 (ADR-0016 D2-c) ─────────────────────────


class TestPassageSpecificOverride:
    """ADR-0016 D2-c: Vocabulary.meaning_ko 가 master 와 달라도 구조적으로 허용.

    정책은 docstring + application 레이어 책임. Pydantic 레이어에서는 강제하지 않음.
    """

    def test_meaning_ko_can_differ_from_master(self):
        """passage 행의 meaning_ko 가 master default 와 달라도 Pydantic 에서 에러 없음.

        ADR-0016 D2-c (i): passage 행이 우선 (passage-specific override).
        실제 master default 비교는 application 레이어 책임.
        """
        master = _make_master(default_meaning_ko="노력하다")
        vocab = _make_vocabulary(
            master_id=master.id,
            meaning_ko="애쓰다",  # master default 와 다름 — override 허용
        )
        assert vocab.meaning_ko == "애쓰다"
        assert vocab.master_id == master.id

    def test_user_edited_flag_set_on_override(self):
        """사용자가 수정한 경우 user_edited=True 설정 가능."""
        vocab = _make_vocabulary(
            master_id=uuid.uuid4(),
            meaning_ko="다른 뜻",
            user_edited=True,
        )
        assert vocab.user_edited is True

    def test_word_surface_form_independent_of_master(self):
        """Vocabulary.word 표면형은 master.word_canonical 과 다를 수 있음 (ADR-0016 D2-b).

        예: master "endeavor" / passage 행 "Endeavored" (굴절형).
        """
        master = _make_master(headword_normalized="endeavor", word_canonical="endeavor")
        vocab = _make_vocabulary(
            master_id=master.id,
            word="Endeavored",  # 굴절형 — 표면형 보존
            headword_normalized="endeavor",  # master 와 동일 (sync 정책)
        )
        assert vocab.word == "Endeavored"
        assert vocab.headword_normalized == "endeavor"
