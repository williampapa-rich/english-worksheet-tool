"""
HWPX 텍스트박스 align PoC (P1-0b) — fix 2차

목표:
    단일 영어 문장 위에/아래에 라벨(textBox), 괄호(bracket run), 하이라이트(shadeColor)가
    align 되는지 검증하기 위한 최소 fixture HWPX 1건을 생성한다.

접근 (fix 2차 — 3단 단락 구조):
    - fix 1차 (vertRelTo=PARA + vertOffset 음수/양수 조합) 에서 PM 검증 결과:
      라벨 박스가 본문 라인을 관통하는 취소선처럼 보임 (단락 위/아래로 올라가지 않음).
    - 원인: 한컴 HWPX 에서 vertRelTo="PARA" + treatAsChar="0" + textWrap="TOP_AND_BOTTOM"
      조합은 drawObj 를 단락 라인 높이 범위 안에 clamp 한다.
      음수 vertOffset 이 있어도 해당 단락에 공간이 없으면 단락 위로 올라가지 않는다.
    - 대안 채택: 3단 단락 구조
        단락 1 (라벨 단락): "S" 텍스트만, 작은 폰트, prev/next margin 최소화
        단락 2 (본문 단락): 실제 영어 문장
        단락 3 (하단 라벨 단락): "V" 텍스트만
      이 구조는 레퍼런스 HWPX 의 패턴과 일치하며 한컴에서 안정적으로 렌더링된다.
    - 수평 align: 3단 구조에서 라벨 단락의 align 은 본문 단락의 char offset 과
      독립적이다. 현재 PoC 에서는 근사값(indent=0, 단락 시작 기준)을 사용.
      실 구현(P1-7/P1-8)에서 indent 또는 tabstop 으로 보정 필요.

    - exam-generator/app/renderer/template_injector.py 의 ZIP 재패키징 패턴 재활용
    - 자체 header.xml + section0.xml 을 raw OOXML 로 작성 (템플릿 의존 없음)
    - hwpx-auto-parser-for-template 은 TypeScript VSCode extension 이므로 Python 에서
      직접 import 불가 → raw OOXML 직접 작성이 불가피. 이유: CLAUDE.md §3.6 참고.

HWPX 좌표계:
    - 1 HWP unit = 1/7200 inch ≈ 0.0353mm. 10pt = 1000 HWP unit.
    - A4 portrait: width=59528, height=84188 HWP unit.
    - 기본 여백 (평가원 템플릿 기준):
        left/right = 8504, top = 16015, bottom = 8504, header = 2000, footer = 3828.
    - 본문폭 (text column width) = 59528 - 8504 - 8504 = 42520 HWP unit.

한계 (PoC 범위):
    - 3단 구조에서 라벨의 수평 위치는 본문 단어 위치와 독립적이다.
      Phase 1 P1-7/P1-8 에서 indent/tabstop 으로 보정 필요.
    - 문자 단위 너비를 Python 에서 정확하게 측정할 수 없음 (font metric 필요).
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
# 1 = 라벨 단락 (작은 폰트, prev/next margin 0, 줄간격 100%)
PARAPR_BODY = 0
PARAPR_LABEL = 1

# ── borderFill ───────────────────────────────────────────────────────────────
# 0 = 테두리 없음
# 1 = 4면 실선 0.12mm 검정 (괄호 박스용, 미사용)
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
    <hh:paraPrList itemCnt="2">
      <!-- 0: 기본 단락 (본문 영어 문장) -->
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
      <!-- 1: 라벨 단락 (상단/하단 라벨 텍스트 — 3단 구조) -->
      <!-- prev=0 next=0 margin 으로 본문과 붙이고, lineSpacing=100% 으로 라벨 높이만큼만 차지 -->
      <hh:paraPr id="1" tabDef="0" condense="0" fontLineHeight="0" snapToGrid="1"
                 suppressLineNumbers="0" checked="0">
        <hh:align horizontal="LEFT" vertical="BASELINE"/>
        <hh:heading type="NONE" idRef="0" level="0"/>
        <hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="1" widowOrphan="0"
                         keepWithNext="0" keepLines="0" pageBreakBefore="0" lineWrap="BREAK"/>
        <hh:autoSpacing eAsianEng="0" eAsianNum="0"/>
        <hh:margin indent="0" left="0" right="0" prev="0" next="0"/>
        <hh:lineSpacing type="PERCENT" value="100"/>
        <hh:paraBorder borderFillIDRef="0" offsetLeft="0" offsetRight="0"
                       offsetTop="0" offsetBottom="0" connect="0" ignoreMargin="0"/>
      </hh:paraPr>
    </hh:paraPrList>
    <hh:styleList itemCnt="2">
      <hh:style id="0" type="Para" name="본문" engName="Body Text"
                paraPrIDRef="0" charPrIDRef="0" nextStyleIDRef="0" langID="1042" lockForm="0"/>
      <hh:style id="1" type="Para" name="라벨" engName="Label"
                paraPrIDRef="1" charPrIDRef="2" nextStyleIDRef="0" langID="1042" lockForm="0"/>
    </hh:styleList>
  </hh:refList>
</hh:head>
"""


