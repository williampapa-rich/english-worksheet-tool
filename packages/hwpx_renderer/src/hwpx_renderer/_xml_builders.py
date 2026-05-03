"""HWPX raw XML 빌더 공통 헬퍼.

PoC (`poc_align.py`) 에서 검증된 패턴을 정식 모듈로 승격한 것.
P1-8a/b/c 가 공유하는 ZIP 구조 빌더 + charPr/run 생성기 모음.

좌표계 메모 (poc_align.py 원문):
    1 HWP unit = 1/7200 inch ≈ 0.0353mm. 10pt = 1000 HWP unit.
    A4 portrait: width=59528, height=84188 HWP unit.
    기본 여백 (평가원 템플릿 기준):
        left/right=8504, top=16015, bottom=8504, header=2000, footer=3828.

직접 구현 근거 (CLAUDE.md §3.6):
    hwpx-auto-parser-for-template 은 TypeScript VSCode extension 이므로
    Python 에서 직접 import 불가 — raw OOXML 직접 작성이 불가피.
    poc_align.py (PR #2 + PR #10) 에서 이미 검증된 XML 패턴을 재활용.
"""

from __future__ import annotations

import io
import zipfile

# ── 페이지 좌표 상수 ──────────────────────────────────────────────────────────
PAGE_W = 59528  # A4 width (HWP unit)
PAGE_H = 84188  # A4 height
MAR_L = 8504  # left margin
MAR_R = 8504  # right margin
MAR_TOP = 16015  # top margin
MAR_BOT = 8504  # bottom margin
MAR_HDR = 2000  # header
MAR_FTR = 3828  # footer
COL_W = PAGE_W - MAR_L - MAR_R  # ≈ 42520 HWP unit

# ── charPr 색상 팔레트 (12색) ────────────────────────────────────────────────
# color_index 1~12 → shadeColor HEX 매핑.
# 영상 레퍼런스 §3.2 에서 확인된 형광펜 계열 12색 팔레트.
# P1-7 §6 미해결 #3 — 본 PR 에서 구현 레벨 결정: 사전 정의 12색 dict.
# 색 기준: 연한 형광펜 + 파스텔 계열 (출력 시 읽기 편한 밝은 색).
HIGHLIGHT_PALETTE: dict[int, str] = {
    1: "#FFFF00",  # 노란색 (기본 형광펜, PoC 검증 완료)
    2: "#ADFF2F",  # 연두
    3: "#00FF7F",  # 민트
    4: "#87CEEB",  # 하늘색
    5: "#DDA0DD",  # 연보라
    6: "#FFB6C1",  # 핑크
    7: "#FFA500",  # 주황
    8: "#FF6347",  # 토마토
    9: "#98FB98",  # 연녹색
    10: "#F0E68C",  # 카키
    11: "#B0C4DE",  # 연파랑
    12: "#F5DEB3",  # 밀색(wheat)
}

# underline color_index 연동 여부 — P1-7 §6 미해결 #4.
# 본 PR 에서 구현 레벨 결정: underline 은 color_index 와 연동하지 않음.
# 이유: 밑줄 색이 하이라이트 배경색과 일치하면 가독성 저하 가능성.
# 단순 흑색(#000000) 고정 사용. domain-expert 검토 follow-up.
UNDERLINE_DEFAULT_COLOR = "#000000"

# inline_note 텍스트 속성
INLINE_NOTE_FONT_SIZE = 700  # 7pt (본문 10pt 대비 작은 크기)
INLINE_NOTE_TEXT_COLOR = "#666666"  # 회색 (부연 정보 시각적 약화)

# ── XML escape ───────────────────────────────────────────────────────────────


