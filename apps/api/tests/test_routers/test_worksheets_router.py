"""GET /worksheets/{id}/preview + POST /worksheets/{id}/export.pdf + POST /worksheets 라우터 단위 테스트.

mock session + mock repository 로 실제 DB 없이 실행한다.

커버 케이스 (POST /worksheets):
  - 201 정상 — id 채워진 Worksheet 반환
  - 422 — cross-tenant passage_id (WorksheetRepository.create_with_items 가 ValueError)
  - 422 — 존재하지 않는 passage_id (IntegrityError mock → 422)
  - 422 — Pydantic validation (kind 가 enum 값이 아님)
  - items=[] 인 Worksheet 정상 생성 확인

커버 케이스 (preview):
  - 200 정상 — fixture worksheet 생성 → preview 호출 → HTML 에 academy.name / title 포함
  - 404 — 존재하지 않는 worksheet_id
  - 404 — cross-tenant (다른 tenant 의 worksheet id)
  - 422 — invalid style
  - 422 — style=classic (MVP 정책 — README §26)
  - 422 — style=modern (MVP 정책 — README §26)
  - 200 + warning — passage 누락 graceful (W-2 후속, R-3)
  - 200 + escape — body_text XSS escape (S-1 회귀)

커버 케이스 (export.pdf):
  - 200 + application/pdf — 정상 (render_worksheet_pdf mock)
  - Content-Disposition: attachment + filename 확인
  - 200 portrait worksheet → landscape=False 로 render_worksheet_pdf 호출 확인
  - 200 landscape worksheet → landscape=True 로 render_worksheet_pdf 호출 확인
  - 404 — 존재하지 않는 worksheet_id
  - 404 — cross-tenant

패턴: test_annotations_router.py 와 동일한 mock 패턴 사용.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from worksheet_api.db import get_db
from worksheet_api.main import app
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context

from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade
from shared.schemas.worksheet import (
    Branding,
    Worksheet,
    WorksheetItem,
    WorksheetKind,
    WorksheetOrientation,
)

# ─── 테스트용 고정 UUID ──────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TENANT_B = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
WORKSPACE_B = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
WORKSHEET_ID_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
PASSAGE_ID_1 = uuid.UUID("22222222-2222-2222-2222-222222222222")


# ─── 헬퍼 팩토리 ────────────────────────────────────────────────────────────


def _make_worksheet(
    worksheet_id: uuid.UUID = WORKSHEET_ID_1,
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
    passage_id: uuid.UUID = PASSAGE_ID_1,
) -> Worksheet:
    """테스트용 Worksheet (저장 완료 상태, id 포함)."""
    return Worksheet(
        id=worksheet_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        title="테스트 워크시트",
        subtitle="Week 01",
        kind=WorksheetKind.STUDENT,
        template_id="playful",
        instruction="다음 지문을 읽고 물음에 답하시오.",
        branding=Branding(
            academy_name="테스트학원",
            primary_color="#1F4E79",
        ),
        items=[
            WorksheetItem(passage_id=passage_id, order=0, label="독해 연습"),
        ],
    )


def _make_passage(
    passage_id: uuid.UUID = PASSAGE_ID_1,
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
) -> Passage:
    """테스트용 Passage."""
    return Passage(
        id=passage_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        body_text="The economy has been growing steadily over the past decade.",
        paragraphs=["The economy has been growing steadily over the past decade."],
        word_count=11,
        target_grade=TargetGrade.HIGH_3,
        topic_tags=[],
        source=SourceMeta(provider=SourceProvider.USER_INPUT),
    )


def _make_item_orm(
    worksheet_id: uuid.UUID = WORKSHEET_ID_1,
    passage_id: uuid.UUID = PASSAGE_ID_1,
) -> MagicMock:
    """WorksheetItemORM mock."""
    item = MagicMock()
    item.worksheet_id = worksheet_id
    item.passage_id = passage_id
    item.order = 0
    item.label = "독해 연습"
    return item


# ─── 픽스처 ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session() -> AsyncMock:
    """트랜잭션 컨텍스트 매니저를 지원하는 mock AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = begin_cm
    return session


