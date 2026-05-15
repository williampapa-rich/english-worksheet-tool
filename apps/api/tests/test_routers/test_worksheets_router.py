"""GET /worksheets + GET /worksheets/{id} + GET /worksheets/{id}/preview
+ POST /worksheets/{id}/export.pdf + POST /worksheets
+ PATCH /worksheets/{id} + DELETE /worksheets/{id}
+ POST /worksheets/{id}/items + PATCH /worksheets/{id}/items/{item_id}
+ DELETE /worksheets/{id}/items/{item_id} 라우터 단위 테스트.

mock session + mock repository 로 실제 DB 없이 실행한다.

커버 케이스 (POST /worksheets):
  - 201 정상 — id 채워진 Worksheet 반환
  - 422 — cross-tenant passage_id (WorksheetRepository.create_with_items 가 ValueError)
  - 422 — 존재하지 않는 passage_id (IntegrityError mock → 422)
  - 422 — Pydantic validation (kind 가 enum 값이 아님)
  - 422 — 같은 passage_id 중복 (W-1 (a) — 도메인 정책)
  - items=[] 인 Worksheet 정상 생성 확인

커버 케이스 (GET /worksheets/{id}):
  - 200 정상 — id + items 포함된 Worksheet 반환
  - 200 — items=[] 인 worksheet (items 조회 결과 빈 리스트)
  - 404 — 존재하지 않는 worksheet_id
  - 404 — cross-tenant (다른 tenant 의 worksheet id)

커버 케이스 (GET /worksheets):
  - 200 정상 — items + total + limit + offset 응답
  - 200 — limit/offset 정확히 repository 에 전달
  - 200 — kind 필터 정확히 전달
  - 200 — 빈 결과 ({items: [], total: 0, ...})
  - 422 — limit > 100 (Pydantic Query validation)
  - 422 — offset < 0
  - 422 — kind 가 enum 값 아님

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

커버 케이스 (PATCH /worksheets/{id}):
  - 200 정상 — title 만 patch → 응답에 title 변경 + 다른 필드 그대로
  - 200 — branding 통째 교체
  - 200 — 여러 필드 동시 patch
  - 404 — 존재하지 않는 worksheet_id (mock update_meta → None)
  - 404 — cross-tenant
  - 422 — extra='forbid' — items 키 보내면 차단
  - 422 — patch body 비어있음 ({})
  - 422 — kind 가 enum 값 아님

커버 케이스 (DELETE /worksheets/{id}):
  - 204 정상 — mock delete → True
  - 404 — mock delete → False (없거나 cross-tenant)

커버 케이스 (POST /worksheets/{id}/items):
  - 201 정상 — id 채워진 WorksheetItem 반환
  - 404 — worksheet not found / cross-tenant (add_item → None)
  - 422 — cross-tenant passage_id (add_item ValueError)
  - 422 — 중복 passage_id (add_item ValueError)
  - 422 — Pydantic validation (order < 0)
  - 422 — extra='forbid' (잘못된 키)

커버 케이스 (PATCH /worksheets/{id}/items/{item_id}):
  - 200 정상 — label 만 patch
  - 200 — 여러 필드 동시 patch
  - 404 — worksheet not found / cross-tenant (update_item → None)
  - 404 — item not found (update_item → None)
  - 422 — passage_id 키 포함 → extra='forbid' 422
  - 422 — NOT NULL 필드 null (order: null → update_item ValueError)
  - 422 — 빈 body

커버 케이스 (DELETE /worksheets/{id}/items/{item_id}):
  - 204 정상 — delete_item → True
  - 404 — worksheet not found (delete_item → False)
  - 404 — item not found (delete_item → False)

패턴: test_annotations_router.py 와 동일한 mock 패턴 사용.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from worksheet_api.db import get_db
from worksheet_api.main import app
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context

from shared.schemas.annotation import (
    AnnotationKind,
    CharacterOffsetV1Span,
    SyntaxAnnotation,
)
from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade
from shared.schemas.translation import Translation, TranslationCreatedBy
from shared.schemas.vocabulary import Vocabulary, VocabularySelectedBy
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
    """WorksheetItemORM mock — WorksheetItem 변환에 필요한 모든 attr 포함."""
    item = MagicMock()
    item.id = uuid.uuid4()
    item.worksheet_id = worksheet_id
    item.passage_id = passage_id
    item.order = 0
    item.label = "독해 연습"
    item.include_translation = False
    item.include_vocabulary = False
    item.include_syntax_annotations = False
    item.include_questions = False
    item.include_variants = False
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
        patch("worksheet_api.routers.worksheets.SyntaxAnnotationRepository") as mock_ann_repo_cls,
        patch("worksheet_api.routers.worksheets.TranslationRepository") as mock_trans_repo_cls,
        patch("worksheet_api.routers.worksheets.VocabularyRepository") as mock_vocab_repo_cls,
    ):
        mock_ann_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
        mock_trans_repo_cls.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_vocab_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
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
        patch("worksheet_api.routers.worksheets.SyntaxAnnotationRepository") as mock_ann_repo_cls,
        patch("worksheet_api.routers.worksheets.TranslationRepository") as mock_trans_repo_cls,
        patch("worksheet_api.routers.worksheets.VocabularyRepository") as mock_vocab_repo_cls,
    ):
        mock_ann_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
        mock_trans_repo_cls.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_vocab_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
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
        patch("worksheet_api.routers.worksheets.SyntaxAnnotationRepository") as mock_ann_repo_cls,
        patch("worksheet_api.routers.worksheets.TranslationRepository") as mock_trans_repo_cls,
        patch("worksheet_api.routers.worksheets.VocabularyRepository") as mock_vocab_repo_cls,
        patch(
            "worksheet_api.routers.worksheets.render_worksheet_pdf",
            new=AsyncMock(return_value=_MOCK_PDF_BYTES),
        ),
    ):
        mock_ann_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
        mock_trans_repo_cls.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_vocab_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
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
        patch("worksheet_api.routers.worksheets.SyntaxAnnotationRepository") as mock_ann_repo_cls,
        patch("worksheet_api.routers.worksheets.TranslationRepository") as mock_trans_repo_cls,
        patch("worksheet_api.routers.worksheets.VocabularyRepository") as mock_vocab_repo_cls,
        patch(
            "worksheet_api.routers.worksheets.render_worksheet_pdf",
            new=AsyncMock(return_value=_MOCK_PDF_BYTES),
        ),
    ):
        mock_ann_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
        mock_trans_repo_cls.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_vocab_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
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
        patch("worksheet_api.routers.worksheets.SyntaxAnnotationRepository") as mock_ann_repo_cls,
        patch("worksheet_api.routers.worksheets.TranslationRepository") as mock_trans_repo_cls,
        patch("worksheet_api.routers.worksheets.VocabularyRepository") as mock_vocab_repo_cls,
        patch("worksheet_api.routers.worksheets.render_worksheet_pdf", new=mock_render),
    ):
        mock_ann_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
        mock_trans_repo_cls.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_vocab_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
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
    # v0.2-α — footer_html kwarg 가 빈 문자열이 아니어야 함 (Chromium native
    # display_header_footer 경로 보장). render_pdf_footer_html 의 실제 출력은
    # 부분 템플릿 렌더 결과라 정확한 문자열 검증은 부서지기 쉬움 — 비어있지 않음만 확인.
    assert kwargs.get("footer_html"), (
        "footer_html 이 비어있으면 v0.2-α D안 (Chromium native footer + margin) 회귀."
    )


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
        patch("worksheet_api.routers.worksheets.SyntaxAnnotationRepository") as mock_ann_repo_cls,
        patch("worksheet_api.routers.worksheets.TranslationRepository") as mock_trans_repo_cls,
        patch("worksheet_api.routers.worksheets.VocabularyRepository") as mock_vocab_repo_cls,
        patch("worksheet_api.routers.worksheets.render_worksheet_pdf", new=mock_render),
    ):
        mock_ann_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
        mock_trans_repo_cls.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_vocab_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
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
    # v0.2-α — footer_html kwarg 가 빈 문자열이 아니어야 함 (Chromium native
    # display_header_footer 경로 보장).
    assert kwargs.get("footer_html"), (
        "footer_html 이 비어있으면 v0.2-α D안 (Chromium native footer + margin) 회귀."
    )


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
async def test_create_worksheet_duplicate_passage_id_422(async_client: AsyncClient) -> None:
    """W-1 (a) — 같은 passage_id 가 여러 item 에 중복 → 422.

    create_with_items 가 ValueError("중복") 를 raise → 라우터 422 매핑.
    Phase 2 PoC 도메인 정책: 동일 passage 두 번 금지.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.create_with_items = AsyncMock(
            side_effect=ValueError("같은 passage_id 를 여러 item 에 중복으로 넣을 수 없습니다.")
        )

        # 같은 passage_id 를 두 item 에 사용
        payload = _make_create_payload()
        payload["items"].append(
            {
                "passage_id": str(PASSAGE_ID_1),
                "order": 1,
                "label": "중복",
            }
        )

        resp = await async_client.post("/worksheets/", json=payload)

    assert resp.status_code == 422
    assert "중복" in resp.json()["detail"]


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


