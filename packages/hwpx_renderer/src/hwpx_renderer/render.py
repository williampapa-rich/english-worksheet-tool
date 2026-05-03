"""HWPX 렌더러 — 정식 entrypoint.

``render_passage_with_annotations(passage, annotations) -> bytes`` 가 공개 API.

P1-8a 범위:
    - ``highlight``, ``underline``, ``inline_note`` 3종 charPr 계열 구현.
    - 나머지 4종 (``top_label``, ``bottom_label``, ``bracket``, ``arrow``) 은
      본 PR 에서 silent-skip + 로그 처리 (P1-8b/c 에서 구현 예정).

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
    id 0  : 본문 body (plain)
    id 1  : 라벨 (7pt bold) — top/bottom label, P1-8b 에서 사용
    id 10 ~ 21 : highlight color_index 1~12
    id 30 ~ 41 : underline color_index 1~12 (underline 은 color 고정 #000000, 자리만)
                 단, 본 PR 에서 underline 은 id 30 단일 (SINGLE 밑줄, 흑색)
    id 50       : inline_note (7pt, 회색)

    ※ id 배치 설계 원칙: 10 단위로 구분해 P1-8b/c 에서 추가 충돌 없이 확장 가능.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from hwpx_renderer._xml_builders import (
    HIGHLIGHT_PALETTE,
    INLINE_NOTE_FONT_SIZE,
    INLINE_NOTE_TEXT_COLOR,
    UNDERLINE_DEFAULT_COLOR,
    build_hwpx_zip,
    charpr_xml,
    plain_run_xml,
    secpr_run_xml,
)
from shared.schemas.annotation import AnnotationKind, SyntaxAnnotation
from shared.schemas.passage import Passage

logger = logging.getLogger(__name__)

# charPr id 범위 상수
_CHARPR_BODY = 0  # 본문 plain
_CHARPR_LABEL_BASE = 1  # 라벨 7pt bold (P1-8b 에서 사용)
_CHARPR_HIGHLIGHT_BASE = 10  # color_index 1 → id 10
_CHARPR_UNDERLINE = 30  # underline 단일 (흑색 SINGLE)
_CHARPR_INLINE_NOTE = 50  # inline_note


def _highlight_charpr_id(color_index: int) -> int:
    """color_index (1~12) → charPr id."""
    return _CHARPR_HIGHLIGHT_BASE + color_index - 1  # 10~21


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

    # charPr 목록 구성
    charpr_list: list[str] = []

    # id 0: 본문 plain 10pt
    charpr_list.append(charpr_xml(_CHARPR_BODY, height=1000))

    # id 1: 라벨 7pt bold (P1-8b 예약 — 본 PR 에서도 정의해 둠)
    charpr_list.append(charpr_xml(_CHARPR_LABEL_BASE, height=700, bold=True))

    # id 10~21: highlight color_index 1~12
    for idx in range(1, 13):
        cid = _highlight_charpr_id(idx)
        color = HIGHLIGHT_PALETTE[idx]
        charpr_list.append(charpr_xml(cid, shade_color=color))

    # id 30: underline SINGLE 흑색
    charpr_list.append(
        charpr_xml(
            _CHARPR_UNDERLINE,
            underline_type="SINGLE",
            underline_color=UNDERLINE_DEFAULT_COLOR,
        )
    )

    # id 50: inline_note 7pt 회색
    charpr_list.append(
        charpr_xml(
            _CHARPR_INLINE_NOTE,
            height=INLINE_NOTE_FONT_SIZE,
            text_color=INLINE_NOTE_TEXT_COLOR,
        )
    )

    total_charpr = len(charpr_list)
    charpr_block = (
        f'<hh:charProperties itemCnt="{total_charpr}">'
        + "".join(charpr_list)
        + "</hh:charProperties>"
    )

    # paraPr
    parapr_block = (
        '<hh:paraPrList itemCnt="2">'
        # 0: 기본 본문 단락
        '<hh:paraPr id="0" tabDef="0" condense="0" fontLineHeight="0" snapToGrid="1"'
        ' suppressLineNumbers="0" checked="0">'
        '<hh:align horizontal="JUSTIFY" vertical="BASELINE"/>'
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


# ── 단락 렌더 헬퍼 ────────────────────────────────────────────────────────────


@dataclass
class _RunSpec:
    """단일 텍스트 run 의 렌더 명세."""

    text: str
    char_pr_id: int


def _build_body_para(run_specs: list[_RunSpec], with_secpr: bool = False) -> str:
    """본문 단락 XML 생성.

    Args:
        run_specs: 이 단락에 포함될 run 목록 (순서 유지).
        with_secpr: True 이면 첫 단락에 secPr run 을 앞에 추가.
    """
    runs_xml = ""
    if with_secpr:
        runs_xml += secpr_run_xml()
    for rs in run_specs:
        runs_xml += plain_run_xml(rs.text, rs.char_pr_id)

    return (
        '<hp:p id="0" paraPrIDRef="0" styleIDRef="0" '
        'pageBreak="0" columnBreak="0" merged="0">' + runs_xml + "</hp:p>"
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


# ── 섹션 XML 빌더 ────────────────────────────────────────────────────────────


def _build_section_xml(
    body_text: str,
    annotations: list[SyntaxAnnotation],
) -> str:
    """단일 지문을 HWPX section0.xml 으로 변환.

    P1-8a 에서는 단일 단락으로 처리한다 (줄바꿈 없음).
    P1-8b 에서 top_label / bottom_label 의 3단 단락 구조가 추가될 때
    단락 분할 로직이 확장된다.

    Args:
        body_text: 렌더 대상 지문 본문.
        annotations: DB 에서 읽어온 SyntaxAnnotation 목록.

    Returns:
        section0.xml 내용 문자열.
    """
    # 텍스트 런 계열 분류
    text_run_kinds = {
        AnnotationKind.HIGHLIGHT,
        AnnotationKind.UNDERLINE,
        AnnotationKind.INLINE_NOTE,
    }
    text_run_anns = [a for a in annotations if a.kind in text_run_kinds]

    # P1-8b/c 에서 구현 예정인 kind — silent skip + log
    unsupported_kinds = {
        AnnotationKind.TOP_LABEL,
        AnnotationKind.BOTTOM_LABEL,
        AnnotationKind.BRACKET,
        AnnotationKind.ARROW,
    }
    for ann in annotations:
        if ann.kind in unsupported_kinds:
            logger.debug(
                "Annotation kind=%s skipped (P1-8b/c not yet implemented).",
                ann.kind.value,
            )

    # inline_note 는 텍스트 span 에 charPr 변경으로 처리 (후보 A 채택)
    # 단, inline_note 의 text 필드 (예: "(=foster)") 를 별도 run 으로 삽입하지 않음.
    # span 범위의 글자를 작은 폰트로만 변경 — 실제 note 텍스트 삽입은 P1-8b follow-up.
    # 이유: annotation span 자체가 note 대상 범위 → 해당 범위를 시각적으로 약화시킴.
    # ann.text 활용 (예: "(=동의어)") 을 inline 삽입하는 형태는 추후 확장 가능.

    segments = _slice_text_with_annotations(body_text, text_run_anns)

    # 단락 1: secPr (섹션 정의 — 빈 단락)
    sec_para = (
        '<hp:p id="0" paraPrIDRef="0" styleIDRef="0" '
        'pageBreak="0" columnBreak="0" merged="0">' + secpr_run_xml() + "</hp:p>"
    )

    # 단락 2: 본문 (run 분할 적용)
    run_xmls = "".join(
        f'<hp:run charPrIDRef="{seg.char_pr_id}"><hp:t>{_xe_local(seg.text)}</hp:t></hp:run>'
        for seg in segments
        if seg.text  # 빈 세그먼트 건너뜀
    )
    body_para = (
        '<hp:p id="0" paraPrIDRef="0" styleIDRef="0" '
        'pageBreak="0" columnBreak="0" merged="0">' + run_xmls + "</hp:p>"
    )

    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        '<hs:sec xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
        ' xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section">'
        + sec_para
        + body_para
        + "</hs:sec>"
    )


def _xe_local(s: str) -> str:
    """XML escape (로컬 alias — import 최소화)."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


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