def xe(s: str) -> str:
    """XML 특수 문자 이스케이프."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ── charPr XML 생성 ─────────────────────────────────────────────────────────


def charpr_xml(
    cid: int,
    *,
    height: int = 1000,
    text_color: str = "#000000",
    shade_color: str = "none",
    underline_type: str = "NONE",
    underline_color: str = "#000000",
    bold: bool = False,
    italic: bool = False,
    font_id: int = 1,
) -> str:
    """범용 charPr XML 빌더.

    Args:
        cid: charPr id 값.
        height: 글자 크기 (HWP unit, 10pt=1000).
        text_color: 텍스트 색상 HEX.
        shade_color: 배경 하이라이트 색 HEX, 없으면 "none".
        underline_type: "NONE" | "BOTTOM" (하단 밑줄) | "CENTER" (취소선) | "TOP" (위) 등.
        underline_color: 밑줄 색 HEX.
        bold: bold 활성화 여부.
        italic: italic 활성화 여부.
        font_id: fontRef 의 latin/other id (0=함초롬돋움, 1=Times New Roman).

    Returns:
        ``<hh:charPr ...>...</hh:charPr>`` XML 문자열.
    """
    # 한컴 스펙: hh:bold / hh:italic 요소 존재 = on, 없음 = off.
    bold_xml = "<hh:bold/>" if bold else ""
    italic_xml = "<hh:italic/>" if italic else ""

    return (
        f'<hh:charPr id="{cid}" height="{height}" textColor="{text_color}"'
        f' shadeColor="{shade_color}"'
        f' useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="0">'
        f'<hh:fontRef hangul="0" latin="{font_id}" hanja="0" japanese="0"'
        f' other="{font_id}" symbol="0" user="0"/>'
        f'<hh:ratio hangul="100" latin="100" hanja="100" japanese="100"'
        f' other="100" symbol="100" user="100"/>'
        f'<hh:spacing hangul="0" latin="0" hanja="0" japanese="0"'
        f' other="0" symbol="0" user="0"/>'
        f'<hh:relSz hangul="100" latin="100" hanja="100" japanese="100"'
        f' other="100" symbol="100" user="100"/>'
        f'<hh:offset hangul="0" latin="0" hanja="0" japanese="0"'
        f' other="0" symbol="0" user="0"/>'
        f"{bold_xml}"
        f"{italic_xml}"
        f'<hh:underline type="{underline_type}" shape="SOLID" color="{underline_color}"/>'
        f'<hh:strikeout shape="NONE" color="#000000"/>'
        f'<hh:outline type="NONE"/>'
        f'<hh:shadow type="NONE" color="#000000" offsetX="0" offsetY="0"/>'
        f"</hh:charPr>"
    )


# ── run XML 빌더 ─────────────────────────────────────────────────────────────


def plain_run_xml(text: str, char_pr_id: int = 0) -> str:
    """기본 텍스트 run."""
    return f'<hp:run charPrIDRef="{char_pr_id}"><hp:t>{xe(text)}</hp:t></hp:run>'


def highlight_run_xml(text: str, char_pr_id: int) -> str:
    """하이라이트 run — shadeColor charPr 를 참조."""
    return f'<hp:run charPrIDRef="{char_pr_id}"><hp:t>{xe(text)}</hp:t></hp:run>'


def underline_run_xml(text: str, char_pr_id: int) -> str:
    """밑줄 run — underline charPr 를 참조."""
    return f'<hp:run charPrIDRef="{char_pr_id}"><hp:t>{xe(text)}</hp:t></hp:run>'


def inline_note_run_xml(text: str, char_pr_id: int) -> str:
    """inline_note run — 작은 폰트 charPr 를 참조.

    후보 A (inline run) 채택 — P1-7 §6 미해결 #2 결정 참고.
    본문 흐름 안에서 짧은 부연 텍스트를 작은 글씨로 inline 삽입.
    """
    return f'<hp:run charPrIDRef="{char_pr_id}"><hp:t>{xe(text)}</hp:t></hp:run>'


def bracket_run_xml(text: str, style: str = "[]", char_pr_id: int = 0) -> str:
    """괄호 run — Unicode bracket 으로 본문에 inline 삽입.

    P1-8b 범위. 본 헬퍼는 P1-8a 에서 자리만 준비.
    """
    open_b, close_b = style[0], style[1]
    escaped = xe(f"{open_b}{text}{close_b}")
    return f'<hp:run charPrIDRef="{char_pr_id}"><hp:t>{escaped}</hp:t></hp:run>'


def label_para_xml(label_text: str) -> str:
    """3단 단락 구조의 라벨 단락 XML.

    paraPrIDRef="1" (라벨 단락 스타일: lineSpacing=100%, margin prev/next=0)
    charPrIDRef="2" (라벨 글자: 7pt bold)
    """
    return (
        f'<hp:p id="0" paraPrIDRef="1" styleIDRef="1" '
        f'pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="2">'
        f"<hp:t>{xe(label_text)}</hp:t>"
        f"</hp:run>"
        f"</hp:p>"
    )


# ── 섹션 정의 run ─────────────────────────────────────────────────────────────


def secpr_run_xml() -> str:
    """섹션 정의 run XML (첫 번째 단락에 embed).

    PoC `poc_align._secpr_run_xml()` 의 정식 버전.
    """
    return (
        f'<hp:run charPrIDRef="0">'
        f'<hp:secPr id="" textDirection="HORIZONTAL" spaceColumns="1134" '
        f'tabStop="8000" tabStopVal="4000" tabStopUnit="HWPUNIT" '
        f'outlineShapeIDRef="0" memoShapeIDRef="0" '
        f'textVerticalWidthHead="0" masterPageCnt="0">'
        f'<hp:grid lineGrid="0" charGrid="0" wonggojiFormat="0"/>'
        f'<hp:startNum pageStartsOn="BOTH" page="0" pic="0" tbl="0" equation="0"/>'
        f'<hp:visibility hideFirstHeader="0" hideFirstFooter="0" '
        f'hideFirstMasterPage="0" border="SHOW_ALL" fill="SHOW_ALL" '
        f'hideFirstPageNum="0" hideFirstEmptyLine="0" showLineNumber="0"/>'
        f'<hp:lineNumberShape restartType="0" countBy="0" distance="0" startNumber="0"/>'
        f'<hp:pagePr landscape="PORTRAIT" width="{PAGE_W}" height="{PAGE_H}" gutterType="LEFT_ONLY">'
        f'<hp:margin header="{MAR_HDR}" footer="{MAR_FTR}" gutter="0" '
        f'left="{MAR_L}" right="{MAR_R}" top="{MAR_TOP}" bottom="{MAR_BOT}"/>'
        f"</hp:pagePr>"
        f"<hp:footNotePr>"
        f'<hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/>'
        f'<hp:noteLine length="-1" type="SOLID" width="0.12 mm" color="#000000"/>'
        f'<hp:noteSpacing betweenNotes="284" belowLine="568" aboveLine="852"/>'
        f'<hp:numbering type="CONTINUOUS" newNum="1"/>'
        f'<hp:placement place="EACH_COLUMN" beneathText="0"/>'
        f"</hp:footNotePr>"
        f"<hp:endNotePr>"
        f'<hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/>'
        f'<hp:noteLine length="0" type="NONE" width="0.12 mm" color="#000000"/>'
        f'<hp:noteSpacing betweenNotes="0" belowLine="576" aboveLine="864"/>'
        f'<hp:numbering type="CONTINUOUS" newNum="1"/>'
        f'<hp:placement place="END_OF_DOCUMENT" beneathText="0"/>'
        f"</hp:endNotePr>"
        f"</hp:secPr>"
        f"</hp:run>"
    )


# ── ZIP 구조 빌더 ─────────────────────────────────────────────────────────────

# HWPX 공통 파일 상수 (poc_align.py 에서 검증된 값 그대로)
_MIMETYPE = b"application/hwp+zip"

_VERSION_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version"'
    ' tagetApplication="WORDPROCESSOR"'
    ' major="5" minor="1" micro="1" buildNumber="0"'
    ' os="10" xmlVersion="1.5"'
    ' application="Hancom Office Hangul"'
    ' appVersion="12.30.0.6382 MAC64LEDarwin_25.3.0"/>'
)

_SETTINGS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    "<ha:HWPApplicationSetting"
    ' xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app"'
    ' xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0">'
    '<ha:CaretPosition listIDRef="0" paraIDRef="0" pos="0"/>'
    "</ha:HWPApplicationSetting>"
)

_MANIFEST_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>'
)

_CONTAINER_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    "<ocf:container"
    ' xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container"'
    ' xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf">'
    "<ocf:rootfiles>"
    '<ocf:rootfile full-path="Contents/content.hpf"'
    ' media-type="application/hwpml-package+xml"/>'
    '<ocf:rootfile full-path="Preview/PrvText.txt"'
    ' media-type="text/plain"/>'
    '<ocf:rootfile full-path="META-INF/container.rdf"'
    ' media-type="application/rdf+xml"/>'
    "</ocf:rootfiles>"
    "</ocf:container>"
)

_CONTAINER_RDF_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    '<rdf:Description rdf:about="">'
    '<ns0:hasPart xmlns:ns0="http://www.hancom.co.kr/hwpml/2016/meta/pkg#"'
    ' rdf:resource="Contents/header.xml"/>'
    "</rdf:Description>"
    '<rdf:Description rdf:about="Contents/header.xml">'
    '<rdf:type rdf:resource="http://www.hancom.co.kr/hwpml/2016/meta/pkg#HeaderFile"/>'
    "</rdf:Description>"
    "{section_rdf}"
    '<rdf:Description rdf:about="">'
    '<rdf:type rdf:resource="http://www.hancom.co.kr/hwpml/2016/meta/pkg#Document"/>'
    "</rdf:Description>"
    "</rdf:RDF>"
)

_SECTION_RDF_ENTRY = (
    '<rdf:Description rdf:about="">'
    '<ns0:hasPart xmlns:ns0="http://www.hancom.co.kr/hwpml/2016/meta/pkg#"'
    ' rdf:resource="Contents/{section_name}"/>'
    "</rdf:Description>"
    '<rdf:Description rdf:about="Contents/{section_name}">'
    '<rdf:type rdf:resource="http://www.hancom.co.kr/hwpml/2016/meta/pkg#SectionFile"/>'
    "</rdf:Description>"
)


def _make_content_hpf(section_names: list[str], title: str = "document") -> str:
    """content.hpf (opf:package) XML 생성.

    opf:item id 는 파일명에서 확장자를 제거한 식별자를 사용한다.
    예: "section0.xml" → id="section0".
    한컴 파서는 id 에 확장자(".")가 포함되면 파일 손상 팝업을 띄운다.
    (poc_align fixture 및 template.hwpx 모두 id="section0" 패턴 사용 — P1-8a 2차 fix)
    """

    def _stem(filename: str) -> str:
        """파일명에서 확장자를 제거한 stem 반환. 예: 'section0.xml' → 'section0'."""
        dot = filename.rfind(".")
        return filename[:dot] if dot > 0 else filename

    section_items = "".join(
        f'<opf:item id="{_stem(name)}" href="Contents/{name}" media-type="application/xml"/>'
        for name in section_names
    )
    section_refs = "".join(
        f'<opf:itemref idref="{_stem(name)}" linear="yes"/>' for name in section_names
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<opf:package"
        ' xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
        ' xmlns:hp10="http://www.hancom.co.kr/hwpml/2016/paragraph"'
        ' xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"'
        ' xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"'
        ' xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history"'
        ' xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page"'
        ' xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:opf="http://www.idpf.org/2007/opf/"'
        ' xmlns:ooxmlchart="http://www.hancom.co.kr/hwpml/2016/ooxmlchart"'
        ' xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"'
        ' xmlns:epub="http://www.idpf.org/2007/ops"'
        ' xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0"'
        ' version="" unique-identifier="" id="">'
        "<opf:metadata>"
        f"<opf:title>{xe(title)}</opf:title>"
        "<opf:language>en</opf:language>"
        "</opf:metadata>"
        "<opf:manifest>"
        '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
        f"{section_items}"
        '<opf:item id="settings" href="settings.xml" media-type="application/xml"/>'
        "</opf:manifest>"
        "<opf:spine>"
        '<opf:itemref idref="header" linear="yes"/>'
        f"{section_refs}"
        "</opf:spine>"
        "</opf:package>"
    )


def _make_container_rdf(section_names: list[str]) -> str:
    """container.rdf RDF XML 생성."""
    section_rdf = "".join(_SECTION_RDF_ENTRY.format(section_name=name) for name in section_names)
    return _CONTAINER_RDF_TEMPLATE.format(section_rdf=section_rdf)


def build_hwpx_zip(
    header_xml: str,
    sections: dict[str, str],
    prv_text: str = "",
    title: str = "document",
) -> bytes:
    """HWPX ZIP bytes 조립.

    Args:
        header_xml: Contents/header.xml 내용 (문자열).
        sections: {"section0.xml": "<hs:sec>...</hs:sec>", ...} 형태.
            키는 파일명 (Contents/ 아래). 순서가 spine 순서와 일치해야 함.
        prv_text: Preview/PrvText.txt 내용.
        title: content.hpf 메타데이터 title.

    Returns:
        HWPX 형식의 ZIP bytes.
    """
    section_names = list(sections.keys())
    content_hpf = _make_content_hpf(section_names, title=title)
    container_rdf = _make_container_rdf(section_names)

    deflated: dict[str, bytes] = {
        "Contents/header.xml": header_xml.encode("utf-8"),
        "Contents/content.hpf": content_hpf.encode("utf-8"),
        "META-INF/container.xml": _CONTAINER_XML.encode("utf-8"),
        "META-INF/manifest.xml": _MANIFEST_XML.encode("utf-8"),
        "META-INF/container.rdf": container_rdf.encode("utf-8"),
        "settings.xml": _SETTINGS_XML.encode("utf-8"),
        "Preview/PrvText.txt": prv_text.encode("utf-8"),
    }
    for name, content in sections.items():
        deflated[f"Contents/{name}"] = content.encode("utf-8")

    stored: dict[str, bytes] = {
        "version.xml": _VERSION_XML.encode("utf-8"),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zout:
        # mimetype 은 반드시 첫 번째, STORED (OCF 규약)
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zout.writestr(info, _MIMETYPE)

        for name, data in deflated.items():
            zout.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

        for name, data in stored.items():
            zout.writestr(zipfile.ZipInfo(name), data)

    buf.seek(0)
    return buf.read()