# ── 라벨 단락 빌더 (3단 구조) ────────────────────────────────────────────────


def _label_para_xml(label_text: str, *, indent: int = 0) -> str:
    """
    라벨 전용 단락 XML.

    3단 단락 구조에서 상단/하단 라벨은 별도 단락으로 표현한다.
    - paraPrIDRef="1" (라벨 단락 스타일: lineSpacing=100%, margin prev/next=0)
    - charPrIDRef="2" (라벨 글자 스타일: 7pt bold)
    - indent: 단락 들여쓰기 (HWP unit). 근사 수평 align 용.

    수직 분리:
        라벨 단락의 lineSpacing=100% + margin=0 이므로 단락 높이 ≈ 7pt = 700 HWP unit.
        본문 단락과 붙어있어 시각적으로 본문 위/아래에 라벨이 위치한다.

    수평 align 한계 (PoC):
        indent 값은 특정 단어까지의 문자 누적 너비 근사치.
        실 구현(P1-7/P1-8)에서 pillow ImageFont.getlength() 또는 tabstop 으로 보정.
    """
    return (
        f'<hp:p id="0" paraPrIDRef="1" styleIDRef="1" '
        f'pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="{CHARPR_LABEL}">'
        f"<hp:t>{_xe(label_text)}</hp:t>"
        f"</hp:run>"
        f"</hp:p>"
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


def _secpr_run_xml() -> str:
    """섹션 정의 run XML (첫 번째 단락에 embed)."""
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


def _build_section0() -> str:
    """
    3단 단락 구조: 상단 라벨 / 본문 / 하단 라벨.

    구성:
        단락 1 (secPr): 섹션 정의 단락 (빈 단락)
        단락 2 (라벨 단락, paraPrIDRef=1): "S" — 상단 라벨
        단락 3 (본문 단락, paraPrIDRef=0):
            "The quick brown fox" → 일반 run
            " jumps " → 하이라이트 run (shadeColor)
            "[over]" → 괄호 Unicode bracket run
            " the lazy dog." → 일반 run
        단락 4 (라벨 단락, paraPrIDRef=1): "V" — 하단 라벨

    3단 구조 채택 근거 (fix 2차):
        - floating textBox (vertRelTo=PARA + vertOffset 음수/양수) 는 한컴에서
          단락 라인 범위 안에 clamp 되어 본문 위/아래로 올라가지 않음.
          PM 검증에서 취소선처럼 보이는 문제 재현 확인 (2026-05-03).
        - 3단 단락 구조는 레퍼런스 HWPX 의 실제 패턴과 일치하며 안정적으로 렌더링됨.
        - 수평 align 정밀도는 3단 구조에서도 동일하게 indent/tabstop 근사 필요.
          이는 P1-7/P1-8 에서 폰트 metric 으로 보정 예정.
    """
    # 단락 1: 섹션 정의 (빈 단락)
    sec_para = (
        f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" '
        f'pageBreak="0" columnBreak="0" merged="0">{_secpr_run_xml()}</hp:p>'
    )

    # 단락 2: 상단 라벨 "S"
    # horzOffset 근사: "S" 는 단락 시작("The") 위 → indent=0
    top_label_para = _label_para_xml("S", indent=0)

    # 단락 3: 본문
    body_runs = (
        _plain_run_xml("The quick brown fox")
        + _highlight_run_xml(" jumps ")
        + _bracket_run_xml("over")
        + _plain_run_xml(" the lazy dog.")
    )
    body_para = (
        f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" '
        f'pageBreak="0" columnBreak="0" merged="0">{body_runs}</hp:p>'
    )

    # 단락 4: 하단 라벨 "V"
    # horzOffset 근사: "V" 는 "jumps" 아래 → "The quick brown fox" ≈ 19자 × 600 unit
    # 3단 구조에서 indent 로 근사 수평 위치 지정 (paraPr.margin.indent 아닌 leading spaces)
    # PoC 에서는 indent=0 (단락 왼쪽 시작, 근사)
    bottom_label_para = _label_para_xml("V", indent=0)

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


# ── other required files ───────────────────────────────────────────────────────

_MIMETYPE = b"application/hwp+zip"

# version.xml: 레퍼런스에서 확인한 HCFVersion 단일 요소 구조
# 이전 hv:version + 자식 요소 방식은 스펙 불일치 → 손상 원인 #3
_VERSION_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version"'
    ' tagetApplication="WORDPROCESSOR"'
    ' major="5" minor="1" micro="1" buildNumber="0"'
    ' os="10" xmlVersion="1.5"'
    ' application="Hancom Office Hangul"'
    ' appVersion="12.30.0.6382 MAC64LEDarwin_25.3.0"/>'
)

