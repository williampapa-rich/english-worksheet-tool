"""Branding ↔ 템플릿 academy dict 매핑 어댑터 + Worksheet 전체 컨텍스트 어댑터.

ADR-0010 §D3 / §D6 구현.

매핑 결정 (``docs/template-rendering-analysis.md`` §2.3 인용):
  - ``academy.name``        ← ``branding.academy_name``  (ADR-0010 §D3)
  - ``academy.theme_color`` ← ``branding.primary_color``
  - ``academy.logo_url``    ← ``branding.logo_url``
  - ``secondary_color``     매핑하지 않음 (현 템플릿 미사용 — 보관 ADR-0010 §D6)

사용 예시::

    from shared.schemas.worksheet import Branding
    from template_renderer.adapters import branding_to_academy_dict

    branding = Branding(
        academy_name="윌리엄 영어학원",
        primary_color="#1F4E79",
        logo_url="https://example.com/logo.png",
    )
    academy = branding_to_academy_dict(branding)
    # {"name": "윌리엄 영어학원", "theme_color": "#1F4E79", "logo_url": "https://..."}
"""

from __future__ import annotations

import uuid
from typing import Any

from markupsafe import escape

from shared.schemas.passage import Passage
from shared.schemas.worksheet import Branding, Worksheet


def branding_to_academy_dict(branding: Branding) -> dict[str, str | None]:
    """``Branding`` Pydantic 모델을 템플릿 ``academy.*`` 변수 dict 로 변환.

    templates/{classic,modern,playful}.html 의 ``academy.name`` / ``academy.theme_color``
    / ``academy.logo_url`` 변수와 1:1 매핑.

    Args:
        branding: ``shared.schemas.worksheet.Branding`` 인스턴스.
            모든 필드가 None 이어도 안전하게 None 을 그대로 통과한다.

    Returns:
        템플릿 Jinja2 컨텍스트의 ``academy`` key 에 직접 전달할 dict.
        keys: ``name``, ``theme_color``, ``logo_url``.

    Note:
        - ``secondary_color`` 는 매핑하지 않는다 (현 템플릿 3종 미사용 — ADR-0010 §D6).
        - 반환값이 None 인 필드는 템플릿에서 폴백 처리 (예: 기본 파란색, 텍스트/아이콘 폴백).
    """
    return {
        "name": branding.academy_name,
        "theme_color": branding.primary_color,
        "logo_url": branding.logo_url,
    }


def worksheet_to_template_context(
    worksheet: Worksheet,
    passages: list[Passage],
) -> dict:
    """``Worksheet`` + ``Passage`` 목록을 Jinja2 템플릿 컨텍스트 dict 로 변환.

    ``packages/template_renderer/README.md`` 데이터 계약의 모든 key 를 채운다.
    passages 는 ``worksheet.items`` 의 passage_id 순서로 join 된 결과를 넘긴다.

    **본 PR 한계 — content_html 정밀도**:
        현재 ``content_html`` 은 ``passage.body_text`` 를 ``<p>`` 로 단순 wrap 한다.
        annotation split-mark 렌더러를 통한 정밀 HTML 주입은 별도 ADR 에서 다룬다
        (``README.md`` §29 참조). 이 한계는 본 PR docstring 과 PR body 에 명시된다.

    Args:
        worksheet: ``shared.schemas.worksheet.Worksheet`` 인스턴스.
        passages: item.passage_id 로 join 된 ``Passage`` 리스트.
            items 의 order 순서와 동일한 순서로 정렬돼 있어야 한다.

    Returns:
        Jinja2 ``Environment.get_template().render()`` 에 바로 전달할 수 있는 dict.
        keys: ``academy``, ``worksheet``, ``student``, ``instruction``, ``questions``.

    Note:
        - ``student`` 는 schema 미도입 (PM 결정 #5 — ``README.md`` 참조).
          렌더 시점에 빈칸 출력만 하므로 항상 ``{"name": "", "class_name": "", "date": ""}`` 반환.
        - ``page_number`` / ``total_pages`` 는 1/1 default (ADR-0010 §D5 — 다중 페이지는
          Stage 2 PoC 에서 정밀화).
        - ``branding`` 이 None 이거나 기본값 ``Branding()`` 이어도 안전하게 동작한다
          (``branding_to_academy_dict`` 가 None 필드를 그대로 통과).
    """
    # passage_id → Passage 빠른 조회용 매핑
    passage_map: dict[uuid.UUID, Passage] = {p.id: p for p in passages}

    # items 를 order 기준으로 정렬한 뒤 질문 목록 구성
    sorted_items = sorted(worksheet.items, key=lambda item: item.order)

    questions: list[dict[str, Any]] = []
    for idx, item in enumerate(sorted_items, start=1):
        passage = passage_map.get(item.passage_id)
        # passage 가 없으면 빈 content 로 graceful degradation
        # (cross-tenant 차단은 라우트 레이어 책임)
        body_text = passage.body_text if passage is not None else ""
        # 한계: body_text raw text 를 <p> 로 단순 wrap.
        # 정밀한 annotation split-mark HTML 주입은 별도 ADR 에서 다룬다.
        # XSS 방어 (S-1): markupsafe.escape() 로 body_text 의 HTML 특수문자를 escape.
        # 결과는 Markup 타입 — 템플릿의 `| safe` 와 결합되어도 escape 가 유지된다.
        # annotation 렌더러 도입 시 신뢰 가능한 HTML 은 명시적으로 Markup(...) 으로 감싸야 함.
        content_html = f"<p>{escape(body_text)}</p>"
        questions.append(
            {
                "number": idx,
                "label": item.label,
                "content_html": content_html,
            }
        )

    return {
        "academy": branding_to_academy_dict(worksheet.branding),
        "worksheet": {
            "title": worksheet.title,
            "subtitle": worksheet.subtitle,
            "page_number": 1,
            "total_pages": 1,
            "orientation": worksheet.orientation.value,
        },
        # PM 결정 #5: student 필드는 schema 미도입 — 렌더 시점 빈칸 출력만.
        "student": {"name": "", "class_name": "", "date": ""},
        "instruction": worksheet.instruction,
        "questions": questions,
    }
