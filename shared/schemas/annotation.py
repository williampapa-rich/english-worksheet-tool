"""SyntaxAnnotation(구문분석 마크) 도메인 모델.

본 모듈은 ``docs/reference-program-analysis.md`` §4.3 의 권고 모델을 v0.2 로 흡수한다.
영상 레퍼런스에서 식별된 7종 ``kind`` + 5종 ``category`` + 12색 ``color_index`` 팔레트
구조를 채택한다.

**v0.2 변경 (P1-3, ADR-0004 결정 적용)**:
  - ``AnnotationSpan`` placeholder (``data: dict[str, Any]``) 폐기.
  - ADR-0004 채택안 (D 하이브리드 — 영속화 character offset) 에 따라
    ``CharacterOffsetV1Span(start: int, end: int)`` 1급 필드로 승격.
  - 미래 확장 (예: ``prosemirror_pos_v1``) 을 위해 ``Annotated[Union[...],
    Discriminator("span_format")]`` 구조를 유지 — 단일 멤버 union 이라도 디스크리미네이터
    유지로 추가 시 무손실 확장 가능.
  - ``arrow`` kind 의 양 끝점 표현 정식화: 출발점 = ``span``,
    도착점 = ``arrow_target_span``. 두 필드 모두 동일 ``AnnotationSpan`` 타입.
    이 비대칭은 ProseMirror mark 가 출발점을 자연스럽게 잡는 구조와 정합한다
    (ADR-0004 §"후속 작업" 참조).
  - ``kind == arrow ↔ arrow_target_span is not None`` model validator 강제.

**v0.3 변경 (P1-annotation-input-dto)**:
  - ``SyntaxAnnotationInput`` API 입력 DTO 추가 (architect 검토 요청 — 필드 변경 최소화).
    클라이언트가 모를 수 없는 서버-side 컨텍스트 필드 (``tenant_id``,
    ``workspace_id``, ``passage_id``) 를 required 에서 제거. 라우터가 path param +
    TenantContext 로 주입.
  - ``SyntaxAnnotation`` 에 ``annotation_id: UUID | None`` 추가 (ADR-Lite — 옵션 A
    영속화 채택). 에디터 chip 단위 그룹 ID 를 DB 에 보존해 라운드트립 강건성을 확보.
    이 필드는 PK ``id`` (DB 부여 UUID) 와 별개로 에디터가 관리하는 논리 식별자.

**Annotation 통합 vs 마커 분리** (ADR-0006):
  - 출제용 마커 (``marker_circled`` / ``marker_blank`` 등) 는 ADR-0006 결정에 따라 본
    ``SyntaxAnnotation`` 모델 외부 (Question.markers 또는 Passage 메타) 에서 다룬다.
    본 모델은 **구문분석 마크 전용**.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Discriminator, Field, model_validator

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

    ADR-0004 채택안에 따라 v0.2 의 정식 형태는 ``character_offset_v1`` 단일.
    미래 확장 (예: ``prosemirror_pos_v1`` 메모리-side 표현 영속화 필요 시,
    또는 token id 도입 시) 은 본 enum 에 값을 추가하고 ``AnnotationSpan`` union 에
    멤버를 늘리는 방식. 디스크리미네이터 구조 자체는 미래 확장에 맞춰 유지된다.
    """

    CHARACTER_OFFSET_V1 = "character_offset_v1"


class CharacterOffsetV1Span(BaseModel):
    """ADR-0004 채택안 — ``Passage.body_text`` 위 character offset.

    ``[start, end)`` 반열린 구간. body_text 는 ADR-0006 의 마커 처리 정책에 따라
    출제용 마커가 분리된 정제 영어 본문 — annotation offset 은 그 정제 본문 기준.
    """

    model_config = ConfigDict(extra="forbid")

    span_format: Literal[SpanFormat.CHARACTER_OFFSET_V1] = Field(
        default=SpanFormat.CHARACTER_OFFSET_V1,
        description="Span 식별 방식 디스크리미네이터.",
    )
    start: int = Field(
        ...,
        ge=0,
        description="본문 내 시작 글자 위치 (inclusive, 0-based).",
    )
    end: int = Field(
        ...,
        gt=0,
        description="본문 내 끝 글자 위치 (exclusive). ``end > start`` 강제.",
    )

    @model_validator(mode="after")
    def _check_end_after_start(self) -> CharacterOffsetV1Span:
        if self.end <= self.start:
            raise ValueError(f"AnnotationSpan: end ({self.end}) must be > start ({self.start}).")
        return self


# Discriminated union — 미래 확장 (prosemirror_pos_v1 등) 시 멤버 추가만으로 무손실 확장.
# 단일 멤버 union 이라도 Discriminator 유지로 직렬화 형태 (span_format key 포함) 안정.
AnnotationSpan = Annotated[
    CharacterOffsetV1Span,
    Discriminator("span_format"),
]
"""Annotation 의 본문 내 위치 식별자 (discriminated union).

ADR-0004 채택안 = ``CharacterOffsetV1Span`` 1단 union.
미래 확장 — 본 union 에 멤버 추가 + ``SpanFormat`` enum 값 추가."""


