"""SyntaxAnnotation(구문분석 마크) 도메인 모델.

본 모듈은 ``docs/reference-program-analysis.md`` §4.3 의 권고 모델을 v0.1 로 흡수한다.
영상 레퍼런스에서 식별된 7종 ``kind`` + 5종 ``category`` + 12색 ``color_index`` 팔레트
구조를 채택한다.

**Span 식별 방식 — 미해결 (ADR-0003 예정)**:
  - audit §4-4 / audit-review-domain §3.4 / reference-program-analysis §4.1 의
    3자 의견을 종합해 Phase 1 진입 전 ADR-0003 에서 확정한다.
  - architect 1차 권고 = character offset, domain-expert 권고 = token id, 영상 레퍼런스
    = 단어 단위 선택. 결정 후보:
      a) character offset (단순, 텍스트 변경에 취약)
      b) token id (직관적, 토큰화 정책 결정 필요)
      c) ProseMirror position (Tiptap-native, 에디터 외부 해석 부담)
  - **본 v0.1 은 placeholder** — ``span_format`` 디스크리미네이터 +
    ``AnnotationSpan`` 의 모호한 dict 구조로 미래 확장을 보장한다. ADR-0003 에서
    구체 schema 가 확정되면 ``AnnotationSpan`` 을 discriminated union 으로 교체.

**Annotation 통합 vs 마커 분리 — 미해결 (ADR-0004 예정)**:
  - audit-review-domain §3.5 권고: 출제용 마커 (``marker_circled`` / ``marker_blank``
    등) 와 구문분석 마커 (``top_label`` / ``bracket`` 등) 가 데이터 모델은 통합
    가능하되 개념적으로 별 카테고리. 현재 v0.1 은 **구문분석 마커만** 다룬다.
  - 출제용 마커는 Phase 1 진입 전 ADR-0004 에서 이 모델에 흡수할지 결정.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from shared.schemas.common import EntityId, WorkspaceScopedEntity


class AnnotationKind(StrEnum):
    """Annotation 종류 (영상 레퍼런스 §2 + CLAUDE.md Phase 1 DoD).

    - ``top_label``: 본문 위 라벨 (예: ``=동명사주어``, ``S``, ``(부사구)``).
    - ``bottom_label``: 본문 아래 한 글자 약어 (예: ``S``, ``V``, ``O``).
    - ``highlight``: 형광펜 (배경색).
    - ``bracket``: 괄호 (), {}, [].
    - ``arrow``: 단어 간 의미 관계 화살표.
    - ``inline_note``: 본문 위 작은 글씨 어휘 동의어 (예: ``=foster, promote``).
    - ``underline``: 밑줄. CLAUDE.md §2.1 명시이지만 영상에서 미관찰 — 자리만 둠.
    """

    TOP_LABEL = "top_label"
    BOTTOM_LABEL = "bottom_label"
    HIGHLIGHT = "highlight"
    BRACKET = "bracket"
    ARROW = "arrow"
    INLINE_NOTE = "inline_note"
    UNDERLINE = "underline"


class AnnotationCategory(StrEnum):
    """하단 분석표 행 분류 (영상 레퍼런스 §3.3).

    레퍼런스 프로그램은 본문에 마크를 추가하면 하단 분석표의 5개 카테고리 행에 자동
    누적한다. 본 카테고리는 그 행을 결정한다.
    """

    NOTE = "note"  # 주석
    SENTENCE_ROLE = "sentence_role"  # 주성분 (S/V/O/OC/SC)
    PHRASE = "phrase"  # 구
    CLAUSE = "clause"  # 절
    OTHER = "other"  # 기타


class SpanFormat(StrEnum):
    """``AnnotationSpan`` 의 식별 방식 디스크리미네이터.

    Phase 1 진입 전 ADR-0003 에서 최종 식별 방식 확정. v0.1 은 placeholder 로
    ``character_offset_v1`` 만 정의 — 후속 ADR 에서 ``token_id_v1`` /
    ``prosemirror_pos_v1`` 등을 추가하고 discriminated union 으로 교체 가능.
    """

    CHARACTER_OFFSET_V1 = "character_offset_v1"


class AnnotationSpan(BaseModel):
    """Annotation 의 본문 내 위치 식별자 (placeholder).

    **주의**: 본 모델은 v0.1 placeholder 다. 실제 식별 방식은 Phase 1 진입 전
    ADR-0003 에서 확정되며, 그 결과에 따라 본 클래스가 discriminated union 으로
    교체될 수 있다.

    현재 ``span_format == "character_offset_v1"`` 일 때 ``data`` 는 다음 형태:
        ``{"start": int, "end": int}``  ← ``Passage.body_text`` 위 [start, end) 반열린 구간

    ``data`` 를 ``dict[str, Any]`` 로 둔 이유:
      - ADR-0003 미확정 상태에서 다양한 실험(token id, ProseMirror pos)을 흡수.
      - mypy strict 환경에서도 placeholder 로서 의미 명시.
      - 후속 ADR 결정 시 ``AnnotationSpan`` 을 discriminated union 으로 교체하면
        기존 데이터는 ``data`` 의 키 마이그레이션만 필요.
    """

    model_config = ConfigDict(extra="forbid")

    span_format: Literal["character_offset_v1"] = Field(
        default="character_offset_v1",
        description=(
            "Span 식별 방식 디스크리미네이터. v0.1 은 ``character_offset_v1`` 단일 — "
            "ADR-0003 에서 확장."
        ),
    )
    data: dict[str, Any] = Field(
        ...,
        description=(
            "``span_format`` 별 위치 데이터. ``character_offset_v1`` 일 때 "
            "``{'start': int, 'end': int}``."
        ),
    )


class SyntaxAnnotation(WorkspaceScopedEntity):
    """Passage 위 구문분석 마크 1개.

    영상 레퍼런스 (`docs/reference-program-analysis.md`) §4.3 의 권고 모델을 그대로
    흡수. ``span`` 의 식별 방식은 ADR-0003 에서 확정 예정 — v0.1 은
    ``AnnotationSpan`` placeholder 로 모호화.

    Annotation 의 의미 흐름:
      - ``kind`` = 시각적 표현 종류 (top_label/highlight/bracket 등).
      - ``category`` = 하단 분석표 행 (note/sentence_role/phrase/clause/other).
      - ``color_index`` = 12색 팔레트 인덱스 (1~12).
      - ``text`` = top_label / inline_note / bottom_label 의 표시 텍스트.
      - ``bracket_style`` = 괄호 모양 (kind == bracket 일 때).
      - ``arrow_target_span`` = 화살표 도착점 span (kind == arrow 일 때).
    """

    passage_id: EntityId = Field(
        ...,
        description="참조 Passage ID (FK → passages.id).",
    )

    kind: AnnotationKind = Field(
        ...,
        description="Annotation 시각 종류 (영상 레퍼런스 §2 의 7종).",
    )
    category: AnnotationCategory | None = Field(
        default=None,
        description=(
            "하단 분석표 행 분류 (영상 레퍼런스 §3.3). Optional — 어떤 마크는 분석표에 "
            "안 들어가거나 분류 미정일 수 있음."
        ),
    )

    span: AnnotationSpan = Field(
        ...,
        description=(
            "본문 내 위치 (시작점). 식별 방식은 ADR-0003 에서 확정 — v0.1 은 placeholder."
        ),
    )

    color_index: int | None = Field(
        default=None,
        ge=1,
        le=12,
        description="12색 팔레트 인덱스 (1~12). 영상 레퍼런스 §1 / §3.2 참고.",
    )
    text: str | None = Field(
        default=None,
        description=(
            "표시 텍스트 — ``top_label`` / ``bottom_label`` / ``inline_note`` 일 때 사용. "
            "``highlight`` / ``bracket`` 등 시각만 적용되는 종류는 None."
        ),
    )

    bracket_style: Literal["()", "{}", "[]"] | None = Field(
        default=None,
        description="괄호 모양 (``kind == bracket`` 일 때).",
    )
    arrow_target_span: AnnotationSpan | None = Field(
        default=None,
        description=("화살표 도착점 span (``kind == arrow`` 일 때). 출발점은 ``span``."),
    )
