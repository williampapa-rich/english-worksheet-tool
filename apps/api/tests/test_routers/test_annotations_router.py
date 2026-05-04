"""POST /passages/{id}/annotations 라우터 단위 테스트.

mock session + mock repository 로 실제 DB 없이 실행한다.
커버 케이스:
  - 정상 POST — replace-all 성공 → 200 + 결과 리스트 반환 (id 포함)
  - 404 — 존재하지 않는 passage_id
  - 422 — sentinel UUID 차단 (replace_all 이 raise 하면 라우터가 422 로 변환)
  - tenant_id / workspace_id / passage_id 없이 전송해도 400/422 아님 (입력 DTO 적용)
  - annotation_id 포함 전송 → 정상 처리 (옵션 A 영속화)

P1-annotation-input-dto:
  클라이언트는 SyntaxAnnotationInput (tenant_id / workspace_id / passage_id 없음) 를 보낸다.
  라우터가 TenantContext + path param 으로 주입해 SyntaxAnnotation 으로 변환.
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
CHIP_ID_1 = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


# ─── 헬퍼 팩토리 ────────────────────────────────────────────────────────────


def _make_annotation(
    ann_id: uuid.UUID = ANN_ID_1,
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
    passage_id: uuid.UUID = PASSAGE_ID_1,
    annotation_id: uuid.UUID | None = None,
) -> SyntaxAnnotation:
    """저장 완료된 SyntaxAnnotation 시뮬레이션 (DB 부여 id 포함)."""
    return SyntaxAnnotation(
        id=ann_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        passage_id=passage_id,
        kind=AnnotationKind.HIGHLIGHT,
        span=CharacterOffsetV1Span(start=0, end=5),
        annotation_id=annotation_id,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )


def _ann_input_body_minimal() -> dict[str, Any]:
    """POST body — SyntaxAnnotationInput 최소 형태.

    P1-annotation-input-dto: tenant_id / workspace_id / passage_id 없음.
    """
    return {
        "annotations": [
            {
                "kind": "highlight",
                "span": {
                    "span_format": "character_offset_v1",
                    "start": 0,
                    "end": 5,
                },
            }
        ]
    }


def _ann_input_body_with_annotation_id() -> dict[str, Any]:
    """POST body — annotation_id 포함 (에디터 chip ID)."""
    return {
        "annotations": [
            {
                "kind": "highlight",
                "span": {
                    "span_format": "character_offset_v1",
                    "start": 0,
                    "end": 5,
                },
                "annotation_id": str(CHIP_ID_1),
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
            json=_ann_input_body_minimal(),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["annotations"]) == 1
    assert body["annotations"][0]["id"] == str(ANN_ID_1)
    assert body["annotations"][0]["kind"] == "highlight"


@pytest.mark.asyncio
async def test_replace_annotations_no_context_fields_required(async_client: AsyncClient) -> None:
    """P1-annotation-input-dto: tenant_id / workspace_id / passage_id 없이도 400/422 아님.

    SyntaxAnnotationInput DTO 가 이 필드들을 요구하지 않으므로
    최소 입력 (kind + span 만) 으로도 정상 처리돼야 한다.
    """
    saved_ann = _make_annotation()

    with (
        patch("worksheet_api.routers.annotations.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.annotations.SyntaxAnnotationRepository") as mock_arepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=object())
        mock_arepo.return_value.replace_all = AsyncMock(return_value=[saved_ann])

        resp = await async_client.post(
            f"/passages/{PASSAGE_ID_1}/annotations",
            json=_ann_input_body_minimal(),
        )

    # 400/422 가 아닌 200 이어야 함
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_replace_annotations_annotation_id_accepted(async_client: AsyncClient) -> None:
    """annotation_id 포함 전송 → 정상 처리 (extra="forbid" 로 거부되지 않음).

    P1-annotation-input-dto 이전엔 extra="forbid" (SyntaxAnnotation) 에서 422 가 났다.
    SyntaxAnnotationInput 은 annotation_id 를 1급 필드로 허용하므로 200 이어야 한다.
    """
    saved_ann = _make_annotation(annotation_id=CHIP_ID_1)

    with (
        patch("worksheet_api.routers.annotations.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.annotations.SyntaxAnnotationRepository") as mock_arepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=object())
        mock_arepo.return_value.replace_all = AsyncMock(return_value=[saved_ann])

        resp = await async_client.post(
            f"/passages/{PASSAGE_ID_1}/annotations",
            json=_ann_input_body_with_annotation_id(),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["annotations"]) == 1
    # 반환된 annotation 에도 annotation_id 가 포함돼야 한다
    assert body["annotations"][0]["annotation_id"] == str(CHIP_ID_1)


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
    """sentinel UUID 차단 → 422.

    replace_all 이 sentinel UUID 를 감지해 ValueError 를 raise 하면
    라우터가 422 로 변환한다. (sentinel 은 repository 레이어에서 잡힘)
    """
    with (
        patch("worksheet_api.routers.annotations.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.annotations.SyntaxAnnotationRepository") as mock_arepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=object())  # passage 존재
        mock_arepo.return_value.replace_all = AsyncMock(
            side_effect=ValueError(f"sentinel UUID 감지: {SENTINEL_UUID}")
        )

        resp = await async_client.post(
            f"/passages/{PASSAGE_ID_1}/annotations",
            json=_ann_input_body_minimal(),
        )

    assert resp.status_code == 422
    assert "sentinel" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_replace_annotations_extra_field_forbidden(async_client: AsyncClient) -> None:
    """SyntaxAnnotationInput extra="forbid" — 미지정 필드 전송 시 422.

    annotation_id 는 허용 (1급 필드), 하지만 unknown_field 같은 임의 필드는 거부.
    """
    body_with_extra = {
        "annotations": [
            {
                "kind": "highlight",
                "span": {
                    "span_format": "character_offset_v1",
                    "start": 0,
                    "end": 5,
                },
                "unknown_field": "should_be_rejected",
            }
        ]
    }

    with patch("worksheet_api.routers.annotations.PassageRepository") as mock_prepo:
        mock_prepo.return_value.get = AsyncMock(return_value=object())

        resp = await async_client.post(
            f"/passages/{PASSAGE_ID_1}/annotations",
            json=body_with_extra,
        )

    assert resp.status_code == 422
