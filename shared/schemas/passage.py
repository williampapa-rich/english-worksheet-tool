"""Passage(영어 지문) 도메인 모델.

PM 결정 D-1 (`docs/adr/_pm-decisions-sprint-0.md`) 반영:
  - ``topic_tags`` / ``source`` / ``target_grade`` 모두 v0.1 필수.
  - CEFR 레벨은 도입하지 않음 ("공식적으로 나눠진 난이도 등급은 없다" — PM).
  - ``SourceMeta`` 는 ``provider`` enum + 출처별 부가 식별자.
  - ``provider == "school_internal"`` 일 때 ``school_name`` 필수 (validator 로 강제).

CLAUDE.md §1.3 가치 명제 "콘텐츠 자산화" 의 핵심 — Passage 는 1급 엔티티이고,
한 번 만들면 Translation / Vocabulary / SyntaxAnnotation / Question 모두가 참조한다.

마커/텍스트 분리 정책 (audit Gap K, ADR-0004 예정):
  본 v0.1 의 ``body_text`` / ``paragraphs`` 는 출제용 마커 (`①②③④⑤`, `_..._`,
  `______` 등) 의 inline 보존 여부에 대해 **중립**이다. Phase 1 진입 전 ADR-0004 에서
  최종 정책 확정. 그 사이의 데이터는 ADR 결정에 따라 마이그레이션 가능.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.schemas.common import WorkspaceScopedEntity


class SourceProvider(StrEnum):
    """Passage 출처 제공자.

    한국 영어 학원 시장 컨텍스트 기반 enum (audit-review-domain §4.5 참고).
    각 provider 별 재배포 정책이 다르므로 출처 메타로 활용 (Phase 4 저작권 ADR).
    """

    AINGKA = "aingka"  # 아잉카 (유료 멤버십)
    EVALUATOR = "evaluator"  # 평가원 (수능/모평)
    EBSI = "ebsi"  # EBSi
    SCHOOL_INTERNAL = "school_internal"  # 학교 내신 기출
    USER_INPUT = "user_input"  # 사용자 직접 입력 (출처 미상 또는 자체 작성)
    OTHER = "other"


class TargetGrade(StrEnum):
    """학년 메타 (audit-review-domain §4.2 권고 반영).

    한국 시장의 학년 분류. ``other`` 는 분류 불명 또는 일반 자료.
    """

    MIDDLE_1 = "middle_1"
    MIDDLE_2 = "middle_2"
    MIDDLE_3 = "middle_3"
    HIGH_1 = "high_1"
    HIGH_2 = "high_2"
    HIGH_3 = "high_3"
    SUNEUNG = "suneung"  # 수능
    OTHER = "other"


class SourceMeta(BaseModel):
    """Passage 출처 메타.

    PM 결정 D-1 명세를 그대로 반영. ``provider == "school_internal"`` 일 때
    ``school_name`` 이 NOT NULL 이며, 다른 provider 에서는 None 허용 (메타용).
    """

    model_config = ConfigDict(extra="forbid")

    provider: SourceProvider = Field(
        ...,
        description="자료 출처 제공자.",
    )
    school_name: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "학교명 (예: '강남고등학교'). ``provider == school_internal`` 일 때 필수, "
            "다른 provider 에서는 메타용으로 허용 (None 가능)."
        ),
    )
    exam_year: int | None = Field(
        default=None,
        ge=1990,
        le=2100,
        description="시험 연도 (예: 2025).",
    )
    exam_round: str | None = Field(
        default=None,
        max_length=255,
        description="시험 회차 (예: '6월 모의평가', '1학기 중간고사').",
    )
    original_question_number: int | None = Field(
        default=None,
        ge=1,
        le=99,
        description="원자료에서의 문항 번호.",
    )
    note: str | None = Field(
        default=None,
        description="자유 텍스트 메모.",
    )

    @model_validator(mode="after")
    def _validate_school_internal_requires_school_name(self) -> SourceMeta:
        """``provider == school_internal`` 일 때 ``school_name`` 필수 강제.

        PM 결정 D-1 의 검증 로직. 다른 provider 에서는 ``school_name`` 이 있어도 무방
        (메타용으로 허용).
        """
        if self.provider == SourceProvider.SCHOOL_INTERNAL and not self.school_name:
            raise ValueError("provider == 'school_internal' 일 때 school_name 은 필수다.")
        return self


class Passage(WorkspaceScopedEntity):
    """정규화된 영어 지문 — 시스템의 핵심 콘텐츠 자산.

    한 Passage 는 여러 Translation / Vocabulary / SyntaxAnnotation / Question 의
    참조 대상이 된다 (CLAUDE.md §1.3, §6.1).

    필수 메타 (PM 결정 D-1):
      - ``source``: SourceMeta — 출처 제공자 + 부가 식별자.
      - ``topic_tags``: list[str] — 자유 문자열 키워드. v0.1 에서는 enum 정규화 안 함.
      - ``target_grade``: TargetGrade enum — 학년 메타.
      - ``word_count``: int — body_text 단어 수 (시스템 자동 계산).

    제외 (PM 결정 D-1):
      - CEFR 레벨 (cefr_level) — 도입하지 않음.
      - subject_domain (과학/인문/사회) — v0.2 검토.
      - 수능 빈도 등급 — v0.2 검토.
    """

    # ─── 본문 ────────────────────────────────────────────────────────────────
    body_text: str = Field(
        ...,
        description=(
            "본문 영어 텍스트. 마커 분리 정책은 ADR-0004 (Phase 1 진입 전 확정) 에서 "
            "최종 결정 — v0.1 은 출제용 마커 inline 여부에 중립."
        ),
    )
    paragraphs: list[str] = Field(
        default_factory=list,
        description="단락 분할 (입력 보존 + 렌더링 단위).",
    )
    word_count: int = Field(
        ...,
        ge=0,
        description="``body_text`` 의 단어 수 (시스템이 자동 계산해 채움).",
    )

    # ─── 메타 ────────────────────────────────────────────────────────────────
    source: SourceMeta = Field(
        ...,
        description="자료 출처 메타 (PM 결정 D-1 — v0.1 필수).",
    )
    topic_tags: list[str] = Field(
        default_factory=list,
        description=(
            "주제 키워드 (자유 문자열, 빈 list 허용). domain-expert 후속 카탈로그에서 "
            "enum 정규화 검토 가능."
        ),
    )
    target_grade: TargetGrade = Field(
        ...,
        description="학년 메타 (audit-review-domain §4.2 도메인 권고 반영).",
    )

    # ─── 비고 ────────────────────────────────────────────────────────────────
    # parser/LLM 메타 (audit Gap N — naturalness_check 등) 는 Question 으로 이동.
    # Passage 는 LLM 입력의 자기검증 메타가 없는 게 자연스럽다 (raw 콘텐츠).
