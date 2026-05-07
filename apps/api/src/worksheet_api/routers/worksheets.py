"""Worksheet API 엔드포인트.

검수 흐름 (2026-05-07~):
  1. POST /passages/extract → passage_id 1+ 확보
  2. POST /worksheets {items: [{passage_id, order: 0}, ...]} → worksheet_id 확보
  3. GET /worksheets → 목록 (필터/pagination)
  4. GET /worksheets/{id} → 단건 (items 포함)
  5. PATCH /worksheets/{id} → 메타 수정 (items 는 A2-b 별 라우트)
  6. DELETE /worksheets/{id} → 삭제 (items cascade)
  7. GET /worksheets/{id}/preview?style=playful → 브라우저로 HTML 확인
  8. POST /worksheets/{id}/export.pdf → PDF 다운로드 확인

현재 라우트:
  POST /worksheets
    → 201 application/json (Worksheet, id 포함)
    → 422 cross-tenant passage_id / validation error
    → 422 passage_id 가 DB 에 없음 (IntegrityError)

  GET /worksheets
    → 200 application/json (WorksheetListResponse — worksheets[] + total + limit + offset).
      각 Worksheet 의 items 는 빈 리스트 (단건 조회로 별도 가져옴, N+1 회피).
    쿼리 파라미터: limit (1~100, default 20), offset (ge=0, default 0), kind (WorksheetKind | None)

  GET /worksheets/{id}
    → 200 application/json (Worksheet — id + items 포함)
    → 404 worksheet not found / cross-tenant

  PATCH /worksheets/{id}
    → 200 application/json (Worksheet — 메타 수정 후 items 포함)
    → 404 worksheet not found / cross-tenant
    → 422 patch body 비어있음 / items 키 포함 (extra="forbid") / enum 값 오류

  DELETE /worksheets/{id}
    → 204 no content (성공)
    → 404 worksheet not found / cross-tenant
    items 는 ON DELETE CASCADE 로 자동 정리 (worksheet_items.worksheet_id FK).

  GET /worksheets/{id}/preview?style=playful
    → 200 text/html
    → 404 worksheet not found / cross-tenant
    → 422 invalid style

  POST /worksheets/{id}/export.pdf
    → 200 application/pdf (PDF 바이너리)
    → 404 worksheet not found / cross-tenant

ADR-0010 §D6 / "PR 후속 4" 명세 구현.

items CRUD 분리 정책 (C안):
  PATCH /worksheets/{id} 는 메타 필드만 수정한다. items 추가/삭제/순서 변경은
  A2-b 별 라우트 (POST/PATCH/DELETE /worksheets/{id}/items/...) 에서 처리한다.

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
from pydantic import BaseModel, ConfigDict, Field
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


# ─── 응답 스키마 (GET /worksheets) ──────────────────────────────────────────


class WorksheetListResponse(BaseModel):
    """GET /worksheets 응답 — pagination 메타 포함.

    각 Worksheet 는 WorksheetItem 리스트를 포함하지 않는다 (목록은 메타만 — N+1 회피).
    단건 조회 (GET /worksheets/{id}) 로 items 를 가져온다.

    필드명 ``worksheets`` (R-3): ``Worksheet.items`` 와의 중첩 혼동을 피한다
    (예: ``response.worksheets[0].items`` vs 잘못된 ``response.items[0].items``).
    AnnotationListResponse.annotations 선례와 동일한 도메인명 복수형 패턴.
    """

    worksheets: list[Worksheet] = Field(
        description="Worksheet 목록 (각 Worksheet 의 items 는 빈 리스트).",
    )
    total: int = Field(description="전체 개수 (현재 tenant + 필터 기준).")
    limit: int = Field(description="요청 limit (echo).")
    offset: int = Field(description="요청 offset (echo).")


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


# ─── 요청 스키마 (PATCH /worksheets/{id}) ───────────────────────────────────


class WorksheetUpdateRequest(BaseModel):
    """PATCH /worksheets/{id} request — 모든 필드 optional (부분 수정).

    items 는 본 request 에 없음 (A2-b 별 라우트로 분리).
    클라이언트가 items 키를 보내면 extra="forbid" 로 422 반환한다.

    branding 은 통째 교체 (부분 patch 미지원) — 클라이언트가 full Branding 을 보내야 한다.

    null 의미론 (R-4): 본 모델의 ``None`` default 는 "변경 없음" 을 의미한다.
    JSON 으로 명시적 ``null`` 을 보내는 것은 다음 두 경우로 나뉜다:
      - nullable 컬럼 (subtitle / instruction / branding / school 등): null 로 설정 가능.
      - NOT NULL 컬럼 (title / kind / template_id / orientation): Repository 레이어에서
        ValueError → 422 매핑 (W-1 차단).
    "변경하지 않음" 을 표현하려면 요청 body 에서 키를 **제외** 하세요.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=255)
    subtitle: str | None = Field(default=None, max_length=255)
    kind: WorksheetKind | None = None
    template_id: str | None = None
    orientation: WorksheetOrientation | None = None
    instruction: str | None = Field(default=None, max_length=2000)
    branding: Branding | None = None
    school: str | None = Field(default=None, max_length=255)
    grade: str | None = Field(default=None, max_length=64)
    exam_date: str | None = Field(default=None, max_length=64)
    time_limit: str | None = Field(default=None, max_length=32)


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


