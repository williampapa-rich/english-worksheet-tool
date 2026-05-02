"""DbUsageSink — `llm_usage_logs` 테이블에 LLM 사용량 이벤트를 기록하는 sink.

PM-4 (ADR-0003):
  1차 보관: 이 sink 가 ``llm_usage_logs`` 테이블에 insert.
  2차 백업: JsonlUsageSink 가 동시 기록 (MultiplexUsageSink 패턴).
  안전망: DB 실패 시 이 sink 는 swallow + log. jsonl 은 계속 기록 → 데이터 손실 없음.

의존성 방향 원칙 (CLAUDE.md):
  ``packages/llm/`` 은 ``apps/api/`` 를 import 하면 안 됨.
  따라서 ORM 클래스와 session factory 는 호출자 (apps/api/) 가 주입한다.
  이 모듈 자체는 SQLAlchemy AsyncSession 인터페이스와 contextlib 만 사용.
"""

from __future__ import annotations

import logging
from typing import Any

from llm.sinks.base import UsageEvent

logger = logging.getLogger(__name__)


class DbUsageSink:
    """``llm_usage_logs`` 테이블에 LLM 사용량 이벤트를 기록하는 sink.

    PM-4 의 "1차 보관" sink. DB 실패 시 예외를 swallow 하고 로그만 남긴다.
    jsonl sink 가 동시 기록 중이므로 DB 실패해도 데이터 손실 없음.

    의존성 방향:
      이 클래스는 SQLAlchemy AsyncSession 타입만 참조한다.
      ORM 클래스 (LlmUsageLogORM) 와 session factory 는 호출자가 주입한다.
      ``packages/llm/`` → ``apps/api/`` import 는 절대 없다.

    Args:
        session_factory: ``async with session_factory() as session:`` 패턴으로
            AsyncSession 을 제공하는 callable. ``apps/api/db._get_session_factory()``
            를 wrapping 해서 주입.
        log_orm_class: ``LlmUsageLogORM`` 클래스 — apps/api 가 주입. keyword 필드 기반
            생성자를 지원해야 한다.

    Example:
        # apps/api/llm_setup.py 에서:
        from worksheet_api.models.llm_usage_log import LlmUsageLogORM
        from worksheet_api.db import _get_session_factory

        db_sink = DbUsageSink(
            session_factory=_get_session_factory(),
            log_orm_class=LlmUsageLogORM,
        )
    """

    def __init__(
        self,
        session_factory: Any,  # async_sessionmaker[AsyncSession] — 타입 주입 회피
        log_orm_class: type,  # LlmUsageLogORM — apps/api 가 주입
    ) -> None:
        self._session_factory = session_factory
        self._log_orm_class = log_orm_class

    async def record(self, event: UsageEvent) -> None:
        """UsageEvent 를 ``llm_usage_logs`` 테이블에 insert.

        DB 실패 시 예외를 swallow 하고 WARNING 로그만 남긴다.
        LLM 호출 흐름 자체를 막으면 안 되기 때문 (PM-4 안전망).
        jsonl sink 가 동시 기록 중이므로 데이터 손실 없음.

        Args:
            event: 기록할 LLM 호출 이벤트.
        """
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    orm = self._log_orm_class(
                        request_id=event.request_id,
                        parent_request_id=event.parent_request_id,
                        tenant_id=event.tenant_id,
                        workspace_id=event.workspace_id,
                        model=event.model,
                        purpose=event.purpose,
                        input_tokens=event.input_tokens,
                        output_tokens=event.output_tokens,
                        cache_read_tokens=event.cache_read_tokens,
                        latency_ms=event.latency_ms,
                        status=event.status,
                        error_class=event.error_class,
                        created_at=event.created_at,
                    )
                    session.add(orm)
        except Exception as exc:  # noqa: BLE001
            # PM-4 안전망: DB 실패가 LLM 호출 흐름을 막으면 안 됨.
            # jsonl sink 가 동시 기록 중이므로 데이터 손실 없음 (MultiplexUsageSink 패턴).
            logger.warning(
                "DbUsageSink.record 실패 (jsonl fallback 활성 — 데이터 손실 없음): %s",
                exc,
            )
