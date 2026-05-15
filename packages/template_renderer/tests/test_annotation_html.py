"""render_annotations_to_html 단위 테스트 (ADR-0014).

매핑 검증:
  - highlight 12색
  - underline
  - inline_note (sup 메모)
  - top_label (<ruby>)
  - bottom_label (data-label)
  - bracket Unicode (5종)
  - arrow skip + 로그
  - XSS escape (D6)
  - 중첩 / out-of-range 처리 (D5)
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import pytest
from template_renderer.annotation_html import render_annotations_to_html

from shared.schemas.annotation import (
    AnnotationKind,
    CharacterOffsetV1Span,
    SyntaxAnnotation,
)
from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade


def _make_passage(body_text: str = "The economy is growing.") -> Passage:
    return Passage(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        workspace_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        body_text=body_text,
        word_count=len(body_text.split()),
        source=SourceMeta(provider=SourceProvider.USER_INPUT),
        target_grade=TargetGrade.HIGH_3,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )


def _make_annotation(
    kind: AnnotationKind,
    start: int,
    end: int,
    *,
    text: str | None = None,
    color_index: int | None = None,
    bracket_style: str | None = None,
    arrow_target_span: CharacterOffsetV1Span | None = None,
) -> SyntaxAnnotation:
    return SyntaxAnnotation(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        workspace_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        passage_id=uuid.uuid4(),
        kind=kind,
        span=CharacterOffsetV1Span(start=start, end=end),
        text=text,
        color_index=color_index,
        bracket_style=bracket_style,  # type: ignore[arg-type]
        arrow_target_span=arrow_target_span,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )


# ─── 기본 ────────────────────────────────────────────────────────────────────


def test_no_annotations_returns_escaped_body() -> None:
    """annotation 0개 → body_text 그대로 escape 후 <p> wrap."""
    passage = _make_passage("Hello & world")
    result = render_annotations_to_html(passage, [])
    assert result == '<p class="annot-passage">Hello &amp; world</p>'


def test_empty_body_text() -> None:
    """body_text 가 빈 문자열이면 빈 <p>."""
    passage = _make_passage("")
    result = render_annotations_to_html(passage, [])
    assert result == '<p class="annot-passage"></p>'


# ─── highlight ──────────────────────────────────────────────────────────────


def test_highlight_color_index_1() -> None:
    passage = _make_passage("Hello world")
    ann = _make_annotation(AnnotationKind.HIGHLIGHT, 0, 5, color_index=1)
    result = str(render_annotations_to_html(passage, [ann]))
    assert "annot-highlight annot-highlight--1" in result
    assert ">Hello<" in result


def test_highlight_color_index_12() -> None:
    passage = _make_passage("Hello world")
    ann = _make_annotation(AnnotationKind.HIGHLIGHT, 6, 11, color_index=12)
    result = str(render_annotations_to_html(passage, [ann]))
    assert "annot-highlight--12" in result


def test_highlight_color_index_out_of_range_fallback_to_1() -> None:
    """schema 가 1~12 강제하지만 방어적 fallback 검증."""
    from template_renderer.annotation_html import _highlight_class

    assert _highlight_class(0) == "annot-highlight annot-highlight--1"
    assert _highlight_class(99) == "annot-highlight annot-highlight--1"


# ─── underline ──────────────────────────────────────────────────────────────


def test_underline() -> None:
    passage = _make_passage("Hello world")
    ann = _make_annotation(AnnotationKind.UNDERLINE, 0, 5)
    result = str(render_annotations_to_html(passage, [ann]))
    assert '<span class="annot-underline">Hello</span>' in result


# ─── inline_note ────────────────────────────────────────────────────────────


def test_inline_note_with_sup() -> None:
    passage = _make_passage("Hello world")
    ann = _make_annotation(AnnotationKind.INLINE_NOTE, 0, 5, text="중요")
    result = str(render_annotations_to_html(passage, [ann]))
    assert '<span class="annot-inline-note">Hello' in result
    assert '<sup class="annot-inline-note__text">중요</sup>' in result


def test_inline_note_text_escaped() -> None:
    """inline_note text 의 HTML 특수문자 escape."""
    passage = _make_passage("Hello")
    ann = _make_annotation(AnnotationKind.INLINE_NOTE, 0, 5, text="<script>")
    result = str(render_annotations_to_html(passage, [ann]))
    assert "<script>" not in result  # raw 가 아닌
    assert "&lt;script&gt;" in result


# ─── top_label ──────────────────────────────────────────────────────────────


def test_top_label_data_attribute() -> None:
    """top_label 도 bottom_label 과 동일하게 inline span + data-label.

    이전 <ruby> 표현 폐기 (2026-05-08) — 에디터 시각 정합 위해 글자 폭 borderline +
    ::after 라벨 텍스트로 통일.
    """
    passage = _make_passage("Hello world")
    ann = _make_annotation(AnnotationKind.TOP_LABEL, 0, 5, text="명사구")
    result = str(render_annotations_to_html(passage, [ann]))
    assert '<span class="annot-top-label" data-label="명사구"' in result
    assert "Hello" in result


def test_top_label_text_escaped() -> None:
    passage = _make_passage("Hello")
    ann = _make_annotation(AnnotationKind.TOP_LABEL, 0, 5, text="A&B")
    result = str(render_annotations_to_html(passage, [ann]))
    assert "A&amp;B" in result


# ─── bottom_label ───────────────────────────────────────────────────────────


def test_bottom_label_data_attribute() -> None:
    passage = _make_passage("Hello world")
    ann = _make_annotation(AnnotationKind.BOTTOM_LABEL, 6, 11, text="동사")
    result = str(render_annotations_to_html(passage, [ann]))
    assert '<span class="annot-bottom-label" data-label="동사">' in result
    assert "world</span>" in result


def test_bottom_label_data_attr_escaped() -> None:
    """data-label 안의 따옴표가 escape 되어야 (HTML attribute 안전)."""
    passage = _make_passage("Hello")
    ann = _make_annotation(AnnotationKind.BOTTOM_LABEL, 0, 5, text='a"b')
    result = str(render_annotations_to_html(passage, [ann]))
    assert 'data-label="a&#34;b"' in result or 'data-label="a&quot;b"' in result


# ─── bracket ────────────────────────────────────────────────────────────────


def test_bracket_square() -> None:
    passage = _make_passage("Hello world")
    ann = _make_annotation(AnnotationKind.BRACKET, 0, 5, bracket_style="[]")
    result = str(render_annotations_to_html(passage, [ann]))
    assert '<span class="annot-bracket">[</span>Hello' in result
    assert 'Hello<span class="annot-bracket">]</span>' in result


def test_bracket_paren_curly_corner_angle() -> None:
    """5종 bracket_style 모두 매핑."""
    passage = _make_passage("abcdefghij")
    annotations = [
        _make_annotation(AnnotationKind.BRACKET, 0, 1, bracket_style="()"),
        _make_annotation(AnnotationKind.BRACKET, 2, 3, bracket_style="{}"),
        _make_annotation(AnnotationKind.BRACKET, 4, 5, bracket_style="⌜⌟"),
        _make_annotation(AnnotationKind.BRACKET, 6, 7, bracket_style="<>"),
    ]
    result = str(render_annotations_to_html(passage, annotations))
    assert "(</span>a<span" in result
    assert "{</span>c<span" in result
    assert "⌜</span>e<span" in result
    # < / > 는 escape — 그러나 우리 wrap 안에 들어가는 글자는 < / >.
    # `<` 가 본문 글자 아니라 bracket 글자라 escape 됨 (markupsafe).
    assert "&lt;</span>g<span" in result


def test_bracket_span_to_end_of_body_no_duplicate_close() -> None:
    """회귀 테스트 — bracket span end == body_len 시 close 가 한 번만 출력.

    버그 (2026-05-08): main loop 의 ``range(seg_start, seg_end + 1)`` 가 이미
    seg_end (= n) 위치 close 를 처리하는데, 별도 후처리 (line 372~381) 가 같은
    close 를 또 출력해서 ``}}`` / ``</span></span>`` 중복. 사용자 보고 → fix.
    """
    body = "I am a boy"
    passage = _make_passage(body)
    ann = _make_annotation(AnnotationKind.BRACKET, 0, len(body), bracket_style="{}")
    result = str(render_annotations_to_html(passage, [ann]))
    # close `}` 가 *정확히 한 번* 등장해야 한다.
    assert result.count('<span class="annot-bracket">}</span>') == 1
    # 본문 모든 글자가 그대로 들어가야 한다 (마지막 글자 누락 방지).
    assert "I am a boy" in result


def test_bracket_emitted_outside_label_span() -> None:
    """회귀 — 라벨 + bracket 이 같은 span 에 적용되면 bracket 글자는 라벨 span *밖*에
    위치해야 한다 (PR #70 정책 유지).

    버그 (2026-05-08 사용자 보고): bracket 이 라벨 span 안에 들어가면 라벨 box 폭 (=
    borderline 폭) 이 괄호 글자까지 확장되어 borderline 이 괄호 위까지 그려진다.
    사용자 의도는 borderline 이 본문 영역에만 그려지는 것.

    Fix 후 DOM 순서:
        <bracket>{</bracket><label>body</label><bracket>}</bracket>
    """
    passage = _make_passage("Hello world")
    annotations = [
        _make_annotation(AnnotationKind.TOP_LABEL, 0, 11, text="구"),
        _make_annotation(AnnotationKind.BRACKET, 0, 11, bracket_style="{}"),
    ]
    result = str(render_annotations_to_html(passage, annotations))

    # bracket open 은 label open *전*.
    assert (
        '<span class="annot-bracket">{</span><span class="annot-top-label"' in result
    ), f"bracket open 이 label open 보다 앞이어야 한다. 실제: {result}"
    # bracket close 는 label close *후*.
    assert (
        '</span><span class="annot-bracket">}</span>' in result
    ), f"bracket close 가 label close 뒤이어야 한다. 실제: {result}"


def test_paragraphs_take_priority_over_mismatched_body_text() -> None:
    """회귀 테스트 — paragraphs 가 있으면 body_text 가 아닌 paragraphs.join('\\n')
    으로 char offset 기준 잡아야 한다.

    버그 (2026-05-08 사용자 보고): extractor 가 LLM 응답에서 body_text 와 paragraphs
    를 독립 저장 → 첫 단락 끝에 trailing space 등으로 둘이 어긋남 (body_text 가
    1글자 김). frontend annotationSerializer 는 paragraphs.join('\\n') 가정으로
    char offset 을 만들어 저장. 렌더러가 body_text 그대로 쓰면 close 위치가 마지막
    글자 1개 *이전* 으로 밀림 → 사용자 시각 "마지막 글자 짤림" 버그.
    """
    paragraphs = [
        "William is the best dog in the world ever.",
        "We have to admire him forever because he is almighty and powerful.",
    ]
    # body_text 는 paragraphs.join 와 어긋남 — 첫 단락 끝에 trailing space 1개 추가.
    body_text_with_trailing_space = paragraphs[0] + " \n" + paragraphs[1]
    passage = Passage(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        workspace_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        body_text=body_text_with_trailing_space,
        paragraphs=paragraphs,
        word_count=len(body_text_with_trailing_space.split()),
        source=SourceMeta(provider=SourceProvider.USER_INPUT),
        target_grade=TargetGrade.HIGH_3,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )
    # frontend serializer 가 만든 char offset: paragraphs.join 기준 "to admire him" 위치.
    joined = "\n".join(paragraphs)
    target = "to admire him"
    start = joined.index(target)
    end = start + len(target)

    ann = _make_annotation(AnnotationKind.BRACKET, start, end, bracket_style="<>")
    result = str(render_annotations_to_html(passage, [ann]))

    # 닫는 괄호 직전의 본문이 정확히 'to admire him' 으로 끝나야 한다.
    assert ">to admire him<" in result.replace("&lt;", "<").replace("&gt;", ">") or (
        '<span class="annot-bracket">&lt;</span>to admire him<span class="annot-bracket">&gt;</span>'
        in result
    )


def test_top_label_span_to_end_of_body_no_duplicate_close() -> None:
    """회귀 — top_label span end == body_len 시 ``</span>`` 가 한 번만."""
    body = "I am a boy"
    passage = _make_passage(body)
    ann = _make_annotation(AnnotationKind.TOP_LABEL, 0, len(body), text="주어")
    result = str(render_annotations_to_html(passage, [ann]))
    # annot-top-label span 닫힘 1회 + 외곽 <p> 닫힘 1회 = </span> 1회만 등장.
    assert result.count("</span>") == 1
    assert "I am a boy" in result


def test_bracket_missing_style_skipped(caplog: pytest.LogCaptureFixture) -> None:
    """bracket_style=None 이면 skip + 경고."""
    passage = _make_passage("Hello")
    # 에디터 입력 버그 시뮬레이션
    ann = _make_annotation(AnnotationKind.BRACKET, 0, 5, bracket_style=None)
    with caplog.at_level(logging.WARNING):
        result = str(render_annotations_to_html(passage, [ann]))
    assert "annot-bracket" not in result
    assert "bracket_style" in caplog.text


# ─── arrow skip ─────────────────────────────────────────────────────────────


def test_arrow_skipped_with_log(caplog: pytest.LogCaptureFixture) -> None:
    """ADR-0014 D4 — arrow 는 명시적 skip + 1회 로그."""
    passage = _make_passage("Hello world")
    ann = _make_annotation(
        AnnotationKind.ARROW,
        0,
        5,
        arrow_target_span=CharacterOffsetV1Span(start=6, end=11),
    )
    with caplog.at_level(logging.INFO):
        result = str(render_annotations_to_html(passage, [ann]))
    # arrow 에 의한 wrap class 가 본문에 없어야
    assert "annot-arrow" not in result
    assert "arrow" in caplog.text.lower()


# ─── XSS escape (D6) ────────────────────────────────────────────────────────


def test_body_text_xss_escaped() -> None:
    """body_text 의 HTML 특수문자 escape."""
    passage = _make_passage("<script>alert(1)</script>")
    result = str(render_annotations_to_html(passage, []))
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_body_text_with_annotation_xss_escaped() -> None:
    """annotation 적용 본문도 escape 되어야."""
    passage = _make_passage('A&B"C')
    ann = _make_annotation(AnnotationKind.HIGHLIGHT, 0, 5, color_index=1)
    result = str(render_annotations_to_html(passage, [ann]))
    assert "&amp;" in result
    assert "&#34;" in result or "&quot;" in result


# ─── 중첩 / 충돌 (D5) ───────────────────────────────────────────────────────


def test_overlapping_text_runs_combined() -> None:
    """highlight + underline 같은 span — 둘 다 적용 (2026-05-10 fix).

    이전 정책 = "마지막 적용 우선" (underline 이 highlight 덮어씀) 은
    "highlight 칠한 부분 안에 underline 추가하면 highlight 가 사라지는" 와이프
    검수 회귀 원인. 두 layer 동시 적용으로 정책 변경.
    """
    passage = _make_passage("Hello")
    annotations = [
        _make_annotation(AnnotationKind.HIGHLIGHT, 0, 5, color_index=1),
        _make_annotation(AnnotationKind.UNDERLINE, 0, 5),
    ]
    result = str(render_annotations_to_html(passage, annotations))
    # 둘 다 같은 span 안에 class 합쳐서 emit.
    assert "annot-highlight--1" in result
    assert "annot-underline" in result


def test_partial_overlap_text_runs() -> None:
    """highlight 0-5 + underline 3-7 → 0-3 highlight 단독, 3-5 highlight+underline,
    5-7 underline 단독 (2026-05-10 fix)."""
    passage = _make_passage("abcdefghij")
    annotations = [
        _make_annotation(AnnotationKind.HIGHLIGHT, 0, 5, color_index=2),
        _make_annotation(AnnotationKind.UNDERLINE, 3, 7),
    ]
    result = str(render_annotations_to_html(passage, annotations))
    assert "annot-highlight--2" in result
    assert "annot-underline" in result
    # 겹치는 3-5 영역 ('de') 가 두 class 모두 가진 단일 span 으로 emit 되어야.
    assert (
        'class="annot-highlight annot-highlight--2 annot-underline">de' in result
        or 'class="annot-highlight annot-highlight--2 annot-underline">de</span>' in result
    )


def test_underline_inside_highlight_preserves_highlight() -> None:
    """highlight 칠한 영역 안에 *일부분* underline 을 추가해도 highlight 가
    underline 자리에서 사라지지 않아야 (2026-05-10 와이프 v0.2 검수 회귀)."""
    passage = _make_passage("These supermarkets and")
    annotations = [
        _make_annotation(AnnotationKind.HIGHLIGHT, 0, 22, color_index=8),
        _make_annotation(AnnotationKind.UNDERLINE, 6, 18),  # "supermarkets"
    ]
    result = str(render_annotations_to_html(passage, annotations))
    # supermarkets 자리에 highlight + underline 둘 다 존재.
    assert "annot-highlight--8 annot-underline" in result
    # 'supermarkets' 글자 자체가 두 class 가진 span 안에 있어야.
    assert ">supermarkets" in result


# ─── out-of-range (D5) ──────────────────────────────────────────────────────


def test_span_out_of_range_skipped(caplog: pytest.LogCaptureFixture) -> None:
    """span 이 body_text 길이 초과 → skip + 경고."""
    passage = _make_passage("Hello")  # n=5
    ann = _make_annotation(AnnotationKind.HIGHLIGHT, 0, 100, color_index=1)
    with caplog.at_level(logging.WARNING):
        result = str(render_annotations_to_html(passage, [ann]))
    # annotation 적용 안 됨
    assert "annot-highlight" not in result
    assert "out of body_text range" in caplog.text


# ─── 복합 fixture ───────────────────────────────────────────────────────────


def test_complex_fixture_highlight_label_bracket() -> None:
    """복합 — highlight + top_label + bracket 동시 적용 시 모든 마크 출력."""
    passage = _make_passage("The economy is growing.")
    annotations = [
        _make_annotation(AnnotationKind.HIGHLIGHT, 4, 11, color_index=1),  # economy
        _make_annotation(AnnotationKind.TOP_LABEL, 0, 11, text="명사구"),
        _make_annotation(AnnotationKind.BRACKET, 0, 23, bracket_style="[]"),
    ]
    result = str(render_annotations_to_html(passage, annotations))
    assert "annot-highlight--1" in result
    assert 'class="annot-top-label"' in result
    assert 'data-label="명사구"' in result
    assert ">[<" in result or '<span class="annot-bracket">[</span>' in result
    assert ">]<" in result or '<span class="annot-bracket">]</span>' in result
