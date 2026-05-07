"""render_worksheet_html 단위 테스트.

검증 케이스:
  1. full context + style=playful — 정상 렌더 (academy.name / worksheet.title 포함)
  2. orientation=landscape — @page size landscape 텍스트 포함
  3. style 화이트리스트 위반 — ValueError
"""

from __future__ import annotations

import pytest
from template_renderer.render import render_worksheet_html

# ─── 테스트 컨텍스트 팩토리 ──────────────────────────────────────────────────


def _make_context(
    academy_name: str = "윌리엄 영어학원",
    title: str = "테스트 워크시트",
    orientation: str = "portrait",
    questions: list[dict] | None = None,
) -> dict:
    """render_worksheet_html 에 전달할 표준 컨텍스트 dict 생성."""
    return {
        "academy": {
            "name": academy_name,
            "theme_color": "#1F4E79",
            "logo_url": None,
        },
        "worksheet": {
            "title": title,
            "subtitle": "Week 01",
            "page_number": 1,
            "total_pages": 1,
            "orientation": orientation,
        },
        "student": {"name": "", "class_name": "", "date": ""},
        "instruction": "다음 지문을 읽고 물음에 답하시오.",
        "questions": questions
        or [
            {
                "number": 1,
                "label": "독해 연습",
                "content_html": "<p>Test passage body.</p>",
            }
        ],
    }


class TestRenderWorksheetHtml:
    """render_worksheet_html 테스트 스위트."""

    def test_full_context_playful(self) -> None:
        """full context + style=playful — 정상 렌더, 핵심 컨텐츠 포함 확인."""
        ctx = _make_context(academy_name="윌리엄 영어학원", title="1학기 중간 대비")
        html = render_worksheet_html(ctx, style="playful")

        assert isinstance(html, str)
        assert len(html) > 0
        # 워크시트 제목이 포함되어야 한다
        assert "1학기 중간 대비" in html
        # 학원명이 포함되어야 한다
        assert "윌리엄 영어학원" in html
        # 질문 내용이 포함되어야 한다
        assert "Test passage body." in html
        # HTML 문서 기본 구조
        assert "<!DOCTYPE html>" in html or "<!doctype html>" in html.lower()

    def test_orientation_landscape_applied(self) -> None:
        """orientation=landscape 일 때 CSS @page 에 landscape 가 포함된다."""
        ctx = _make_context(orientation="landscape")
        html = render_worksheet_html(ctx, style="playful")

        # playful.html 에서 is_landscape 조건으로 '@page { size: A4 landscape' 생성
        assert "landscape" in html

    def test_style_whitelist_violation_raises_value_error(self) -> None:
        """style 이 허용 화이트리스트에 없으면 ValueError 발생."""
        ctx = _make_context()

        with pytest.raises(ValueError, match="허용되지 않은 style"):
            render_worksheet_html(ctx, style="unknown_style")

    def test_style_whitelist_classic_allowed(self) -> None:
        """style=classic 은 함수 레벨에서 허용된다 (라우트 레벨 제한과 별도)."""
        ctx = _make_context()
        html = render_worksheet_html(ctx, style="classic")

        assert isinstance(html, str)
        assert len(html) > 0

    def test_style_whitelist_modern_allowed(self) -> None:
        """style=modern 은 함수 레벨에서 허용된다."""
        ctx = _make_context()
        html = render_worksheet_html(ctx, style="modern")

        assert isinstance(html, str)
        assert len(html) > 0

    def test_default_style_is_playful(self) -> None:
        """style 인자 생략 시 기본값 playful 로 렌더된다."""
        ctx = _make_context(title="기본 스타일 테스트")
        html = render_worksheet_html(ctx)

        assert "기본 스타일 테스트" in html

    def test_empty_questions_renders_safely(self) -> None:
        """questions 가 빈 리스트여도 오류 없이 렌더된다."""
        ctx = _make_context(questions=[])
        html = render_worksheet_html(ctx, style="playful")

        assert isinstance(html, str)
        assert len(html) > 0
