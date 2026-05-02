"""pytest 전역 설정.

테스트 환경에서는 실제 DB 없이 동작해야 하므로:
1. DATABASE_URL을 더미 값으로 설정 (실제 연결하지 않음 — get_db는 Mock으로 대체)
2. get_settings() 캐시를 초기화해 테스트 환경변수가 적용되도록 함

통합 테스트 (pytest -m integration):
  pg_session 픽스처가 Docker compose PostgreSQL 에 연결한다.
  TEST_DATABASE_URL 또는 DATABASE_URL 환경변수가 필요.
  트랜잭션 rollback 기반 격리 (ADR-0005 §D-5.7).
"""

import os
import sys
from pathlib import Path

import pytest

# apps/api/src 를 경로에 추가 (uv workspace 가 설치되지 않은 환경 대비)
_api_src = Path(__file__).parent.parent / "src"
if str(_api_src) not in sys.path:
    sys.path.insert(0, str(_api_src))

# shared 패키지 경로 추가 (uv workspace editable install 이 안 된 환경 대비)
# shared/__init__.py 가 workspace root 아래에 있으므로 workspace root 를 sys.path 에 추가
_workspace_root = Path(__file__).parent.parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

# pydantic-settings가 로드되기 전에 환경변수를 설정해야 한다
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test_db",
)
os.environ.setdefault("MVP_TENANT_ID", "00000000-0000-0000-0000-000000000001")
os.environ.setdefault("MVP_WORKSPACE_ID", "00000000-0000-0000-0000-000000000002")


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    """각 테스트 전후로 settings 캐시를 초기화한다."""
    from worksheet_api.config import get_settings

    get_settings.cache_clear()
    yield  # type: ignore[misc]
    get_settings.cache_clear()


# ─── 통합 테스트 픽스처 (PostgreSQL) ─────────────────────────────────────────


def _get_test_db_url() -> str:
    """테스트용 DATABASE_URL 을 환경변수에서 가져온다."""
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL 환경변수가 없어 통합 테스트 건너뜀")
    return url  # type: ignore[return-value]


@pytest.fixture(scope="session")
def pg_engine():  # type: ignore[return]
    """세션 레벨 PostgreSQL async engine.

    ADR-0005 §D-5.7: Docker compose PostgreSQL 에 연결.
    세션 레벨로 생성해 연결 오버헤드를 줄인다.
    """
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import SQLModel

    url = _get_test_db_url()
    if "sqlite" in url:
        pytest.skip("통합 테스트는 PostgreSQL 전용 (JSONB 컬럼)")

    engine = create_async_engine(url, echo=False)

    async def _setup() -> None:
        import worksheet_api.models  # noqa: F401 — SQLModel.metadata 등록

        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    asyncio.get_event_loop().run_until_complete(_setup())

    yield engine

    async def _teardown() -> None:
        await engine.dispose()

    asyncio.get_event_loop().run_until_complete(_teardown())


@pytest.fixture
async def pg_session(pg_engine):  # type: ignore[return]
    """테스트별 async session — 종료 시 rollback 으로 격리.

    ADR-0005 §D-5.7 의 transaction rollback 기반 격리 패턴.
    """
    from sqlmodel.ext.asyncio.session import AsyncSession

    async with AsyncSession(pg_engine) as session:
        async with session.begin():
            yield session
            await session.rollback()