# ─── GET /worksheets ─────────────────────────────────────────────────────────


@router.get("/", response_model=WorksheetListResponse, status_code=200)
async def list_worksheets(
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100, description="최대 반환 건수 (1~100)."),
    offset: int = Query(default=0, ge=0, description="건너뛸 건수."),
    kind: WorksheetKind | None = Query(
        default=None,
        description="Worksheet 유형 필터. 미지정이면 전체 반환.",
    ),
) -> WorksheetListResponse:
    """Worksheet 목록을 pagination 으로 반환한다.

    목록의 각 Worksheet 는 items 를 포함하지 않는다 (N+1 회피).
    items 가 필요하면 GET /worksheets/{id} 로 단건 조회한다.

    정렬: created_at DESC (가장 최근 워크시트 먼저).
    멀티테넌트: tenant_id / workspace_id 필터 자동 적용.

    Args:
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        session: DB 세션.
        limit: 최대 반환 건수 (1~100, default 20).
        offset: 건너뛸 건수 (default 0).
        kind: WorksheetKind 필터 (optional).

    Returns:
        WorksheetListResponse: worksheets + total + limit + offset.
    """
    worksheet_repo = WorksheetRepository(session, tenant_ctx)
    worksheets, total = await worksheet_repo.list_with_pagination(
        limit=limit,
        offset=offset,
        kind=kind.value if kind is not None else None,
    )
    return WorksheetListResponse(
        worksheets=worksheets,
        total=total,
        limit=limit,
        offset=offset,
    )


# ─── GET /worksheets/{id} ────────────────────────────────────────────────────