# ─── GET /worksheets/{id} 테스트 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_worksheet_ok_with_items(async_client: AsyncClient) -> None:
    """정상 — id + items 포함된 Worksheet 반환.

    WorksheetRepository.get 이 worksheet 를 반환하고
    list_items_for_worksheet 가 item_orm 을 반환하면
    라우터는 200 + items 가 채워진 Worksheet 를 반환해야 한다.
    """
    worksheet = _make_worksheet()
    item_orm = _make_item_orm()
    item_orm.id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    item_orm.include_translation = False
    item_orm.include_vocabulary = False
    item_orm.include_syntax_annotations = False
    item_orm.include_questions = False
    item_orm.include_variants = False

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.get = AsyncMock(return_value=worksheet)
        mock_ws_repo.list_items_for_worksheet = AsyncMock(return_value=[item_orm])

        resp = await async_client.get(f"/worksheets/{WORKSHEET_ID_1}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(WORKSHEET_ID_1)
    assert len(body["items"]) == 1
    assert body["items"][0]["passage_id"] == str(PASSAGE_ID_1)


@pytest.mark.asyncio
async def test_get_worksheet_ok_empty_items(async_client: AsyncClient) -> None:
    """items=[] 인 worksheet — 200 + items 빈 리스트.

    list_items_for_worksheet 가 빈 리스트를 반환하면
    라우터도 items=[] 로 반환해야 한다.
    """
    worksheet = _make_worksheet().model_copy(update={"items": []})

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.get = AsyncMock(return_value=worksheet)
        mock_ws_repo.list_items_for_worksheet = AsyncMock(return_value=[])

        resp = await async_client.get(f"/worksheets/{WORKSHEET_ID_1}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []


@pytest.mark.asyncio
async def test_get_worksheet_not_found_404(async_client: AsyncClient) -> None:
    """존재하지 않는 worksheet_id → 404."""
    unknown_id = uuid.UUID("99999999-9999-9999-9999-999999999999")

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.get(f"/worksheets/{unknown_id}")

    assert resp.status_code == 404
    assert "찾을 수 없" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_worksheet_cross_tenant_404(async_client: AsyncClient) -> None:
    """cross-tenant: 다른 tenant 의 worksheet_id → 404 (존재 여부 노출 방지).

    WorksheetRepository.get() 이 tenant_id 필터로 None 을 반환하면
    라우터는 404 를 반환해야 한다.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.get(f"/worksheets/{WORKSHEET_ID_1}")

    assert resp.status_code == 404


# ─── GET /worksheets 테스트 ──────────────────────────────────────────────────

WORKSHEET_ID_2 = uuid.UUID("33333333-3333-3333-3333-333333333333")
WORKSHEET_ID_3 = uuid.UUID("44444444-4444-4444-4444-444444444444")


@pytest.mark.asyncio
async def test_list_worksheets_ok(async_client: AsyncClient) -> None:
    """정상 — worksheets + total + limit + offset 응답.

    list_with_pagination 이 worksheets 리스트와 total 을 반환하면
    라우터는 200 + WorksheetListResponse 를 반환해야 한다.
    각 worksheet 의 items 는 빈 리스트 (목록 응답 정책).
    응답 필드명은 ``worksheets`` (R-3) — Worksheet.items 와 중첩 혼동 회피.
    """
    ws1 = _make_worksheet(worksheet_id=WORKSHEET_ID_1).model_copy(update={"items": []})
    ws2 = _make_worksheet(worksheet_id=WORKSHEET_ID_2).model_copy(update={"items": []})

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.list_with_pagination = AsyncMock(return_value=([ws1, ws2], 2))

        resp = await async_client.get("/worksheets/")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["worksheets"]) == 2
    assert body["total"] == 2
    assert body["limit"] == 20
    assert body["offset"] == 0


@pytest.mark.asyncio
async def test_list_worksheets_limit_offset_forwarded(async_client: AsyncClient) -> None:
    """limit/offset 파라미터가 repository 에 정확히 전달되는지 검증."""
    ws = _make_worksheet().model_copy(update={"items": []})

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.list_with_pagination = AsyncMock(return_value=([ws], 10))

        resp = await async_client.get("/worksheets/", params={"limit": 5, "offset": 3})

    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 5
    assert body["offset"] == 3

    # repository 호출 시 파라미터 확인
    mock_ws_repo.list_with_pagination.assert_called_once_with(limit=5, offset=3, kind=None)


@pytest.mark.asyncio
async def test_list_worksheets_kind_filter_forwarded(async_client: AsyncClient) -> None:
    """kind 필터가 repository 에 정확히 전달되는지 검증."""
    ws = _make_worksheet().model_copy(update={"items": []})

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.list_with_pagination = AsyncMock(return_value=([ws], 1))

        resp = await async_client.get("/worksheets/", params={"kind": "student"})

    assert resp.status_code == 200
    mock_ws_repo.list_with_pagination.assert_called_once_with(limit=20, offset=0, kind="student")


@pytest.mark.asyncio
async def test_list_worksheets_empty_result(async_client: AsyncClient) -> None:
    """빈 결과 — {items: [], total: 0, limit: 20, offset: 0}."""
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.list_with_pagination = AsyncMock(return_value=([], 0))

        resp = await async_client.get("/worksheets/")

    assert resp.status_code == 200
    body = resp.json()
    assert body["worksheets"] == []
    assert body["total"] == 0
    assert body["limit"] == 20
    assert body["offset"] == 0


@pytest.mark.asyncio
async def test_list_worksheets_limit_over_100_422(async_client: AsyncClient) -> None:
    """limit > 100 → 422 (Pydantic Query validation)."""
    resp = await async_client.get("/worksheets/", params={"limit": 101})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_worksheets_offset_negative_422(async_client: AsyncClient) -> None:
    """offset < 0 → 422 (Pydantic Query validation)."""
    resp = await async_client.get("/worksheets/", params={"offset": -1})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_worksheets_invalid_kind_422(async_client: AsyncClient) -> None:
    """kind 가 WorksheetKind enum 값 아님 → 422."""
    resp = await async_client.get("/worksheets/", params={"kind": "invalid_kind_xyz"})

    assert resp.status_code == 422


# ─── PATCH /worksheets/{id} 테스트 ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_worksheet_title_only_200(async_client: AsyncClient) -> None:
    """title 만 patch → 200 + 응답에 새 title 반영.

    update_meta 가 업데이트된 Worksheet 를, list_items_for_worksheet 가 items_orm 을
    반환하면 라우터는 200 + 갱신된 Worksheet (items 포함) 를 반환해야 한다.
    """
    original = _make_worksheet()
    updated = original.model_copy(update={"title": "수정된 제목"})
    item_orm = _make_item_orm()
    item_orm.id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    item_orm.include_translation = False
    item_orm.include_vocabulary = False
    item_orm.include_syntax_annotations = False
    item_orm.include_questions = False
    item_orm.include_variants = False

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.update_meta = AsyncMock(return_value=updated)
        mock_ws_repo.list_items_for_worksheet = AsyncMock(return_value=[item_orm])

        resp = await async_client.patch(
            f"/worksheets/{WORKSHEET_ID_1}",
            json={"title": "수정된 제목"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "수정된 제목"
    # items 가 포함되어야 한다
    assert len(body["items"]) == 1


@pytest.mark.asyncio
async def test_patch_worksheet_branding_200(async_client: AsyncClient) -> None:
    """branding 통째 교체 → 200."""
    new_branding = Branding(academy_name="새 학원", primary_color="#FF0000")
    updated = _make_worksheet().model_copy(update={"branding": new_branding, "items": []})

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.update_meta = AsyncMock(return_value=updated)
        mock_ws_repo.list_items_for_worksheet = AsyncMock(return_value=[])

        resp = await async_client.patch(
            f"/worksheets/{WORKSHEET_ID_1}",
            json={"branding": {"academy_name": "새 학원", "primary_color": "#FF0000"}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["branding"]["academy_name"] == "새 학원"
    assert body["branding"]["primary_color"] == "#FF0000"


@pytest.mark.asyncio
async def test_patch_worksheet_multiple_fields_200(async_client: AsyncClient) -> None:
    """여러 필드 동시 patch → 200."""
    updated = _make_worksheet().model_copy(
        update={"title": "새 제목", "subtitle": "새 부제", "grade": "고2", "items": []}
    )

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.update_meta = AsyncMock(return_value=updated)
        mock_ws_repo.list_items_for_worksheet = AsyncMock(return_value=[])

        resp = await async_client.patch(
            f"/worksheets/{WORKSHEET_ID_1}",
            json={"title": "새 제목", "subtitle": "새 부제", "grade": "고2"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "새 제목"
    assert body["subtitle"] == "새 부제"
    assert body["grade"] == "고2"


@pytest.mark.asyncio
async def test_patch_worksheet_not_found_404(async_client: AsyncClient) -> None:
    """존재하지 않는 worksheet_id → 404.

    update_meta 가 None 을 반환하면 라우터는 404 를 반환해야 한다.
    """
    unknown_id = uuid.UUID("99999999-9999-9999-9999-999999999999")

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.update_meta = AsyncMock(return_value=None)

        resp = await async_client.patch(
            f"/worksheets/{unknown_id}",
            json={"title": "없는 워크시트"},
        )

    assert resp.status_code == 404
    assert "찾을 수 없" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_patch_worksheet_cross_tenant_404(async_client: AsyncClient) -> None:
    """cross-tenant: 다른 tenant 의 worksheet_id → 404 (존재 여부 노출 방지).

    update_meta 가 tenant 필터 후 None 을 반환하면 라우터는 404 를 반환해야 한다.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.update_meta = AsyncMock(return_value=None)

        resp = await async_client.patch(
            f"/worksheets/{WORKSHEET_ID_1}",
            json={"title": "cross-tenant 시도"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_worksheet_items_key_422(async_client: AsyncClient) -> None:
    """items 키 보내면 422 — extra='forbid' (C안 정책 강제).

    WorksheetUpdateRequest.model_config = ConfigDict(extra='forbid') 이므로
    items 키가 포함된 body 는 Pydantic validation error → 422.
    """
    resp = await async_client.patch(
        f"/worksheets/{WORKSHEET_ID_1}",
        json={"title": "새 제목", "items": [{"passage_id": str(PASSAGE_ID_1), "order": 0}]},
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_worksheet_empty_body_422(async_client: AsyncClient) -> None:
    """patch body 가 비어있음 ({}) → 422.

    변경할 필드가 없는 PATCH 는 의미 없으므로 422 반환.
    """
    resp = await async_client.patch(
        f"/worksheets/{WORKSHEET_ID_1}",
        json={},
    )

    assert resp.status_code == 422
    assert "변경할 필드" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_patch_worksheet_invalid_kind_422(async_client: AsyncClient) -> None:
    """kind 가 WorksheetKind enum 값 아님 → 422 (Pydantic validation)."""
    resp = await async_client.patch(
        f"/worksheets/{WORKSHEET_ID_1}",
        json={"kind": "invalid_kind_xyz"},
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_worksheet_nonnull_field_null_422(async_client: AsyncClient) -> None:
    """W-1 회귀 — NOT NULL 메타 필드에 null 전송 → 422.

    Repository.update_meta 가 ValueError ("'title' 필드는 null 로 설정할 수 없습니다") 를
    raise 하면 라우터 try/except 가 422 로 매핑한다 (W-2). IntegrityError 500 노출 차단.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.update_meta = AsyncMock(
            side_effect=ValueError("'title' 필드는 null 로 설정할 수 없습니다 (NOT NULL).")
        )

        resp = await async_client.patch(
            f"/worksheets/{WORKSHEET_ID_1}",
            json={"title": None},
        )

    assert resp.status_code == 422
    assert "null" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_patch_worksheet_integrity_error_422(async_client: AsyncClient) -> None:
    """W-2 — Repository 가 IntegrityError raise → 라우터 422 매핑.

    DB 제약 조건 위배 (예: 이론적으로 unique constraint 추가될 경우) 도 500 대신
    422 로 매핑된다. create_worksheet 와 동일한 방어 패턴.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.update_meta = AsyncMock(
            side_effect=IntegrityError("constraint violation", None, None)
        )

        resp = await async_client.patch(
            f"/worksheets/{WORKSHEET_ID_1}",
            json={"title": "new title"},
        )

    assert resp.status_code == 422
    assert "DB 제약" in resp.json()["detail"]


# ─── DELETE /worksheets/{id} 테스트 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_worksheet_204(async_client: AsyncClient) -> None:
    """정상 삭제 → 204 no content.

    BaseRepository.delete() 가 True 를 반환하면 라우터는 204 를 반환해야 한다.
    items 는 ON DELETE CASCADE 로 자동 정리 (마이그레이션 보장).
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.delete = AsyncMock(return_value=True)

        resp = await async_client.delete(f"/worksheets/{WORKSHEET_ID_1}")

    assert resp.status_code == 204
    assert resp.content == b""


@pytest.mark.asyncio
async def test_delete_worksheet_not_found_404(async_client: AsyncClient) -> None:
    """존재하지 않는 worksheet_id → 404.

    BaseRepository.delete() 가 False 를 반환하면 라우터는 404 를 반환해야 한다.
    """
    unknown_id = uuid.UUID("99999999-9999-9999-9999-999999999999")

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.delete = AsyncMock(return_value=False)

        resp = await async_client.delete(f"/worksheets/{unknown_id}")

    assert resp.status_code == 404
    assert "찾을 수 없" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_delete_worksheet_cross_tenant_404(async_client: AsyncClient) -> None:
    """cross-tenant: 다른 tenant 의 worksheet_id → 404 (존재 여부 노출 방지).

    BaseRepository.delete() 가 tenant 필터 후 False 를 반환하면 라우터는 404.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.delete = AsyncMock(return_value=False)

        resp = await async_client.delete(f"/worksheets/{WORKSHEET_ID_1}")

    assert resp.status_code == 404


# ─── POST /worksheets/{id}/items 테스트 ──────────────────────────────────────

ITEM_ID_1 = uuid.UUID("66666666-6666-6666-6666-666666666666")
PASSAGE_ID_2 = uuid.UUID("77777777-7777-7777-7777-777777777777")


def _make_saved_item(
    item_id: uuid.UUID = ITEM_ID_1,
    passage_id: uuid.UUID = PASSAGE_ID_1,
    order: int = 0,
    label: str | None = "독해 연습",
) -> WorksheetItem:
    """테스트용 저장된 WorksheetItem (id 포함)."""
    return WorksheetItem(
        id=item_id,
        passage_id=passage_id,
        order=order,
        label=label,
    )


def _make_add_item_payload(
    passage_id: uuid.UUID = PASSAGE_ID_1,
    order: int = 1,
    label: str | None = "새 항목",
) -> dict[str, Any]:
    """POST /worksheets/{id}/items 요청 본문 헬퍼."""
    return {
        "passage_id": str(passage_id),
        "order": order,
        "label": label,
        "include_translation": False,
        "include_vocabulary": False,
        "include_syntax_annotations": False,
        "include_questions": False,
        "include_variants": False,
    }


@pytest.mark.asyncio
async def test_add_worksheet_item_ok_201(async_client: AsyncClient) -> None:
    """정상 — 201 + id 채워진 WorksheetItem 반환.

    add_item 이 WorksheetItem 을 반환하면 라우터는 201 + JSON 을 반환해야 한다.
    """
    saved_item = _make_saved_item()

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo = mock_ws_repo_cls.return_value
        mock_ws_repo.add_item = AsyncMock(return_value=saved_item)

        resp = await async_client.post(
            f"/worksheets/{WORKSHEET_ID_1}/items",
            json=_make_add_item_payload(),
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == str(ITEM_ID_1)
    assert body["passage_id"] == str(PASSAGE_ID_1)
    assert body["order"] == 0


@pytest.mark.asyncio
async def test_add_worksheet_item_worksheet_not_found_404(async_client: AsyncClient) -> None:
    """worksheet_id not found / cross-tenant → 404.

    add_item 이 None 을 반환하면 라우터는 404 를 반환해야 한다.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.add_item = AsyncMock(return_value=None)

        resp = await async_client.post(
            f"/worksheets/{WORKSHEET_ID_1}/items",
            json=_make_add_item_payload(),
        )

    assert resp.status_code == 404
    assert "찾을 수 없" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_add_worksheet_item_cross_tenant_passage_422(async_client: AsyncClient) -> None:
    """cross-tenant passage_id → 422.

    add_item 이 ValueError 를 raise 하면 라우터는 422 를 반환해야 한다.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.add_item = AsyncMock(
            side_effect=ValueError("passage_id 가 현재 tenant 소유가 아니거나 존재하지 않습니다.")
        )

        resp = await async_client.post(
            f"/worksheets/{WORKSHEET_ID_1}/items",
            json=_make_add_item_payload(),
        )

    assert resp.status_code == 422
    assert "passage_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_add_worksheet_item_duplicate_passage_422(async_client: AsyncClient) -> None:
    """중복 passage_id → 422.

    같은 worksheet 안에 이미 동일 passage_id 가 있으면 add_item 이 ValueError 를
    raise → 라우터 422 매핑.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.add_item = AsyncMock(
            side_effect=ValueError("같은 worksheet 안에 동일 passage_id 중복.")
        )

        resp = await async_client.post(
            f"/worksheets/{WORKSHEET_ID_1}/items",
            json=_make_add_item_payload(),
        )

    assert resp.status_code == 422
    assert "중복" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_add_worksheet_item_invalid_order_422(async_client: AsyncClient) -> None:
    """order < 0 → 422 (Pydantic ge=0 validation).

    WorksheetItemCreateRequest.order 의 ge=0 constraint 위반.
    """
    payload = _make_add_item_payload(order=-1)
    resp = await async_client.post(
        f"/worksheets/{WORKSHEET_ID_1}/items",
        json=payload,
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_add_worksheet_item_extra_field_422(async_client: AsyncClient) -> None:
    """extra='forbid' — 잘못된 키 포함 → 422.

    WorksheetItemCreateRequest.model_config = ConfigDict(extra='forbid').
    """
    payload = _make_add_item_payload()
    payload["unknown_field"] = "bad"
    resp = await async_client.post(
        f"/worksheets/{WORKSHEET_ID_1}/items",
        json=payload,
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_add_worksheet_item_integrity_error_422(async_client: AsyncClient) -> None:
    """W-3 — Repository 가 IntegrityError raise → 라우터 422 매핑.

    passage_id 사전 검증 후에도 race condition 등으로 INSERT 시 FK 위배가
    발생하면 500 대신 422 로 매핑한다 (create_worksheet / patch_worksheet 와
    동일한 방어 패턴).
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.add_item = AsyncMock(
            side_effect=IntegrityError("FK violation", None, None)
        )

        resp = await async_client.post(
            f"/worksheets/{WORKSHEET_ID_1}/items",
            json=_make_add_item_payload(),
        )

    assert resp.status_code == 422
    assert "DB 제약" in resp.json()["detail"] or "passage_id" in resp.json()["detail"]


# ─── PATCH /worksheets/{id}/items/{item_id} 테스트 ───────────────────────────


@pytest.mark.asyncio
async def test_patch_worksheet_item_label_only_200(async_client: AsyncClient) -> None:
    """label 만 patch → 200 + 업데이트된 WorksheetItem 반환."""
    updated_item = _make_saved_item(label="수정된 라벨")

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.update_item = AsyncMock(return_value=updated_item)

        resp = await async_client.patch(
            f"/worksheets/{WORKSHEET_ID_1}/items/{ITEM_ID_1}",
            json={"label": "수정된 라벨"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(ITEM_ID_1)
    assert body["label"] == "수정된 라벨"


@pytest.mark.asyncio
async def test_patch_worksheet_item_multiple_fields_200(async_client: AsyncClient) -> None:
    """여러 필드 동시 patch → 200."""
    updated_item = _make_saved_item(order=5, label="변경된 라벨")
    updated_item = updated_item.model_copy(
        update={"include_translation": True, "include_vocabulary": True}
    )

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.update_item = AsyncMock(return_value=updated_item)

        resp = await async_client.patch(
            f"/worksheets/{WORKSHEET_ID_1}/items/{ITEM_ID_1}",
            json={
                "order": 5,
                "label": "변경된 라벨",
                "include_translation": True,
                "include_vocabulary": True,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["order"] == 5
    assert body["label"] == "변경된 라벨"
    assert body["include_translation"] is True


@pytest.mark.asyncio
async def test_patch_worksheet_item_worksheet_not_found_404(async_client: AsyncClient) -> None:
    """worksheet not found / cross-tenant → 404.

    update_item 이 None 을 반환하면 라우터는 404 를 반환해야 한다.
    """
    unknown_ws_id = uuid.UUID("99999999-9999-9999-9999-999999999999")

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.update_item = AsyncMock(return_value=None)

        resp = await async_client.patch(
            f"/worksheets/{unknown_ws_id}/items/{ITEM_ID_1}",
            json={"label": "변경"},
        )

    assert resp.status_code == 404
    assert "찾을 수 없" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_patch_worksheet_item_not_found_404(async_client: AsyncClient) -> None:
    """item not found → 404.

    update_item 이 None 을 반환하면 (worksheet 있지만 item 없음) 라우터는 404.
    """
    unknown_item_id = uuid.UUID("88888888-8888-8888-8888-888888888888")

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.update_item = AsyncMock(return_value=None)

        resp = await async_client.patch(
            f"/worksheets/{WORKSHEET_ID_1}/items/{unknown_item_id}",
            json={"label": "변경"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_worksheet_item_passage_id_key_422(async_client: AsyncClient) -> None:
    """passage_id 키 포함 → 422 (extra='forbid' — WorksheetItemUpdateRequest).

    WorksheetItemUpdateRequest 는 passage_id 를 포함하지 않으므로 extra='forbid' 로
    Pydantic validation error → 422.
    """
    resp = await async_client.patch(
        f"/worksheets/{WORKSHEET_ID_1}/items/{ITEM_ID_1}",
        json={"passage_id": str(PASSAGE_ID_1), "order": 1},
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_worksheet_item_order_null_422(async_client: AsyncClient) -> None:
    """order: null → 422 (NOT NULL 필드 — Repository W-1 차단).

    update_item 이 ValueError ("'order' 필드는 null 로 설정할 수 없습니다") 를 raise →
    라우터 422 매핑.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.update_item = AsyncMock(
            side_effect=ValueError(
                "'order' 필드는 null 로 설정할 수 없습니다 (NOT NULL item 필드)."
            )
        )

        resp = await async_client.patch(
            f"/worksheets/{WORKSHEET_ID_1}/items/{ITEM_ID_1}",
            json={"order": None},
        )

    assert resp.status_code == 422
    assert "null" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_patch_worksheet_item_empty_body_422(async_client: AsyncClient) -> None:
    """빈 body ({}) → 422 (변경할 필드 없음).

    라우터가 빈 patch 를 거부해야 한다.
    """
    resp = await async_client.patch(
        f"/worksheets/{WORKSHEET_ID_1}/items/{ITEM_ID_1}",
        json={},
    )

    assert resp.status_code == 422
    assert "변경할 필드" in resp.json()["detail"]


# ─── DELETE /worksheets/{id}/items/{item_id} 테스트 ──────────────────────────


@pytest.mark.asyncio
async def test_delete_worksheet_item_204(async_client: AsyncClient) -> None:
    """정상 삭제 → 204 no content.

    delete_item 이 True 를 반환하면 라우터는 204 를 반환해야 한다.
    """
    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.delete_item = AsyncMock(return_value=True)

        resp = await async_client.delete(f"/worksheets/{WORKSHEET_ID_1}/items/{ITEM_ID_1}")

    assert resp.status_code == 204
    assert resp.content == b""


@pytest.mark.asyncio
async def test_delete_worksheet_item_worksheet_not_found_404(async_client: AsyncClient) -> None:
    """worksheet not found → 404.

    delete_item 이 False 를 반환하면 (worksheet 없거나 cross-tenant) 라우터는 404.
    """
    unknown_ws_id = uuid.UUID("99999999-9999-9999-9999-999999999999")

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.delete_item = AsyncMock(return_value=False)

        resp = await async_client.delete(f"/worksheets/{unknown_ws_id}/items/{ITEM_ID_1}")

    assert resp.status_code == 404
    assert "찾을 수 없" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_delete_worksheet_item_not_found_404(async_client: AsyncClient) -> None:
    """item not found → 404.

    delete_item 이 False 를 반환하면 (worksheet 있지만 item 없음) 라우터는 404.
    """
    unknown_item_id = uuid.UUID("88888888-8888-8888-8888-888888888888")

    with patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls:
        mock_ws_repo_cls.return_value.delete_item = AsyncMock(return_value=False)

        resp = await async_client.delete(f"/worksheets/{WORKSHEET_ID_1}/items/{unknown_item_id}")

    assert resp.status_code == 404


# ─── B4 — preview 컨텍스트 주입 (annotation / translation / vocabulary) ──────


def _make_annotation(
    passage_id: uuid.UUID,
    kind: AnnotationKind = AnnotationKind.HIGHLIGHT,
    start: int = 0,
    end: int = 5,
    color_index: int | None = 1,
) -> SyntaxAnnotation:
    return SyntaxAnnotation(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=passage_id,
        kind=kind,
        span=CharacterOffsetV1Span(start=start, end=end),
        color_index=color_index,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )


def _make_b4_translation(passage_id: uuid.UUID) -> Translation:
    return Translation(
        id=uuid.uuid4(),
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        passage_id=passage_id,
        text="경제는 꾸준히 성장하고 있다.",
        created_by=TranslationCreatedBy.LLM,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )


def _make_b4_vocabulary(passage_id: uuid.UUID) -> list[Vocabulary]:
    return [
        Vocabulary(
            id=uuid.uuid4(),
            tenant_id=TENANT_A,
            workspace_id=WORKSPACE_A,
            passage_id=passage_id,
            word="economy",
            headword_normalized="economy",
            pos="noun",
            meaning_ko="경제",
            level_label="수능 필수",
            selected_by=VocabularySelectedBy.LLM,
            created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
            updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        ),
    ]


@pytest.mark.asyncio
async def test_preview_renders_annotations(async_client: AsyncClient) -> None:
    """annotation 이 있으면 ADR-0014 정밀 렌더 — annot-highlight class 가 HTML 에 등장."""
    worksheet = _make_worksheet()
    passage = _make_passage()
    item_orm = _make_item_orm()
    annotation = _make_annotation(
        passage.id, kind=AnnotationKind.HIGHLIGHT, start=4, end=11, color_index=1
    )

    with (
        patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls,
        patch("worksheet_api.routers.worksheets.PassageRepository") as mock_passage_repo_cls,
        patch("worksheet_api.routers.worksheets.SyntaxAnnotationRepository") as mock_ann_repo_cls,
        patch("worksheet_api.routers.worksheets.TranslationRepository") as mock_trans_repo_cls,
        patch("worksheet_api.routers.worksheets.VocabularyRepository") as mock_vocab_repo_cls,
    ):
        mock_ws_repo_cls.return_value.get = AsyncMock(return_value=worksheet)
        mock_ws_repo_cls.return_value.list_items_for_worksheet = AsyncMock(return_value=[item_orm])
        mock_passage_repo_cls.return_value.get = AsyncMock(return_value=passage)
        mock_ann_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[annotation])
        mock_trans_repo_cls.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_vocab_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])

        resp = await async_client.get(
            f"/worksheets/{WORKSHEET_ID_1}/preview", params={"style": "playful"}
        )

    assert resp.status_code == 200
    body = resp.text
    # ADR-0014 D2 — highlight color_index 1 → CSS class
    assert "annot-highlight--1" in body


@pytest.mark.asyncio
async def test_preview_includes_translation_when_flag_true(
    async_client: AsyncClient,
) -> None:
    """include_translation=True 면 translation block 이 컨텍스트에 주입."""
    worksheet = _make_worksheet()
    passage = _make_passage()
    item_orm = _make_item_orm()
    item_orm.include_translation = True
    item_orm.include_vocabulary = False
    translation = _make_b4_translation(passage.id)

    with (
        patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls,
        patch("worksheet_api.routers.worksheets.PassageRepository") as mock_passage_repo_cls,
        patch("worksheet_api.routers.worksheets.SyntaxAnnotationRepository") as mock_ann_repo_cls,
        patch("worksheet_api.routers.worksheets.TranslationRepository") as mock_trans_repo_cls,
        patch("worksheet_api.routers.worksheets.VocabularyRepository") as mock_vocab_repo_cls,
    ):
        mock_ws_repo_cls.return_value.get = AsyncMock(return_value=worksheet)
        mock_ws_repo_cls.return_value.list_items_for_worksheet = AsyncMock(return_value=[item_orm])
        mock_passage_repo_cls.return_value.get = AsyncMock(return_value=passage)
        mock_ann_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
        mock_trans_repo_cls.return_value.get_by_passage = AsyncMock(return_value=translation)
        mock_vocab_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])

        resp = await async_client.get(
            f"/worksheets/{WORKSHEET_ID_1}/preview", params={"style": "playful"}
        )

    assert resp.status_code == 200
    body = resp.text
    # 한글 해석 헤딩 + text 가 본문에 포함
    assert "한글 해석" in body
    assert translation.text in body
    # repository.get_by_passage 가 호출됨 (include_translation=True)
    mock_trans_repo_cls.return_value.get_by_passage.assert_awaited_once_with(passage.id)


@pytest.mark.asyncio
async def test_preview_skips_translation_when_flag_false(
    async_client: AsyncClient,
) -> None:
    """include_translation=False (default) → translation 조회 자체 X (비용 회피)."""
    worksheet = _make_worksheet()
    passage = _make_passage()
    item_orm = _make_item_orm()
    item_orm.include_translation = False
    item_orm.include_vocabulary = False

    with (
        patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls,
        patch("worksheet_api.routers.worksheets.PassageRepository") as mock_passage_repo_cls,
        patch("worksheet_api.routers.worksheets.SyntaxAnnotationRepository") as mock_ann_repo_cls,
        patch("worksheet_api.routers.worksheets.TranslationRepository") as mock_trans_repo_cls,
        patch("worksheet_api.routers.worksheets.VocabularyRepository") as mock_vocab_repo_cls,
    ):
        mock_ws_repo_cls.return_value.get = AsyncMock(return_value=worksheet)
        mock_ws_repo_cls.return_value.list_items_for_worksheet = AsyncMock(return_value=[item_orm])
        mock_passage_repo_cls.return_value.get = AsyncMock(return_value=passage)
        mock_ann_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
        mock_trans_repo_cls.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_vocab_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])

        resp = await async_client.get(
            f"/worksheets/{WORKSHEET_ID_1}/preview", params={"style": "playful"}
        )

    assert resp.status_code == 200
    body = resp.text
    assert "한글 해석" not in body
    # 비용 회피 — translation 조회 안 함
    mock_trans_repo_cls.return_value.get_by_passage.assert_not_awaited()


@pytest.mark.asyncio
async def test_preview_includes_vocabulary_when_flag_true(
    async_client: AsyncClient,
) -> None:
    """include_vocabulary=True → 어휘 박스 렌더."""
    worksheet = _make_worksheet()
    passage = _make_passage()
    item_orm = _make_item_orm()
    item_orm.include_translation = False
    item_orm.include_vocabulary = True
    vocabulary = _make_b4_vocabulary(passage.id)

    with (
        patch("worksheet_api.routers.worksheets.WorksheetRepository") as mock_ws_repo_cls,
        patch("worksheet_api.routers.worksheets.PassageRepository") as mock_passage_repo_cls,
        patch("worksheet_api.routers.worksheets.SyntaxAnnotationRepository") as mock_ann_repo_cls,
        patch("worksheet_api.routers.worksheets.TranslationRepository") as mock_trans_repo_cls,
        patch("worksheet_api.routers.worksheets.VocabularyRepository") as mock_vocab_repo_cls,
    ):
        mock_ws_repo_cls.return_value.get = AsyncMock(return_value=worksheet)
        mock_ws_repo_cls.return_value.list_items_for_worksheet = AsyncMock(return_value=[item_orm])
        mock_passage_repo_cls.return_value.get = AsyncMock(return_value=passage)
        mock_ann_repo_cls.return_value.list_by_passage = AsyncMock(return_value=[])
        mock_trans_repo_cls.return_value.get_by_passage = AsyncMock(return_value=None)
        mock_vocab_repo_cls.return_value.list_by_passage = AsyncMock(return_value=vocabulary)

        resp = await async_client.get(
            f"/worksheets/{WORKSHEET_ID_1}/preview", params={"style": "playful"}
        )

    assert resp.status_code == 200
    body = resp.text
    # 어휘 헤딩 + word + meaning_ko + 표 헤더 (v0.2-α: 표 형태 + 큰 박스 밖 분리).
    # level_label 은 v0.2-γ Vocabulary schema 확장 (synonyms/antonyms/example_sentences)
    # 진입 전까지 표 컬럼에 포함 안 됨.
    assert "어휘" in body
    assert "economy" in body
    assert "경제" in body
    # 표 헤더 — v0.2-α 어휘 표 변환 확인.
    assert "단어 (품사)" in body
    assert "한글 뜻" in body
    mock_vocab_repo_cls.return_value.list_by_passage.assert_awaited_once_with(passage.id)
