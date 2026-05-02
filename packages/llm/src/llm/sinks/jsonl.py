"""JsonlUsageSink — LLM 사용량을 JSONL 파일에 append-only 기록.

PM-4 의 "2차 백업 sink": DB 장애 / 마이그레이션 안전망.
1차 보관 (DB sink) 은 P0-2b 에서 구현. 본 PR 은 jsonl 파일 기록만.

특성:
  - append-only: 파일을 열어서 한 줄씩 추가. 읽기 / 수정 없음.
  - 동시성 안전: asyncio.Lock 으로 동시 write 직렬화.
  - 디렉토리 자동 생성: 부모 디렉토리 없으면 makedirs.
  - 기록 실패 graceful 처리: permission 오류 등 → log 하고 무시.
    LLM 호출 자체가 성공해야 하므로 sink 실패가 호출 실패로 전파 금지.
  - 파일 경로: 환경변수 ``LLM_USAGE_LOG_PATH`` 또는 ``var/llm_usage.jsonl`` (default).

JSONL 한 줄 포맷:
  UTF-8, 줄바꿈 구분. 각 줄은 UsageEvent 의 JSON 직렬화.
  UUID 는 str, datetime 은 ISO 8601 (UTC).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import UUID

from llm.sinks.base import UsageEvent

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = Path("var") / "llm_usage.jsonl"


def _get_default_log_path() -> Path:
    """기본 JSONL 로그 파일 경로 반환.

    환경변수 ``LLM_USAGE_LOG_PATH`` 로 override 가능 (테스트 등).
    """
    override = os.environ.get("LLM_USAGE_LOG_PATH")
    if override:
        return Path(override)
    return _DEFAULT_LOG_PATH


def _serialize_event(event: UsageEvent) -> str:
    """UsageEvent → JSON 문자열 (한 줄).

    UUID 는 str, datetime 은 ISO 8601 UTC 문자열로 직렬화.
    """

    def _default(obj: object) -> str:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"직렬화 불가 타입: {type(obj)}")

    data = asdict(event)  # type: ignore[call-overload]
    return json.dumps(data, default=_default, ensure_ascii=False)


class JsonlUsageSink:
    """LLM 사용량을 JSONL 파일에 append-only 기록하는 sink.

    PM-4 의 백업 sink 역할. DB sink (P0-2b) 와 MultiplexUsageSink 로 결합 예정.

    Args:
        path: 로그 파일 경로. 기본값은 환경변수 ``LLM_USAGE_LOG_PATH`` 또는
            ``var/llm_usage.jsonl``.

    Example:
        sink = JsonlUsageSink()  # 기본 경로 사용
        sink = JsonlUsageSink(path=Path("/tmp/test_usage.jsonl"))  # 경로 지정
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path if path is not None else _get_default_log_path()
        self._lock = asyncio.Lock()

    async def record(self, event: UsageEvent) -> None:
        """사용량 이벤트를 JSONL 파일에 한 줄 추가.

        기록 실패 (permission 오류 등) 는 로그 경고 후 무시.
        LLM 호출 자체는 성공해야 하므로 예외를 밖으로 전파하지 않는다.

        Args:
            event: 기록할 LLM 호출 이벤트.
        """
        try:
            line = _serialize_event(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning("UsageEvent 직렬화 실패 (무시): %s", exc)
            return

        async with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except PermissionError as exc:
                logger.warning(
                    "JSONL 로그 파일 기록 권한 오류 (무시) path=%s: %s",
                    self._path,
                    exc,
                )
            except OSError as exc:
                logger.warning(
                    "JSONL 로그 파일 기록 실패 (무시) path=%s: %s",
                    self._path,
                    exc,
                )
