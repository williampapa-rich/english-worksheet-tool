"""Playwright headless Chromium 기반 HTML → PDF 변환.

``render_worksheet_pdf()`` 는 Jinja2 로 렌더된 HTML 문자열을 받아 PDF 바이트를 반환한다.

설계 결정:
  - **async**: Playwright API 가 async 우선, FastAPI 라우터와 동일 이벤트 루프 사용.
  - **HTML 입력 (URL 아님)**: ``page.set_content(html, wait_until="networkidle")`` 로
    CDN webfont (Pretendard, Tabler Icons) 로딩 대기 후 PDF 생성.
  - **prefer_css_page_size=True**: templates/ 의 ``@page { size: A4; margin: 0; }`` 정의
    우선. landscape 는 Worksheet.orientation 에서 결정되며 라우터가 전달.
  - **매 호출마다 browser launch**: Stage 2 PoC 라 OK. process-wide pool 은 성능 ADR
    후속 PR 에서 다룬다.

의존성:
  Playwright Python 패키지 (``playwright>=1.40.0``) + Chromium 바이너리.
  브라우저 바이너리는 Python 패키지와 별도로 설치 필요:
    ``playwright install chromium``
  CI / Docker 환경에서 별도 셋업 필요 (README.md §Playwright 설치 참조).
"""

from __future__ import annotations


async def render_worksheet_pdf(
    html: str,
    *,
    landscape: bool = False,
    print_background: bool = True,
    footer_html: str = "",
) -> bytes:
    """HTML 문자열을 PDF 바이트로 변환한다.

    Playwright Chromium headless 로 HTML 을 렌더한 뒤 PDF 를 생성한다.
    ``footer_html`` 이 주어지면 Chromium native ``display_header_footer`` 로 매
    페이지 하단에 자동 주입 — 박스 분할 한계선이 footer 위 11mm (= margin-bottom
    33mm = footer 22mm + 11mm 시각 margin) 에서 자동으로 끊어진다.

    Args:
        html: ``render_worksheet_html()`` 산출 HTML 문자열.
            CDN 에서 webfont 를 로드하므로 네트워크 접근 가능 환경 권장.
        landscape: True 면 A4 가로 (297mm × 210mm). ``Worksheet.orientation`` 에서
            결정 — 라우터에서 전달.
        print_background: True 면 CSS background-color / background-image 를 PDF 에
            포함. playful.html 의 컬러 배너가 PDF 에서 사라지지 않으려면 True 필수.
        footer_html: Chromium native ``footer_template`` 으로 주입할 HTML 문자열.
            빈 문자열이면 ``display_header_footer=False`` 로 fallback (backward
            compat — 기존 호출부 영향 없음). 인라인 스타일만 적용되고 외부
            CSS / webfont 는 로드 안 됨 (Chromium 제약).

    Returns:
        PDF 바이트. b"%PDF" 로 시작하는 유효한 PDF 바이너리.

    Raises:
        playwright.async_api.Error: Playwright / Chromium 실행 오류.
            브라우저 바이너리가 설치되지 않은 경우 포함.
            ``playwright install chromium`` 으로 해결.

    Note:
        - footer_html 이 주어지면 Playwright ``margin={top: 12mm, bottom: 33mm}``
          을 자동 적용 — 페이지 콘텐츠 박스가 33mm 만큼 작아져 박스 분할
          한계선이 footer 위 11mm (footer 22mm + 11mm 시각 margin = 33mm)
          에서 끊어짐. 상단 12mm 는 page2+ 박스 재개 시 종이 끝 시각 보정 (page1
          banner 는 .banner { margin-top: -12mm } 음수 마진으로 종이 위 붙임).
          fixed footer 트릭 (Paged Media level 3 fallback) 대체 — Chromium
          native API 라 박스 border 가 footer 영역 침범 원리적으로 불가.
        - footer_html 이 빈 문자열이면 ``prefer_css_page_size=True`` + CSS
          @page 정의 우선 (구버전 호환). 이 fallback 경로는 margin 인자 미전달
          이라 박스 한계선 시각 보장 없음 — 새 호출부는 footer_html 명시 권장.
        - CDN webfont 로딩 대기: ``wait_until="networkidle"`` 로 font load
          완료 보장. 인터넷 없는 환경에서는 timeout 발생 가능.
    """
    # lazy import: Playwright 바이너리가 없는 환경에서도 모듈 import 는 성공해야 한다.
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle")
            if footer_html:
                # Chromium native footer — page.pdf() 가 margin.bottom 영역에
                # footer 를 별도 layout 으로 그림. 박스 border 와 절대 안 겹침.
                pdf_bytes: bytes = await page.pdf(
                    format="A4",
                    landscape=landscape,
                    print_background=print_background,
                    # margin.top: 12mm — page2+ 상단 박스 재개 시 종이 끝에
                    # 안 붙도록. page1 banner 는 .banner { margin-top: -12mm }
                    # 음수 마진으로 보정 (종이 위에 붙는 디자인 유지).
                    # margin.bottom: 33mm — footer 22mm + 11mm 시각 margin.
                    # 박스 분할 한계선이 footer 위 11mm 에서 끊어짐.
                    margin={"top": "12mm", "bottom": "33mm", "left": "0", "right": "0"},
                    display_header_footer=True,
                    header_template="<span></span>",
                    footer_template=footer_html,
                    prefer_css_page_size=False,
                )
            else:
                # 구버전 호환 — footer_html 미전달 시 CSS @page 정의 우선.
                pdf_bytes = await page.pdf(
                    format="A4",
                    landscape=landscape,
                    print_background=print_background,
                    prefer_css_page_size=True,
                )
        finally:
            await browser.close()

    return pdf_bytes
