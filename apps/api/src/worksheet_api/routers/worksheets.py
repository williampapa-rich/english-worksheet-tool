"""Worksheet API 엔드포인트.

검수 흐름 (2026-05-07~):
  1. POST /passages/extract → passage_id 1+ 확보
  2. POST /worksheets {items: [{passage_id, order: 0}, ...]} → worksheet_id 확보
  3. GET /worksheets/{id}/preview?style=playful → 브라우저로 HTML 확인
  4. POST /worksheets/{id}/export.pdf → PDF 다운로드 확인

현재 라우트:
  POST /worksheets
    → 201 application/json (Worksheet, id 포함)
    → 422 cross-tenant passage_id / validation error
    → 422 passage_id 가 DB 에 없음 (IntegrityError)

  GET /worksheets/{id}/preview?style=playful
    → 200 text/html
    → 404 worksheet not found / cross-tenant
    → 422 invalid style

  POST /worksheets/{id}/export.pdf
    → 200 application/pdf (PDF 바이너리)
    → 404 worksheet not found / cross-tenant

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

import logging
import urllib.parse
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession
from template_renderer.adapters import worksheet_to_template_context
from template_renderer.pdf import render_worksheet_pdf
from template_renderer.render import render_worksheet_html

from shared.schemas.passage import Passage
from shared.schemas.worksheet import (
    Branding,
    Worksheet,
    WorksheetItem,
    WorksheetKind,
    WorksheetOrientation,
)
from worksheet_api.db import get_db
from worksheet_api.repositories import (
    PassageRepository,
    TenantContext,
    WorksheetRepository,
    get_tenant_context,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/worksheets", tags=["worksheets"])

# MVP 라우트에서 허용하는 style 값 (README §26)
_MVP_ALLOWED_STYLES: frozenset[str] = frozenset({"playful"})


# ─── 요청 스키마 (POST /worksheets) ─────────────────────────────────────────


class WorksheetItemCreate(BaseModel):
    """WorksheetItem 입력 — order/passage_id/옵션."""

    passage_id: uuid.UUID
    order: int = Field(..., ge=0, description="Worksheet 안의 노출 순서 (0-based).")
    label: str | None = Field(
        default=None,
        max_length=255,
        description="항목 라벨 (예: '관계절이 포함된 문장').",
    )
    include_translation: bool = False
    include_vocabulary: bool = False
    include_syntax_annotations: bool = False
    include_questions: bool = False
    include_variants: bool = False


class WorksheetCreateRequest(BaseModel):
    """POST /worksheets request body."""

    title: str = Field(..., max_length=255, description="Worksheet 제목.")
    subtitle: str | None = Field(default=None, max_length=255)
    kind: WorksheetKind
    template_id: str = Field(..., description="템플릿 식별자 (예: 'playful').")
    orientation: WorksheetOrientation = WorksheetOrientation.PORTRAIT
    instruction: str | None = Field(default=None, max_length=2000)
    branding: Branding = Field(default_factory=Branding)
    school: str | None = Field(default=None, max_length=255)
    grade: str | None = Field(default=None, max_length=64)
    exam_date: str | None = Field(default=None, max_length=64)
    time_limit: str | None = Field(default=None, max_length=32)
    items: list[WorksheetItemCreate] = Field(default_factory=list)


# ─── POST /worksheets ────────────────────────────────────────────────────────


@router.post("/", response_model=Worksheet, status_code=201)
async def create_worksheet(
    body: WorksheetCreateRequest,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Worksheet:
    """Worksheet 를 생성한다.

    request body 의 items[].passage_id 가 모두 현재 tenant 소속인지 검증한다.
    cross-tenant passage_id 또는 존재하지 않는 passage_id → 422.

    멀티테넌트: tenant_id / workspace_id 는 TenantContext 에서 채운다.
    request body 에서 tenant_id / workspace_id 를 받지 않아 크로스-테넌트 쓰기가
    구조적으로 불가능하다.

    Args:
        body: WorksheetCreateRequest — 제목/kind/items 등.
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        session: DB 세션.

    Returns:
        201 + 저장된 Worksheet (id + items 포함).

    Raises:
        HTTPException 422: cross-tenant passage_id / validation error /
            존재하지 않는 passage_id (IntegrityError).
    """
    # 1. request → domain Worksheet (tenant_id / workspace_id 는 tenant_ctx 에서 채움)
    domain_items = [
        WorksheetItem(
            passage_id=item.passage_id,
            order=item.order,
            label=item.label,
            include_translation=item.include_translation,
            include_vocabulary=item.include_vocabulary,
            include_syntax_annotations=item.include_syntax_annotations,
            include_questions=item.include_questions,
            include_variants=item.include_variants,
        )
        for item in body.items
    ]

    worksheet = Worksheet(
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
        title=body.title,
        subtitle=body.subtitle,
        kind=body.kind,
        template_id=body.template_id,
        orientation=body.orientation,
        instruction=body.instruction,
        branding=body.branding,
        school=body.school,
        grade=body.grade,
        exam_date=body.exam_date,
        time_limit=body.time_limit,
        items=domain_items,
    )

    # 2. 영속화 (단일 트랜잭션)
    worksheet_repo = WorksheetRepository(session, tenant_ctx)
    try:
        async with session.begin():
            saved = await worksheet_repo.create_with_items(worksheet)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except IntegrityError as exc:
        # passage_id FK 위배 (passages.id 미존재) — 422 (보안: 다른 tenant passage 존재 노출 방지)
        raise HTTPException(
            status_code=422,
            detail=(
                "items 의 passage_id 중 하나 이상이 존재하지 않습니다. "
                "passage_id 를 확인하세요."
            ),
        ) from exc

    return saved


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

    # 2~5. 조회 + 렌더 — export_pdf 와 동일 흐름 (DRY: _build_worksheet_html 공유)
    # style 검증은 preview 전용이므로 이 라우트에서 처리.
    # _build_worksheet_html 은 style=playful 고정 — MVP 단일 스타일 정책 준수.
    _worksheet, html_content = await _build_worksheet_html(
        worksheet_id, tenant_ctx, session
    )

    return HTMLResponse(content=html_content, status_code=200)


# ─── 공유 헬퍼 ──────────────────────────────────────────────────────────────


async def _build_worksheet_html(
    worksheet_id: uuid.UUID,
    tenant_ctx: TenantContext,
    session: AsyncSession,
) -> tuple[Worksheet, str]:
    """Worksheet ID → (Worksheet, rendered HTML) 공유 헬퍼.

    ``preview`` 와 ``export_pdf`` 가 동일한 조회 + 렌더 흐름을 공유한다 (DRY).
    tenant_id 필터, W-2 가드 패턴, passage None warning 모두 이 함수에서 처리.

    Args:
        worksheet_id: 조회할 Worksheet UUID.
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        session: DB 세션.

    Returns:
        tuple: (Worksheet 인스턴스, 렌더된 HTML 문자열).
        style 은 항상 ``playful`` (MVP 정책 — README §26).

    Raises:
        HTTPException 404: Worksheet 가 존재하지 않거나 다른 tenant 소유.
    """
    worksheet_repo = WorksheetRepository(session, tenant_ctx)
    passage_repo = PassageRepository(session, tenant_ctx)

    # Worksheet 조회 — tenant_id 필터 자동 적용
    worksheet = await worksheet_repo.get(worksheet_id)
    if worksheet is None:
        raise HTTPException(
            status_code=404,
            detail=f"Worksheet {worksheet_id} 를 찾을 수 없습니다.",
        )

    # WorksheetItems 조회 — W-2 가드 패턴 (tenant 재검증 포함)
    items_orm = await worksheet_repo.list_items_for_worksheet(worksheet_id)

    # 각 item 의 Passage 조회 (tenant 필터 자동 적용)
    # passage 가 None 이면 데이터 무결성 이상 (cross-tenant FK 또는 삭제된 passage).
    # graceful degradation: 렌더는 계속하되 warning 로그로 추적.
    passages: list[Passage] = []
    for item_orm in items_orm:
        passage = await passage_repo.get(item_orm.passage_id)
        if passage is None:
            logger.warning(
                "worksheet item passage missing — possible data integrity issue: "
                "worksheet_id=%s, item_id=%s, passage_id=%s",
                worksheet_id,
                item_orm.id,
                item_orm.passage_id,
            )
            continue
        passages.append(passage)

    # 템플릿 컨텍스트 생성 + 렌더링 (MVP: style=playful 고정)
    context = worksheet_to_template_context(worksheet, passages)
    html_content = render_worksheet_html(context, style="playful")

    return worksheet, html_content


# ─── POST /worksheets/{id}/export.pdf ────────────────────────────────────────


@router.post("/{worksheet_id}/export.pdf", status_code=200)
async def export_worksheet_pdf(
    worksheet_id: uuid.UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Worksheet 를 PDF 로 렌더해 반환한다.

    Playwright Chromium headless 로 HTML 을 렌더한 뒤 PDF 바이너리를 반환한다.
    style 은 항상 ``playful`` (MVP 정책 — ``README.md`` §26).

    ``Content-Disposition: attachment`` 로 브라우저가 다운로드 창을 열도록 한다.
    파일명은 ``worksheet.title`` 기반. 한글/공백/특수문자는 RFC 5987
    ``filename*=UTF-8''<encoded>`` 형식으로 인코딩한다.

    멀티테넌트: worksheet 존재 여부 + tenant 소유 확인.
    다른 tenant 의 worksheet_id 로 조회하면 404 반환 (존재 여부 노출 방지).

    content_html 한계:
        현재 각 질문의 content_html 은 passage.body_text 를 ``<p>`` 로 단순 wrap 한다.
        annotation split-mark 렌더러를 통한 정밀 HTML 주입은 별도 ADR 에서 다룬다.

    한계 (Stage 2):
        매 호출마다 Chromium browser 를 launch / close 한다.
        PDF 캐싱 없음. process-wide browser pool 은 별도 성능 ADR 에서 다룬다.

    Args:
        worksheet_id: 내보낼 Worksheet UUID.
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        session: DB 세션.

    Returns:
        Response: application/pdf Content-Type, PDF 바이너리 body.
            Content-Disposition: attachment; filename*=UTF-8''<encoded-title>.pdf

    Raises:
        HTTPException 404: Worksheet 가 존재하지 않거나 다른 tenant 소유.
    """
    # preview 와 동일한 조회 + 렌더 흐름 (DRY: _build_worksheet_html 공유)
    worksheet, html_content = await _build_worksheet_html(
        worksheet_id, tenant_ctx, session
    )

    # Worksheet.orientation → Playwright landscape 파라미터
    landscape = worksheet.orientation == WorksheetOrientation.LANDSCAPE

    # Playwright 로 PDF 생성
    pdf_bytes = await render_worksheet_pdf(html_content, landscape=landscape)

    # RFC 5987 filename* 인코딩 — 한글/공백/특수문자 안전 처리
    safe_filename = urllib.parse.quote(worksheet.title, safe="")
    content_disposition = f"attachment; filename*=UTF-8''{safe_filename}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition},
    )
