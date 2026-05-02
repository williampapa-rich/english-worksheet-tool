"""DbUsageSink 통합 테스트 — 실제 PostgreSQL 사용.

pytest.mark.integration 으로 마킹. 실행 시 Docker compose 가 필요:
  pytest -m integration apps/api/tests/test_llm_db_sink_integration.py

테스트 범위:
  1. DbUsageSink 가 실제 llm_usage_logs 테이블에 row insert.
  2. tenant_id=None 인 시스템 호출 케이스 (PM-4 nullable 허용).
  3. MultiplexUsageSink (jsonl + db) 동시 기록 검증.

주의: 이 파일은 로컬 실행 전용 — CI 에서는 integration mark 를 skip 해도 됨.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from llm.sinks import DbUsageSink, JsonlUsageSink, MultiplexUsageSink
from llm.sinks.base import UsageEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


# ─── 헬퍼 ───────────────────────────────────────────────────────────────────


def _make_event(**kwargs) -> UsageEvent:  # type: ignore[no-untyped-def]
    """테스트용 UsageEvent 생성 헬퍼."""
    defaults = {
        "request_id": uuid4(),
        "model": "claude-test-integration",
        "purpose": "integration_test",
        "input_tokens": 150,
        "output_tokens": 75,
        "latency_ms": 420,
        "status": "success",
        "created_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return UsageEvent(**defaults)


def _make_session_factory(session: AsyncSession) -> async_sessionmaker:  # type: ignore[return]
    """테스트용 session 을 반환하는 factory.

    실제 pg_session 을 래핑해 begin() / add() 호출을 실제 DB 에 반영.
    """

    @asynccontextmanager
    async def _factory():  # type: ignore[return]
        yield session

    return _factory  # type: ignore[return-value]


# ─── 통합 테스트 ──────────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_db_sink_inserts_row(pg_session: AsyncSession) -> None:
    """DbUsageSink.record() 가 llm_usage_logs 테이블에 실제 row 를 insert 한다."""
    from worksheet_api.models.llm_usage_log import LlmUsageLogORM

    event = _make_event(purpose="db_sink_insert_test")
    factory = _make_session_factory(pg_session)

    sink = DbUsageSink(session_factory=factory, log_orm_class=LlmUsageLogORM)
    await sink.record(event)
    await pg_session.flush()

    # DB 에서 조회
    result = await pg_session.execute(
        select(LlmUsageLogORM).where(LlmUsageLogORM.request_id == event.request_id)
    )
    row = result.scalar_one_or_none()

    assert row is not None
    assert row.purpose == "db_sink_insert_test"
    assert row.model == "claude-test-integration"
    assert row.status == "success"
    assert row.input_tokens == 150
    assert row.output_tokens == 75
    assert row.latency_ms == 420


@pytest.mark.integration
async def test_db_sink_nullable_tenant_id(pg_session: AsyncSession) -> None:
    """tenant_id=None 인 시스템 호출 케이스 — PM-4 nullable 허용 검증."""
    from worksheet_api.models.llm_usage_log import LlmUsageLogORM

    event = _make_event(tenant_id=None, workspace_id=None, purpose="system_call_test")
    factory = _make_session_factory(pg_session)

    sink = DbUsageSink(session_factory=factory, log_orm_class=LlmUsageLogORM)
    await sink.record(event)
    await pg_session.flush()

    result = await pg_session.execute(
        select(LlmUsageLogORM).where(LlmUsageLogORM.request_id == event.request_id)
    )
    row = result.scalar_one_or_none()

    assert row is not None
    assert row.tenant_id is None
    assert row.workspace_id is None
    assert row.purpose == "system_call_test"


@pytest.mark.integration
async def test_multiplex_sink_both_db_and_jsonl(
    pg_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """MultiplexUsageSink (jsonl + db) 동시 기록 — 양쪽 모두 기록됨을 검증."""
    from worksheet_api.models.llm_usage_log import LlmUsageLogORM

    log_file = tmp_path / "integration_usage.jsonl"
    jsonl_sink = JsonlUsageSink(path=log_file)

    factory = _make_session_factory(pg_session)
    db_sink = DbUsageSink(session_factory=factory, log_orm_class=LlmUsageLogORM)

    multiplex = MultiplexUsageSink(sinks=[jsonl_sink, db_sink])

    event = _make_event(purpose="dual_sink_integration")
    await multiplex.record(event)
    await pg_session.flush()

    # jsonl 검증
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["purpose"] == "dual_sink_integration"

    # DB 검증
    result = await pg_session.execute(
        select(LlmUsageLogORM).where(LlmUsageLogORM.request_id == event.request_id)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.purpose == "dual_sink_integration"
