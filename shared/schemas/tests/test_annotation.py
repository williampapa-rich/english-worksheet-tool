"""SyntaxAnnotation v0.2 단위 테스트 (P1-3, ADR-0004 적용 후).

검증 대상:
  - ``CharacterOffsetV1Span`` 의 정수 검증 (start/end 경계, end > start)
  - ``AnnotationSpan`` discriminated union — span_format 디스크리미네이터로 라우팅
  - ``SyntaxAnnotation`` 의 arrow ↔ arrow_target_span invariant
  - 직렬화 형태 (TS 미러와의 계약)
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import TypeAdapter, ValidationError

from shared.schemas.annotation import (
    AnnotationCategory,
    AnnotationKind,
    AnnotationSpan,
    CharacterOffsetV1Span,
    SpanFormat,
    SyntaxAnnotation,
)

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
PASSAGE_ID = uuid.uuid4()


def _make(**kwargs: object) -> SyntaxAnnotation:
    defaults: dict[str, object] = dict(
        tenant_id=TENANT_ID,
        workspace_id=WORKSPACE_ID,
        passage_id=PASSAGE_ID,
        kind=AnnotationKind.HIGHLIGHT,
        span=CharacterOffsetV1Span(start=0, end=3),
    )
    defaults.update(kwargs)
    return SyntaxAnnotation(**defaults)  # type: ignore[arg-type]


class TestCharacterOffsetV1Span:
    def test_basic(self) -> None:
        s = CharacterOffsetV1Span(start=4, end=11)
        assert s.start == 4
        assert s.end == 11
        assert s.span_format == SpanFormat.CHARACTER_OFFSET_V1

    def test_default_span_format(self) -> None:
        # span_format 미지정 시 기본값.
        s = CharacterOffsetV1Span(start=0, end=1)
        assert s.span_format == SpanFormat.CHARACTER_OFFSET_V1

    def test_negative_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CharacterOffsetV1Span(start=-1, end=5)

    def test_zero_end_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CharacterOffsetV1Span(start=0, end=0)

    def test_end_le_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CharacterOffsetV1Span(start=10, end=5)

    def test_end_equal_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CharacterOffsetV1Span(start=5, end=5)

    def test_serialization_form(self) -> None:
        # TS 미러 계약 — { span_format, start, end } 평탄 구조 (data dict 없음).
        s = CharacterOffsetV1Span(start=4, end=11)
        dumped = s.model_dump(mode="json")
        assert dumped == {
            "span_format": "character_offset_v1",
            "start": 4,
            "end": 11,
        }


class TestAnnotationSpanDiscriminator:
    def test_dict_validates_via_discriminator(self) -> None:
        adapter: TypeAdapter[AnnotationSpan] = TypeAdapter(AnnotationSpan)
        s = adapter.validate_python({"span_format": "character_offset_v1", "start": 0, "end": 7})
        assert isinstance(s, CharacterOffsetV1Span)
        assert s.start == 0
        assert s.end == 7

    def test_unknown_span_format_rejected(self) -> None:
        adapter: TypeAdapter[AnnotationSpan] = TypeAdapter(AnnotationSpan)
        with pytest.raises(ValidationError):
            adapter.validate_python(
                {"span_format": "prosemirror_pos_v1", "from_pos": 0, "to_pos": 1}
            )


class TestSyntaxAnnotationArrowInvariant:
    def test_non_arrow_without_target_ok(self) -> None:
        ann = _make(kind=AnnotationKind.HIGHLIGHT)
        assert ann.arrow_target_span is None

    def test_arrow_requires_target(self) -> None:
        with pytest.raises(ValidationError, match="requires arrow_target_span"):
            _make(kind=AnnotationKind.ARROW)

    def test_arrow_with_target_ok(self) -> None:
        ann = _make(
            kind=AnnotationKind.ARROW,
            span=CharacterOffsetV1Span(start=0, end=2),
            arrow_target_span=CharacterOffsetV1Span(start=10, end=16),
        )
        assert ann.kind == AnnotationKind.ARROW
        assert ann.arrow_target_span is not None
        assert ann.arrow_target_span.start == 10

    def test_non_arrow_with_target_rejected(self) -> None:
        with pytest.raises(ValidationError, match="only valid when kind == 'arrow'"):
            _make(
                kind=AnnotationKind.HIGHLIGHT,
                arrow_target_span=CharacterOffsetV1Span(start=10, end=16),
            )


class TestSyntaxAnnotationCategoryAndExtras:
    def test_category_optional(self) -> None:
        ann = _make()
        assert ann.category is None

    def test_category_set(self) -> None:
        ann = _make(category=AnnotationCategory.SENTENCE_ROLE)
        assert ann.category == AnnotationCategory.SENTENCE_ROLE

    def test_color_index_range(self) -> None:
        with pytest.raises(ValidationError):
            _make(color_index=0)
        with pytest.raises(ValidationError):
            _make(color_index=13)
        ann = _make(color_index=12)
        assert ann.color_index == 12

    def test_bracket_style_literal(self) -> None:
        ann = _make(kind=AnnotationKind.BRACKET, bracket_style="()")
        assert ann.bracket_style == "()"
        with pytest.raises(ValidationError):
            _make(kind=AnnotationKind.BRACKET, bracket_style="<>")
