"""Worksheet API 엔드포인트.

현재 라우트:
  GET /worksheets/{id}/preview?style=playful
    → 200 text/html
    → 404 worksheet not found / cross-tenant
    → 422 invalid style

ADR-0010 §D6 / "PR 후속 4" 명세 구현.

MVP 정책 (``packages/template_renderer/README.md`` §26):
  ``style`` 는 라우트 레벨에서 ``playful`` 만 허용.
  함수 레벨 (``render_worksheet_html``) 은 3종 지원하지만, 이 라우트에서 제한.
  classic / modern 값 전달 시 422 반환.

content_html 한계 (본 PR):
  현재 ``content_html`` 은 ``passage.body_text`` 를 ``<p>`` 로 단순 wrap 한다.
  annotation split-mark 렌더러를 통한 정밀 HTML 주입은 별도 ADR 에서 다룬다.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from template_renderer.adapters import worksheet_to_template_context
from template_renderer.render import render_worksheet_html

from shared.schemas.passage import Passage
from worksheet_api.db import get_db
from worksheet_api.repositories import (
    PassageRepository,
    TenantContext,
    WorksheetRepository,
    get_tenant_context,
)

router = APIRouter(prefix="/worksheets", tags=["worksheets"])

# MVP 라우트에서 허용하는 style 값 (README §26)
_MVP_ALLOWED_STYLES: frozenset[str] = frozenset({"playful"})


@router.get("/{worksheet_id}/preview", response_class=HTMLResponse, status_code=200)
async def preview_worksheet(
    worksheet_id: uuid.UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    style: str = Query(default="playful", description="템플릿 스타일. MVP: playful 만 허용."),
) -> HTMLResponse:
    """Worksheet 를 HTML 로 렌더해 반환한다.

    ``packages/template_renderer`` 의 Jinja2 렌더러를 사용해 ``style`` 에 맞는 템플릿으로
    HTML 을 생성한다. Content-Type: text/html; charset=utf-8.

    MVP 정책 (``README.md`` §26): ``style=playful`` 만 허용.
    ``classic`` / ``modern`` 전달 시 422.

    멀티테넌트: worksheet 존재 여부 + tenant 소유 확인.
    다른 tenant 의 worksheet_id 로 조회하면 404 반환 (존재 여부 노출 방지).

    content_html 한계:
        현재 각 질문의 content_html 은 passage.body_text 를 ``<p>`` 로 단순 wrap 한다.
        annotation split-mark 렌더러를 통한 정밀 HTML 주입은 별도 ADR 에서 다룬다.

    Args:
        worksheet_id: 미리보기할 Worksheet UUID.
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        session: DB 세션.
        style: 템플릿 스타일 식별자. MVP 에서는 ``playful`` 만 허용.

    Returns:
        HTMLResponse: 렌더링된 HTML 문자열.

    Raises:
        HTTPException 404: Worksheet 가 존재하지 않거나 다른 tenant 소유.
        HTTPException 422: 허용되지 않은 style 값.
    """
    # 1. style 화이트리스트 검증 (MVP 정책 — README §26)
    if style not in _MVP_ALLOWED_STYLES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"허용되지 않은 style: '{style}'. "
                f"MVP 에서는 {sorted(_MVP_ALLOWED_STYLES)} 만 허용됩니다."
            ),
        )

    worksheet_repo = WorksheetRepository(session, tenant_ctx)
    passage_repo = PassageRepository(session, tenant_ctx)

    # 2. Worksheet 조회 — tenant_id 필터 자동 적용
    worksheet = await worksheet_repo.get_by_id(worksheet_id, tenant_ctx)
    if worksheet is None:
        raise HTTPException(
            status_code=404,
            detail=f"Worksheet {worksheet_id} 를 찾을 수 없습니다.",
        )

    # 3. WorksheetItems 조회 — W-2 가드 패턴 (tenant 재검증 포함)
    items_orm = await worksheet_repo.list_items_for_worksheet(worksheet_id, tenant_ctx)

    # 4. 각 item 의 Passage 조회 (tenant 필터 자동 적용)
    passages: list[Passage] = []
    for item_orm in items_orm:
        passage = await passage_repo.get(item_orm.passage_id)
        if passage is not None:
            passages.append(passage)

    # 5. 템플릿 컨텍스트 생성 + 렌더링
    context = worksheet_to_template_context(worksheet, passages)
    html_content = render_worksheet_html(context, style=style)

    return HTMLResponse(content=html_content, status_code=200)
