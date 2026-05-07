"""``template_renderer.pdf.render_worksheet_pdf`` 테스트.

테스트 분리:
  - **단위 테스트** (integration 마커 없음): Playwright / Chromium 없이 도는 것.
      - 모듈 import 가능 여부 (Chromium 미설치 환경에서도 import 성공해야 함).
      - 함수 시그니처 확인 (inspect 기반).
  - **integration 테스트** (``@pytest.mark.integration``): 실제 Chromium 이 설치된
      환경에서만 실행. ``pytest -m "not integration"`` 으로 CI 기본 실행 시 skip.

실행 예시:
  # 단위만 (Chromium 없는 환경):
  uv run pytest packages/template_renderer/tests/test_pdf.py -m "not integration" -q

  # 전체 (Chromium 설치된 환경):
  uv run pytest packages/template_renderer/tests/test_pdf.py -q
"""

from __future__ import annotations

import inspect

import pytest

# ─── 단위 테스트 — Chromium 없는 환경에서도 통과해야 함 ─────────────────────


def test_module_import() -> None:
    """``template_renderer.pdf`` 모듈이 import 가능해야 한다.

    lazy import 패턴 덕분에 Playwright 바이너리가 없는 환경에서도
    모듈 레벨 import 는 성공해야 한다.
    """
    import template_renderer.pdf  # noqa: F401 — import 성공 여부만 확인

    assert hasattr(template_renderer.pdf, "render_worksheet_pdf")


def test_function_signature() -> None:
    """``render_worksheet_pdf`` 의 시그니처를 확인한다.

    - ``html`` 위치 인자 존재
    - ``landscape: bool = False`` 키워드 전용
    - ``print_background: bool = True`` 키워드 전용

    Note:
        ``from __future__ import annotations`` 로 인해 어노테이션이 lazy string 으로
        평가되므로 ``is str`` / ``is bytes`` 대신 파라미터 이름 + default 값으로 검증.
        타입 정확성은 mypy 가 보증.
    """
    from template_renderer.pdf import render_worksheet_pdf

    sig = inspect.signature(render_worksheet_pdf)
    params = sig.parameters

    assert "html" in params

    assert "landscape" in params
    assert params["landscape"].default is False
    assert params["landscape"].kind == inspect.Parameter.KEYWORD_ONLY

    assert "print_background" in params
    assert params["print_background"].default is True
    assert params["print_background"].kind == inspect.Parameter.KEYWORD_ONLY


def test_is_coroutine_function() -> None:
    """``render_worksheet_pdf`` 가 async 함수여야 한다.

    FastAPI 라우터와 동일 이벤트 루프에서 await 가능해야 하므로.
    """
    import inspect

    from template_renderer.pdf import render_worksheet_pdf

    assert inspect.iscoroutinefunction(render_worksheet_pdf)


# ─── integration 테스트 — 실제 Chromium 필요 ─────────────────────────────────


@pytest.mark.integration
async def test_render_pdf_returns_pdf_bytes() -> None:
    """정상 HTML → PDF bytes (b'%PDF' 로 시작).

    실제 Chromium 을 launch 해 HTML 을 렌더하고 PDF 를 생성.
    결과가 유효한 PDF 바이너리인지 magic bytes 로 확인.
    """
    from template_renderer.pdf import render_worksheet_pdf

    minimal_html = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
@page { size: A4 portrait; margin: 0; }
body { font-family: sans-serif; padding: 20mm; }
</style></head>
<body><h1>Test Worksheet</h1><p>Hello, PDF!</p></body></html>"""

    pdf_bytes = await render_worksheet_pdf(minimal_html)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF"), (
        f"PDF magic bytes 확인 실패. 앞 8바이트: {pdf_bytes[:8]!r}"
    )
    # 최소 크기 확인 (빈 PDF 도 수 KB 이상)
    assert len(pdf_bytes) > 1024, f"PDF 너무 작음: {len(pdf_bytes)} bytes"


@pytest.mark.integration
async def test_render_pdf_landscape() -> None:
    """landscape=True 로 호출해도 에러 없이 PDF 를 생성해야 한다."""
    from template_renderer.pdf import render_worksheet_pdf

    minimal_html = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
@page { size: A4 landscape; margin: 0; }
body { font-family: sans-serif; padding: 15mm; }
</style></head>
<body><p>Landscape test</p></body></html>"""

    pdf_bytes = await render_worksheet_pdf(minimal_html, landscape=True)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


@pytest.mark.integration
async def test_render_pdf_minimal_html() -> None:
    """빈 body / 최소 HTML 도 에러 없이 PDF 를 생성해야 한다 (graceful)."""
    from template_renderer.pdf import render_worksheet_pdf

    # 최소 유효 HTML
    bare_html = "<!DOCTYPE html><html><head></head><body></body></html>"

    pdf_bytes = await render_worksheet_pdf(bare_html)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


@pytest.mark.integration
async def test_render_pdf_print_background_false() -> None:
    """print_background=False 로 호출해도 에러 없이 PDF 를 생성해야 한다."""
    from template_renderer.pdf import render_worksheet_pdf

    minimal_html = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="background: red;"><p>No background in PDF</p></body></html>"""

    pdf_bytes = await render_worksheet_pdf(minimal_html, print_background=False)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")
