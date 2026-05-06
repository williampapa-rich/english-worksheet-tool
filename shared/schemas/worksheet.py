"""Worksheet(출력물 단위) 도메인 모델.

CLAUDE.md §6.1:
  - Worksheet 는 ``template + branding(로고, 컬러) + items[] → Passage 참조`` 구조.
  - 학생용 / 교사용 / 변형문제집 / 구문분석 자료 등 다중 템플릿.

audit §4.2 권고를 그대로 반영. exam-generator 의 ``ExamMeta`` (시험지 제목/학교/학년/
시간 등) 는 ``Worksheet.meta`` 로 흡수 — v0.1 에서는 단순 dict 로 두지 않고 별도 모델
없이 Worksheet 에 직접 펼친다 (필드 수가 작고 검색 메타가 아니므로).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from shared.schemas.common import EntityId, WorkspaceScopedEntity


class WorksheetKind(StrEnum):
    """Worksheet 유형.

    - ``STUDENT``: 학생 배포용 자료 (Phase 2 — 지문 + 한글 해석 + 어휘 박스).
    - ``TEACHER``: 교사용 자료 (정답/해설 포함).
    - ``SYNTAX_ANALYSIS``: 구문분석 자료 (Phase 1 — Tiptap 에디터 산출).
    - ``VARIANT_SET``: 변형문제집 (Phase 3).
    """

    STUDENT = "student"
    TEACHER = "teacher"
    SYNTAX_ANALYSIS = "syntax_analysis"
    VARIANT_SET = "variant_set"


class WorksheetOrientation(StrEnum):
    """Worksheet 출력 방향 — A4 페이지 회전.

    - ``PORTRAIT``: 210mm × 297mm (세로). 일반 워크시트 default.
    - ``LANDSCAPE``: 297mm × 210mm (가로). 좌우 비교 / 긴 영어 문장 유지에 유리.

    템플릿 렌더 시 CSS ``@page size`` 분기 + Playwright ``landscape`` 파라미터의
    source. ADR-0010 §D2.
    """

    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class Branding(BaseModel):
    """Worksheet 의 브랜딩 (학원명, 로고, 컬러).

    Phase 2 학생용 템플릿의 컬러/로고 프리셋 변경 (CLAUDE.md Phase 2 DoD).
    템플릿 (``packages/template_renderer/templates/``) 의 ``academy.*`` 변수와 매핑된다
    (ADR-0010 §D3, §D6).
    """

    model_config = ConfigDict(extra="forbid")

    logo_url: str | None = Field(
        default=None,
        description="로고 이미지 URL 또는 storage ref. 템플릿 변수 ``academy.logo_url`` 매핑.",
    )
    primary_color: str | None = Field(
        default=None,
        description=("기본 색상 (HEX, 예: '#1F4E79'). 템플릿 변수 ``academy.theme_color`` 매핑."),
    )
    secondary_color: str | None = Field(
        default=None,
        description=(
            "보조 색상 (HEX). **현 템플릿 (classic / modern / playful) 미사용 — Phase 2 "
            "디자인 확장용 보관 (ADR-0010 §D6).** playful 의 ``--theme-soft`` / "
            "``--theme-mid`` 는 ``color-mix(in srgb, ...)`` 로 자동 생성하므로 본 필드를 "
            "참조하지 않는다. WeasyPrint 등 ``color-mix`` 미지원 PDF 엔진으로 전환 시 "
            "fallback 으로 활성화 가능."
        ),
    )
    academy_name: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "학원/기관 표시명 (출력물 헤더). 템플릿 변수 ``academy.name`` 매핑. "
            "ADR-0010 §D3 — Workspace.name (운영용 라벨) 과 분리해 customer-facing "
            "표시 목적으로 Branding 에 둠."
        ),
    )


class WorksheetItem(BaseModel):
    """Worksheet 안의 항목 1개 — Passage 참조 + 옵션.

    한 Worksheet 안의 ``items`` 순서가 출력물 안의 노출 순서.
    """

    model_config = ConfigDict(extra="forbid")

    passage_id: EntityId = Field(
        ...,
        description="참조 Passage ID (FK → passages.id).",
    )
    order: int = Field(
        ...,
        ge=0,
        description="Worksheet 안의 노출 순서 (0-based).",
    )
    label: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "항목 라벨 (예: '관계절이 포함된 문장', '빈칸 추론 — 주제'). 템플릿 변수 "
            "``questions[].label`` 매핑. ADR-0010 §D1 #4. kind 별 의미: STUDENT 분류 / "
            "TEACHER 출제 의도 / SYNTAX_ANALYSIS 분석 포커스 / VARIANT_SET 변형 유형 "
            "displayed text (``VariantQuestion.variant_kind`` enum 과 별도 — 어댑터에서 "
            "파생할지 후속 결정)."
        ),
    )

    # ─── kind 별 옵션 ────────────────────────────────────────────────────
    include_translation: bool = Field(
        default=False,
        description=(
            "한글 해석 포함 여부 (학생용/교사용). Worksheet.kind 별 default 권고는 "
            "Worksheet 생성 어댑터 책임."
        ),
    )
    include_vocabulary: bool = Field(
        default=False,
        description="어휘 박스 포함 여부.",
    )
    include_syntax_annotations: bool = Field(
        default=False,
        description="구문분석 마크 포함 여부 (kind == SYNTAX_ANALYSIS 권고).",
    )
    include_questions: bool = Field(
        default=False,
        description="원본 Question 포함 여부.",
    )
    include_variants: bool = Field(
        default=False,
        description="변형 Question 포함 여부 (kind == VARIANT_SET 권고).",
    )


class Worksheet(WorkspaceScopedEntity):
    """출력물 단위 — 학생용/교사용/구문분석/변형문제집 등 1개의 인쇄/내보내기 단위.

    한 Worksheet 는 N개의 Passage 를 ``items`` 순서로 포함하며, kind 에 따라 출력
    어댑터 (HWPX/PDF) 가 분기한다.
    """

    title: str = Field(
        ...,
        max_length=255,
        description="Worksheet 제목 (예: '2025 1학기 중간 영어 자료').",
    )
    subtitle: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Worksheet 부제 (예: 'Week 04', 'Mock Exam #2'). 템플릿 변수 "
            "``worksheet.subtitle`` 매핑 (ADR-0010 §D1 #1). 모든 kind 에서 의미 있음."
        ),
    )
    kind: WorksheetKind = Field(
        ...,
        description="Worksheet 유형 (학생용/교사용/구문분석/변형문제집).",
    )
    template_id: str = Field(
        ...,
        description=(
            "템플릿 식별자 (예: 'student_v0_1', 'syntax_v0_1'). 템플릿 카탈로그는 "
            "후속 PR 에서 packages/hwpx_renderer 가 정의."
        ),
    )
    orientation: WorksheetOrientation = Field(
        default=WorksheetOrientation.PORTRAIT,
        description=(
            "출력 방향 (portrait/landscape). 템플릿 변수 ``worksheet.orientation`` 매핑 "
            "(ADR-0010 §D1 #2, §D2). CSS ``@page size`` 분기 + Playwright ``landscape`` "
            "파라미터의 source. default=portrait — 한국 영어 학원 워크시트 디폴트."
        ),
    )
    instruction: str | None = Field(
        default=None,
        max_length=2000,
        description=(
            "워크시트 지시문 (예: '다음 문장을 읽고 어법상 어색한 부분을 고치시오.'). "
            "템플릿 변수 ``instruction`` 매핑 (ADR-0010 §D1 #3). SYNTAX_ANALYSIS 에서는 "
            "보통 빈 값."
        ),
    )

    branding: Branding = Field(
        default_factory=Branding,
        description="브랜딩 (로고, 컬러).",
    )

    # ─── exam-generator ExamMeta 흡수 ────────────────────────────────────
    school: str | None = Field(
        default=None,
        max_length=255,
        description="학교명 (출력물 헤더용).",
    )
    grade: str | None = Field(
        default=None,
        max_length=64,
        description="학년 (출력물 헤더용, 예: '고3 (수능)').",
    )
    exam_date: str | None = Field(
        default=None,
        max_length=64,
        description="시험 일자 또는 발행 일자 (예: '2025-04-10').",
    )
    time_limit: str | None = Field(
        default=None,
        max_length=32,
        description="제한 시간 (예: '45분').",
    )

    items: list[WorksheetItem] = Field(
        default_factory=list,
        description="Worksheet 안의 Passage 항목 리스트 (``order`` 로 정렬).",
    )