@router.get("/{worksheet_id}", response_model=Worksheet, status_code=200)
async def get_worksheet(
    worksheet_id: uuid.UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Worksheet:
    """Worksheet 단건을 items 포함해 반환한다.

    멀티테넌트: 다른 tenant 의 worksheet_id 로 조회하면 404 반환 (존재 여부 노출 방지).
    W-2 가드 패턴: WorksheetItemORM 조회 전 부모 WorksheetORM 의 tenant_id 재검증.

    Args:
        worksheet_id: 조회할 Worksheet UUID.
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        session: DB 세션.

    Returns:
        Worksheet: id + items 포함.

    Raises:
        HTTPException 404: Worksheet 가 존재하지 않거나 다른 tenant 소유.
    """
    worksheet_repo = WorksheetRepository(session, tenant_ctx)

    # 1. Worksheet 조회 — tenant_id 필터 자동 적용
    worksheet = await worksheet_repo.get(worksheet_id)
    if worksheet is None:
        raise HTTPException(
            status_code=404,
            detail=f"Worksheet {worksheet_id} 를 찾을 수 없습니다.",
        )

    # 2. WorksheetItems 조회 — W-2 가드 패턴 (tenant 재검증 포함)
    items_orm = await worksheet_repo.list_items_for_worksheet(worksheet_id)

    # 3. ORM → WorksheetItem 변환 (인라인 list comprehension — 단순 매핑)
    items = [
        WorksheetItem(
            id=item_orm.id,
            passage_id=item_orm.passage_id,
            order=item_orm.order,
            label=item_orm.label,
            include_translation=item_orm.include_translation,
            include_vocabulary=item_orm.include_vocabulary,
            include_syntax_annotations=item_orm.include_syntax_annotations,
            include_questions=item_orm.include_questions,
            include_variants=item_orm.include_variants,
        )
        for item_orm in items_orm
    ]

    return worksheet.model_copy(update={"items": items})


# ─── PATCH /worksheets/{id} ─────────────────────────────────────────────────


@router.patch("/{worksheet_id}", response_model=Worksheet, status_code=200)
async def patch_worksheet(
    worksheet_id: uuid.UUID,
    body: WorksheetUpdateRequest,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Worksheet:
    """Worksheet 의 메타 필드를 부분 수정한다.

    수정 가능 필드: title / subtitle / kind / template_id / orientation /
    instruction / branding / school / grade / exam_date / time_limit.

    items 는 본 라우트에서 수정하지 않는다 (C안 정책). 클라이언트가 items 키를
    보내면 extra="forbid" (WorksheetUpdateRequest) 로 422 반환한다.

    branding 은 통째 교체 — 부분 patch 미지원. 클라이언트가 full Branding 을 보내야 한다.

    멀티테넌트: 다른 tenant 의 worksheet_id 로 수정하면 404 반환 (존재 여부 노출 방지).

    Args:
        worksheet_id: 수정할 Worksheet UUID.
        body: WorksheetUpdateRequest — 수정할 필드만 포함 (unset 필드는 변경 없음).
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        session: DB 세션.

    Returns:
        200 + 업데이트된 Worksheet (items 포함).

    Raises:
        HTTPException 404: Worksheet 가 존재하지 않거나 다른 tenant 소유.
        HTTPException 422: patch body 비어있음 / items 키 포함 / 잘못된 enum 값.
    """
    patch = body.model_dump(exclude_unset=True)

    # patch 가 비어있으면 의미 없는 PATCH — 422
    if not patch:
        raise HTTPException(
            status_code=422,
            detail="PATCH 요청에 변경할 필드가 없습니다. 최소 하나의 필드를 포함하세요.",
        )

    worksheet_repo = WorksheetRepository(session, tenant_ctx)

    # W-2 — Repository 의 ValueError (items 키 / NOT NULL null) 와 IntegrityError 를
    # 422 로 매핑. create_worksheet 와 동일한 방어 패턴.
    try:
        async with session.begin():
            updated = await worksheet_repo.update_meta(worksheet_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=422,
            detail="변경 값이 DB 제약 조건을 위반합니다.",
        ) from exc

    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"Worksheet {worksheet_id} 를 찾을 수 없습니다.",
        )

    # items 조회 — W-2 가드 패턴 (tenant 재검증 포함)
    items_orm = await worksheet_repo.list_items_for_worksheet(worksheet_id)
    items = [
        WorksheetItem(
            id=item_orm.id,
            passage_id=item_orm.passage_id,
            order=item_orm.order,
            label=item_orm.label,
            include_translation=item_orm.include_translation,
            include_vocabulary=item_orm.include_vocabulary,
            include_syntax_annotations=item_orm.include_syntax_annotations,
            include_questions=item_orm.include_questions,
            include_variants=item_orm.include_variants,
        )
        for item_orm in items_orm
    ]
    return updated.model_copy(update={"items": items})


# ─── DELETE /worksheets/{id} ─────────────────────────────────────────────────


@router.delete("/{worksheet_id}", status_code=204)
async def delete_worksheet(
    worksheet_id: uuid.UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Worksheet 를 삭제한다.

    worksheet_items 는 ``worksheet_id FK ondelete=CASCADE`` 로 자동 정리된다
    (Alembic 마이그레이션 ``20260507_0006_*`` 확정).

    멀티테넌트: 다른 tenant 의 worksheet_id 로 삭제하면 404 반환 (존재 여부 노출 방지).

    Args:
        worksheet_id: 삭제할 Worksheet UUID.
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        session: DB 세션.

    Returns:
        204 no content.

    Raises:
        HTTPException 404: Worksheet 가 존재하지 않거나 다른 tenant 소유.
    """
    worksheet_repo = WorksheetRepository(session, tenant_ctx)

    async with session.begin():
        deleted = await worksheet_repo.delete(worksheet_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Worksheet {worksheet_id} 를 찾을 수 없습니다.",
        )

    return Response(status_code=204)


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
