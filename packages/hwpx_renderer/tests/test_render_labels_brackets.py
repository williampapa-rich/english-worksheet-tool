"""P1-8b — HWPX 렌더러 라벨/괄호 단위 테스트.

검증 대상:
    1. top_label / bottom_label 단락이 본문 단락 앞/뒤에 삽입되는가 (3단 단락 구조).
    2. 같은 종류의 라벨이 여러 개 있을 때 한 단락으로 join 되는가.
    3. bracket annotation 의 Unicode 여닫이 ( ADR-0007: `[ ]` `( )` `{ }` ) 가
       본문 inline run 으로 정확한 위치에 삽입되는가.
    4. bracket 이 highlight 와 겹쳐도 charPr 가 보존되는가.
    5. 라벨이 없을 때 라벨 단락이 생성되지 않는가 (빈 단락 방지).
    6. fixture 파일 packages/hwpx_renderer/tests/fixtures/p1_8b_labels_brackets.hwpx 생성.

PM 한글 오피스 검증 항목:
    - "S V" 라벨이 본문 위에 표시되는가?
    - "동격" 라벨이 본문 아래에 표시되는가?
    - "[over]" 와 "(brown)" 가 괄호 표기로 본문에 표시되는가?
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from hwpx_renderer.render import render_passage_with_annotations

# ── fixture 경로 ──────────────────────────────────────────────────────────────
_FIXTURE_DIR = Path(__file__).parent / "fixtures"
_FIXTURE_PATH = _FIXTURE_DIR / "p1_8b_labels_brackets.hwpx"

# ── 테스트용 상수 ─────────────────────────────────────────────────────────────
_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
_WORKSPACE_ID = UUID("22222222-2222-2222-2222-222222222222")
_PASSAGE_ID = UUID("33333333-3333-3333-3333-333333333333")

# 본문: bracket / 라벨 다중 케이스를 포함하는 짧은 문장.
# "The quick brown fox jumps over the lazy dog."
#  0         1         2         3         4
#  012345678901234567890123456789012345678901234
_BODY_TEXT = "The quick brown fox jumps over the lazy dog."
# 단어 위치 (0-based, [start, end)):
#   "The"   → [0, 3)
#   "quick" → [4, 9)
#   "brown" → [10, 15)
#   "fox"   → [16, 19)
#   "jumps" → [20, 25)
#   "over"  → [26, 30)
#   "the"   → [31, 34)
#   "lazy"  → [35, 39)
#   "dog"   → [40, 43)


def _make_passage(body_text: str = _BODY_TEXT):
    p = MagicMock()
    p.id = _PASSAGE_ID
    p.body_text = body_text
    p.tenant_id = _TENANT_ID
    p.workspace_id = _WORKSPACE_ID
    return p


def _make_span(start: int, end: int):
    s = MagicMock()
    s.start = start
    s.end = end
    return s


def _make_annotation(
    kind_value: str,
    start: int,
    end: int,
    *,
    color_index: int = 1,
    text: str | None = None,
    bracket_style: str | None = None,
):
    from shared.schemas.annotation import AnnotationKind

    ann = MagicMock()
    ann.kind = AnnotationKind(kind_value)
    ann.span = _make_span(start, end)
    ann.color_index = color_index
    ann.text = text
    ann.bracket_style = bracket_style
    ann.arrow_target_span = None
    ann.passage_id = _PASSAGE_ID
    ann.tenant_id = _TENANT_ID
    ann.workspace_id = _WORKSPACE_ID
    return ann


# ── 공통 HWPX fixture ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def hwpx_bytes() -> bytes:
    """라벨 + 괄호 + 하이라이트 조합 HWPX bytes (PM 검증용 fixture 파일 생성)."""
    passage = _make_passage()
    annotations = [
        # top_label 2개 — 본문 단락 위에 "S V" 1단락으로 join
        _make_annotation("top_label", 16, 19, text="S"),  # "fox" 위
        _make_annotation("top_label", 20, 25, text="V"),  # "jumps" 위
        # bottom_label 1개 — 본문 단락 아래
        _make_annotation("bottom_label", 35, 43, text="동격"),  # "lazy dog" 아래
        # bracket — Unicode [over]
        _make_annotation("bracket", 26, 30, bracket_style="[]"),  # "over"
        # bracket — Unicode (brown)
        _make_annotation("bracket", 10, 15, bracket_style="()"),  # "brown"
        # highlight — bracket 과 다른 위치 ("jumps")
        _make_annotation("highlight", 20, 25, color_index=1),
    ]

    data = render_passage_with_annotations(passage, annotations)

    _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _FIXTURE_PATH.write_bytes(data)
    return data


@pytest.fixture(scope="module")
def hwpx_zip(hwpx_bytes: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(hwpx_bytes))


@pytest.fixture(scope="module")
def section0_xml(hwpx_zip: zipfile.ZipFile) -> str:
    return hwpx_zip.read("Contents/section0.xml").decode("utf-8")


# ── 1. ZIP 유효성 ────────────────────────────────────────────────────────────


def test_is_valid_zip(hwpx_bytes: bytes) -> None:
    assert zipfile.is_zipfile(io.BytesIO(hwpx_bytes))


def test_fixture_file_written(hwpx_bytes: bytes) -> None:
    assert _FIXTURE_PATH.exists()
    assert _FIXTURE_PATH.stat().st_size > 0


# ── 2. 3단 단락 구조 검증 ────────────────────────────────────────────────────


def _paragraph_count(section_xml: str) -> int:
    """section0.xml 안의 <hp:p ...> 단락 개수."""
    return len(re.findall(r"<hp:p\s", section_xml))


def test_three_paragraph_structure(section0_xml: str) -> None:
    """secPr + top_label + 본문 + bottom_label = 4 단락."""
    assert _paragraph_count(section0_xml) == 4


def test_top_label_para_uses_label_style(section0_xml: str) -> None:
    """top_label 단락이 paraPrIDRef=1 (라벨 단락) 을 사용해야 한다."""
    assert 'paraPrIDRef="1"' in section0_xml
    assert 'styleIDRef="1"' in section0_xml


def test_top_label_text_in_section(section0_xml: str) -> None:
    """top_label 'S' 와 'V' 가 한 단락 안에 공백으로 join 되어야 한다."""
    assert "S V" in section0_xml


def test_bottom_label_text_in_section(section0_xml: str) -> None:
    """bottom_label '동격' 이 section0 에 있어야 한다."""
    assert "동격" in section0_xml


def test_label_paragraph_order(section0_xml: str) -> None:
    """단락 순서: secPr → top_label → 본문 → bottom_label."""
    s_idx = section0_xml.index(">S V<")
    body_idx = section0_xml.index("The quick")
    bottom_idx = section0_xml.index("동격")
    assert s_idx < body_idx < bottom_idx


# ── 3. bracket Unicode 삽입 검증 ─────────────────────────────────────────────


def test_bracket_square_inserted(section0_xml: str) -> None:
    """Unicode `[ ]` 가 본문 inline run 으로 삽입되어야 한다."""
    # "[" + "over" + "]" 패턴은 별 run 으로 분리되어 있어 인접 텍스트를 직접 비교할 수 없으므로
    # 각 글자가 hp:t 안에 단독 존재하는지 확인.
    assert "<hp:t>[</hp:t>" in section0_xml
    assert "<hp:t>]</hp:t>" in section0_xml


def test_bracket_round_inserted(section0_xml: str) -> None:
    """Unicode `( )` 가 본문 inline run 으로 삽입되어야 한다."""
    assert "<hp:t>(</hp:t>" in section0_xml
    assert "<hp:t>)</hp:t>" in section0_xml


def test_bracket_open_before_target_word(section0_xml: str) -> None:
    """`[` 가 'over' 직전에 위치해야 한다."""
    open_idx = section0_xml.index("<hp:t>[</hp:t>")
    over_idx = section0_xml.index(">over<")
    close_idx = section0_xml.index("<hp:t>]</hp:t>")
    assert open_idx < over_idx < close_idx


# ── 4. bracket + highlight 공존 ──────────────────────────────────────────────


def test_highlight_charpr_preserved_with_bracket(section0_xml: str) -> None:
    """bracket 과 다른 위치의 highlight charPr (id=4) 가 보존되어야 한다."""
    assert 'charPrIDRef="4"' in section0_xml


def test_jumps_in_highlight_run(section0_xml: str) -> None:
    """'jumps' 는 highlight charPr (id=4) run 안에 있어야 한다."""
    # charPrIDRef="4" 다음에 hp:t 안 'jumps' 가 와야 함
    assert re.search(r'charPrIDRef="4"><hp:t>jumps</hp:t>', section0_xml)


# ── 5. 빈 라벨 단락 방지 ──────────────────────────────────────────────────────


def test_no_label_paragraph_when_no_labels() -> None:
    """라벨 annotation 이 없으면 라벨 단락이 생성되지 않아야 한다 (총 2 단락)."""
    passage = _make_passage()
    anns = [_make_annotation("highlight", 0, 3, color_index=1)]
    data = render_passage_with_annotations(passage, anns)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sec = zf.read("Contents/section0.xml").decode("utf-8")
    # secPr + 본문 = 2 단락
    assert _paragraph_count(sec) == 2


def test_only_top_label_creates_three_paragraphs() -> None:
    """top_label 만 있으면 secPr + top_label + 본문 = 3 단락."""
    passage = _make_passage()
    anns = [_make_annotation("top_label", 0, 3, text="S")]
    data = render_passage_with_annotations(passage, anns)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sec = zf.read("Contents/section0.xml").decode("utf-8")
    assert _paragraph_count(sec) == 3


def test_label_with_empty_text_is_skipped() -> None:
    """text=None 인 라벨은 join 결과가 비어 단락이 생성되지 않아야 한다."""
    passage = _make_passage()
    anns = [_make_annotation("top_label", 0, 3, text=None)]
    data = render_passage_with_annotations(passage, anns)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sec = zf.read("Contents/section0.xml").decode("utf-8")
    # secPr + 본문 = 2 단락
    assert _paragraph_count(sec) == 2


# ── 6. bracket out-of-range 안전성 ───────────────────────────────────────────


def test_bracket_out_of_range_skipped() -> None:
    """span 이 본문 길이를 초과하는 bracket 은 skip + 예외 없이 렌더되어야 한다."""
    passage = _make_passage()
    n = len(_BODY_TEXT)
    anns = [_make_annotation("bracket", 0, n + 50, bracket_style="[]")]
    data = render_passage_with_annotations(passage, anns)
    assert zipfile.is_zipfile(io.BytesIO(data))


def test_bracket_unsupported_style_skipped() -> None:
    """bracket_style 이 미지원 값이면 skip + 예외 없이 렌더되어야 한다."""
    passage = _make_passage()
    anns = [_make_annotation("bracket", 0, 3, bracket_style="<>")]
    data = render_passage_with_annotations(passage, anns)
    assert zipfile.is_zipfile(io.BytesIO(data))
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sec = zf.read("Contents/section0.xml").decode("utf-8")
    # 미지원 style 이므로 여닫이 글자가 본문에 추가되지 않아야 함
    assert "<hp:t>&lt;</hp:t>" not in sec


def test_bracket_default_style_is_square() -> None:
    """bracket_style=None 일 때 default `[ ]` 가 사용되어야 한다."""
    passage = _make_passage()
    anns = [_make_annotation("bracket", 4, 9, bracket_style=None)]  # "quick"
    data = render_passage_with_annotations(passage, anns)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sec = zf.read("Contents/section0.xml").decode("utf-8")
    assert "<hp:t>[</hp:t>" in sec
    assert "<hp:t>]</hp:t>" in sec


# ── 7. 본문 글자 보존 (bracket 으로 텍스트가 잘리지 않음) ──────────────────────


def test_body_text_chars_preserved(section0_xml: str) -> None:
    """bracket 처리 후에도 본문의 모든 단어가 section0 에 존재해야 한다."""
    for word in ["The", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]:
        assert word in section0_xml, f"Word missing after bracket processing: {word}"
