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
) -> bytes:
    """HTML 문자열을 PDF 바이트로 변환한다.

    Playwright Chromium headless 로 HTML 을 렌더한 뒤 PDF 를 생성한다.
    ``playful.html`` 의 ``@page { size: A4; margin: 0; }`` 정의를 그대로 따른다.

    Args:
        html: ``render_worksheet_html()`` 산출 HTML 문자열.
            CDN 에서 webfont 를 로드하므로 네트워크 접근 가능 환경 권장.
        landscape: True 면 A4 가로 (297mm × 210mm). ``Worksheet.orientation`` 에서
            결정 — 라우터에서 전달. ``prefer_css_page_size=True`` 와 함께 사용되므로
            CSS ``@page size`` 에 ``landscape`` 가 명시된 경우 CSS 가 우선된다.
        print_background: True 면 CSS background-color / background-image 를 PDF 에
            포함. playful.html 의 컬러 배너가 PDF 에서 사라지지 않으려면 True 필수.

    Returns:
        PDF 바이트. b"%PDF" 로 시작하는 유효한 PDF 바이너리.

    Raises:
        playwright.async_api.Error: Playwright / Chromium 실행 오류.
            브라우저 바이너리가 설치되지 않은 경우 포함.
            ``playwright install chromium`` 으로 해결.

    Note:
        - CDN webfont 로딩 대기: ``wait_until="networkidle"`` 로 font load 완료 보장.
          인터넷 없는 환경에서는 timeout 발생 가능 — CDN 의존성은 PM 결정
          (packages/template_renderer/README.md §폰트 / CDN 정책).
        - ``prefer_css_page_size=True``: CSS ``@page size`` 정의를 Playwright 파라미터
          보다 우선. ``format="A4"`` / ``landscape`` 는 CSS 에 ``@page size`` 없는 경우의
          fallback 으로 동작.
        - 브라우저는 함수 호출마다 launch / close (try/finally 로 close 보장).
          process-wide pool 최적화는 별도 PR.
    """
    # lazy import: Playwright 바이너리가 없는 환경에서도 모듈 import 는 성공해야 한다.
    # (단위 테스트 환경 — Chromium 미설치 상태에서 import 만 테스트하는 케이스 지원)
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            # wait_until="networkidle": CDN webfont 로딩 완료 대기
            await page.set_content(html, wait_until="networkidle")
            pdf_bytes: bytes = await page.pdf(
                format="A4",
                landscape=landscape,
                print_background=print_background,
                # CSS @page { size: A4; margin: 0; } 우선 — 템플릿 정의 존중
                prefer_css_page_size=True,
            )
        finally:
            await browser.close()

    return pdf_bytes
