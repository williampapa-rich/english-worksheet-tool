"""HWPX 렌더러 — 정식 entrypoint.

``render_passage_with_annotations(passage, annotations) -> bytes`` 가 공개 API.

P1-8a 범위:
    - ``highlight``, ``underline``, ``inline_note`` 3종 charPr 계열 구현.

P1-8b 범위 (본 PR):
    - ``top_label`` / ``bottom_label`` — 3단 단락 구조 (라벨 / 본문 / 라벨).
      본문 단락 앞/뒤에 별도 라벨 단락을 삽입한다. 같은 단락 안에 여러 라벨이
      있으면 각 라벨 anchor (``span.start``) 위치까지 폰트 metric 기반 leading
      whitespace 를 채워 본문 단어 위/아래에 정렬한다 (`_font_metrics.label_leading_spaces`).
    - ``bracket`` — ADR-0007 채택안 = Unicode `[ ]` `( )` `{ }` 를 본문 inline run
      으로 양 끝점에 삽입. 본문 텍스트 분할 시 bracket span 의 시작/끝을
      분할점으로 추가하고 해당 위치에 여닫이 charPrIDRef=0 run 삽입.
    - 본문 paraPr ``align="LEFT"`` 고정 — JUSTIFY 는 단어 사이 간격이 가변이라
      폰트 metric 정렬과 호환되지 않음.

P1-8b fix 라운드 (PM 검수 후):
    - 라벨 charPr id 버그 수정 — `_xml_builders.label_para_xml` 가 PoC 시절 매핑
      (charPrIDRef=2 = underline charPr) 을 하드코딩해 라벨에 BOTTOM 밑줄이 그어졌음.
      헬퍼에 `char_pr_id` 인자 추가, render.py 가 `_CHARPR_LABEL_BASE` (=1) 를 명시.
    - 라벨 수평 align — pillow `ImageFont.getlength()` 로 본문 prefix 폭 측정
      → 라벨 단락에 leading whitespace 삽입.

P1-8c 범위 (이후 PR):
    - ``arrow`` 는 별도 PoC 필요 — 본 PR 에서 silent-skip 유지.

inline_note 결정 (P1-7 §6 미해결 #2):
    후보 A (inline run, 작은 폰트 charPr) 채택.
    사유: 본문 흐름 안에서 짧은 부연이라면 inline 이 자연스럽다.
    별 단락은 top_label / bottom_label 의 역할과 겹친다.
    domain-expert 검토 follow-up 필요.

12색 팔레트 결정 (P1-7 §6 미해결 #3):
    사전 정의 12색 dict 채택 (`_xml_builders.HIGHLIGHT_PALETTE`).
    동적 생성 대신 사전 정의를 선택한 이유:
    - charPr id 충돌 없이 header.xml 에 명시적으로 등록 가능.
    - 테스트에서 id 범위를 예측하기 쉬움.
    - 색상 변경 시 dict 한 곳만 수정.

charPr id 배치 (header.xml 안):
    id 0       : 본문 body (plain 10pt)
    id 1       : 라벨 (7pt bold) — top/bottom label, P1-8b 에서 사용
    id 2       : underline BOTTOM 흑색
    id 3       : inline_note (7pt, 회색)
    id 4 ~ 15  : highlight color_index 1~12

    itemCnt = 16, max id = 15 → 0~15 연속 배치.
    한컴 HWPX 스펙: itemCnt 는 실제 항목 수여야 하며, id 는 0 부터 (itemCnt-1) 까지
    연속이어야 한다. 비연속 id (예: 0,1,10,30,50) + itemCnt=16 조합은 한컴 파서가
    OOB(Out-of-Bounds) 로 처리해 파일 손상 팝업을 발생시킨다.
    (P1-8a fix: PM 한글 오피스 검증에서 손상 팝업 발생 → 연속 id 로 재설계)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from hwpx_renderer._font_metrics import label_leading_spaces
from hwpx_renderer._xml_builders import (
    HIGHLIGHT_PALETTE,
    INLINE_NOTE_FONT_SIZE,
    INLINE_NOTE_TEXT_COLOR,
    UNDERLINE_DEFAULT_COLOR,
    build_hwpx_zip,
    charpr_xml,
    label_para_xml,
    secpr_run_xml,
    xe,
)
from shared.schemas.annotation import AnnotationKind, SyntaxAnnotation
from shared.schemas.passage import Passage

logger = logging.getLogger(__name__)

# charPr id 상수 — 0부터 연속 배치 (itemCnt = max_id + 1 필수)
# 한컴 스펙: id 가 비연속이면 파서가 OOB 처리 → 파일 손상 거부.
_CHARPR_BODY = 0  # 본문 plain 10pt
_CHARPR_LABEL_BASE = 1  # 라벨 7pt bold (P1-8b 예약)
_CHARPR_UNDERLINE = 2  # underline BOTTOM 흑색
_CHARPR_INLINE_NOTE = 3  # inline_note 7pt 회색
_CHARPR_HIGHLIGHT_BASE = 4  # color_index 1 → id 4, ..., color_index 12 → id 15


def _highlight_charpr_id(color_index: int) -> int:
    """color_index (1~12) → charPr id (4~15)."""
    return _CHARPR_HIGHLIGHT_BASE + color_index - 1  # 4~15


# ── header.xml 빌더 ──────────────────────────────────────────────────────────


def _build_header_xml() -> str:
    """P1-8a 용 header.xml — 텍스트 런 계열 charPr 포함.

    P1-8b 에서 top/bottom label charPr (id=1) 이 이미 id=1 로 예약되어 있음.
    본 헤더는 P1-8b 와의 충돌 없이 id 배치가 설계된다.
    """
    # 폰트 정의
    fontfaces = (
        '<hh:fontfaces itemCnt="1">'
        '<hh:fontface lang="LATIN" fontCnt="2">'
        '<hh:font id="0" face="함초롬돋움" type="TTF" isEmbedded="0"/>'
        '<hh:font id="1" face="Times New Roman" type="TTF" isEmbedded="0"/>'
        "</hh:fontface>"
        "</hh:fontfaces>"
    )

    # borderFill — id 0 (테두리 없음)
    border_fills = (
        '<hh:borderFills itemCnt="1">'
        '<hh:borderFill id="0" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
        '<hh:slash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:leftBorder type="NONE" width="0.1mm" color="#000000"/>'
        '<hh:rightBorder type="NONE" width="0.1mm" color="#000000"/>'
        '<hh:topBorder type="NONE" width="0.1mm" color="#000000"/>'
        '<hh:bottomBorder type="NONE" width="0.1mm" color="#000000"/>'
        "<hh:fillBrush>"
        '<hh:windowBrush faceColor="none" hatchColor="#000000" hatchStyle="NONE" alpha="0"/>'
        "</hh:fillBrush>"
        "</hh:borderFill>"
        "</hh:borderFills>"
    )

    # charPr 목록 구성 — id 0부터 연속으로 등록 (itemCnt = len = max_id + 1)
    charpr_list: list[str] = []

    # id 0: 본문 plain 10pt
    charpr_list.append(charpr_xml(_CHARPR_BODY, height=1000))

    # id 1: 라벨 7pt bold (P1-8b 예약 — 본 PR 에서도 정의해 둠)
    charpr_list.append(charpr_xml(_CHARPR_LABEL_BASE, height=700, bold=True))

    # id 2: underline BOTTOM 흑색 (type="BOTTOM" = 하단 단일 밑줄 — 한컴 스펙)
    charpr_list.append(
        charpr_xml(
            _CHARPR_UNDERLINE,
            underline_type="BOTTOM",
            underline_color=UNDERLINE_DEFAULT_COLOR,
        )
    )

    # id 3: inline_note 7pt 회색
    charpr_list.append(
        charpr_xml(
            _CHARPR_INLINE_NOTE,
            height=INLINE_NOTE_FONT_SIZE,
            text_color=INLINE_NOTE_TEXT_COLOR,
        )
    )

    # id 4~15: highlight color_index 1~12
    for idx in range(1, 13):
        cid = _highlight_charpr_id(idx)
        color = HIGHLIGHT_PALETTE[idx]
        charpr_list.append(charpr_xml(cid, shade_color=color))

    total_charpr = len(charpr_list)
    charpr_block = (
        f'<hh:charProperties itemCnt="{total_charpr}">'
        + "".join(charpr_list)
        + "</hh:charProperties>"
    )

    # paraPr
    parapr_block = (
        '<hh:paraPrList itemCnt="2">'
        # 0: 기본 본문 단락 — align=LEFT (P1-8b fix 2: 라벨 metric 정렬을 위해 단어 사이
        # 간격을 고정. JUSTIFY 는 단어 간격이 가변이라 폰트 metric 으로 라벨을 단어 위에
        # 정렬하는 것이 불가능해진다.)
        '<hh:paraPr id="0" tabDef="0" condense="0" fontLineHeight="0" snapToGrid="1"'
        ' suppressLineNumbers="0" checked="0">'
        '<hh:align horizontal="LEFT" vertical="BASELINE"/>'
        '<hh:heading type="NONE" idRef="0" level="0"/>'
        '<hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="1" widowOrphan="0"'
        ' keepWithNext="0" keepLines="0" pageBreakBefore="0" lineWrap="BREAK"/>'
        '<hh:autoSpacing eAsianEng="0" eAsianNum="0"/>'
        '<hh:margin indent="0" left="0" right="0" prev="0" next="0"/>'
        '<hh:lineSpacing type="PERCENT" value="160"/>'
        '<hh:paraBorder borderFillIDRef="0" offsetLeft="0" offsetRight="0"'
        ' offsetTop="0" offsetBottom="0" connect="0" ignoreMargin="0"/>'
        "</hh:paraPr>"
        # 1: 라벨 단락 (lineSpacing=100%, margin prev/next=0)
        '<hh:paraPr id="1" tabDef="0" condense="0" fontLineHeight="0" snapToGrid="1"'
        ' suppressLineNumbers="0" checked="0">'
        '<hh:align horizontal="LEFT" vertical="BASELINE"/>'
        '<hh:heading type="NONE" idRef="0" level="0"/>'
        '<hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="1" widowOrphan="0"'
        ' keepWithNext="0" keepLines="0" pageBreakBefore="0" lineWrap="BREAK"/>'
        '<hh:autoSpacing eAsianEng="0" eAsianNum="0"/>'
        '<hh:margin indent="0" left="0" right="0" prev="0" next="0"/>'
        '<hh:lineSpacing type="PERCENT" value="100"/>'
        '<hh:paraBorder borderFillIDRef="0" offsetLeft="0" offsetRight="0"'
        ' offsetTop="0" offsetBottom="0" connect="0" ignoreMargin="0"/>'
        "</hh:paraPr>"
        "</hh:paraPrList>"
    )

    # style list
    style_block = (
        '<hh:styleList itemCnt="2">'
        '<hh:style id="0" type="Para" name="본문" engName="Body Text"'
        ' paraPrIDRef="0" charPrIDRef="0" nextStyleIDRef="0" langID="1042" lockForm="0"/>'
        '<hh:style id="1" type="Para" name="라벨" engName="Label"'
        ' paraPrIDRef="1" charPrIDRef="1" nextStyleIDRef="0" langID="1042" lockForm="0"/>'
        "</hh:styleList>"
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<hh:head"
        ' xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
        ' xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"'
        ' version="1.3" secCnt="1">'
        '<hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/>'
        "<hh:refList>"
        + fontfaces
        + border_fills
        + charpr_block
        + parapr_block
        + style_block
        + "</hh:refList>"
        "</hh:head>"
    )


# ── 텍스트 런 annotation 라우터 ──────────────────────────────────────────────


@dataclass
class _AnnotatedSegment:
    """body_text 를 annotation 에 따라 분할한 세그먼트."""

    text: str
    char_pr_id: int = _CHARPR_BODY


def _slice_text_with_annotations(
    body_text: str,
    text_run_annotations: list[SyntaxAnnotation],
) -> list[_AnnotatedSegment]:
    """body_text 를 annotation span 으로 분할해 각 세그먼트에 charPr id 를 배정.

    중첩 span 은 마지막으로 적용된 annotation 이 우선 (P1-8a 에서는 단순 선형 처리).
    multi-attr charPr (highlight + underline 동시) 는 P1-8a 범위 밖 — 단일 속성 우선.

    Args:
        body_text: 분할 대상 본문 (Passage.body_text).
        text_run_annotations: 텍스트 런 계열 SyntaxAnnotation 목록 (highlight/underline/inline_note).

    Returns:
        순서대로 이어 붙이면 body_text 가 재구성되는 세그먼트 목록.
    """
    n = len(body_text)

    # 각 char 위치의 charPr id (기본 = BODY)
    char_pr_map: list[int] = [_CHARPR_BODY] * n

    for ann in text_run_annotations:
        start = ann.span.start
        end = ann.span.end
        if start >= n or end > n:
            logger.warning(
                "Annotation span (%d, %d) out of body_text range (%d). Skipped.",
                start,
                end,
                n,
            )
            continue

        if ann.kind == AnnotationKind.HIGHLIGHT:
            color_idx = ann.color_index or 1
            cpr_id = _highlight_charpr_id(color_idx)
        elif ann.kind == AnnotationKind.UNDERLINE:
            cpr_id = _CHARPR_UNDERLINE
        elif ann.kind == AnnotationKind.INLINE_NOTE:
            cpr_id = _CHARPR_INLINE_NOTE
        else:
            # 텍스트 런 계열이 아닌 kind 는 이 함수에서 처리하지 않음
            continue

        for i in range(start, end):
            char_pr_map[i] = cpr_id

    # 연속된 동일 charPr id 를 하나의 세그먼트로 묶음
    if n == 0:
        return []

    segments: list[_AnnotatedSegment] = []
    cur_start = 0
    cur_id = char_pr_map[0]

    for i in range(1, n):
        if char_pr_map[i] != cur_id:
            segments.append(_AnnotatedSegment(body_text[cur_start:i], cur_id))
            cur_start = i
            cur_id = char_pr_map[i]

    segments.append(_AnnotatedSegment(body_text[cur_start:], cur_id))
    return segments


# ── bracket 처리 ────────────────────────────────────────────────────────────

# bracket_style 별 여닫이 Unicode 매핑 (ADR-0007).
# 스키마는 "()" / "{}" / "[]" 3종만 지원.
_BRACKET_OPEN_CLOSE: dict[str, tuple[str, str]] = {
    "[]": ("[", "]"),
    "()": ("(", ")"),
    "{}": ("{", "}"),
}


def _bracket_runs_at_position(
    pos: int,
    open_brackets_at: dict[int, list[str]],
    close_brackets_at: dict[int, list[str]],
) -> str:
    """주어진 본문 위치에서 시작/끝나는 bracket 의 inline run XML 을 생성.

    여닫이 Unicode 글자 1개씩을 charPrIDRef=0 plain run 으로 본문에 삽입.
    같은 위치에 여러 bracket 이 시작/끝나는 경우 모두 이어 붙임.
    닫는 bracket 을 먼저 (position 에서 끝나는 span 을 닫고) 그 뒤 여는 bracket.
    """
    parts: list[str] = []
    for close_char in close_brackets_at.get(pos, []):
        parts.append(f'<hp:run charPrIDRef="{_CHARPR_BODY}"><hp:t>{xe(close_char)}</hp:t></hp:run>')
    for open_char in open_brackets_at.get(pos, []):
        parts.append(f'<hp:run charPrIDRef="{_CHARPR_BODY}"><hp:t>{xe(open_char)}</hp:t></hp:run>')
    return "".join(parts)


# ── 라벨 단락 빌더 ──────────────────────────────────────────────────────────


def _build_label_text(
    annotations: list[SyntaxAnnotation],
    body_text: str,
) -> str | None:
    """라벨 annotation 목록을 단일 라벨 단락의 텍스트로 합성 (폰트 metric 정렬 포함).

    각 라벨이 자기 anchor 단어 위/아래에 위치하도록 라벨 사이 공백 수를 폰트 metric
    으로 산출 (`_font_metrics.label_leading_spaces`).

    원리:
        라벨 단락은 본문과 별도 단락이므로 라벨 자체의 char offset 외에는 위치 단서가
        없다. 따라서 라벨 단락의 leading whitespace + 라벨 사이 공백을 실측해 본문
        ``body_text[0:span.start]`` 의 폭 위치까지 채운다.

    span.start 가 같은 라벨이 여러 개면 공백 1개로만 join (중복 영역 누적 방지).

    빈 라벨 텍스트 (text=None) 만 있으면 None 반환 → 단락 생성 안 함.
    """
    if not annotations:
        return None
    sorted_anns = sorted(annotations, key=lambda a: a.span.start)
    valid = [a for a in sorted_anns if a.text]
    if not valid:
        return None

    parts: list[str] = []
    used_columns = 0  # 현재까지 라벨 단락에 차지한 라벨-폰트 좌표계 공백 글자 수
    last_anchor = -1
    for ann in valid:
        anchor = ann.span.start
        prefix = body_text[:anchor]
        target_col = label_leading_spaces(prefix)

        if anchor == last_anchor:
            # 같은 단어를 여러 라벨이 가리키는 경우 공백 1개로 join
            parts.append(" ")
            used_columns += 1
        else:
            pad = max(0, target_col - used_columns)
            # 라벨 사이에 최소 공백 1개는 보장 (붙이지 않음). 첫 라벨은 pad 그대로.
            if parts and pad == 0:
                pad = 1
            parts.append(" " * pad)
            used_columns += pad

        text = ann.text or ""
        parts.append(text)
        # 라벨 텍스트 자체가 차지한 컬럼을 누적 (라벨 폰트 좌표계).
        # 한글/한자 라벨은 _font_metrics 에서 1.0em 근사이므로 글자 수가 곧 컬럼 근사.
        used_columns += len(text)
        last_anchor = anchor

    return "".join(parts)


# ── 섹션 XML 빌더 ────────────────────────────────────────────────────────────


def _build_section_xml(
    body_text: str,
    annotations: list[SyntaxAnnotation],
) -> str:
    """단일 지문을 HWPX section0.xml 으로 변환.

    P1-8b 출력 구조 (단일 줄 본문 가정 — 다중 줄 본문 wrap 처리는 P1-10):
        단락 0: secPr (섹션 정의)
        단락 1: top_label 단락 (top_label 이 1개 이상일 때만)
        단락 2: 본문 단락 (highlight/underline/inline_note charPr 적용
                + bracket Unicode inline run 삽입)
        단락 3: bottom_label 단락 (bottom_label 이 1개 이상일 때만)

    P1-8c 에서 arrow 도형이 추가되며, 다중 단락 본문 처리는 P1-10 에서.

    Args:
        body_text: 렌더 대상 지문 본문.
        annotations: DB 에서 읽어온 SyntaxAnnotation 목록.

    Returns:
        section0.xml 내용 문자열.
    """
    # kind 별 분류
    text_run_kinds = {
        AnnotationKind.HIGHLIGHT,
        AnnotationKind.UNDERLINE,
        AnnotationKind.INLINE_NOTE,
    }
    text_run_anns = [a for a in annotations if a.kind in text_run_kinds]
    top_label_anns = [a for a in annotations if a.kind == AnnotationKind.TOP_LABEL]
    bottom_label_anns = [a for a in annotations if a.kind == AnnotationKind.BOTTOM_LABEL]
    bracket_anns = [a for a in annotations if a.kind == AnnotationKind.BRACKET]

    # arrow 는 P1-8c 에서 구현 예정 — silent skip
    for ann in annotations:
        if ann.kind == AnnotationKind.ARROW:
            logger.debug("Annotation kind=arrow skipped (P1-8c not yet implemented).")

    # bracket span → 위치별 여닫이 dict 사전 구성
    n = len(body_text)
    open_brackets_at: dict[int, list[str]] = {}
    close_brackets_at: dict[int, list[str]] = {}
    for ann in bracket_anns:
        start = ann.span.start
        end = ann.span.end
        if start >= n or end > n:
            logger.warning(
                "Bracket annotation span (%d, %d) out of body_text range (%d). Skipped.",
                start,
                end,
                n,
            )
            continue
        style = ann.bracket_style or "[]"
        open_close = _BRACKET_OPEN_CLOSE.get(style)
        if open_close is None:
            logger.warning("Bracket annotation has unsupported bracket_style=%r. Skipped.", style)
            continue
        open_char, close_char = open_close
        open_brackets_at.setdefault(start, []).append(open_char)
        close_brackets_at.setdefault(end, []).append(close_char)

    # 본문 segment 분할 (highlight/underline/inline_note charPr 적용)
    segments = _slice_text_with_annotations(body_text, text_run_anns)

    # bracket run 을 segment 사이에 삽입하면서 본문 run XML 조립
    body_runs: list[str] = []
    cursor = 0
    for seg in segments:
        if not seg.text:
            continue
        seg_start = cursor
        seg_end = cursor + len(seg.text)

        # 세그먼트 내부에서 시작/끝나는 bracket 위치를 찾아 sub-segment 로 분할
        # (한 세그먼트 안에 bracket 시작/끝이 있을 수 있으므로)
        split_points = sorted(
            {seg_start, seg_end}
            | {p for p in open_brackets_at if seg_start < p < seg_end}
            | {p for p in close_brackets_at if seg_start < p < seg_end}
        )

        # seg_start 위치의 bracket run 을 먼저 삽입 (이 segment 가 시작되는 지점)
        body_runs.append(_bracket_runs_at_position(seg_start, open_brackets_at, close_brackets_at))

        # split point 사이의 텍스트를 segment charPr 로 출력 + 각 split point 에서 bracket run 삽입
        for i in range(len(split_points) - 1):
            sub_start = split_points[i]
            sub_end = split_points[i + 1]
            sub_text = body_text[sub_start:sub_end]
            if sub_text:
                body_runs.append(
                    f'<hp:run charPrIDRef="{seg.char_pr_id}"><hp:t>{xe(sub_text)}</hp:t></hp:run>'
                )
            # sub_end 가 segment 끝 (seg_end) 이면 bracket 은 다음 segment 시작 시 처리 — 중복 방지
            if sub_end < seg_end:
                body_runs.append(
                    _bracket_runs_at_position(sub_end, open_brackets_at, close_brackets_at)
                )

        cursor = seg_end

    # 본문 끝 (n) 위치의 닫는 bracket 처리
    body_runs.append(_bracket_runs_at_position(n, open_brackets_at, close_brackets_at))

    body_runs_xml = "".join(body_runs)

    # 단락 0: secPr (섹션 정의 — 빈 단락)
    sec_para = (
        '<hp:p id="0" paraPrIDRef="0" styleIDRef="0" '
        'pageBreak="0" columnBreak="0" merged="0">' + secpr_run_xml() + "</hp:p>"
    )

    # 단락 1: top_label (있을 때만)
    top_label_text = _build_label_text(top_label_anns, body_text)
    top_label_para = (
        label_para_xml(top_label_text, char_pr_id=_CHARPR_LABEL_BASE) if top_label_text else ""
    )

    # 단락 2: 본문
    body_para = (
        '<hp:p id="0" paraPrIDRef="0" styleIDRef="0" '
        'pageBreak="0" columnBreak="0" merged="0">' + body_runs_xml + "</hp:p>"
    )

    # 단락 3: bottom_label (있을 때만)
    bottom_label_text = _build_label_text(bottom_label_anns, body_text)
    bottom_label_para = (
        label_para_xml(bottom_label_text, char_pr_id=_CHARPR_LABEL_BASE)
        if bottom_label_text
        else ""
    )

    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        '<hs:sec xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
        ' xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section">'
        + sec_para
        + top_label_para
        + body_para
        + bottom_label_para
        + "</hs:sec>"
    )


# ── 공개 API ─────────────────────────────────────────────────────────────────


def render_passage_with_annotations(
    passage: Passage,
    annotations: list[SyntaxAnnotation],
) -> bytes:
    """지문 + annotation 목록을 HWPX bytes 로 렌더.

    P1-8 공식 entrypoint. P1-8a 에서는 텍스트 런 계열
    (highlight / underline / inline_note) 만 구현.
    나머지 4종 (top_label / bottom_label / bracket / arrow) 은
    silent-skip + 로그 처리 (P1-8b/c 에서 추가 예정).

    Args:
        passage: 렌더 대상 Passage (shared.schemas.passage.Passage).
        annotations: 해당 Passage 의 SyntaxAnnotation 목록
            (shared.schemas.annotation.SyntaxAnnotation).
            passage.id 와 일치하는 것만 넘길 것 — tenant 격리는 호출자 (API) 책임.

    Returns:
        HWPX 형식의 ZIP bytes.
    """
    header_xml = _build_header_xml()
    body_text = passage.body_text
    section_xml = _build_section_xml(body_text, annotations)

    return build_hwpx_zip(
        header_xml=header_xml,
        sections={"section0.xml": section_xml},
        prv_text=body_text[:200],  # 미리보기 텍스트 (최대 200자)
        title=f"passage_{passage.id}",
    )