class SyntaxAnnotation(WorkspaceScopedEntity):
    """Passage 위 구문분석 마크 1개.

    영상 레퍼런스 (`docs/reference-program-analysis.md`) §4.3 의 권고 모델 흡수.
    ``span`` 은 ADR-0004 채택안 (character offset) 으로 정식화된다 (v0.2).

    필드 의미:
      - ``kind`` = 시각적 표현 종류 (top_label/highlight/bracket 등).
      - ``category`` = 하단 분석표 행 (note/sentence_role/phrase/clause/other).
      - ``color_index`` = 12색 팔레트 인덱스 (1~12).
      - ``text`` = top_label / inline_note / bottom_label 의 표시 텍스트.
      - ``bracket_style`` = 괄호 모양 (kind == bracket 일 때).
      - ``span`` = 본문 내 위치 (모든 kind 의 출발점 — arrow 의 출발점 포함).
      - ``arrow_target_span`` = 화살표 도착점 span (kind == arrow 일 때만).
        모델 invariant: ``kind == arrow ↔ arrow_target_span is not None`` (validator 강제).
      - ``annotation_id`` = 에디터 chip 단위 논리 ID (v0.3 추가). 에디터가 부여하는
        그룹 식별자로, DB PK ``id`` 와 별개. 라운드트립 시 에디터 상태 복원에 사용.
        nullable — 에디터가 미지정하거나 구형 클라이언트 호환 시 None 가능.
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
        description="본문 내 위치. arrow kind 일 땐 출발점.",
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
        description=(
            "화살표 도착점 span (``kind == arrow`` 일 때 필수). 출발점은 ``span``. "
            "ADR-0004 §후속작업 참조 — ProseMirror mark 가 출발점을 자연스럽게 잡는 "
            "구조와의 정합으로 비대칭 표현 채택."
        ),
    )

    annotation_id: UUID | None = Field(
        default=None,
        description=(
            "에디터 chip 단위 논리 식별자 (v0.3, P1-annotation-input-dto). "
            "DB PK ``id`` 와 별개 — 에디터(Tiptap)가 chip 그룹에 부여하는 UUID. "
            "같은 chip 의 여러 mark 가 동일 annotation_id 를 공유. "
            "nullable — 구형 클라이언트 또는 에디터가 미지정 시 None."
        ),
    )

    @model_validator(mode="after")
    def _check_arrow_target(self) -> SyntaxAnnotation:
        if self.kind == AnnotationKind.ARROW and self.arrow_target_span is None:
            raise ValueError("SyntaxAnnotation: kind == 'arrow' requires arrow_target_span.")
        if self.kind != AnnotationKind.ARROW and self.arrow_target_span is not None:
            raise ValueError(
                f"SyntaxAnnotation: arrow_target_span is only valid when "
                f"kind == 'arrow' (got kind == {self.kind.value!r})."
            )
        return self


class SyntaxAnnotationInput(BaseModel):
    """POST /passages/{passage_id}/annotations 의 개별 annotation 입력 DTO.

    **architect 검토 요청**: 본 모델은 ``SyntaxAnnotation`` 도메인 모델의 sibling 으로
    ``shared/schemas/annotation.py`` 에 위치한다. 의존성 방향 (shared → apps) 위반 없음.
    도메인 모델에 비해 서버-side 컨텍스트 필드가 제거 또는 optional 화된 API 전용 입력 뷰.

    **P1-annotation-input-dto ADR-Lite**:
      ``tenant_id`` / ``workspace_id`` / ``passage_id`` 를 클라이언트 입력에서 제거:
        - ``tenant_id``, ``workspace_id``: TenantContext (서버 의존성 주입) 으로 결정.
          클라이언트가 이 값을 알 방법이 없고, 알더라도 신뢰할 수 없다.
        - ``passage_id``: URL path param 으로 전달됨 — body 중복은 불필요.
      ``annotation_id``: 에디터 chip ID 영속화 (옵션 A 채택) — 클라이언트가 보내면 저장.
      ``id``, ``created_at``, ``updated_at``: 서버 생성 값 — 입력 불필요.

    라우터는 본 DTO 를 수신 후 ``tenant_id`` / ``workspace_id`` / ``passage_id`` 를 주입해
    ``SyntaxAnnotation`` 도메인 모델로 변환한다.
    """

    model_config = ConfigDict(extra="forbid")

    kind: AnnotationKind = Field(
        ...,
        description="Annotation 시각 종류 (영상 레퍼런스 §2 의 7종).",
    )
    category: AnnotationCategory | None = Field(
        default=None,
        description="하단 분석표 행 분류. Optional.",
    )
    span: AnnotationSpan = Field(
        ...,
        description="본문 내 위치. arrow kind 일 땐 출발점.",
    )
    color_index: int | None = Field(
        default=None,
        ge=1,
        le=12,
        description="12색 팔레트 인덱스 (1~12).",
    )
    text: str | None = Field(
        default=None,
        description="표시 텍스트 (top_label / bottom_label / inline_note).",
    )
    bracket_style: Literal["()", "{}", "[]"] | None = Field(
        default=None,
        description="괄호 모양 (kind == bracket 일 때).",
    )
    arrow_target_span: AnnotationSpan | None = Field(
        default=None,
        description="화살표 도착점 span (kind == arrow 일 때 필수).",
    )
    annotation_id: UUID | None = Field(
        default=None,
        description=(
            "에디터 chip 단위 논리 식별자. DB PK 와 별개. "
            "같은 chip 의 여러 mark 가 동일 annotation_id 를 공유."
        ),
    )

    @model_validator(mode="after")
    def _check_arrow_target(self) -> SyntaxAnnotationInput:
        if self.kind == AnnotationKind.ARROW and self.arrow_target_span is None:
            raise ValueError("SyntaxAnnotationInput: kind == 'arrow' requires arrow_target_span.")
        if self.kind != AnnotationKind.ARROW and self.arrow_target_span is not None:
            raise ValueError(
                f"SyntaxAnnotationInput: arrow_target_span is only valid when "
                f"kind == 'arrow' (got kind == {self.kind.value!r})."
            )
        return self
