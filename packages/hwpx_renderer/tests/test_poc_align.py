"""
P1-0b — HWPX 텍스트박스 align PoC 단위 테스트 (fix 2차)

검증 대상:
    1. build_poc_hwpx() 가 유효한 ZIP 을 반환하는지
    2. mimetype 파일이 ZIP 첫 번째 엔트리이고 STORED 압축인지
    3. 필수 파일이 모두 존재하는지
    4. section0.xml 에 핵심 XML 요소가 존재하는지
       - 3단 단락 구조: paraPrIDRef="1" (라벨 단락)
       - shadeColor="#FFFF00" (하이라이트)
       - "[over]" (괄호 run)
       - label text "S" and "V" (별도 라벨 단락)
    5. header.xml 에 charPr 3개 + paraPr 2개가 정의되는지

fix 2차 변경사항:
    - floating textBox (vertRelTo=PARA + vertOffset 음수/양수) 제거.
      한컴에서 단락 라인 범위 안에 clamp 되어 취소선처럼 보이는 문제 확인 (PM 검증).
    - 3단 단락 구조로 전환:
        단락 1 (섹션 정의) / 단락 2 (상단 라벨 "S") / 단락 3 (본문) / 단락 4 (하단 라벨 "V")
    - 라벨 단락 스타일 (paraPrIDRef=1): lineSpacing=100%, margin=0

자동화 불가 범위 (단위 테스트 한계):
    - 단위 테스트는 zip 구조와 핵심 XML 요소만 검증한다.
    - 한컴 오피스 실제 오픈 여부 및 렌더링 결과는 PM 수동 확인 필수.
    - fixture 파일 경로: packages/hwpx_renderer/tests/fixtures/poc_align.hwpx
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from hwpx_renderer.poc_align import build_poc_hwpx

# ── fixture 출력 경로 ─────────────────────────────────────────────────────────
_FIXTURE_DIR = Path(__file__).parent / "fixtures"
_FIXTURE_PATH = _FIXTURE_DIR / "poc_align.hwpx"


@pytest.fixture(scope="module")
def hwpx_bytes() -> bytes:
    """PoC HWPX bytes (모듈 단위 1회 생성)."""
    data = build_poc_hwpx()
    # 부산물: fixtures/ 에도 저장 (PM 이 직접 열 수 있도록)
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


# ── 1. ZIP 유효성 ─────────────────────────────────────────────────────────────


def test_is_valid_zip(hwpx_bytes: bytes) -> None:
    """반환값이 유효한 ZIP 파일이어야 한다."""
    assert zipfile.is_zipfile(io.BytesIO(hwpx_bytes))


# ── 2. mimetype ───────────────────────────────────────────────────────────────


def test_mimetype_is_first_entry(hwpx_zip: zipfile.ZipFile) -> None:
    """mimetype 이 첫 번째 엔트리여야 한다 (OCF 규약)."""
    names = hwpx_zip.namelist()
    assert names[0] == "mimetype"


def test_mimetype_is_stored(hwpx_bytes: bytes) -> None:
    """mimetype 엔트리는 ZIP_STORED 로 압축되지 않아야 한다."""
    with zipfile.ZipFile(io.BytesIO(hwpx_bytes)) as zf:
        info = zf.getinfo("mimetype")
        assert info.compress_type == zipfile.ZIP_STORED


def test_mimetype_value(hwpx_zip: zipfile.ZipFile) -> None:
    content = hwpx_zip.read("mimetype")
    assert content == b"application/hwp+zip"


# ── 3. 필수 파일 존재 ─────────────────────────────────────────────────────────

REQUIRED_FILES = [
    "mimetype",
    "Contents/header.xml",
    "Contents/section0.xml",
    "Contents/content.hpf",
    "META-INF/container.xml",
    "META-INF/manifest.xml",
    "META-INF/container.rdf",  # 레퍼런스 HWPX 분석으로 필수 확인 (2026-05-03)
    "version.xml",
    "settings.xml",
    "Preview/PrvText.txt",
]


@pytest.mark.parametrize("filename", REQUIRED_FILES)
def test_required_file_exists(hwpx_zip: zipfile.ZipFile, filename: str) -> None:
    assert filename in hwpx_zip.namelist(), f"Missing file: {filename}"


# ── 4. section0.xml 핵심 요소 ────────────────────────────────────────────────


def test_no_draw_obj_textbox(section0_xml: str) -> None:
    """fix 2차: floating textBox drawObj 제거 — drawObj + textBox 가 없어야 한다.

    3단 단락 구조로 전환했으므로 hp:drawObj, hp:textBox 가 없어야 한다.
    """
    assert "hp:drawObj" not in section0_xml
    assert "hp:textBox" not in section0_xml


def test_has_label_para_style(section0_xml: str) -> None:
    """3단 구조: 라벨 단락이 paraPrIDRef="1" 으로 존재해야 한다."""
    assert 'paraPrIDRef="1"' in section0_xml


def test_has_highlight_shade_color(section0_xml: str) -> None:
    """하이라이트는 charPrIDRef=1 (shadeColor=#FFFF00) 으로 표현되어야 한다."""
    assert 'charPrIDRef="1"' in section0_xml


def test_has_bracket_text(section0_xml: str) -> None:
    """괄호 텍스트 '[over]' 가 본문 run 에 포함되어야 한다."""
    assert "[over]" in section0_xml


def test_has_label_s(section0_xml: str) -> None:
    """상단 라벨 'S' 가 라벨 단락 run 에 존재해야 한다."""
    assert ">S<" in section0_xml


def test_has_label_v(section0_xml: str) -> None:
    """하단 라벨 'V' 가 라벨 단락 run 에 존재해야 한다."""
    assert ">V<" in section0_xml


def test_body_text_present(section0_xml: str) -> None:
    """본문 핵심 텍스트가 section0 에 존재해야 한다."""
    assert "The quick brown fox" in section0_xml
    assert "the lazy dog." in section0_xml
    assert "jumps" in section0_xml


def test_label_para_uses_charpr2(section0_xml: str) -> None:
    """라벨 단락 run 이 charPrIDRef="2" (7pt bold) 를 사용해야 한다."""
    assert 'charPrIDRef="2"' in section0_xml


# ── 5. header.xml charPr + paraPr 정의 ───────────────────────────────────────


def test_header_has_three_charpr(header_xml: str) -> None:
    """header.xml 에 charPr 0, 1, 2 가 모두 정의되어야 한다."""
    assert 'id="0"' in header_xml
    assert 'id="1"' in header_xml
    assert 'id="2"' in header_xml


def test_header_highlight_shade_color(header_xml: str) -> None:
    """charPr id=1 에 shadeColor="#FFFF00" 이 정의되어야 한다."""
    assert 'shadeColor="#FFFF00"' in header_xml


def test_header_body_no_shade(header_xml: str) -> None:
    """charPr id=0 은 shadeColor 가 none 이어야 한다."""
    assert 'shadeColor="none"' in header_xml


def test_header_has_two_parapr(header_xml: str) -> None:
    """header.xml 에 paraPr 0 (본문) 과 1 (라벨) 이 정의되어야 한다."""
    assert 'hh:paraPr id="0"' in header_xml
    assert 'hh:paraPr id="1"' in header_xml


def test_header_label_parapr_line_spacing(header_xml: str) -> None:
    """라벨 단락(paraPr id=1) 은 lineSpacing value=100 이어야 한다."""
    # paraPr id=1 블록 안에 lineSpacing value="100" 이 있어야 함
    # 단순 문자열 검색으로 근사 검증
    assert 'value="100"' in header_xml


# ── 6. fixture 파일 출력 확인 ─────────────────────────────────────────────────


def test_fixture_file_written(hwpx_bytes: bytes) -> None:
    """fixtures/poc_align.hwpx 파일이 디스크에 기록되어야 한다."""
    assert _FIXTURE_PATH.exists()
    assert _FIXTURE_PATH.stat().st_size > 0
