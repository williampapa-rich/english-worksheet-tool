"""
HWPX 텍스트박스 align PoC (P1-0b)

목표:
    단일 영어 문장 위에/아래에 라벨(textBox), 괄호(bracket run), 하이라이트(shadeColor)가
    align 되는지 검증하기 위한 최소 fixture HWPX 1건을 생성한다.

접근:
    - exam-generator/app/renderer/template_injector.py 의 ZIP 재패키징 패턴 재활용
    - 자체 header.xml + section0.xml 을 raw OOXML 로 작성 (템플릿 의존 없음)
    - hwpx-auto-parser-for-template 은 TypeScript VSCode extension 이므로 Python 에서
      직접 import 불가 → raw OOXML 직접 작성이 불가피. 이유: CLAUDE.md §3.6 참고.

HWPX 좌표계:
    - 1 HWP unit = 1/7200 inch ≈ 0.0353mm. 10pt = 1000 HWP unit.
    - A4 portrait: width=59528, height=84188 HWP unit.
    - 기본 여백 (평가원 템플릿 기준):
        left/right = 8788, top = 16015, bottom = 8504, header = 2000, footer = 3828.
    - 본문폭 (text column width) = 59528 - 8788 - 8788 = 41952 HWP unit.

텍스트박스 anchor 전략:
    - `horzRelTo="PARA"` `vertRelTo="PARA"` + `horzOffset` / `vertOffset` 절대값으로
      단락 기준 상대 배치.
    - `treatAsChar="0"` + `allowOverlap="0"` 으로 본문 위/아래 공간 확보.
    - 라벨 텍스트박스가 본문 텍스트 런의 문자 시작 위치에 align 되려면 horzOffset 을
      문자 누적 너비(approximate)로 계산해야 한다.
      PoC 단계에서는 근사값(horzOffset = 0, 단락 시작 기준)을 사용하고
      visual alignment 확인은 PM 이 한글 오피스로 직접 수행.

한계 (PoC 범위):
    - 문자 단위 너비를 Python 에서 정확하게 측정할 수 없음 (font metric 필요).
    - 따라서 horzOffset 은 근사. 실제 phase 1 P1-7/P1-8 단계에서 정밀화.
"""

from __future__ import annotations

import io
import zipfile

# ── 좌표 상수 ──────────────────────────────────────────────────────────────────
_PAGE_W = 59528  # A4 width (HWP unit)
_PAGE_H = 84188  # A4 height
_MAR_L = 8504  # left margin  ※ 평가원 양식 값 그대로
_MAR_R = 8504  # right margin
_MAR_TOP = 16015  # top margin
_MAR_BOT = 8504  # bottom margin
_MAR_HDR = 2000  # header
_MAR_FTR = 3828  # footer
_COL_W = _PAGE_W - _MAR_L - _MAR_R  # ≈ 42520 HWP unit

# ── 글자 크기 / charPr 상수 ───────────────────────────────────────────────────
# PoC 전용 header.xml 에 3개 charPr 정의:
#   0 = 본문 영어 (height=1000, 10pt, shadeColor="none")
#   1 = 하이라이트 본문 (height=1000, shadeColor="#FFFF00", borderFillIDRef=0)
#   2 = 라벨 / 텍스트박스 안 텍스트 (height=700, bold)
CHARPR_BODY = 0
CHARPR_HIGHLIGHT = 1
CHARPR_LABEL = 2

# ── 단락 스타일 ──────────────────────────────────────────────────────────────
# 0 = 기본 단락 (본문)
PARAPR_BODY = 0

# ── borderFill ───────────────────────────────────────────────────────────────
# 0 = 테두리 없음 (라벨 텍스트박스)
# 1 = 4면 실선 0.12mm 검정 (괄호 박스)
BFILL_NONE = 0
BFILL_SOLID = 1


# ── XML escape ───────────────────────────────────────────────────────────────


