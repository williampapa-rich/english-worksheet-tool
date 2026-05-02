"""Alembic 마이그레이션 환경 설정.

async 엔진을 사용하며, DATABASE_URL을 환경변수에서 로드한다.
autogenerate가 모든 ORM 모델을 감지하려면 이 파일에서 모델 패키지를 import해야 한다.
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# apps/api/src를 Python 경로에 추가 (alembic 실행 위치가 apps/api/이므로)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ORM 모델 import — 반드시 Base.metadata보다 먼저 import해야 autogenerate 작동
import worksheet_api.models  # noqa: F401
from worksheet_api.db import Base

# alembic.ini의 logging 설정 적용
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate 대상 메타데이터
target_metadata = Base.metadata


def get_url() -> str:
    """환경변수에서 DB URL을 가져온다.

    alembic.ini의 sqlalchemy.url보다 환경변수를 우선시해
    시크릿이 설정 파일에 들어가지 않도록 한다.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError(
            "DATABASE_URL 환경변수가 설정되지 않았습니다. "
            ".env 파일을 확인하거나 환경변수를 설정하세요."
        )
    return url


def run_migrations_offline() -> None:
    """오프라인 모드: SQL 스크립트만 생성하고 실제 DB 연결은 하지 않는다."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """실제 마이그레이션 실행 (sync 컨텍스트)."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """async 엔진으로 마이그레이션을 실행한다.

    NullPool을 사용하는 이유: 마이그레이션은 일회성 실행이므로
    커넥션 풀이 필요 없다. 마이그레이션 후 연결이 즉시 닫힌다.
    """
    engine = create_async_engine(get_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    """온라인 모드: 실제 DB에 연결해 마이그레이션을 실행한다."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
