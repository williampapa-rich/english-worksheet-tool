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

from markupsafe import Markup, escape

from shared.schemas.annotation import SyntaxAnnotation
from shared.schemas.passage import Passage
from shared.schemas.translation import Translation
from shared.schemas.vocabulary import Vocabulary
from shared.schemas.worksheet import Branding, Worksheet
from template_renderer.annotation_html import render_annotations_to_html


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
    *,
    annotations_by_passage: dict[uuid.UUID, list[SyntaxAnnotation]] | None = None,
    translations_by_passage: dict[uuid.UUID, Translation | None] | None = None,
    vocabulary_by_passage: dict[uuid.UUID, list[Vocabulary]] | None = None,
) -> dict:
    """``Worksheet`` + ``Passage`` 목록을 Jinja2 템플릿 컨텍스트 dict 로 변환.

    ``packages/template_renderer/README.md`` 데이터 계약의 모든 key 를 채운다.
    passages 는 ``worksheet.items`` 의 passage_id 순서로 join 된 결과를 넘긴다.

    **B4 (2026-05-07)** — annotation / translation / vocabulary 컨텍스트 주입:
        ``annotations_by_passage`` 가 주어지면 ``content_html`` 은 ADR-0014 의
        ``render_annotations_to_html`` 로 정밀 렌더. 미주어지면 단순 wrap fallback
        (후방 호환). ``translations_by_passage`` / ``vocabulary_by_passage`` 도
        item 별 block 으로 주입 (``WorksheetItem.include_translation`` /
        ``include_vocabulary`` flag 가 True 일 때만).

    Args:
        worksheet: ``shared.schemas.worksheet.Worksheet`` 인스턴스.
        passages: item.passage_id 로 join 된 ``Passage`` 리스트.
            items 의 order 순서와 동일한 순서로 정렬돼 있어야 한다.
        annotations_by_passage: passage_id → SyntaxAnnotation list. None / 미존재
            key 는 빈 list (annotation 적용 안 함).
        translations_by_passage: passage_id → Translation | None. ``include_translation``
            가 True 인 item 의 ``translation`` 블록 채움.
        vocabulary_by_passage: passage_id → Vocabulary list. ``include_vocabulary``
            가 True 인 item 의 ``vocabulary`` 블록 채움.

    Returns:
        Jinja2 ``Environment.get_template().render()`` 에 바로 전달할 수 있는 dict.
        keys: ``academy``, ``worksheet``, ``student``, ``instruction``, ``questions``.
        각 question 은 ``number``, ``label``, ``content_html``, 그리고 옵션으로
        ``translation`` (str | None), ``vocabulary`` (list[dict] | None) 를 포함.

    Note:
        - ``student`` 는 schema 미도입 (PM 결정 #5 — ``README.md`` 참조).
        - ``page_number`` / ``total_pages`` 는 1/1 default (ADR-0010 §D5).
        - ``branding`` 이 None 이거나 기본값 ``Branding()`` 이어도 안전하게 동작.
    """
    # passage_id → Passage 빠른 조회용 매핑
    passage_map: dict[uuid.UUID, Passage] = {p.id: p for p in passages}
    annotations_by_passage = annotations_by_passage or {}
    translations_by_passage = translations_by_passage or {}
    vocabulary_by_passage = vocabulary_by_passage or {}

    # items 를 order 기준으로 정렬한 뒤 질문 목록 구성
    sorted_items = sorted(worksheet.items, key=lambda item: item.order)

    questions: list[dict[str, Any]] = []
    for idx, item in enumerate(sorted_items, start=1):
        passage = passage_map.get(item.passage_id)

        # B4: content_html — annotations 가 주어지면 ADR-0014 정밀 렌더, 아니면 단순 wrap.
        # passage 가 None 이면 빈 content (graceful degradation — 라우트 레이어가
        # cross-tenant 차단 책임).
        content_html: str | Markup
        if passage is None:
            content_html = "<p></p>"
        else:
            anns = annotations_by_passage.get(passage.id, [])
            if anns:
                content_html = render_annotations_to_html(passage, anns)
            else:
                # annotation 없는 경우 단순 wrap (XSS escape).
                # paragraphs 가 있으면 각 단락을 별 <p> 로 분할 — 사용자 에디터
                # 줄바꿈 == PDF 줄바꿈 정합 (2026-05-09).
                if passage.paragraphs:
                    paragraph_html = "".join(
                        f"<p>{escape(p)}</p>" for p in passage.paragraphs
                    )
                    content_html = Markup(paragraph_html)
                else:
                    content_html = Markup(f"<p>{escape(passage.body_text)}</p>")

        question: dict[str, Any] = {
            "number": idx,
            "label": item.label,
            "content_html": content_html,
        }

        # B4: translation / vocabulary 옵션 주입.
        # WorksheetItem.include_* flag 가 True 인 경우만 컨텍스트에 포함.
        # (template 은 falsy 값 — None / 빈 list — 을 자연스럽게 skip 처리)
        if item.include_translation and passage is not None:
            t = translations_by_passage.get(passage.id)
            question["translation"] = t.text if t is not None else None
        else:
            question["translation"] = None

        if item.include_vocabulary and passage is not None:
            vocab = vocabulary_by_passage.get(passage.id, [])
            question["vocabulary"] = [
                {
                    "word": v.word,
                    "pos": v.pos,
                    "meaning_ko": v.meaning_ko,
                    "level_label": v.level_label,
                }
                for v in vocab
            ]
        else:
            question["vocabulary"] = []

        questions.append(question)

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
