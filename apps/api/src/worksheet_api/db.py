"""SQLAlchemy 2.x async 엔진 + 세션 팩토리.

Alembic env.py와 이 모듈이 동일한 engine URL과 metadata를 공유한다.
FastAPI 라우터에서는 get_db() 의존성을 통해 세션을 주입받는다.

엔진은 첫 get_db() 호출 시 lazy하게 생성된다.
이렇게 하면 테스트에서 DATABASE_URL 없이도 모듈을 import할 수 있다.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 ORM 모델의 공통 베이스 클래스.

    NOTE: 이 모델들은 architect 작업 #5 (shared/schemas/ v0.1) 완료 후
    Pydantic 모델과 연결되는 placeholder다. 현재는 Tenant/Workspace만 정의.
    """


# 엔진/세션팩토리는 처음 사용 시 초기화 (lazy init)
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    """엔진 싱글턴 — 첫 호출 시 생성."""
    global _engine
    if _engine is None:
        from worksheet_api.config import get_settings

        cfg = get_settings()
        _engine = create_async_engine(
            str(cfg.database_url),
            echo=cfg.debug,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """세션 팩토리 싱글턴 — 첫 호출 시 생성.

    expire_on_commit=False: 커밋 후에도 인스턴스 속성을 lazy load 없이 사용하기 위함
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends에서 사용하는 DB 세션 의존성.

    Usage:
        @router.get("/")
        async def handler(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = _get_session_factory()
    async with factory() as session:
        yield session
