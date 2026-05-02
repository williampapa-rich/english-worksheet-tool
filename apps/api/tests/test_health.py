"""헬스체크 엔드포인트 테스트.

httpx + ASGITransport 를 사용해 실제 HTTP 서버 없이 인-프로세스로 테스트한다.
DB 세션은 Mock으로 대체해 단위 테스트 수준에서 빠르게 실행한다.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from worksheet_api.db import get_db
from worksheet_api.main import app


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """DB 세션 Mock — SELECT 1이 성공하는 정상 케이스."""
    session = AsyncMock(spec=AsyncSession)
    # execute()는 결과 객체를 반환하면 충분 (실제 row 불필요)
    session.execute.return_value = MagicMock()
    return session


@pytest.fixture
def mock_db_session_unreachable() -> AsyncMock:
    """DB 세션 Mock — execute()가 예외를 던지는 연결 불가 케이스."""
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = Exception("DB 연결 실패")
    return session


@pytest.fixture
def override_get_db(mock_db_session: AsyncMock) -> AsyncGenerator[AsyncSession, None]:
    """정상 DB 세션을 주입하는 의존성 오버라이드."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db_session

    return _override  # type: ignore[return-value]


@pytest.fixture
def override_get_db_unreachable(
    mock_db_session_unreachable: AsyncMock,
) -> AsyncGenerator[AsyncSession, None]:
    """연결 불가 DB 세션을 주입하는 의존성 오버라이드."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db_session_unreachable

    return _override  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_health_returns_200_ok(override_get_db: AsyncGenerator[AsyncSession, None]) -> None:
    """정상 케이스: /health → 200 OK, status=ok, db=ok."""
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


@pytest.mark.asyncio
async def test_health_db_unreachable(
    override_get_db_unreachable: AsyncGenerator[AsyncSession, None],
) -> None:
    """DB 연결 불가 케이스: status=ok이지만 db=unreachable."""
    app.dependency_overrides[get_db] = override_get_db_unreachable

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "unreachable"


@pytest.mark.asyncio
async def test_health_response_schema(
    override_get_db: AsyncGenerator[AsyncSession, None],
) -> None:
    """응답 JSON이 HealthResponse 스키마와 일치하는지 검증."""
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    app.dependency_overrides.clear()

    body = response.json()
    assert set(body.keys()) == {"status", "db"}
