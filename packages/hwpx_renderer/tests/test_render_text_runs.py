"""
P1-8a — HWPX 렌더러 텍스트 런 계열 단위 테스트
(fix: charPr id 연속 배치 + itemCnt 일치 — 한컴 파일 손상 거부 회귀)

검증 대상:
    1. ZIP 구조 + 한컴 스펙 핵심 값 (P1-0b 검증 케이스 흡수)
       - container.xml media-type = "application/hwpml-package+xml"
       - content.hpf 루트 요소 = "opf:package"
       - version.xml 루트 = "hv:HCFVersion" (self-closing)
       - META-INF/container.rdf 존재
       - mimetype 첫 번째 STORED 엔트리
    2. highlight charPr — shadeColor 가 HIGHLIGHT_PALETTE 에 맞게 렌더됨
    3. underline charPr — underline type=BOTTOM color=#000000
    4. inline_note charPr — 작은 폰트 (height=INLINE_NOTE_FONT_SIZE) + 회색 텍스트색
    5. fixture 파일 packages/hwpx_renderer/tests/fixtures/p1_8a_text_runs.hwpx 생성

PM 한글 오피스 검증 항목:
    - "highlights" 단어가 노란 형광펜으로 표시되는가?
    - "underlined" 단어 아래에 단일 밑줄이 표시되는가?
    - "note" 단어가 회색 작은 글씨로 표시되는가?

자동화 불가 범위:
    - 한글 오피스 실제 렌더링 결과는 PM 수동 확인 필수.
    - fixture 파일: packages/hwpx_renderer/tests/fixtures/p1_8a_text_runs.hwpx
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from hwpx_renderer._xml_builders import (
    HIGHLIGHT_PALETTE,
    INLINE_NOTE_FONT_SIZE,
    INLINE_NOTE_TEXT_COLOR,
)
from hwpx_renderer.render import render_passage_with_annotations

# ── fixture 경로 ──────────────────────────────────────────────────────────────
_FIXTURE_DIR = Path(__file__).parent / "fixtures"
_FIXTURE_PATH = _FIXTURE_DIR / "p1_8a_text_runs.hwpx"

# ── 테스트용 상수 ─────────────────────────────────────────────────────────────
_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
_WORKSPACE_ID = UUID("22222222-2222-2222-2222-222222222222")
_PASSAGE_ID = UUID("33333333-3333-3333-3333-333333333333")

# 본문: highlight / underline / inline_note 각 1건을 포함하는 짧은 문장.
# "The quick brown fox highlights the underlined inline note."
#  0         1         2         3         4         5
#  0123456789012345678901234567890123456789012345678901234567890
_BODY_TEXT = "The quick brown fox highlights the underlined inline note."
# 단어 위치 (0-based, [start, end)):
#   "highlights" → [20, 30)
#   "underlined" → [35, 45)
#   "note"       → [53, 57)


def _make_passage(body_text: str = _BODY_TEXT):
    """테스트용 Passage mock (shared.schemas 의존 최소화)."""
    p = MagicMock()
    p.id = _PASSAGE_ID
    p.body_text = body_text
    p.tenant_id = _TENANT_ID
    p.workspace_id = _WORKSPACE_ID
    return p


def _make_span(start: int, end: int):
    """테스트용 AnnotationSpan mock."""
    s = MagicMock()
    s.start = start
    s.end = end
    return s


def _make_annotation(
    kind_value: str, start: int, end: int, color_index: int = 1, text: str | None = None
):
    """테스트용 SyntaxAnnotation mock."""
    from hwpx_renderer._xml_builders import HIGHLIGHT_PALETTE  # noqa: F401 (확인용)

    from shared.schemas.annotation import AnnotationKind

    ann = MagicMock()
    ann.kind = AnnotationKind(kind_value)
    ann.span = _make_span(start, end)
    ann.color_index = color_index
    ann.text = text
    ann.arrow_target_span = None
    ann.passage_id = _PASSAGE_ID
    ann.tenant_id = _TENANT_ID
    ann.workspace_id = _WORKSPACE_ID
    return ann


# ── 공통 HWPX fixture (module scope) ─────────────────────────────────────────


@pytest.fixture(scope="module")
def hwpx_bytes() -> bytes:
    """3종 annotation 포함 HWPX bytes (모듈 단위 1회 생성)."""
    passage = _make_passage()
    annotations = [
        _make_annotation("highlight", 20, 30, color_index=1),  # "highlights"
        _make_annotation("underline", 35, 45),  # "underlined"
        _make_annotation("inline_note", 53, 57, text="(=주석)"),  # "note"
    ]

    data = render_passage_with_annotations(passage, annotations)

    # fixture 파일 저장 (PM 한글 오피스 검증용)
    _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _FIXTURE_PATH.write_bytes(data)

    return data


@pytest.fixture(scope="module")
def hwpx_zip(hwpx_bytes: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(hwpx_bytes))


@pytest.fixture(scope="module")
def section0_xml(hwpx_zip: zipfile.ZipFile) -> str:
    return hwpx_zip.read("Contents/section0.xml").decode("utf-8")


@pytest.fixture(scope="module")
def header_xml(hwpx_zip: zipfile.ZipFile) -> str:
    return hwpx_zip.read("Contents/header.xml").decode("utf-8")


@pytest.fixture(scope="module")
def container_xml(hwpx_zip: zipfile.ZipFile) -> str:
    return hwpx_zip.read("META-INF/container.xml").decode("utf-8")


@pytest.fixture(scope="module")
def content_hpf(hwpx_zip: zipfile.ZipFile) -> str:
    return hwpx_zip.read("Contents/content.hpf").decode("utf-8")


@pytest.fixture(scope="module")
def version_xml(hwpx_zip: zipfile.ZipFile) -> str:
    return hwpx_zip.read("version.xml").decode("utf-8")


# ── 1. ZIP 유효성 + 한컴 스펙 핵심 값 (P1-0b 흡수) ──────────────────────────


def test_is_valid_zip(hwpx_bytes: bytes) -> None:
    """반환값이 유효한 ZIP 파일이어야 한다."""
    assert zipfile.is_zipfile(io.BytesIO(hwpx_bytes))


def test_mimetype_is_first_entry(hwpx_zip: zipfile.ZipFile) -> None:
    """mimetype 이 첫 번째 엔트리여야 한다 (OCF 규약)."""
    assert hwpx_zip.namelist()[0] == "mimetype"


def test_mimetype_is_stored(hwpx_bytes: bytes) -> None:
    """mimetype 엔트리는 ZIP_STORED 여야 한다."""
    with zipfile.ZipFile(io.BytesIO(hwpx_bytes)) as zf:
        assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED


def test_mimetype_value(hwpx_zip: zipfile.ZipFile) -> None:
    assert hwpx_zip.read("mimetype") == b"application/hwp+zip"


REQUIRED_FILES = [
    "mimetype",
    "Contents/header.xml",
    "Contents/section0.xml",
    "Contents/content.hpf",
    "META-INF/container.xml",
    "META-INF/manifest.xml",
    "META-INF/container.rdf",
    "version.xml",
    "settings.xml",
    "Preview/PrvText.txt",
]


@pytest.mark.parametrize("filename", REQUIRED_FILES)
def test_required_file_exists(hwpx_zip: zipfile.ZipFile, filename: str) -> None:
    assert filename in hwpx_zip.namelist(), f"Missing: {filename}"


def test_container_xml_media_type(container_xml: str) -> None:
    """container.xml rootfile media-type = 'application/hwpml-package+xml'."""
    assert 'media-type="application/hwpml-package+xml"' in container_xml


def test_container_xml_namespaces(container_xml: str) -> None:
    """container.xml 에 ocf + hpf namespace 선언 필수."""
    assert 'xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container"' in container_xml
    assert 'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf"' in container_xml


def test_content_hpf_root_element(content_hpf: str) -> None:
    """content.hpf 루트 요소 = 'opf:package'."""
    assert "<opf:package" in content_hpf


def test_container_rdf_exists(hwpx_zip: zipfile.ZipFile) -> None:
    """META-INF/container.rdf 파일이 존재해야 한다."""
    assert "META-INF/container.rdf" in hwpx_zip.namelist()


def test_version_xml_hcfversion_element(version_xml: str) -> None:
    """version.xml 루트 = 'hv:HCFVersion' self-closing."""
    assert "<hv:HCFVersion" in version_xml
    assert "</hv:HCFVersion>" not in version_xml


# ── 2. header.xml charPr 검증 ─────────────────────────────────────────────────


def test_header_has_highlight_shade_colors(header_xml: str) -> None:
    """header.xml 에 12색 팔레트 shadeColor 가 모두 정의되어야 한다."""
    for idx in range(1, 13):
        color = HIGHLIGHT_PALETTE[idx]
        assert color in header_xml, f"HIGHLIGHT_PALETTE[{idx}]={color} not found in header.xml"


def test_header_has_underline_bottom(header_xml: str) -> None:
    """header.xml 에 underline type=BOTTOM 이 정의되어야 한다.

    한컴 스펙: type="BOTTOM" = 하단 단일 밑줄.
    type="SINGLE" 은 한컴 오피스에서 무시됨 (레퍼런스 template.hwpx 검증).
    """
    assert 'type="BOTTOM"' in header_xml


def test_header_has_inline_note_charpr(header_xml: str) -> None:
    """header.xml 에 inline_note 용 charPr (작은 폰트 + 회색) 가 정의되어야 한다."""
    assert f'height="{INLINE_NOTE_FONT_SIZE}"' in header_xml
    assert INLINE_NOTE_TEXT_COLOR in header_xml


def test_header_has_body_charpr(header_xml: str) -> None:
    """header.xml 에 본문 charPr id=0 이 존재해야 한다."""
    assert 'id="0"' in header_xml
    assert 'shadeColor="none"' in header_xml


def test_header_has_two_parapr(header_xml: str) -> None:
    """header.xml 에 paraPr 0 (본문) + 1 (라벨) 이 정의되어야 한다."""
    assert 'hh:paraPr id="0"' in header_xml
    assert 'hh:paraPr id="1"' in header_xml


# ── 3. section0.xml 본문 분할 검증 ───────────────────────────────────────────


def test_body_text_present_in_section(section0_xml: str) -> None:
    """본문 텍스트가 section0.xml 에 있어야 한다."""
    assert "The quick brown fox" in section0_xml
    assert "highlights" in section0_xml
    assert "underlined" in section0_xml
    assert "note" in section0_xml


def test_highlight_charpr_in_section(section0_xml: str) -> None:
    """highlight charPr (id=4, color_index=1) 가 section0 run 에 참조되어야 한다."""
    # color_index=1 → charPr id=4 (_highlight_charpr_id(1) = 4 + 1 - 1 = 4)
    assert 'charPrIDRef="4"' in section0_xml


def test_underline_charpr_in_section(section0_xml: str) -> None:
    """underline charPr (id=2) 가 section0 run 에 참조되어야 한다."""
    assert 'charPrIDRef="2"' in section0_xml


def test_inline_note_charpr_in_section(section0_xml: str) -> None:
    """inline_note charPr (id=3) 가 section0 run 에 참조되어야 한다."""
    assert 'charPrIDRef="3"' in section0_xml


def test_body_charpr_in_section(section0_xml: str) -> None:
    """plain body charPr (id=0) 가 section0 run 에 참조되어야 한다."""
    assert 'charPrIDRef="0"' in section0_xml


# ── 4. highlight 색상 다양성 테스트 ─────────────────────────────────────────


def test_highlight_color_index_2_uses_correct_shade() -> None:
    """color_index=2 로 생성한 HWPX 에 HIGHLIGHT_PALETTE[2] shadeColor 가 포함되어야 한다."""
    passage = _make_passage()
    anns = [_make_annotation("highlight", 4, 9, color_index=2)]  # "quick"
    data = render_passage_with_annotations(passage, anns)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        header = zf.read("Contents/header.xml").decode("utf-8")
    assert HIGHLIGHT_PALETTE[2] in header


# ── 5. 빈 annotation 케이스 ──────────────────────────────────────────────────


def test_render_with_no_annotations() -> None:
    """annotation 없을 때도 유효한 HWPX 를 반환해야 한다."""
    passage = _make_passage()
    data = render_passage_with_annotations(passage, [])
    assert zipfile.is_zipfile(io.BytesIO(data))
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sec = zf.read("Contents/section0.xml").decode("utf-8")
    assert "The quick brown fox" in sec


# ── 6. unsupported kind (P1-8b/c) silent skip ────────────────────────────────


def test_unsupported_kind_does_not_raise() -> None:
    """top_label 등 미구현 kind 가 있어도 예외 없이 렌더되어야 한다."""
    passage = _make_passage()
    anns = [
        _make_annotation("highlight", 20, 30, color_index=1),
        _make_annotation("top_label", 4, 9),  # P1-8b 예정 — silent skip
    ]
    data = render_passage_with_annotations(passage, anns)
    assert zipfile.is_zipfile(io.BytesIO(data))


# ── 7. out-of-range span (경계 안전성) ───────────────────────────────────────


def test_out_of_range_span_skipped() -> None:
    """span.end 가 body_text 길이를 초과하는 annotation 은 skip 되어야 한다."""
    passage = _make_passage()
    n = len(_BODY_TEXT)
    anns = [_make_annotation("highlight", 0, n + 100)]  # 범위 초과
    # 예외 없이 렌더되어야 함
    data = render_passage_with_annotations(passage, anns)
    assert zipfile.is_zipfile(io.BytesIO(data))


# ── 8. fixture 파일 출력 확인 ─────────────────────────────────────────────────


def test_fixture_file_written(hwpx_bytes: bytes) -> None:
    """fixtures/p1_8a_text_runs.hwpx 파일이 디스크에 기록되어야 한다."""
    assert _FIXTURE_PATH.exists()
    assert _FIXTURE_PATH.stat().st_size > 0


# ── 9. charPr id 연속성 + itemCnt 일치 회귀 테스트 (한컴 파일 손상 방지) ─────
# 배경: 비연속 id (0,1,10,30,50) + itemCnt=16 조합이 한컴 파서 OOB → 손상 거부.
# 이 테스트가 통과하면 해당 패턴이 재발하지 않음을 보장한다.


def test_header_charprs_have_consecutive_ids(header_xml: str) -> None:
    """charPr id 가 0 부터 (itemCnt-1) 까지 빠짐없이 연속해야 한다.

    한컴 HWPX 스펙: itemCnt 는 실제 항목 수이며, id 는 0~(itemCnt-1) 연속.
    비연속 id 는 한컴 파서가 OOB 처리 → 파일 손상 팝업 발생.
    """
    # itemCnt 추출
    item_cnt_match = re.search(r'<hh:charProperties itemCnt="(\d+)">', header_xml)
    assert item_cnt_match, "charProperties itemCnt 를 header.xml 에서 찾을 수 없음"
    item_cnt = int(item_cnt_match.group(1))

    # 실제 charPr id 목록 추출
    ids = [int(m) for m in re.findall(r'<hh:charPr id="(\d+)"', header_xml)]

    assert len(ids) == item_cnt, f"charPr 실제 개수({len(ids)}) 와 itemCnt({item_cnt}) 불일치"
    assert sorted(ids) == list(range(item_cnt)), (
        f"charPr id 가 0~{item_cnt - 1} 연속이 아님: 실제 ids={sorted(ids)}"
    )


def test_header_charpr_item_cnt_equals_charpr_count(header_xml: str) -> None:
    """itemCnt 속성값이 실제 <hh:charPr> 요소 개수와 정확히 일치해야 한다."""
    item_cnt_match = re.search(r'<hh:charProperties itemCnt="(\d+)">', header_xml)
    assert item_cnt_match, "charProperties itemCnt 를 header.xml 에서 찾을 수 없음"
    item_cnt = int(item_cnt_match.group(1))

    actual_count = len(re.findall(r"<hh:charPr ", header_xml))
    assert actual_count == item_cnt, f"itemCnt={item_cnt} 이지만 실제 charPr 요소 수={actual_count}"


# ── 10. content.hpf opf:item id 확장자 금지 회귀 테스트 (P1-8a 2차 fix) ───────
# 배경: _make_content_hpf 가 section 파일명("section0.xml")을 opf:item id 로 그대로 사용하면
#       한컴 파서가 id 에 점(".")이 포함된 식별자를 거부해 파일 손상 팝업을 발생시킨다.
#       poc_align.hwpx / template.hwpx 양쪽 모두 id="section0" (확장자 없음) 패턴을 사용한다.


def test_content_hpf_section_item_id_has_no_extension(content_hpf: str) -> None:
    """content.hpf 의 opf:item id 에 파일 확장자(".xml")가 포함되면 안 된다.

    한컴 파서는 id 속성에 "."이 포함된 식별자를 파싱 에러로 처리해
    "파일이 손상되었습니다" 팝업을 띄운다.
    올바른 패턴: id="section0" href="Contents/section0.xml"
    잘못된 패턴: id="section0.xml" href="Contents/section0.xml"
    """
    # opf:item id 목록 추출 (header / section / settings 모두 포함)
    item_ids = re.findall(r'<opf:item\s+id="([^"]+)"', content_hpf)
    assert item_ids, "content.hpf 에서 opf:item 요소를 찾을 수 없음"

    for item_id in item_ids:
        assert "." not in item_id, (
            f"opf:item id='{item_id}' 에 확장자가 포함되어 있음 — "
            "한컴 파서 파일 손상 팝업 유발. _make_content_hpf 의 _stem() 함수 확인 필요."
        )


def test_content_hpf_section_itemref_idref_matches_item_id(content_hpf: str) -> None:
    """opf:spine 의 itemref idref 가 manifest 의 item id 와 정확히 일치해야 한다.

    id/idref 불일치는 한컴 파서가 섹션 파일을 찾지 못해 손상 거부를 유발한다.
    """
    item_ids = set(re.findall(r'<opf:item\s+id="([^"]+)"', content_hpf))
    item_refs = re.findall(r'<opf:itemref\s+idref="([^"]+)"', content_hpf)

    assert item_refs, "content.hpf 에서 opf:itemref 요소를 찾을 수 없음"

    for idref in item_refs:
        assert idref in item_ids, (
            f"opf:itemref idref='{idref}' 에 대응하는 opf:item id 가 manifest 에 없음"
        )
