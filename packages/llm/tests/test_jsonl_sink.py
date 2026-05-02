"""JsonlUsageSink 테스트 — append, 동시성, permission 오류 graceful 처리."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from llm.sinks.base import UsageEvent
from llm.sinks.jsonl import JsonlUsageSink, _serialize_event


def _make_event(**kwargs) -> UsageEvent:
    """테스트용 UsageEvent 생성 헬퍼."""
    defaults = {
        "request_id": uuid4(),
        "model": "claude-test",
        "purpose": "test",
        "input_tokens": 100,
        "output_tokens": 50,
        "latency_ms": 500,
        "status": "success",
        "created_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return UsageEvent(**defaults)


class TestSerializeEvent:
    def test_basic_serialization(self) -> None:
        """기본 이벤트 직렬화."""
        event = _make_event()
        line = _serialize_event(event)
        parsed = json.loads(line)
        assert parsed["model"] == "claude-test"
        assert parsed["purpose"] == "test"
        assert parsed["status"] == "success"

    def test_uuid_serialized_as_str(self) -> None:
        """UUID 는 str 로 직렬화."""
        event = _make_event()
        line = _serialize_event(event)
        parsed = json.loads(line)
        # UUID 가 str 형태인지 확인
        assert isinstance(parsed["request_id"], str)

    def test_datetime_serialized_as_iso(self) -> None:
        """datetime 은 ISO 8601 str 로 직렬화."""
        event = _make_event()
        line = _serialize_event(event)
        parsed = json.loads(line)
        assert isinstance(parsed["created_at"], str)
        # ISO 형식 파싱 가능한지 확인
        datetime.fromisoformat(parsed["created_at"])

    def test_none_fields_included(self) -> None:
        """None 필드도 포함됨."""
        event = _make_event(parent_request_id=None, error_class=None)
        line = _serialize_event(event)
        parsed = json.loads(line)
        assert "parent_request_id" in parsed
        assert "error_class" in parsed


class TestJsonlUsageSinkAppend:
    async def test_single_record(self, tmp_path: Path) -> None:
        """단일 이벤트 기록."""
        log_file = tmp_path / "usage.jsonl"
        sink = JsonlUsageSink(path=log_file)
        event = _make_event()
        await sink.record(event)

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["status"] == "success"

    async def test_multiple_records_appended(self, tmp_path: Path) -> None:
        """여러 이벤트가 append 됨."""
        log_file = tmp_path / "usage.jsonl"
        sink = JsonlUsageSink(path=log_file)

        for i in range(5):
            await sink.record(_make_event(purpose=f"test_{i}"))

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 5

    async def test_directory_auto_created(self, tmp_path: Path) -> None:
        """부모 디렉토리 자동 생성."""
        log_file = tmp_path / "nested" / "deep" / "usage.jsonl"
        sink = JsonlUsageSink(path=log_file)
        await sink.record(_make_event())
        assert log_file.exists()


class TestJsonlUsageSinkConcurrency:
    async def test_concurrent_writes_safe(self, tmp_path: Path) -> None:
        """asyncio.gather 로 동시 기록 — 라인 수 정합성 확인."""
        log_file = tmp_path / "concurrent.jsonl"
        sink = JsonlUsageSink(path=log_file)

        num_events = 20
        events = [_make_event(purpose=f"event_{i}") for i in range(num_events)]
        await asyncio.gather(*[sink.record(e) for e in events])

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == num_events
        # 모든 줄이 유효한 JSON 인지 확인
        for line in lines:
            json.loads(line)


class TestJsonlUsageSinkErrorHandling:
    async def test_permission_error_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """permission 오류 → log 하고 무시 (예외 전파 안 함)."""
        log_file = tmp_path / "usage.jsonl"
        sink = JsonlUsageSink(path=log_file)

        # open 을 PermissionError 로 패치
        import builtins

        original_open = builtins.open

        def mock_open(*args, **kwargs):  # type: ignore[no-untyped-def]
            if str(log_file) in str(args[0]) if args else False:
                raise PermissionError("권한 없음")
            return original_open(*args, **kwargs)

        monkeypatch.setattr(builtins, "open", mock_open)

        # 예외가 전파되지 않아야 함
        await sink.record(_make_event())  # should not raise

    async def test_record_does_not_raise_on_os_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OSError → 무시 (LLM 호출 자체 실패 안 함)."""
        log_file = tmp_path / "usage.jsonl"
        sink = JsonlUsageSink(path=log_file)

        # mkdir 을 OSError 로 패치
        def mock_mkdir(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            raise OSError("디렉토리 생성 실패")

        monkeypatch.setattr(Path, "mkdir", mock_mkdir)

        # 예외가 전파되지 않아야 함
        await sink.record(_make_event())  # should not raise
