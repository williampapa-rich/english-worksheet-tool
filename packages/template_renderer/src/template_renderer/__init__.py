"""template_renderer — Worksheet HTML 템플릿 렌더링 패키지.

Stage 진행 상태:
  - Stage 0: 자산 도입 완료 (templates/ HTML 3종).
  - Stage 1 (이 패키지): Python 패키지 구조 + Branding 어댑터.
  - Stage 2: Playwright 도입 + 렌더 PoC (FastAPI 라우트).
  - ADR-0014: annotation HTML 렌더러 (SyntaxAnnotation → HTML, hwpx_renderer 와 대칭).
"""

from template_renderer.annotation_html import render_annotations_to_html

__all__ = [
    "render_annotations_to_html",
]
