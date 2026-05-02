"""DbUsageSink + MultiplexUsageSink 단위 테스트.

PM-4 안전망 검증:
  - DbUsageSink.record() 가 session.begin() + session.add() 를 올바르게 호출.
  - DB 실패 시 예외를 swallow — LLM 흐름을 막지 않음.
  - MultiplexUsageSink 가 모든 sink 를 동시 호출.
  - 한 sink 실패해도 다른 sink 는 계속 동작.
  - session_factory 의 commit (begin() context manager) 흐름 검증.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from llm.sinks.base import MultiplexUsageSink, UsageEvent
from llm.sinks.db import DbUsageSink

# ─── 헬퍼 ───────────────────────────────────────────────────────────────────


def _make_event(**kwargs: Any) -> UsageEvent:
    """테스트용 UsageEvent 생성 헬퍼."""
    defaults = {
        "request_id": uuid4(),
        "model": "claude-test",
        "purpose": "test_purpose",
        "input_tokens": 100,
        "output_tokens": 50,
        "latency_ms": 300,
        "status": "success",
        "created_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return UsageEvent(**defaults)


def _make_mock_session_factory(session: Any) -> Any:
    """mock session 을 반환하는 async context manager factory."""

    @asynccontextmanager
    async def _factory():  # type: ignore[return]
        yield session

    return _factory


def _make_mock_session() -> MagicMock:
    """begin() + add() 를 mock 하는 AsyncSession 유사 객체."""
    session = MagicMock()
    session.add = MagicMock()

    @asynccontextmanager
    async def _begin():  # type: ignore[return]
        yield

    session.begin = _begin
    return session


# ─── DbUsageSink.record() ────────────────────────────────────────────────────


class TestDbUsageSinkRecord:
    async def test_record_calls_session_add(self) -> None:
        """record() 가 ORM 인스턴스를 session.add() 로 전달한다."""
        session = _make_mock_session()
        factory = _make_mock_session_factory(session)

        # ORM 클래스 mock — keyword args 로 생성되는 가상 ORM
        MockORM = MagicMock()
        mock_orm_instance = MagicMock()
        MockORM.return_value = mock_orm_instance

        sink = DbUsageSink(session_factory=factory, log_orm_class=MockORM)
        event = _make_event()

        await sink.record(event)

        # session.add 가 ORM 인스턴스로 1회 호출됐는지 확인
        session.add.assert_called_once_with(mock_orm_instance)

    async def test_record_passes_all_event_fields_to_orm(self) -> None:
        """event 의 모든 필드가 ORM 생성자에 전달된다."""
        session = _make_mock_session()
        factory = _make_mock_session_factory(session)

        captured_kwargs: dict = {}  # type: ignore[type-arg]

        class CapturingORM:
            def __init__(self, **kwargs: Any) -> None:
                captured_kwargs.update(kwargs)

        sink = DbUsageSink(session_factory=factory, log_orm_class=CapturingORM)

        tenant_id = uuid4()
        workspace_id = uuid4()
        parent_id = uuid4()
        event = _make_event(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            parent_request_id=parent_id,
            status="schema_invalid",
            error_class="LLMSchemaValidationError",
            cache_read_tokens=20,
        )

        await sink.record(event)

        # 주요 필드 검증
        assert captured_kwargs["tenant_id"] == tenant_id
        assert captured_kwargs["workspace_id"] == workspace_id
        assert captured_kwargs["parent_request_id"] == parent_id
        assert captured_kwargs["status"] == "schema_invalid"
        assert captured_kwargs["error_class"] == "LLMSchemaValidationError"
        assert captured_kwargs["cache_read_tokens"] == 20
        assert captured_kwargs["model"] == "claude-test"
        assert captured_kwargs["purpose"] == "test_purpose"

    async def test_record_with_nullable_tenant_id(self) -> None:
        """tenant_id=None 인 시스템 호출도 정상 처리 (PM-4 nullable 허용)."""
        session = _make_mock_session()
        factory = _make_mock_session_factory(session)

        captured_kwargs: dict = {}  # type: ignore[type-arg]

        class CapturingORM:
            def __init__(self, **kwargs: Any) -> None:
                captured_kwargs.update(kwargs)

        sink = DbUsageSink(session_factory=factory, log_orm_class=CapturingORM)
        event = _make_event(tenant_id=None, workspace_id=None)

        await sink.record(event)

        assert captured_kwargs["tenant_id"] is None
        assert captured_kwargs["workspace_id"] is None

    async def test_record_swallows_db_exception(self) -> None:
        """DB 장애 시 예외를 swallow — LLM 호출 흐름을 막지 않음 (PM-4 안전망)."""

        @asynccontextmanager
        async def _failing_factory():  # type: ignore[return]
            raise RuntimeError("DB 연결 실패")
            yield  # type: ignore[misc]

        sink = DbUsageSink(
            session_factory=_failing_factory,
            log_orm_class=MagicMock(),
        )
        event = _make_event()

        # 예외가 전파되지 않아야 함 — PM-4 안전망
        await sink.record(event)  # must not raise

    async def test_record_swallows_session_begin_exception(self) -> None:
        """session.begin() 실패 시 swallow."""
        session = MagicMock()

        @asynccontextmanager
        async def _failing_begin():  # type: ignore[return]
            raise OSError("트랜잭션 시작 실패")
            yield  # type: ignore[misc]

        session.begin = _failing_begin

        factory = _make_mock_session_factory(session)
        sink = DbUsageSink(session_factory=factory, log_orm_class=MagicMock())
        event = _make_event()

        await sink.record(event)  # must not raise

    async def test_record_swallows_session_add_exception(self) -> None:
        """session.add() 실패 시 swallow."""
        session = MagicMock()
        session.add.side_effect = Exception("insert 실패")

        @asynccontextmanager
        async def _begin():  # type: ignore[return]
            yield

        session.begin = _begin
        factory = _make_mock_session_factory(session)
        sink = DbUsageSink(session_factory=factory, log_orm_class=MagicMock())
        event = _make_event()

        await sink.record(event)  # must not raise

    async def test_record_logs_warning_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """DB 실패 시 WARNING 로그를 남긴다."""
        import logging

        @asynccontextmanager
        async def _failing_factory():  # type: ignore[return]
            raise RuntimeError("의도된 실패")
            yield  # type: ignore[misc]

        sink = DbUsageSink(session_factory=_failing_factory, log_orm_class=MagicMock())
        event = _make_event()

        with caplog.at_level(logging.WARNING, logger="llm.sinks.db"):
            await sink.record(event)

        assert any("DbUsageSink" in r.message for r in caplog.records)

    async def test_session_begin_commit_flow(self) -> None:
        """session.begin() context manager 가 정상 commit 흐름을 거친다."""
        begin_entered = False
        begin_exited = False

        class TrackingSession:
            def __init__(self) -> None:
                self.added: list = []

            @asynccontextmanager
            async def begin(self):  # type: ignore[return]
                nonlocal begin_entered, begin_exited
                begin_entered = True
                yield
                begin_exited = True

            def add(self, orm: Any) -> None:
                self.added.append(orm)

        tracking_session = TrackingSession()
        factory = _make_mock_session_factory(tracking_session)

        MockORM = MagicMock()
        sink = DbUsageSink(session_factory=factory, log_orm_class=MockORM)
        event = _make_event()

        await sink.record(event)

        assert begin_entered, "session.begin() 이 호출되지 않음"
        assert begin_exited, "session.begin() context manager 가 정상 exit 하지 않음"
        assert len(tracking_session.added) == 1


# ─── MultiplexUsageSink ──────────────────────────────────────────────────────


class TestMultiplexUsageSink:
    async def test_all_sinks_called(self) -> None:
        """모든 sink 가 동시 호출된다."""
        sink1 = AsyncMock()
        sink2 = AsyncMock()

        multiplex = MultiplexUsageSink(sinks=[sink1, sink2])
        event = _make_event()

        await multiplex.record(event)

        sink1.record.assert_called_once_with(event)
        sink2.record.assert_called_once_with(event)

    async def test_failed_sink_does_not_block_other_sink(self) -> None:
        """한 sink 실패해도 다른 sink 는 계속 호출된다 (PM-4 안전망)."""
        failing_sink = AsyncMock()
        failing_sink.record.side_effect = RuntimeError("DB 장애")

        success_sink = AsyncMock()

        multiplex = MultiplexUsageSink(sinks=[failing_sink, success_sink])
        event = _make_event()

        # 예외가 전파되지 않아야 함
        await multiplex.record(event)  # must not raise

        # 성공 sink 는 호출되어야 함
        success_sink.record.assert_called_once_with(event)

    async def test_both_sinks_called_concurrently(self) -> None:
        """두 sink 가 asyncio.gather 기반으로 동시 호출된다 (순차 대기 아님)."""
        call_order: list[str] = []

        class Sink1:
            async def record(self, event: UsageEvent) -> None:
                call_order.append("sink1_start")
                await asyncio.sleep(0)  # yield 로 협력적 스케줄링
                call_order.append("sink1_end")

        class Sink2:
            async def record(self, event: UsageEvent) -> None:
                call_order.append("sink2_start")
                await asyncio.sleep(0)
                call_order.append("sink2_end")

        multiplex = MultiplexUsageSink(sinks=[Sink1(), Sink2()])
        event = _make_event()

        await multiplex.record(event)

        # 두 sink 모두 호출됨
        assert "sink1_start" in call_order
        assert "sink1_end" in call_order
        assert "sink2_start" in call_order
        assert "sink2_end" in call_order

    async def test_empty_sinks_list(self) -> None:
        """sink 목록이 비어 있어도 예외 없음."""
        multiplex = MultiplexUsageSink(sinks=[])
        event = _make_event()

        await multiplex.record(event)  # must not raise

    async def test_multiple_failures_all_swallowed(self) -> None:
        """여러 sink 가 모두 실패해도 예외 전파 없음."""
        failing1 = AsyncMock()
        failing1.record.side_effect = RuntimeError("sink1 실패")

        failing2 = AsyncMock()
        failing2.record.side_effect = ValueError("sink2 실패")

        multiplex = MultiplexUsageSink(sinks=[failing1, failing2])
        event = _make_event()

        await multiplex.record(event)  # must not raise

    async def test_failure_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """sink 실패 시 WARNING 로그를 남긴다."""
        import logging

        failing = AsyncMock()
        failing.record.side_effect = RuntimeError("의도된 실패")

        multiplex = MultiplexUsageSink(sinks=[failing])
        event = _make_event()

        with caplog.at_level(logging.WARNING, logger="llm.sinks.base"):
            await multiplex.record(event)

        assert len(caplog.records) >= 1
        assert any("실패" in r.message for r in caplog.records)

    async def test_db_plus_jsonl_dual_sink_pattern(self, tmp_path: Any) -> None:
        """DB + jsonl dual sink 패턴 — DB 실패 시 jsonl 은 계속 기록 (PM-4 검증)."""
        import json

        from llm.sinks.jsonl import JsonlUsageSink

        log_file = tmp_path / "usage.jsonl"
        jsonl_sink = JsonlUsageSink(path=log_file)

        # DB sink — 항상 실패하도록 mock
        @asynccontextmanager
        async def _failing_factory():  # type: ignore[return]
            raise RuntimeError("DB 완전 장애")
            yield  # type: ignore[misc]

        db_sink = DbUsageSink(
            session_factory=_failing_factory,
            log_orm_class=MagicMock(),
        )

        multiplex = MultiplexUsageSink(sinks=[jsonl_sink, db_sink])
        event = _make_event(purpose="dual_sink_test")

        await multiplex.record(event)

        # DB 실패해도 jsonl 은 기록됨
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["purpose"] == "dual_sink_test"
