"""Jinja2 템플릿 렌더러.

``render_worksheet_html()`` 은 ``worksheet_to_template_context()`` 산출 dict 를 받아
``templates/{style}.html`` 을 렌더링해 HTML 문자열을 반환한다.

라우트 레벨 MVP 정책 (``README.md`` §26):
  ``playful`` 1종만 ``GET /worksheets/{id}/preview`` 에서 노출.
  ``classic`` / ``modern`` 은 보관 — Phase 2 종료 후 와이프 피드백에 따라 추가 노출.
  하지만 이 함수 자체는 3종 모두 지원 (라우트에서 화이트리스트 제한).
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
        raise ValueError(
            f"허용되지 않은 style: '{style}'. "
            f"허용 값: {sorted(_ALLOWED_STYLES)}"
        )

    template = _env.get_template(f"{style}.html")
    return template.render(**context)