@pytest.fixture
def tenant_ctx_a() -> TenantContext:
    """테넌트 A 컨텍스트."""
    return TenantContext(tenant_id=TENANT_A, workspace_id=WORKSPACE_A)


@pytest.fixture
def override_deps(
    mock_session: AsyncMock,
    tenant_ctx_a: TenantContext,
) -> dict[Any, Any]:
    """FastAPI dependency_overrides 딕셔너리 반환."""

    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def _get_tenant() -> TenantContext:
        return tenant_ctx_a

    return {
        get_db: _get_db,
        get_tenant_context: _get_tenant,
    }


@pytest.fixture
async def async_client(override_deps: dict[Any, Any]) -> AsyncGenerator[AsyncClient, None]:
    """의존성 오버라이드가 적용된 AsyncClient."""
    app.dependency_overrides.update(override_deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ─── GET /worksheets/{id}/preview 테스트 ────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_worksheet_ok(async_client: AsyncClient) -> None:
    """정상 — worksheet + passage 존재, style=playful → 200 HTML.

    HTML 안에 academy.name ('테스트학원') 과 worksheet.title ('테스트 워크시트') 가
    포함돼야 한다.
    """
    worksheet = _make_worksheet()
    passage = _make_passage()
    item_orm = _make_item_orm()

    with (
        patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls,
        patch("worksheet_api.routers.worksheets.PassageRepository") as mock_passage_repo_cls,
    ):
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.get = AsyncMock(return_value=worksheet)
        mock_ws_repo.list_items_for_worksheet = AsyncMock(return_value=[item_orm])

        mock_passage_repo = mock_passage_repo_cls.return_value
        mock_passage_repo.get = AsyncMock(return_value=passage)

        resp = await async_client.get(
            f"/worksheets/{WORKSHEET_ID_1}/preview",
            params={"style": "playful"},
        )

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "테스트학원" in body
    assert "테스트 워크시트" in body


@pytest.mark.asyncio
async def test_preview_worksheet_not_found_404(async_client: AsyncClient) -> None:
    """존재하지 않는 worksheet_id → 404."""
    unknown_id = uuid.UUID("99999999-9999-9999-9999-999999999999")

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.get(
            f"/worksheets/{unknown_id}/preview",
            params={"style": "playful"},
        )

    assert resp.status_code == 404
    assert "찾을 수 없" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_preview_worksheet_cross_tenant_404(async_client: AsyncClient) -> None:
    """cross-tenant: 다른 tenant 의 worksheet_id → 404 (존재 여부 노출 방지).

    WorksheetRepository.get() 이 tenant_id 필터로 None 을 반환하면
    라우터는 404 를 반환해야 한다.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        # 다른 tenant 소유 → tenant 필터 후 None
        mock_ws_repo_cls.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.get(
            f"/worksheets/{WORKSHEET_ID_1}/preview",
            params={"style": "playful"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_preview_worksheet_invalid_style_422(async_client: AsyncClient) -> None:
    """허용되지 않은 style 값 → 422."""
    resp = await async_client.get(
        f"/worksheets/{WORKSHEET_ID_1}/preview",
        params={"style": "invalid_xyz"},
    )

    assert resp.status_code == 422
    assert "허용되지 않은 style" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_preview_worksheet_style_classic_422(async_client: AsyncClient) -> None:
    """style=classic → 422 (MVP 정책 — README §26: playful 만 노출)."""
    resp = await async_client.get(
        f"/worksheets/{WORKSHEET_ID_1}/preview",
        params={"style": "classic"},
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_preview_worksheet_style_modern_422(async_client: AsyncClient) -> None:
    """style=modern → 422 (MVP 정책 — README §26: playful 만 노출)."""
    resp = await async_client.get(
        f"/worksheets/{WORKSHEET_ID_1}/preview",
        params={"style": "modern"},
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_preview_worksheet_passage_missing_graceful(
    async_client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """W-2 후속: passage 가 None 이어도 200 + warning 로그.

    데이터 무결성 이상 (cross-tenant FK 또는 삭제된 passage) 시 silently 스킵
    하지 않고 logger.warning 으로 추적해야 한다. graceful degradation 으로
    렌더는 계속하되 questions 가 빈 리스트가 된다.
    """
    import logging

    worksheet = _make_worksheet()
    item_orm = _make_item_orm()

    with (
        caplog.at_level(logging.WARNING, logger="worksheet_api.routers.worksheets"),
        patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls,
        patch("worksheet_api.routers.worksheets.PassageRepository") as mock_passage_repo_cls,
    ):
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.get = AsyncMock(return_value=worksheet)
        mock_ws_repo.list_items_for_worksheet = AsyncMock(return_value=[item_orm])

        mock_passage_repo = mock_passage_repo_cls.return_value
        mock_passage_repo.get = AsyncMock(return_value=None)  # passage 누락

        resp = await async_client.get(
            f"/worksheets/{WORKSHEET_ID_1}/preview",
            params={"style": "playful"},
        )

    assert resp.status_code == 200
    assert any("passage missing" in rec.message for rec in caplog.records), (
        "passage 누락 시 warning 로그가 남아야 한다"
    )


@pytest.mark.asyncio
async def test_preview_worksheet_xss_escape(async_client: AsyncClient) -> None:
    """S-1 회귀: passage.body_text 의 HTML 특수문자가 escape 되어야 한다.

    body_text 에 ``<script>`` 가 포함돼도 렌더 결과에 raw <script> 태그가
    들어가지 않아야 한다 (markupsafe.escape() 적용).
    """
    worksheet = _make_worksheet()
    item_orm = _make_item_orm()
    malicious_text = '<script>alert("xss")</script>'
    passage = _make_passage()
    passage = passage.model_copy(update={"body_text": malicious_text})

    with (
        patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls,
        patch("worksheet_api.routers.worksheets.PassageRepository") as mock_passage_repo_cls,
    ):
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.get = AsyncMock(return_value=worksheet)
        mock_ws_repo.list_items_for_worksheet = AsyncMock(return_value=[item_orm])

        mock_passage_repo = mock_passage_repo_cls.return_value
        mock_passage_repo.get = AsyncMock(return_value=passage)

        resp = await async_client.get(
            f"/worksheets/{WORKSHEET_ID_1}/preview",
            params={"style": "playful"},
        )

    assert resp.status_code == 200
    body = resp.text
    # raw <script> 태그가 들어가서는 안 된다
    assert "<script>alert" not in body
    # escape 된 형태가 들어가야 한다 (markupsafe escape)
    assert "&lt;script&gt;" in body


# ─── POST /worksheets/{id}/export.pdf 테스트 ─────────────────────────────────

# Playwright 호출을 mock 하는 고정 PDF 바이트 (magic bytes 포함)
_MOCK_PDF_BYTES = b"%PDF-1.4 mock pdf content for testing"


@pytest.mark.asyncio
async def test_export_pdf_ok(async_client: AsyncClient) -> None:
    """정상 — 200 + Content-Type=application/pdf + b'%PDF' 시작.

    ``render_worksheet_pdf`` 를 mock 해 Chromium 없이 라우터 로직만 검증한다.
    """
    worksheet = _make_worksheet()
    passage = _make_passage()
    item_orm = _make_item_orm()

    with (
        patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls,
        patch("worksheet_api.routers.worksheets.PassageRepository") as mock_passage_repo_cls,
        patch(
            "worksheet_api.routers.worksheets.render_worksheet_pdf",
            new=AsyncMock(return_value=_MOCK_PDF_BYTES),
        ),
    ):
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.get = AsyncMock(return_value=worksheet)
        mock_ws_repo.list_items_for_worksheet = AsyncMock(return_value=[item_orm])

        mock_passage_repo = mock_passage_repo_cls.return_value
        mock_passage_repo.get = AsyncMock(return_value=passage)

        resp = await async_client.post(f"/worksheets/{WORKSHEET_ID_1}/export.pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_export_pdf_content_disposition(async_client: AsyncClient) -> None:
    """Content-Disposition 헤더에 attachment + filename 이 포함돼야 한다.

    worksheet.title = "테스트 워크시트" → filename 에 URL 인코딩된 한글 포함.
    """
    worksheet = _make_worksheet()
    passage = _make_passage()
    item_orm = _make_item_orm()

    with (
        patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls,
        patch("worksheet_api.routers.worksheets.PassageRepository") as mock_passage_repo_cls,
        patch(
            "worksheet_api.routers.worksheets.render_worksheet_pdf",
            new=AsyncMock(return_value=_MOCK_PDF_BYTES),
        ),
    ):
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.get = AsyncMock(return_value=worksheet)
        mock_ws_repo.list_items_for_worksheet = AsyncMock(return_value=[item_orm])

        mock_passage_repo = mock_passage_repo_cls.return_value
        mock_passage_repo.get = AsyncMock(return_value=passage)

        resp = await async_client.post(f"/worksheets/{WORKSHEET_ID_1}/export.pdf")

    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd
    # RFC 5987 filename* 형식 확인
    assert "filename*=UTF-8''" in cd
    # .pdf 확장자 포함 확인
    assert ".pdf" in cd


@pytest.mark.asyncio
async def test_export_pdf_portrait_calls_landscape_false(async_client: AsyncClient) -> None:
    """portrait orientation worksheet → landscape=False 로 render_worksheet_pdf 호출."""
    worksheet = _make_worksheet()
    assert worksheet.orientation == WorksheetOrientation.PORTRAIT  # fixture 기본값 확인

    passage = _make_passage()
    item_orm = _make_item_orm()

    mock_render = AsyncMock(return_value=_MOCK_PDF_BYTES)

    with (
        patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls,
        patch("worksheet_api.routers.worksheets.PassageRepository") as mock_passage_repo_cls,
        patch("worksheet_api.routers.worksheets.render_worksheet_pdf", new=mock_render),
    ):
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.get = AsyncMock(return_value=worksheet)
        mock_ws_repo.list_items_for_worksheet = AsyncMock(return_value=[item_orm])

        mock_passage_repo = mock_passage_repo_cls.return_value
        mock_passage_repo.get = AsyncMock(return_value=passage)

        resp = await async_client.post(f"/worksheets/{WORKSHEET_ID_1}/export.pdf")

    assert resp.status_code == 200
    # landscape=False 로 호출됐는지 확인
    mock_render.assert_called_once()
    _args, kwargs = mock_render.call_args
    assert kwargs.get("landscape") is False


@pytest.mark.asyncio
async def test_export_pdf_landscape_calls_landscape_true(async_client: AsyncClient) -> None:
    """landscape orientation worksheet → landscape=True 로 render_worksheet_pdf 호출."""
    worksheet = _make_worksheet()
    landscape_worksheet = worksheet.model_copy(
        update={"orientation": WorksheetOrientation.LANDSCAPE}
    )

    passage = _make_passage()
    item_orm = _make_item_orm()

    mock_render = AsyncMock(return_value=_MOCK_PDF_BYTES)

    with (
        patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls,
        patch("worksheet_api.routers.worksheets.PassageRepository") as mock_passage_repo_cls,
        patch("worksheet_api.routers.worksheets.render_worksheet_pdf", new=mock_render),
    ):
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.get = AsyncMock(return_value=landscape_worksheet)
        mock_ws_repo.list_items_for_worksheet = AsyncMock(return_value=[item_orm])

        mock_passage_repo = mock_passage_repo_cls.return_value
        mock_passage_repo.get = AsyncMock(return_value=passage)

        resp = await async_client.post(f"/worksheets/{WORKSHEET_ID_1}/export.pdf")

    assert resp.status_code == 200
    mock_render.assert_called_once()
    _args, kwargs = mock_render.call_args
    assert kwargs.get("landscape") is True


@pytest.mark.asyncio
async def test_export_pdf_not_found_404(async_client: AsyncClient) -> None:
    """존재하지 않는 worksheet_id → 404."""
    unknown_id = uuid.UUID("99999999-9999-9999-9999-999999999999")

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.post(f"/worksheets/{unknown_id}/export.pdf")

    assert resp.status_code == 404
    assert "찾을 수 없" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_export_pdf_cross_tenant_404(async_client: AsyncClient) -> None:
    """cross-tenant: 다른 tenant 의 worksheet_id → 404 (존재 여부 노출 방지).

    WorksheetRepository.get() 이 tenant_id 필터로 None 을 반환하면
    라우터는 404 를 반환해야 한다.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.post(f"/worksheets/{WORKSHEET_ID_1}/export.pdf")

    assert resp.status_code == 404


# ─── POST /worksheets 테스트 ────────────────────────────────────────────────


def _make_create_payload(
    *,
    passage_id: uuid.UUID = PASSAGE_ID_1,
    kind: str = "student",
    include_items: bool = True,
) -> dict[str, Any]:
    """POST /worksheets 요청 본문 헬퍼."""
    payload: dict[str, Any] = {
        "title": "신규 워크시트",
        "kind": kind,
        "template_id": "playful",
        "orientation": "portrait",
        "branding": {
            "academy_name": "테스트학원",
            "primary_color": "#1F4E79",
        },
    }
    if include_items:
        payload["items"] = [
            {
                "passage_id": str(passage_id),
                "order": 0,
                "label": "독해 연습",
                "include_translation": False,
            }
        ]
    return payload


@pytest.mark.asyncio
async def test_create_worksheet_ok_201(async_client: AsyncClient) -> None:
    """정상 — 201 + body 에 id 채워진 Worksheet 반환.

    create_with_items 가 성공적으로 Worksheet 를 반환하면 라우터는 201 + JSON 을
    반환해야 한다.
    """
    saved_worksheet = _make_worksheet()

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        # session.begin() 컨텍스트 매니저 mock (라우터가 async with session.begin() 사용)
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.create_with_items = AsyncMock(return_value=saved_worksheet)

        resp = await async_client.post("/worksheets/", json=_make_create_payload())

    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == str(saved_worksheet.id)
    assert body["title"] == "테스트 워크시트"


@pytest.mark.asyncio
async def test_create_worksheet_cross_tenant_passage_422(async_client: AsyncClient) -> None:
    """cross-tenant passage_id → 422.

    create_with_items 가 ValueError (cross-tenant passage_id) 를 raise 하면
    라우터는 422 를 반환해야 한다.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.create_with_items = AsyncMock(
            side_effect=ValueError(
                "passage_id 중 하나 이상이 현재 tenant 소유가 아니거나 존재하지 않습니다."
            )
        )

        resp = await async_client.post("/worksheets/", json=_make_create_payload())

    assert resp.status_code == 422
    assert "passage_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_worksheet_integrity_error_422(async_client: AsyncClient) -> None:
    """존재하지 않는 passage_id (IntegrityError) → 422.

    FK 위배로 IntegrityError 가 발생하면 라우터는 422 를 반환해야 한다.
    (보안: 다른 tenant passage 의 존재 여부 노출 방지 — 404 대신 422)
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.create_with_items = AsyncMock(
            side_effect=IntegrityError("FK violation", None, None)
        )

        resp = await async_client.post("/worksheets/", json=_make_create_payload())

    assert resp.status_code == 422
    assert "passage_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_worksheet_invalid_kind_422(async_client: AsyncClient) -> None:
    """kind 가 WorksheetKind enum 값이 아님 → 422 (Pydantic validation)."""
    payload = _make_create_payload(kind="invalid_kind_xyz")

    resp = await async_client.post("/worksheets/", json=payload)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_worksheet_empty_items_ok(async_client: AsyncClient) -> None:
    """items=[] 인 Worksheet 정상 생성 — 201.

    Worksheet schema 는 items 를 default_factory=[] 로 허용한다.
    items 없이도 worksheet 생성이 가능해야 한다.
    """
    saved_worksheet = _make_worksheet().model_copy(update={"items": []})

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.create_with_items = AsyncMock(return_value=saved_worksheet)

        payload = _make_create_payload(include_items=False)
        resp = await async_client.post("/worksheets/", json=payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["items"] == []
