"""pytest 전역 설정.

테스트 환경에서는 실제 DB 없이 동작해야 하므로:
1. DATABASE_URL을 더미 값으로 설정 (실제 연결하지 않음 — get_db는 Mock으로 대체)
2. get_settings() 캐시를 초기화해 테스트 환경변수가 적용되도록 함
"""

import os
import sys
from pathlib import Path

# apps/api/src를 경로에 추가 (uv workspace가 설치되지 않은 환경 대비)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# pydantic-settings가 로드되기 전에 환경변수를 설정해야 한다
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test_db",
)
os.environ.setdefault("MVP_TENANT_ID", "00000000-0000-0000-0000-000000000001")

# get_settings() 캐시 초기화 (다른 테스트가 캐시를 오염시키지 않도록)
import pytest


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    """각 테스트 전후로 settings 캐시를 초기화한다."""
    from worksheet_api.config import get_settings

    get_settings.cache_clear()
    yield  # type: ignore[misc]
    get_settings.cache_clear()