def _xe(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ── header.xml ────────────────────────────────────────────────────────────────

_HEADER_XML = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<hh:head
  xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"
  xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"
  xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
  xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"
  version="1.3" secCnt="1">
  <hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/>
  <hh:refList>
    <hh:fontfaces itemCnt="1">
      <hh:fontface lang="LATIN" fontCnt="2">
        <hh:font id="0" face="함초롬돋움" type="TTF" isEmbedded="0"/>
        <hh:font id="1" face="Times New Roman" type="TTF" isEmbedded="0"/>
      </hh:fontface>
    </hh:fontfaces>
    <hh:borderFills itemCnt="2">
      <hh:borderFill id="0" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">
        <hh:slash type="NONE" Crooked="0" isCounter="0"/>
        <hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
        <hh:leftBorder type="NONE" width="0.1mm" color="#000000"/>
        <hh:rightBorder type="NONE" width="0.1mm" color="#000000"/>
        <hh:topBorder type="NONE" width="0.1mm" color="#000000"/>
        <hh:bottomBorder type="NONE" width="0.1mm" color="#000000"/>
        <hh:fillBrush><hh:windowBrush faceColor="none" hatchColor="#000000" hatchStyle="NONE" alpha="0"/></hh:fillBrush>
      </hh:borderFill>
      <hh:borderFill id="1" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">
        <hh:slash type="NONE" Crooked="0" isCounter="0"/>
        <hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
        <hh:leftBorder type="SOLID" width="0.12mm" color="#000000"/>
        <hh:rightBorder type="SOLID" width="0.12mm" color="#000000"/>
        <hh:topBorder type="SOLID" width="0.12mm" color="#000000"/>
        <hh:bottomBorder type="SOLID" width="0.12mm" color="#000000"/>
        <hh:fillBrush><hh:windowBrush faceColor="none" hatchColor="#000000" hatchStyle="NONE" alpha="0"/></hh:fillBrush>
      </hh:borderFill>
    </hh:borderFills>
    <hh:charProperties itemCnt="3">
      <!-- 0: 본문 영어 10pt -->
      <hh:charPr id="0" height="1000" textColor="#000000" shadeColor="none"
                 useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="0">
        <hh:fontRef hangul="0" latin="1" hanja="0" japanese="0" other="1" symbol="0" user="0"/>
        <hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>
        <hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
        <hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>
        <hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
        <hh:bold value="0"/>
        <hh:italic value="0"/>
        <hh:underline type="NONE" shape="SOLID" color="#000000"/>
        <hh:strikeout type="NONE" shape="SOLID" color="#000000"/>
        <hh:outline type="NONE"/>
        <hh:shadow type="NONE" color="#000000" offsetX="0" offsetY="0"/>
      </hh:charPr>
      <!-- 1: 하이라이트 10pt — shadeColor 노란색 -->
      <hh:charPr id="1" height="1000" textColor="#000000" shadeColor="#FFFF00"
                 useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="0">
        <hh:fontRef hangul="0" latin="1" hanja="0" japanese="0" other="1" symbol="0" user="0"/>
        <hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>
        <hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
        <hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>
        <hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
        <hh:bold value="0"/>
        <hh:italic value="0"/>
        <hh:underline type="NONE" shape="SOLID" color="#000000"/>
        <hh:strikeout type="NONE" shape="SOLID" color="#000000"/>
        <hh:outline type="NONE"/>
        <hh:shadow type="NONE" color="#000000" offsetX="0" offsetY="0"/>
      </hh:charPr>
      <!-- 2: 라벨 텍스트박스 안 7pt bold -->
      <hh:charPr id="2" height="700" textColor="#000000" shadeColor="none"
                 useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="0">
        <hh:fontRef hangul="0" latin="1" hanja="0" japanese="0" other="1" symbol="0" user="0"/>
        <hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>
        <hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
        <hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>
        <hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
        <hh:bold value="1"/>
        <hh:italic value="0"/>
        <hh:underline type="NONE" shape="SOLID" color="#000000"/>
        <hh:strikeout type="NONE" shape="SOLID" color="#000000"/>
        <hh:outline type="NONE"/>
        <hh:shadow type="NONE" color="#000000" offsetX="0" offsetY="0"/>
      </hh:charPr>
    </hh:charProperties>
    <hh:paraPrList itemCnt="1">
      <!-- 0: 기본 단락 -->
      <hh:paraPr id="0" tabDef="0" condense="0" fontLineHeight="0" snapToGrid="1"
                 suppressLineNumbers="0" checked="0">
        <hh:align horizontal="JUSTIFY" vertical="BASELINE"/>
        <hh:heading type="NONE" idRef="0" level="0"/>
        <hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="1" widowOrphan="0"
                         keepWithNext="0" keepLines="0" pageBreakBefore="0" lineWrap="BREAK"/>
        <hh:autoSpacing eAsianEng="0" eAsianNum="0"/>
        <hh:margin indent="0" left="0" right="0" prev="0" next="0"/>
        <hh:lineSpacing type="PERCENT" value="160"/>
        <hh:paraBorder borderFillIDRef="0" offsetLeft="0" offsetRight="0"
                       offsetTop="0" offsetBottom="0" connect="0" ignoreMargin="0"/>
      </hh:paraPr>
    </hh:paraPrList>
    <hh:styleList itemCnt="1">
      <hh:style id="0" type="Para" name="본문" engName="Body Text"
                paraPrIDRef="0" charPrIDRef="0" nextStyleIDRef="0" langID="1042" lockForm="0"/>
    </hh:styleList>
  </hh:refList>
</hh:head>
"""


# ── 텍스트박스 / 라벨 빌더 ────────────────────────────────────────────────────


def _label_textbox_xml(
    label_text: str,
    *,
    horz_offset: int,  # 단락 왼쪽 시작점 기준 수평 offset (HWP unit)
    vert_offset: int,  # 단락 기준선 기준 수직 offset (음수 = 위, 양수 = 아래)
    box_w: int = 1200,
    box_h: int = 700,
    border_fill: int = BFILL_NONE,
) -> str:
    """
    단락에 anchor 된 floating 텍스트박스 XML.

    anchor 전략:
        horzRelTo="PARA" horzAlign="LEFT" horzOffset=<horz_offset>
        vertRelTo="PARA" vertAlign="TOP"  vertOffset=<vert_offset>
        treatAsChar="0" → 본문과 겹치거나 옆에 배치 (floating).
        textWrap="TOP_AND_BOTTOM" → 텍스트박스 위/아래로만 본문 흐름.
        allowOverlap="0"

    주의:
        - vertOffset < 0 이면 단락 상단보다 위 → 상단 라벨
        - vertOffset > 단락 높이 이면 단락 하단보다 아래 → 하단 라벨
        - 정밀 align 은 PM 이 한글 오피스로 확인 필요 (font metric 없이 Python 에서
          픽셀 단위 정렬 불가).
    """
    inner_para = (
        f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="{CHARPR_LABEL}">'
        f"<hp:t>{_xe(label_text)}</hp:t>"
        f"</hp:run></hp:p>"
    )
    return (
        f'<hp:drawObj id="0" zOrder="0" numberingType="FIGURE" '
        f'textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" '
        f'dropcapStyle="NONE">'
        f'<hp:sz width="{box_w}" widthRelTo="ABSOLUTE" '
        f'height="{box_h}" heightRelTo="ABSOLUTE" protect="0"/>'
        f'<hp:pos treatAsChar="0" affectLSpacing="1" flowWithText="1" '
        f'allowOverlap="0" holdAnchorAndSO="0" '
        f'vertRelTo="PARA" horzRelTo="PARA" '
        f'vertAlign="TOP" horzAlign="LEFT" '
        f'vertOffset="{vert_offset}" horzOffset="{horz_offset}"/>'
        f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
        f'<hp:textBox margin="0" textDirection="HORIZONTAL" '
        f'numberingType="NONE" isEditable="1">'
        f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
        f'vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" '
        f'textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
        f"{inner_para}"
        f"</hp:subList>"
        f"</hp:textBox>"
        f'<hp:shapeComponent rotateAngle="0" rotateXRelTo="0" rotateYRelTo="0" '
        f'xRelTo="0" yRelTo="0" groupLevel="0">'
        f'<hp:lineShape color="#000000" width="0" style="NONE" startCap="NONE" '
        f'endCap="NONE" startArrow="NONE" endArrow="NONE" '
        f'startArrowSz="MEDIUM_MEDIUM" endArrowSz="MEDIUM_MEDIUM" '
        f'outlineStyle="NORMAL" alpha="0"/>'
        f"<hp:fillBrush>"
        f'<hp:winBrush faceColor="none" hatchColor="#000000" '
        f'hatchStyle="NONE" alpha="0"/>'
        f"</hp:fillBrush>"
        f"</hp:shapeComponent>"
        f"</hp:drawObj>"
    )


def _bracket_run_xml(text: str) -> str:
    """
    괄호 표현: 유니코드 각괄호 [ ] 를 일반 charPr=0 run 으로.

    Phase 1 P1-7/P1-8 에서 "실제 괄호 도형" 구현 여부를 결정.
    PoC 에서는 가장 단순한 방법 — Unicode bracket char 사용.
    """
    escaped = _xe(f"[{text}]")
    return f'<hp:run charPrIDRef="{CHARPR_BODY}"><hp:t>{escaped}</hp:t></hp:run>'


def _highlight_run_xml(text: str) -> str:
    """shadeColor="#FFFF00" charPr=1 로 하이라이트 효과."""
    return f'<hp:run charPrIDRef="{CHARPR_HIGHLIGHT}"><hp:t>{_xe(text)}</hp:t></hp:run>'


def _plain_run_xml(text: str) -> str:
    return f'<hp:run charPrIDRef="{CHARPR_BODY}"><hp:t>{_xe(text)}</hp:t></hp:run>'


# ── section0.xml ──────────────────────────────────────────────────────────────


def _build_section0() -> str:
    """
    단일 단락: "The quick brown fox jumps over the lazy dog."
    구성:
        - 상단 라벨 "S" → floating textBox, vertOffset = -900 (단락 위)
        - 하단 라벨 "V" → floating textBox, vertOffset = +1500 (단락 아래)
        - "The quick brown fox" → 일반 run
        - " jumps " → 하이라이트 run (shadeColor)
        - "over" → 괄호 [ over ] run
        - " the lazy dog." → 일반 run

    단락 구조 (HWPX):
        <hp:p ...>
          [drawObj 상단 라벨 "S"]
          [drawObj 하단 라벨 "V"]
          <hp:run>The quick brown fox</hp:run>
          <hp:run highlight> jumps </hp:run>
          <hp:run>[over]</hp:run>
          <hp:run> the lazy dog.</hp:run>
        </hp:p>

    섹션 정의 (hp:secPr) 는 페이지 크기/여백 포함.
    """
    # 상단 라벨 "S": 단락 시작점 기준 위쪽
    # "The" 가 단락 시작이므로 horzOffset=0, vertOffset=-900 (900 HWP unit = 약 9pt 위)
    label_s = _label_textbox_xml("S", horz_offset=0, vert_offset=-900, box_w=800, box_h=700)

    # 하단 라벨 "V": " jumps " 부분 아래 → horzOffset 근사 (10pt * ~19chars ≈ 19000 HWP unit)
    # PoC 에서는 approximate: "The quick brown fox" = 약 19자 × 600 unit/char ≈ 11400
    label_v = _label_textbox_xml(
        "V",
        horz_offset=11400,
        vert_offset=1600,  # 단락 아래
        box_w=800,
        box_h=700,
    )

    runs = (
        label_s
        + label_v
        + _plain_run_xml("The quick brown fox")
        + _highlight_run_xml(" jumps ")
        + _bracket_run_xml("over")
        + _plain_run_xml(" the lazy dog.")
    )

    # 섹션 정의 단락 (첫 번째 단락에 secPr embed)
    secpr = (
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
        f'<hp:pagePr landscape="PORTRAIT" width="{_PAGE_W}" height="{_PAGE_H}" gutterType="LEFT_ONLY">'
        f'<hp:margin header="{_MAR_HDR}" footer="{_MAR_FTR}" gutter="0" '
        f'left="{_MAR_L}" right="{_MAR_R}" top="{_MAR_TOP}" bottom="{_MAR_BOT}"/>'
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

    sec_para = (
        f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" '
        f'pageBreak="0" columnBreak="0" merged="0">{secpr}</hp:p>'
    )
    body_para = (
        f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" '
        f'pageBreak="0" columnBreak="0" merged="0">{runs}</hp:p>'
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


# ── other required files ───────────────────────────────────────────────────────

_MIMETYPE = b"application/hwp+zip"

_VERSION_XML = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<hv:version xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version">
  <hv:appVersion major="9" minor="0" micro="0" buildNumber="2105"/>
  <hv:fileVersion major="1" minor="3" micro="0" buildNumber="0"/>
</hv:version>
"""

_SETTINGS_XML = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<hs:settings xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"/>
"""

_CONTENT_HPF = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<hpf:rootfile
  xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:opf="http://www.idpf.org/2007/opf/">
  <hpf:item id="header" mediaType="application/xml" href="header.xml"/>
  <hpf:item id="section0" mediaType="application/xml" href="section0.xml"/>
</hpf:rootfile>
"""

_CONTAINER_XML = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
           xmlns:pkg="http://www.idpf.org/2007/opf">
  <rootfiles>
    <rootfile full-path="Contents/content.hpf"
              media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_MANIFEST_XML = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<manifest xmlns="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
  <file-entry full-path="/" media-type="application/hwp+zip"/>
  <file-entry full-path="Contents/header.xml" media-type="application/xml"/>
  <file-entry full-path="Contents/section0.xml" media-type="application/xml"/>
</manifest>
"""

_PRV_TEXT = "The quick brown fox jumps over the lazy dog."


# ── 공개 API ──────────────────────────────────────────────────────────────────


def build_poc_hwpx() -> bytes:
    """
    PoC fixture HWPX bytes 반환.

    구성:
        - "The quick brown fox jumps over the lazy dog."
        - 상단 라벨 "S" (단락 시작 위)
        - 하단 라벨 "V" (jumps 아래)
        - " jumps " 하이라이트 (shadeColor #FFFF00)
        - "[over]" 괄호 (Unicode bracket run)
    """
    section0_xml = _build_section0()

    files: dict[str, bytes] = {
        "Contents/header.xml": _HEADER_XML.encode("utf-8"),
        "Contents/section0.xml": section0_xml.encode("utf-8"),
        "Contents/content.hpf": _CONTENT_HPF.encode("utf-8"),
        "META-INF/container.xml": _CONTAINER_XML.encode("utf-8"),
        "META-INF/manifest.xml": _MANIFEST_XML.encode("utf-8"),
        "settings.xml": _SETTINGS_XML.encode("utf-8"),
        "version.xml": _VERSION_XML.encode("utf-8"),
        "Preview/PrvText.txt": _PRV_TEXT.encode("utf-8"),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zout:
        # mimetype must be first, STORED (OCF 규약)
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zout.writestr(info, _MIMETYPE)

        for name, data in files.items():
            zout.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

    buf.seek(0)
    return buf.read()
