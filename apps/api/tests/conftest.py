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
import uuid
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

# packages/*/src 경로 추가 — extractor, llm 등 내부 패키지 import 가 worksheet_api.main 에서 필요
# 각 패키지는 packages/<name>/src/<name>/ 구조 (uv workspace src-layout)
for _pkg_src in (_workspace_root / "packages").glob("*/src"):
    if str(_pkg_src) not in sys.path:
        sys.path.insert(0, str(_pkg_src))

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

    Schema 생성: 운영과 동일하게 Alembic 마이그레이션으로 생성 (test_migrations.py
    와 같은 패턴). ``worksheet_api.models`` import 부수 효과로 Base.metadata 의
    tenants / workspaces 가 SQLModel.metadata 에 attach 되어 cross-metadata FK 가
    해소된다.

    Python 3.14 호환: ``asyncio.get_event_loop()`` 는 running loop 없으면 RuntimeError.
    fixture 단위 ``new_event_loop()`` 로 명시적 loop 관리.
    """
    import asyncio

    from alembic import command
    from alembic.config import Config
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _get_test_db_url()
    if "sqlite" in url:
        pytest.skip("통합 테스트는 PostgreSQL 전용 (JSONB 컬럼)")

    # Alembic 으로 schema 생성 (동기 — psycopg2 드라이버 사용)
    api_root = Path(__file__).parent.parent
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    # env.py 가 DATABASE_URL 환경변수를 우선시하므로 그대로 사용
    command.upgrade(cfg, "head")

    # async engine 은 테스트가 사용
    loop = asyncio.new_event_loop()
    engine = create_async_engine(url, echo=False)

    yield engine

    loop.run_until_complete(engine.dispose())
    loop.close()
    # schema 는 다음 세션을 위해 downgrade — DB 깨끗하게
    command.downgrade(cfg, "base")


# 통합 테스트 표준 테넌트 / 워크스페이스 UUID — 각 테스트 파일이 동일 값 사용.
# pg_session 픽스처가 매 테스트 시작 시 이 UUID 들을 tenants / workspaces 에 시드.
TEST_TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEST_WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TEST_TENANT_B = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
TEST_WORKSPACE_B = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


@pytest.fixture
async def pg_session(pg_engine):  # type: ignore[return]
    """테스트별 async session — 종료 시 rollback 으로 격리.

    ADR-0005 §D-5.7 의 transaction rollback 기반 격리 패턴.

    Repository 테스트가 TENANT_A / TENANT_B 의 데이터를 만들 수 있도록, 매 테스트
    시작 시 tenants / workspaces 행을 시드한다. rollback 으로 자동 정리됨.
    """
    from sqlmodel.ext.asyncio.session import AsyncSession
    from worksheet_api.models.tenant import Tenant, Workspace

    async with AsyncSession(pg_engine) as session:
        async with session.begin():
            # 표준 테스트 테넌트 / 워크스페이스 시드
            session.add(Tenant(id=TEST_TENANT_A, name="test-tenant-a"))
            session.add(Tenant(id=TEST_TENANT_B, name="test-tenant-b"))
            await session.flush()
            session.add(Workspace(id=TEST_WORKSPACE_A, tenant_id=TEST_TENANT_A, name="ws-a"))
            session.add(Workspace(id=TEST_WORKSPACE_B, tenant_id=TEST_TENANT_B, name="ws-b"))
            await session.flush()

            yield session
            await session.rollback()
