"""VocabularyMaster (글로벌 어휘 dedup) 도메인 모델.

ADR-0016 D1 권장안 (a) 구현:
  별 ``VocabularyMaster`` 테이블 + ``Vocabulary.master_id`` nullable FK.
  ``tenant_id`` 별 글로벌 단어장 — UNIQUE (tenant_id, headword_normalized).

결정 사항 (ADR-0016):
  - D1=(a): 별 테이블 + Vocabulary.master_id nullable FK.
  - D2-c: passage 행 (Vocabulary.meaning_ko) 이 master default 와 다르면
    passage-specific override — master prefill / fallback 으로만 활용.
  - D3: tenant_id 별 UNIQUE — master 는 강사별 단어장 (cross-tenant 공유 없음).
  - D5: 학년 분리 X + homonym 는 별 행 (headword_normalized 구별 — Phase 4 검토).
  - D6: Phase 2-edit Stage E2 머지 후 backfill (별 PR).

Stage E1-c 통합 완료 (feat/stage-e1-c-vocabulary-master-integration):
  - ``POST /passages/{id}/vocabulary/manual`` (manual add) 라우트:
    headword_normalized 계산 → master 조회/생성 → Vocabulary.master_id 채움.
    created_by=USER. ADR-0016 D2-c override 정책 적용.
  - ``POST /passages/{id}/vocabulary`` (LLM 보강) 라우트:
    각 LLM 어휘마다 master 조회/생성 → Vocabulary.master_id 채움.
    created_by=LLM. ADR-0013 mode 정책은 그대로 유지.
  - ``DELETE /passages/{id}/vocabulary/{vid}``:
    master_id 있는 vocabulary 삭제 시 master.usage_count -= 1.
  - ``VocabularyMasterRepository.find_by_headword`` /
    ``increment_usage_count`` / ``decrement_usage_count`` 신규.

멀티테넌트:
  ``WorkspaceScopedEntity`` 베이스 — ``tenant_id`` + ``workspace_id`` 포함.
  UNIQUE 제약은 (tenant_id, headword_normalized) — DB 레벨 (Alembic).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from shared.schemas.common import WorkspaceScopedEntity


class VocabularyMasterCreatedBy(StrEnum):
    """VocabularyMaster 생성 주체.

    ADR-0016 D2-a 정의.
    """

    LLM = "llm"
    USER = "user"
    IMPORT = "import"  # 대량 import (CSV 등) — Phase 4 별 chore


class VocabularyMaster(WorkspaceScopedEntity):
    """글로벌 어휘 dedup 마스터 (tenant 별).

    한 강사(tenant)의 평생 단어장 자산. 동일 ``headword_normalized`` 는 tenant 안에서
    1행만 존재 (UNIQUE per tenant_id — ADR-0016 D3).

    ``Vocabulary`` 와의 관계:
      - ``Vocabulary.master_id`` 가 이 테이블을 FK 참조.
      - ``Vocabulary.master_id`` 가 NULL 이면 master link 없음 (legacy / 신규 미연결).
      - ``Vocabulary.meaning_ko`` 가 ``default_meaning_ko`` 와 다르면 passage-specific
        override (ADR-0016 D2-c — passage 행 우선).

    ``usage_count``:
      master 가 link 된 ``Vocabulary`` 행 수 캐시. 보강 라우트 / Stage E1-c 에서 갱신.
      usage_count = 0 인 master 는 삭제하지 않음 (개인 단어장 자산 보존 — ADR-0016 D4-a).

    homonym (다의어) 정책 (ADR-0016 D5):
      v0.1 은 1행 1뜻 (``default_meaning_ko`` 1개) + passage override (D2-c) 로 흡수.
      Phase 4 에서 (i) meaning_ko → list[str] 검토.
    """

    # ─── 표제어 ──────────────────────────────────────────────────────────────
    headword_normalized: str = Field(
        ...,
        max_length=255,
        description=(
            "정규화된 표제어 (소문자 + lemma). UNIQUE per (tenant_id, headword_normalized) — "
            "DB 레벨 UNIQUE 인덱스. ``Vocabulary.headword_normalized`` 와 동일해야 link 가능 "
            "(ADR-0016 D2-b sync 정책)."
        ),
    )
    word_canonical: str = Field(
        ...,
        max_length=255,
        description=(
            "lemma 표면형 (대소문자 보존 표시용). 예: 'endeavor'. "
            "``headword_normalized`` 는 소문자 ('endeavor'), ``word_canonical`` 은 "
            "표시용 (예: 'Endeavor' 도 가능)."
        ),
    )

    # ─── master 기본 뜻 / 품사 / 등급 ────────────────────────────────────────
    default_meaning_ko: str = Field(
        ...,
        description=(
            "master 기본 한국어 뜻. passage 별 override 허용 (ADR-0016 D2-c). "
            "Stage E1-c 에서 manual add 시 prefill 값으로 사용."
        ),
    )
    default_pos: str | None = Field(
        default=None,
        max_length=64,
        description="master 기본 품사 (예: 'verb', 'noun'). v0.1 자유 문자열.",
    )
    default_level_label: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "master 기본 등급 라벨 (예: '수능 필수', '고1 교과서'). "
            "ADR-0016 D5 — 학년 분리 X, 단일 label 로 통합."
        ),
    )

    # ─── 통계 메타 ────────────────────────────────────────────────────────────
    usage_count: int = Field(
        default=0,
        ge=0,
        description=(
            "이 master 에 link 된 Vocabulary 행 수 (캐시). "
            "보강 라우트 / Stage E1-c POST 시 +1, E1-d DELETE 시 -1. "
            "usage_count = 0 인 master 는 유지 (개인 단어장 자산 보존 — ADR-0016 D4-a)."
        ),
    )

    # ─── 생성 주체 ────────────────────────────────────────────────────────────
    created_by: VocabularyMasterCreatedBy = Field(
        ...,
        description="master 생성 주체 (LLM 보강 / 사용자 직접 / 대량 import).",
    )