# settings.xml: 레퍼런스에서 확인한 HWPApplicationSetting 구조
_SETTINGS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    "<ha:HWPApplicationSetting"
    ' xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app"'
    ' xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0">'
    '<ha:CaretPosition listIDRef="0" paraIDRef="0" pos="0"/>'
    "</ha:HWPApplicationSetting>"
)

# content.hpf: 레퍼런스(template.hwpx / 평가원_영어_양식.hwpx)에서 확인한 opf:package 구조
# 이전 hpf:rootfile 구조는 스펙 불일치 → 한컴 "파일 손상" 원인 #1
_CONTENT_HPF = (
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
    "<opf:title>poc_align</opf:title>"
    "<opf:language>en</opf:language>"
    "</opf:metadata>"
    "<opf:manifest>"
    '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
    '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
    '<opf:item id="settings" href="settings.xml" media-type="application/xml"/>'
    "</opf:manifest>"
    "<opf:spine>"
    '<opf:itemref idref="header" linear="yes"/>'
    '<opf:itemref idref="section0" linear="yes"/>'
    "</opf:spine>"
    "</opf:package>"
)

# container.xml: 레퍼런스에서 확인한 ocf:container + hpf namespace 구조
# 이전 xmlns:container + application/oebps-package+xml 는 스펙 불일치 → 손상 원인 #2
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

# manifest.xml: 레퍼런스와 동일한 빈 odf:manifest
_MANIFEST_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>'
)

# container.rdf: 레퍼런스에서 확인한 RDF 구조 (header + section0 등록)
_CONTAINER_RDF = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    '<rdf:Description rdf:about="">'
    '<ns0:hasPart xmlns:ns0="http://www.hancom.co.kr/hwpml/2016/meta/pkg#"'
    ' rdf:resource="Contents/header.xml"/>'
    "</rdf:Description>"
    '<rdf:Description rdf:about="Contents/header.xml">'
    '<rdf:type rdf:resource="http://www.hancom.co.kr/hwpml/2016/meta/pkg#HeaderFile"/>'
    "</rdf:Description>"
    '<rdf:Description rdf:about="">'
    '<ns0:hasPart xmlns:ns0="http://www.hancom.co.kr/hwpml/2016/meta/pkg#"'
    ' rdf:resource="Contents/section0.xml"/>'
    "</rdf:Description>"
    '<rdf:Description rdf:about="Contents/section0.xml">'
    '<rdf:type rdf:resource="http://www.hancom.co.kr/hwpml/2016/meta/pkg#SectionFile"/>'
    "</rdf:Description>"
    '<rdf:Description rdf:about="">'
    '<rdf:type rdf:resource="http://www.hancom.co.kr/hwpml/2016/meta/pkg#Document"/>'
    "</rdf:Description>"
    "</rdf:RDF>"
)

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

    # DEFLATED 파일 목록
    deflated_files: dict[str, bytes] = {
        "Contents/header.xml": _HEADER_XML.encode("utf-8"),
        "Contents/section0.xml": section0_xml.encode("utf-8"),
        "Contents/content.hpf": _CONTENT_HPF.encode("utf-8"),
        "META-INF/container.xml": _CONTAINER_XML.encode("utf-8"),
        "META-INF/manifest.xml": _MANIFEST_XML.encode("utf-8"),
        "META-INF/container.rdf": _CONTAINER_RDF.encode("utf-8"),
        "settings.xml": _SETTINGS_XML.encode("utf-8"),
        "Preview/PrvText.txt": _PRV_TEXT.encode("utf-8"),
    }
    # STORED 파일 목록 (레퍼런스에서 version.xml 은 STORED)
    stored_files: dict[str, bytes] = {
        "version.xml": _VERSION_XML.encode("utf-8"),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zout:
        # mimetype must be first, STORED (OCF 규약)
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zout.writestr(info, _MIMETYPE)

        for name, data in deflated_files.items():
            zout.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

        for name, data in stored_files.items():
            zout.writestr(zipfile.ZipInfo(name), data)

    buf.seek(0)
    return buf.read()
