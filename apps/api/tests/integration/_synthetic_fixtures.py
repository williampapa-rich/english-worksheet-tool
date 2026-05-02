"""Phase 0 smoke test 용 synthetic fixture 생성 헬퍼.

저작권 자료 의존 없이 git commit 가능한 PDF / PNG 를 생성한다.
PyMuPDF (fitz) 만 사용 — 이미 packages/extractor 의 의존성이므로 신규 도입 없음.
PIL 대신 PyMuPDF 를 선택한 이유:
  - extractor 패키지가 이미 PyMuPDF 를 사용 (CLAUDE.md §3.6 "No Reinventing the Wheel").
  - 텍스트 레이어가 있는 PDF 와 이미지(PNG) 를 하나의 라이브러리로 생성 가능.
  - PIL 을 추가로 도입할 이유 없음.
"""

from typing import Final

# 통합 테스트가 공유하는 샘플 영어 지문 (자체 생성 — 저작권 무관)
SAMPLE_TEXT: Final[str] = (
    "The Industrial Revolution began in the late 18th century in Britain. "
    "It transformed manufacturing, agriculture, and transportation. "
    "Steam power and mechanization changed how goods were produced.\n\n"
    "1. What was the main change brought by the Industrial Revolution?\n"
    "(A) The invention of the wheel\n"
    "(B) Mechanization of production\n"
    "(C) The discovery of electricity\n"
    "(D) The development of computers\n"
    "(E) None of the above"
)


def make_synthetic_pdf(text: str = SAMPLE_TEXT) -> bytes:
    """PyMuPDF 로 텍스트 레이어가 있는 PDF 를 생성한다.

    CLAUDE.md §3.4: 텍스트 레이어 있는 PDF → PyMuPDF 텍스트 추출 경로.
    이 fixture 는 force_vision=False 경로를 검증하는 데 사용한다.

    Args:
        text: PDF 에 삽입할 영어 텍스트.

    Returns:
        PDF bytes (텍스트 레이어 있음).
    """
    import fitz  # PyMuPDF

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 포인트
    # 여러 줄 텍스트 삽입 — 텍스트 레이어 생성
    page.insert_text(
        point=(50, 80),
        text=text,
        fontsize=11,
        color=(0, 0, 0),
    )
    pdf_bytes: bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_synthetic_png(text: str = SAMPLE_TEXT) -> bytes:
    """PyMuPDF 로 텍스트가 렌더링된 PNG 이미지를 생성한다.

    실제 시험지 스캔본 대신 synthetic PNG 를 사용해 Vision 경로를 검증한다.

    Args:
        text: PNG 에 렌더링할 영어 텍스트.

    Returns:
        PNG bytes (이미지, 텍스트 레이어 없음).
    """
    import fitz  # PyMuPDF

    # PDF 를 생성한 뒤 pixmap 으로 변환 — 텍스트가 픽셀로 렌더링됨
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(
        point=(50, 80),
        text=text,
        fontsize=11,
        color=(0, 0, 0),
    )
    # dpi=150 — 적당한 해상도 (파일 크기 vs Vision 품질 균형)
    pix = page.get_pixmap(dpi=150)
    png_bytes: bytes = pix.tobytes("png")
    doc.close()
    return png_bytes
