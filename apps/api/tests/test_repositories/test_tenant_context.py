"""TenantContext + get_tenant_context Depends 단위 테스트.

환경변수 stub 동작과 유효하지 않은 UUID 에러 처리를 검증한다.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context


class TestTenantContext:
    """TenantContext Pydantic 모델 단위 테스트."""

    def test_frozen_model_cannot_be_mutated(self) -> None:
        """frozen=True 로 인스턴스 생성 후 필드 변경 시 에러."""
        ctx = TenantContext(
            tenant_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
        )
        with pytest.raises((ValidationError, TypeError)):
            ctx.tenant_id = uuid.uuid4()  # type: ignore[misc]

    def test_user_id_optional_default_none(self) -> None:
        """user_id 는 기본값 None."""
        ctx = TenantContext(
            tenant_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
        )
        assert ctx.user_id is None

    def test_user_id_can_be_set(self) -> None:
        """user_id 를 명시적으로 설정 가능 (Phase 4 OAuth 준비)."""
        uid = uuid.uuid4()
        ctx = TenantContext(
            tenant_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            user_id=uid,
        )
        assert ctx.user_id == uid


class TestGetTenantContext:
    """get_tenant_context Depends stub 단위 테스트."""

    @pytest.mark.asyncio
    async def test_returns_context_from_env(self) -> None:
        """환경변수에서 TenantContext 반환 (ADR-0009 — user_id 도 stub 주입)."""
        tenant_id = "00000000-0000-0000-0000-000000000001"
        workspace_id = "00000000-0000-0000-0000-000000000002"
        user_id = "00000000-0000-0000-0000-000000000003"

        with patch.dict(
            os.environ,
            {
                "MVP_TENANT_ID": tenant_id,
                "MVP_WORKSPACE_ID": workspace_id,
                "MVP_USER_ID": user_id,
            },
        ):
            # get_settings 캐시 무효화
            from worksheet_api.config import get_settings

            get_settings.cache_clear()

            ctx = await get_tenant_context()

            assert ctx.tenant_id == uuid.UUID(tenant_id)
            assert ctx.workspace_id == uuid.UUID(workspace_id)
            # ADR-0009: user_id 는 이제 MVP_USER_ID env 에서 자동 주입 — backward
            # compatibility 유지 (기존 라우터 / repository 가 user_id 무시).
            assert ctx.user_id == uuid.UUID(user_id)

            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_invalid_user_id_raises_value_error(self) -> None:
        """MVP_USER_ID 가 유효하지 않은 UUID 형식이면 ValueError (ADR-0009)."""
        with patch.dict(
            os.environ,
            {
                "MVP_TENANT_ID": "00000000-0000-0000-0000-000000000001",
                "MVP_WORKSPACE_ID": "00000000-0000-0000-0000-000000000002",
                "MVP_USER_ID": "not-a-uuid",
            },
        ):
            from worksheet_api.config import get_settings

            get_settings.cache_clear()

            with pytest.raises(ValueError, match="MVP_USER_ID"):
                await get_tenant_context()

            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_invalid_tenant_id_raises_value_error(self) -> None:
        """MVP_TENANT_ID 가 유효하지 않은 UUID 형식이면 ValueError."""
        with patch.dict(
            os.environ,
            {
                "MVP_TENANT_ID": "not-a-uuid",
                "MVP_WORKSPACE_ID": "00000000-0000-0000-0000-000000000002",
            },
        ):
            from worksheet_api.config import get_settings

            get_settings.cache_clear()

            with pytest.raises(ValueError, match="MVP_TENANT_ID"):
                await get_tenant_context()

            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_invalid_workspace_id_raises_value_error(self) -> None:
        """MVP_WORKSPACE_ID 가 유효하지 않은 UUID 형식이면 ValueError."""
        with patch.dict(
            os.environ,
            {
                "MVP_TENANT_ID": "00000000-0000-0000-0000-000000000001",
                "MVP_WORKSPACE_ID": "not-a-uuid",
            },
        ):
            from worksheet_api.config import get_settings

            get_settings.cache_clear()

            with pytest.raises(ValueError, match="MVP_WORKSPACE_ID"):
                await get_tenant_context()

            get_settings.cache_clear()
