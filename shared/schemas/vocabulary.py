"""Vocabulary(어휘) 도메인 모델.

PM 권고 (`docs/adr/_pm-decisions-sprint-0.md` §영향받는 다른 결정):
  - audit-review-domain §3.3 권고에 따라 ``headword_normalized`` 자리만 박아둠
    (글로벌 dedup 마스터 도입 시 retrofit 비용 회피).
  - 본 v0.1 은 **Passage 종속** 모델. 글로벌 마스터 (``VocabularyMaster``) 는 Phase 2/3
    진입 전 별도 ADR 로 결정.

audit-review-domain §3.3 도메인 인사이트:
  한국 영어 학원 강사의 어휘 관리는 2계층 hybrid 가 표준이다.
    1. 지문 종속 어휘 박스 (학생용 자료에 들어가는 8~15개 핵심 어휘)
    2. 개인 단어장 (강사 본인이 평생 누적하는 어휘 자산)

audit-review-domain §4.3 권고:
  - ``selected_by`` 와 ``user_edited`` 메타로 LLM 출력 보존 추적 ("AI 자동 ≠ 완성").

어휘 등급 표기 (audit-review-domain §3.3):
  CEFR 보다 한국 시장은 "수능 빈도 등급" 또는 "교과서 등급" 이 익숙하다. v0.1 은
  ``level_label: Optional[str]`` 자유 문자열로 두고, Phase 2 에서 enum 정규화 검토.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from shared.schemas.common import EntityId, WorkspaceScopedEntity


class VocabularySelectedBy(StrEnum):
    """어휘 선택 주체 (audit-review-domain §4.3 권고)."""

    LLM = "llm"
    USER = "user"
    FREQUENCY_FILTER = "frequency_filter"  # 시스템 빈도 필터 자동 선정


class Vocabulary(WorkspaceScopedEntity):
    """Passage 종속 어휘 항목.

    한 Passage 의 어휘 박스에 들어가는 항목 1개. 동일 단어가 여러 Passage 에 등장할
    때 v0.1 에서는 매번 새 엔트리 (Passage 종속). 글로벌 dedup 은 Phase 2/3 의 ADR
    이후 ``VocabularyMaster`` 도입과 함께 마이그레이션.
    """

    passage_id: EntityId = Field(
        ...,
        description="참조 Passage ID (FK → passages.id). v0.1 은 Passage 종속.",
    )

    # ─── 표제어 ──────────────────────────────────────────────────────────────
    word: str = Field(
        ...,
        max_length=255,
        description="원형 (사용자 입력 표면형, 대소문자/굴절 보존).",
    )
    headword_normalized: str = Field(
        ...,
        max_length=255,
        description=(
            "정규화된 표제어 (소문자 + lemma). Phase 2/3 의 글로벌 dedup 마스터 "
            "도입 시 join 키. v0.1 에서는 단순 LOWER(word) 또는 lemmatizer 결과."
        ),
    )

    # ─── 뜻 / 등급 / 품사 ─────────────────────────────────────────────────────
    pos: str | None = Field(
        default=None,
        max_length=64,
        description="품사 (예: 'verb', 'noun', 'adj'). v0.1 자유 문자열, 후속 enum 검토.",
    )
    meaning_ko: str = Field(
        ...,
        description="한국어 뜻.",
    )
    level_label: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "어휘 등급 라벨 (자유 문자열, 예: '수능 필수', '고1 교과서'). CEFR / "
            "수능 빈도 / 자체 분류 등을 자유 표기 — Phase 2 enum 정규화 검토."
        ),
    )

    # ─── VocabularyMaster link (ADR-0016 D1 권장안 (a)) ─────────────────────
    master_id: EntityId | None = Field(
        default=None,
        description=(
            "글로벌 어휘 마스터 ID (FK → vocabulary_master.id, NULLABLE). "
            "None 이면 master 미연결 (legacy / 신규 미연결). "
            "link 시 headword_normalized == master.headword_normalized 강제 "
            "(ADR-0016 D2-b — model_validator 로 검증 불가, application 레이어 책임). "
            "ON DELETE SET NULL — master 삭제 시 passage 행은 유지, master_id → NULL."
        ),
    )

    # ─── 추적 메타 ────────────────────────────────────────────────────────────
    selected_by: VocabularySelectedBy = Field(
        ...,
        description="이 어휘를 선택한 주체 (LLM/user/system filter).",
    )
    user_edited: bool = Field(
        default=False,
        description="사용자가 LLM 결과를 수정했는지 여부.",
    )

    # ─── 검증 ─────────────────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _validate_master_link_consistency(self) -> Vocabulary:
        """master_id link 시 headword_normalized 가 비어있지 않음을 확인.

        ADR-0016 D2-b sync 정책:
          master link 시 Vocabulary.headword_normalized 가 있어야 한다.
          master.headword_normalized 와의 일치 검증은 application 레이어 (repository)
          책임 — Pydantic 레이어에서는 master 객체가 없어 cross-entity 검증 불가.
        """
        if self.master_id is not None and not self.headword_normalized.strip():
            raise ValueError(
                "master_id 가 있으면 headword_normalized 는 비어있을 수 없다 (ADR-0016 D2-b)."
            )
        return self
