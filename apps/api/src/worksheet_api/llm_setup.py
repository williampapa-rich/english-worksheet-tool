"""API 기동 시 LLM 클라이언트 + dual sink 구성.

PM-4 (ADR-0003):
  DB sink (1차) + jsonl sink (2차 백업) 를 MultiplexUsageSink 로 결합.
  DB sink 실패해도 jsonl 은 계속 기록 → 데이터 손실 없음.

의존성 방향:
  packages/llm/ 은 apps/api/ 를 import 하지 않는다.
  이 모듈 (apps/api/) 이 ORM 클래스와 session factory 를 DbUsageSink 에 주입.
  반대 방향 (packages/llm/ → apps/api/) 은 절대 없음.

FastAPI 사용 패턴:
  @router.post("/extract")
  async def extract(
      client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
      ...
  ) -> ...:
      result = await client.extract_structured(...)
"""

from __future__ import annotations

import logging
from functools import lru_cache

from llm.client import AnthropicStructuredLLMClient, StructuredLLMClient
from llm.sinks import DbUsageSink, JsonlUsageSink, MultiplexUsageSink

logger = logging.getLogger(__name__)


def make_llm_sink() -> MultiplexUsageSink:
    """DB + jsonl dual sink (MultiplexUsageSink) 를 구성한다.

    API 기동 시 1회 호출. lru_cache 로 싱글턴화.

    PM-4 패턴:
      - jsonl sink: 항상 동작하는 안전망 (DB 장애 / 마이그레이션 시에도 기록).
      - db sink: 1차 보관 — 실패 시 swallow + log, jsonl 이 계속 기록.

    Returns:
        MultiplexUsageSink: [jsonl_sink, db_sink] 로 구성된 멀티플렉서.
    """
    from worksheet_api.config import get_settings
    from worksheet_api.db import _get_session_factory
    from worksheet_api.models.llm_usage_log import LlmUsageLogORM

    settings = get_settings()

    jsonl_sink = JsonlUsageSink(path=settings.llm_usage_log_path)
    db_sink = DbUsageSink(
        session_factory=_get_session_factory(),
        log_orm_class=LlmUsageLogORM,
    )

    return MultiplexUsageSink(sinks=[jsonl_sink, db_sink])


@lru_cache
def get_llm_client() -> StructuredLLMClient:
    """API 핸들러용 싱글턴 LLM 클라이언트 (dual sink 주입됨).

    FastAPI Depends 로 사용:
        from worksheet_api.llm_setup import get_llm_client

        @router.post("/extract")
        async def extract(
            client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
        ) -> ...:
            result = await client.extract_structured(...)

    anthropic_api_key 가 None 이면 환경변수 ANTHROPIC_API_KEY 를 사용.
    환경변수도 없으면 실제 LLM 호출 시점에 PermanentLLMError 발생.

    Returns:
        AnthropicStructuredLLMClient: sink 가 주입된 LLM 클라이언트.
    """
    from worksheet_api.config import get_settings

    settings = get_settings()
    sink = make_llm_sink()

    return AnthropicStructuredLLMClient(
        api_key=settings.anthropic_api_key,
        sink=sink,
    )
