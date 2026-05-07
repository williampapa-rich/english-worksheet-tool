"""SyntaxAnnotation → HTML 렌더러 (ADR-0014).

`packages/hwpx_renderer/render.py` 의 SyntaxAnnotation → HWPX 렌더러와 *대칭*.
같은 `SyntaxAnnotation[]` 입력에서 HTML 출력을 생성. 양 렌더러는 매핑 single-
source-of-truth (`docs/annotation-hwpx-mapping.md`) 를 공유.

ADR-0014 D2 — HTML class 매핑:
  highlight     -> <mark class="annot-highlight annot-highlight--{idx}">
  underline     -> <span class="annot-underline">
  inline_note   -> <span class="annot-inline-note">{본문}<sup class="annot-inline-note__text">{text}</sup></span>
  top_label     -> <ruby class="annot-top-label">{본문}<rt>{text}</rt></ruby>
  bottom_label  -> <span class="annot-bottom-label" data-label="{text}">{본문}</span>
  bracket       -> Unicode 본문 양 끝 inline (ADR-0007) — wrap class 없음
  arrow         -> 명시적 skip (D4) + 로그

ADR-0014 D6 — XSS:
  body_text 와 SyntaxAnnotation.text 모두 markupsafe.escape() 처리. 본 함수는
  *escape 된 HTML 만 반환* — 호출자가 Jinja2 ``| safe`` 로 escape 우회 시 안전.

ADR-0014 D5 — 중첩:
  텍스트 런 (highlight / underline / inline_note) 은 char-by-char 마지막 적용 우선.
  multi-attr (highlight + underline 동시) 은 v0.1 범위 밖. hwpx_renderer 와 정책 통일.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from markupsafe import Markup, escape

from shared.schemas.annotation import AnnotationKind, SyntaxAnnotation
from shared.schemas.passage import Passage

logger = logging.getLogger(__name__)


# ─── 텍스트 런 charPr id 와 대칭되는 HTML class 토큰 ─────────────────────────

_CSS_BODY = "body"  # 기본 (no class wrap)
_CSS_UNDERLINE = "annot-underline"
_CSS_INLINE_NOTE = "annot-inline-note"


def _highlight_class(color_index: int) -> str:
    """color_index (1~12) → CSS class 토큰. 1~12 외는 1 fallback."""
    idx = color_index if 1 <= color_index <= 12 else 1
    return f"annot-highlight annot-highlight--{idx}"


# ─── 분할 자료 구조 ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Segment:
    """body_text 의 한 조각 + 적용된 텍스트 런 token.

    token = "body" / "annot-underline" / "annot-inline-note" / "annot-highlight ...".
    bracket / label 은 char-position 단위 별 처리 (segment 외).
    """

    text: str
    css_token: str
    # inline_note 의 경우 메모 텍스트
    inline_note_text: str | None = None


# ─── bracket 처리 (ADR-0007 — Unicode inline) ──────────────────────────────


_BRACKET_OPEN_CLOSE: dict[str, tuple[str, str]] = {
    "[]": ("[", "]"),
    "()": ("(", ")"),
    "{}": ("{", "}"),
    "⌜⌟": ("⌜", "⌟"),
    "<>": ("<", ">"),
}


def _collect_brackets(
    annotations: list[SyntaxAnnotation],
    body_len: int,
) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    """bracket annotation 의 open/close 글자 위치별 매핑.

    Returns:
        (open_at, close_at) — char position → 삽입할 글자 list.
    """
    open_at: dict[int, list[str]] = {}
    close_at: dict[int, list[str]] = {}
    for ann in annotations:
        if ann.kind != AnnotationKind.BRACKET:
            continue
        if ann.bracket_style is None:
            logger.warning("bracket annotation 에 bracket_style 누락 — skip.")
            continue
        pair = _BRACKET_OPEN_CLOSE.get(ann.bracket_style)
        if pair is None:
            logger.warning("bracket_style %s 매핑 없음 — skip.", ann.bracket_style)
            continue
        if ann.span.start < 0 or ann.span.end > body_len:
            logger.warning(
                "bracket span (%d, %d) out of range %d — skip.",
                ann.span.start,
                ann.span.end,
                body_len,
            )
            continue
        open_at.setdefault(ann.span.start, []).append(pair[0])
        # close 는 end 위치 *직전* (end exclusive 라 end-1 의 *다음* 에 삽입)
        # 단순화: close 도 end position 에 삽입 → 본문 마지막 글자와 분리되지 않게.
        close_at.setdefault(ann.span.end, []).append(pair[1])
    return open_at, close_at


# ─── 텍스트 런 분할 (highlight / underline / inline_note) ─────────────────


def _slice_text_runs(
    body_text: str,
    annotations: list[SyntaxAnnotation],
) -> list[_Segment]:
    """body_text 를 텍스트 런 annotation 으로 분할.

    hwpx_renderer 의 `_slice_text_with_annotations` 와 동일 정책 (마지막 적용 우선).
    """
    n = len(body_text)
    if n == 0:
        return []

    css_map: list[str] = [_CSS_BODY] * n
    inline_note_map: list[str | None] = [None] * n

    for ann in annotations:
        start, end = ann.span.start, ann.span.end
        if start >= n or end > n:
            logger.warning(
                "Annotation span (%d, %d) out of body_text range (%d). Skipped.",
                start,
                end,
                n,
            )
            continue

        if ann.kind == AnnotationKind.HIGHLIGHT:
            token = _highlight_class(ann.color_index or 1)
        elif ann.kind == AnnotationKind.UNDERLINE:
            token = _CSS_UNDERLINE
        elif ann.kind == AnnotationKind.INLINE_NOTE:
            token = _CSS_INLINE_NOTE
        else:
            continue

        for i in range(start, end):
            css_map[i] = token
            if ann.kind == AnnotationKind.INLINE_NOTE:
                inline_note_map[i] = ann.text or ""

    # 연속된 동일 css_token + inline_note_text 를 하나의 segment 로 묶음
    segments: list[_Segment] = []
    cur_start = 0
    cur_token = css_map[0]
    cur_note = inline_note_map[0]

    for i in range(1, n):
        if css_map[i] != cur_token or inline_note_map[i] != cur_note:
            segments.append(
                _Segment(
                    text=body_text[cur_start:i],
                    css_token=cur_token,
                    inline_note_text=cur_note,
                )
            )
            cur_start = i
            cur_token = css_map[i]
            cur_note = inline_note_map[i]

    segments.append(
        _Segment(
            text=body_text[cur_start:],
            css_token=cur_token,
            inline_note_text=cur_note,
        )
    )
    return segments


# ─── 라벨 처리 (top_label / bottom_label) ──────────────────────────────────


def _collect_labels(
    annotations: list[SyntaxAnnotation],
    body_len: int,
) -> dict[tuple[int, int], list[tuple[AnnotationKind, str]]]:
    """라벨 annotation 의 (start, end) → [(kind, text), ...] 매핑.

    같은 span 에 라벨 여러 개 (top + bottom 또는 top 2개) 도 list 로 누적.
    """
    labels: dict[tuple[int, int], list[tuple[AnnotationKind, str]]] = {}
    for ann in annotations:
        if ann.kind not in (AnnotationKind.TOP_LABEL, AnnotationKind.BOTTOM_LABEL):
            continue
        if ann.span.start < 0 or ann.span.end > body_len:
            logger.warning(
                "label span (%d, %d) out of range %d — skip.",
                ann.span.start,
                ann.span.end,
                body_len,
            )
            continue
        text = ann.text or ""
        labels.setdefault((ann.span.start, ann.span.end), []).append((ann.kind, text))
    return labels


# ─── 메인 렌더 ──────────────────────────────────────────────────────────────


def render_annotations_to_html(
    passage: Passage,
    annotations: list[SyntaxAnnotation],
) -> Markup:
    """SyntaxAnnotation 을 적용한 HTML <p> 문자열 반환.

    출력 = 단일 paragraph (Passage.body_text). Phase 2 후반에 paragraph 분할이
    필요하면 별 함수 (본 ADR 범위 밖).

    ADR-0014 D2 매핑 + D5 중첩 정책 + D6 XSS escape.

    Args:
        passage: 대상 Passage. ``body_text`` 만 사용.
        annotations: 적용할 SyntaxAnnotation list. ``passage_id`` 일치 검증은
            호출자 책임 (라우트 레이어). arrow kind 는 명시적 skip + 로그 (D4).

    Returns:
        ``<p>...</p>`` 으로 wrap 된 escape-safe HTML. ``markupsafe.Markup`` 타입 —
        Jinja2 ``| safe`` 로 우회 escape 시 안전.
    """
    body_text = passage.body_text
    n = len(body_text)

    # arrow 는 명시적 skip + 1회 로그 (D4)
    arrow_count = sum(1 for a in annotations if a.kind == AnnotationKind.ARROW)
    if arrow_count > 0:
        logger.info(
            "render_annotations_to_html: arrow %d 개 skip (ADR-0014 D4 — v0.1 미지원).",
            arrow_count,
        )

    # 라벨 / bracket 위치 매핑
    open_brackets, close_brackets = _collect_brackets(annotations, n)
    labels = _collect_labels(annotations, n)

    # 텍스트 런 segments
    text_run_anns = [
        a
        for a in annotations
        if a.kind
        in (AnnotationKind.HIGHLIGHT, AnnotationKind.UNDERLINE, AnnotationKind.INLINE_NOTE)
    ]
    segments = _slice_text_runs(body_text, text_run_anns)

    # bracket / label 은 segments 와 별 layer 로 char-position 위에 *삽입*.
    # 단순화 전략 (v0.1): segments 의 각 char 시작 위치에서 open bracket / 라벨 시작 처리,
    # char 끝 위치에서 close bracket 처리. 라벨 wrap 은 (start, end) span 단위.

    # 라벨 wrap 은 segment 분할과 충돌할 수 있어 v0.1 은 *전체 라벨 span 이 단일 segment
    # 안에 있을 때만* 정확. 여러 segment 에 걸치면 첫 segment 시작 / 마지막 segment 끝
    # 위치에서 wrap (시각 부정확 — 라벨 위에 다른 텍스트 런이 겹칠 때 이슈).
    # → 본 ADR D5 의 v0.1 정책: multi-attr 미지원. 라벨이 텍스트 런과 겹치면 라벨 우선
    # 또는 텍스트 런 우선 중 하나 선택해야 함. 단순화: 라벨이 텍스트 런 _밖_ 으로 wrap
    # 됨 (라벨 span 안에 텍스트 런이 있어도 라벨이 부모 wrap).

    # 구현: char position 별 open/close 이벤트 list 를 만들고 segments 를 다시 한번
    # char 단위로 walk 하며 출력 build.
    open_events: dict[int, list[tuple[str, AnnotationKind | None]]] = {}
    close_events: dict[int, list[tuple[str, AnnotationKind | None]]] = {}

    # 라벨 open/close
    for (start, end), items in labels.items():
        for kind, text in items:
            if kind == AnnotationKind.TOP_LABEL:
                open_tag = '<ruby class="annot-top-label">'
                close_tag = f"<rt>{escape(text)}</rt></ruby>"
            else:  # BOTTOM_LABEL
                # CSS ::after 가 data-label 을 표시
                open_tag = f'<span class="annot-bottom-label" data-label="{escape(text)}">'
                close_tag = "</span>"
            open_events.setdefault(start, []).append((open_tag, kind))
            close_events.setdefault(end, []).append((close_tag, kind))

    # 출력 build
    parts: list[str] = ['<p class="annot-passage">']
    cursor = 0
    for seg in segments:
        seg_start = cursor
        seg_end = cursor + len(seg.text)

        # segment 안의 char position 마다 open/close + bracket 이벤트 처리
        seg_parts: list[str] = []
        # segment 시작 시 open 이벤트
        for pos in range(seg_start, seg_end + 1):
            # close 이벤트 (라벨 / bracket close) — pos 도착 시 처리
            if pos in close_brackets:
                for c in close_brackets[pos]:
                    seg_parts.append(f'<span class="annot-bracket">{escape(c)}</span>')
            if pos in close_events:
                for tag, _kind in close_events[pos]:
                    seg_parts.append(tag)

            if pos == seg_end:
                break

            # open 이벤트 (라벨 / bracket open) — pos 시작 시 처리
            if pos in open_events:
                for tag, _kind in open_events[pos]:
                    seg_parts.append(tag)
            if pos in open_brackets:
                for c in open_brackets[pos]:
                    seg_parts.append(f'<span class="annot-bracket">{escape(c)}</span>')

            # segment 시작 위치에서 css wrap 시작
            if pos == seg_start and seg.css_token != _CSS_BODY:
                seg_parts.append(f'<span class="{seg.css_token}">')

            # 본문 글자 1개
            seg_parts.append(str(escape(body_text[pos])))

            # segment 끝 직전에 css wrap 닫음 (다음 iteration 의 close 이벤트 *전*)
            if pos == seg_end - 1 and seg.css_token != _CSS_BODY:
                # inline_note 는 본문 wrap 에 sup 추가
                if seg.css_token == _CSS_INLINE_NOTE and seg.inline_note_text:
                    seg_parts.append(
                        f'<sup class="annot-inline-note__text">{escape(seg.inline_note_text)}</sup>'
                    )
                seg_parts.append("</span>")
                # highlight 는 mark 태그 권고지만 v0.1 은 span 통일 (CSS 동일 동작).
                # mark vs span: mark 가 의미 더 정확하지만, 12색 변형 + 다른 마크와 중첩
                # 처리 단순화 위해 span 채택. CSS 가 동일 시각 표현 보장.

        parts.append("".join(seg_parts))
        cursor = seg_end

    # 본문 끝 위치의 close 이벤트 (end-of-body 라벨 / bracket)
    if n in close_brackets:
        for c in close_brackets[n]:
            parts.append(f'<span class="annot-bracket">{escape(c)}</span>')
    if n in close_events:
        for tag, _kind in close_events[n]:
            parts.append(tag)

    parts.append("</p>")
    return Markup("".join(parts))
