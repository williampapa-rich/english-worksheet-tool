"""POST /passages/{id}/annotations 라우터 단위 테스트.

mock session + mock repository 로 실제 DB 없이 실행한다.
커버 케이스 (3개):
  - 정상 POST — replace-all 성공 → 200 + 결과 리스트 반환 (id 포함)
  - 404 — 존재하지 않는 passage_id
  - 422 — sentinel UUID 차단 (tenant_id 또는 workspace_id 가 sentinel)
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from worksheet_api.db import get_db
from worksheet_api.main import app
from worksheet_api.models.base import SENTINEL_UUID
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context

from shared.schemas.annotation import (
    AnnotationKind,
    CharacterOffsetV1Span,
    SyntaxAnnotation,
)

# ─── 테스트용 고정 UUID ──────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
PASSAGE_ID_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
ANN_ID_1 = uuid.UUID("55555555-5555-5555-5555-555555555555")


# ─── 헬퍼 팩토리 ────────────────────────────────────────────────────────────


def _make_annotation(
    ann_id: uuid.UUID = ANN_ID_1,
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
    passage_id: uuid.UUID = PASSAGE_ID_1,
) -> SyntaxAnnotation:
    """저장 완료된 SyntaxAnnotation 시뮬레이션 (DB 부여 id 포함)."""
    return SyntaxAnnotation(
        id=ann_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        passage_id=passage_id,
        kind=AnnotationKind.HIGHLIGHT,
        span=CharacterOffsetV1Span(start=0, end=5),
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )


def _ann_request_body() -> dict[str, Any]:
    """POST body — 에디터에서 전달되는 형태 (id 없음, sentinel 없음)."""
    return {
        "annotations": [
            {
                "tenant_id": str(TENANT_A),
                "workspace_id": str(WORKSPACE_A),
                "passage_id": str(PASSAGE_ID_1),
                "kind": "highlight",
                "span": {
                    "span_format": "character_offset_v1",
                    "start": 0,
                    "end": 5,
                },
            }
        ]
    }


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


# ─── POST /passages/{id}/annotations 테스트 ─────────────────────────────────


@pytest.mark.asyncio
async def test_replace_annotations_ok(async_client: AsyncClient) -> None:
    """정상 POST → 200, 저장된 annotation 리스트 (id 포함) 반환."""
    saved_ann = _make_annotation()

    with (
        patch("worksheet_api.routers.annotations.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.annotations.SyntaxAnnotationRepository") as mock_arepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=object())  # passage 존재
        mock_arepo.return_value.replace_all = AsyncMock(return_value=[saved_ann])

        resp = await async_client.post(
            f"/passages/{PASSAGE_ID_1}/annotations",
            json=_ann_request_body(),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["annotations"]) == 1
    assert body["annotations"][0]["id"] == str(ANN_ID_1)
    assert body["annotations"][0]["kind"] == "highlight"


@pytest.mark.asyncio
async def test_replace_annotations_passage_not_found_404(async_client: AsyncClient) -> None:
    """존재하지 않는 passage_id → 404."""
    unknown_id = uuid.UUID("99999999-9999-9999-9999-999999999999")

    with patch("worksheet_api.routers.annotations.PassageRepository") as mock_prepo:
        mock_prepo.return_value.get = AsyncMock(return_value=None)

        resp = await async_client.post(
            f"/passages/{unknown_id}/annotations",
            json={"annotations": []},
        )

    assert resp.status_code == 404
    assert "찾을 수 없" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_replace_annotations_sentinel_uuid_422(async_client: AsyncClient) -> None:
    """sentinel UUID 가 포함된 annotation body → 422 차단.

    replace_all 이 sentinel UUID 를 감지해 ValueError 를 raise 하면
    라우터가 422 로 변환한다.
    """
    with (
        patch("worksheet_api.routers.annotations.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.annotations.SyntaxAnnotationRepository") as mock_arepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=object())  # passage 존재
        mock_arepo.return_value.replace_all = AsyncMock(
            side_effect=ValueError(f"sentinel UUID 감지: {SENTINEL_UUID}")
        )

        # sentinel UUID 가 tenant_id 로 포함된 body
        body = {
            "annotations": [
                {
                    "tenant_id": str(SENTINEL_UUID),
                    "workspace_id": str(WORKSPACE_A),
                    "passage_id": str(PASSAGE_ID_1),
                    "kind": "highlight",
                    "span": {
                        "span_format": "character_offset_v1",
                        "start": 0,
                        "end": 5,
                    },
                }
            ]
        }

        resp = await async_client.post(
            f"/passages/{PASSAGE_ID_1}/annotations",
            json=body,
        )

    assert resp.status_code == 422
    assert "sentinel" in resp.json()["detail"].lower()
