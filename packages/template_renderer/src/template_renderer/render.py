"""Jinja2 템플릿 렌더러.

``render_worksheet_html()`` 은 ``worksheet_to_template_context()`` 산출 dict 를 받아
``templates/{style}.html`` 을 렌더링해 HTML 문자열을 반환한다.

라우트 레벨 MVP 정책 (``README.md`` §26):
  ``playful`` 1종만 ``GET /worksheets/{id}/preview`` 에서 노출.
  ``classic`` / ``modern`` 은 보관 — Phase 2 종료 후 와이프 피드백에 따라 추가 노출.
  하지만 이 함수 자체는 3종 모두 지원 (라우트에서 화이트리스트 제한).

ADR-0014 D2 — annotation CSS 주입:
  ``templates/_annotation.css`` 를 모듈 로드 시점에 한 번 읽어 캐시. 모든 템플릿이
  ``{{ annotation_css | safe }}`` 로 inline. 별 파일 import 없음 (Playwright
  file:// 컨텍스트에서도 안전).
"""

from __future__ import annotations

from pathlib import Path

import jinja2

# templates/ 디렉토리 — 이 모듈 기준 두 단계 위에 위치
# packages/template_renderer/src/template_renderer/render.py
# → packages/template_renderer/templates/
_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

# 허용 style 화이트리스트 (라우트 레벨에서 추가로 제한)
_ALLOWED_STYLES = frozenset({"classic", "modern", "playful"})

# Jinja2 Environment (모듈 레벨에서 한 번만 생성 — 재사용)
# autoescape=True: HTML 이스케이프로 XSS 방지.
# content_html 은 템플릿 내에서 ``| safe`` 필터로 명시적으로 이스케이프 해제.
_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
    keep_trailing_newline=True,
)

# ADR-0014 D2 — annotation CSS 모듈 로드 시점 캐시 (재읽기 비용 회피).
# _annotation.css 는 구 annotation_html.py (.annot-* 셀렉터) 전용 — legacy fallback.
# 신규 server-side Tiptap 출력에는 _editor_annotation.css 를 사용한다.
_ANNOTATION_CSS = (_TEMPLATES_DIR / "_annotation.css").read_text(encoding="utf-8")

# Phase 2.5 Stage F4 fix (2026-05-15) — annotation CSS 단일 SOT.
# server-side Tiptap 이 생성하는 [data-annotation-kind] / [data-*-widget] 마크업에
# 매칭되는 CSS. EditorPoc.css 와 @import 로 공유 (단일 source-of-truth).
# _annotation.css (구 .annot-* 셀렉터) 와 별도 — 두 파일 모두 주입하면 중복되지 않음.
_EDITOR_ANNOTATION_CSS = (_TEMPLATES_DIR / "_editor_annotation.css").read_text(encoding="utf-8")

# 2026-05-08 사용자 보고 fix — 본문 wrap 정합. PDF (.q-content) 와 에디터
# (#editor-print-area .ProseMirror) 가 동일한 본문 폭/폰트/letter-spacing 등
# CSS 를 사용해 자동 wrap 위치를 정확히 일치시킨다. 본 partial 은 PDF 에 inline
# 주입하고, 에디터는 별 경로로 동일 내용 import (단일 source-of-truth).
_PASSAGE_BODY_CSS = (_TEMPLATES_DIR / "_passage_body.css").read_text(encoding="utf-8")


def render_worksheet_html(context: dict, style: str = "playful") -> str:
    """Jinja2 로 templates/{style}.html 렌더 → HTML 문자열.

    Args:
        context: ``worksheet_to_template_context()`` 가 반환한 dict.
            keys: ``academy``, ``worksheet``, ``student``, ``instruction``, ``questions``.
        style: 템플릿 스타일 식별자. 허용 값: ``"classic"``, ``"modern"``, ``"playful"``.
            MVP 라우트 레벨에서는 ``"playful"`` 만 노출 (``README.md`` §26).

    Returns:
        렌더링된 HTML 문자열. ``Content-Type: text/html; charset=utf-8`` 로 반환해야 한다.

    Raises:
        ValueError: ``style`` 이 허용 화이트리스트에 없는 경우.
        jinja2.TemplateNotFound: templates/{style}.html 이 존재하지 않는 경우
            (정상 배포 환경에서는 발생하지 않아야 함).
    """
    if style not in _ALLOWED_STYLES:
        raise ValueError(f"허용되지 않은 style: '{style}'. 허용 값: {sorted(_ALLOWED_STYLES)}")

    template = _env.get_template(f"{style}.html")
    # ADR-0014 D2 — annotation CSS 자동 주입. context 에 동일 key 가 있으면 우선
    # (테스트 / 커스텀 렌더 시 override 가능).
    if "annotation_css" not in context:
        context = {**context, "annotation_css": _ANNOTATION_CSS}
    if "passage_body_css" not in context:
        context = {**context, "passage_body_css": _PASSAGE_BODY_CSS}
    # Phase 2.5 Stage F4 fix — server-side Tiptap 마크업용 annotation CSS 주입.
    # [data-annotation-kind] / [data-*-widget] 셀렉터 + --anno-color-N 변수 정의.
    if "editor_annotation_css" not in context:
        context = {**context, "editor_annotation_css": _EDITOR_ANNOTATION_CSS}
    return template.render(**context)


def render_pdf_footer_html(context: dict) -> str:
    """Chromium ``footer_template`` 로 주입할 footer HTML 을 렌더한다.

    ``_pdf_footer.html`` 부분 템플릿을 같은 ``context`` 로 렌더 — 학원명 +
    페이지 번호 (Chromium native ``pageNumber`` / ``totalPages`` variable).
    인라인 스타일만 적용 (Chromium ``footer_template`` 제약 — 외부 CSS / webfont
    미지원). ``render_worksheet_pdf(footer_html=...)`` 에 전달.

    Args:
        context: ``worksheet_to_template_context()`` 가 반환한 dict.
            ``academy.name`` 만 사용.

    Returns:
        footer HTML 문자열.
    """
    template = _env.get_template("_pdf_footer.html")
    return template.render(**context)
