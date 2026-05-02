"""UsageSink 프로토콜 + UsageEvent 모델.

PM-4 (LLM 호출 로깅 결정):
  1차 보관: DB 테이블 ``llm_usage_logs`` (P0-2b 에서 구현 — 본 PR 범위 밖)
  2차 백업: jsonl 파일 sink (본 PR 에서 구현 — JsonlUsageSink)

``UsageSink`` 는 typing.Protocol — DB sink 가 P0-2b 에서 추가될 때 동일 인터페이스로
plug-in 가능. 소비자 (AnthropicStructuredLLMClient) 는 이 프로토콜만 본다.

``MultiplexUsageSink`` 는 여러 sink 에 동시에 기록. P0-2b 에서 DB sink 가 추가되면
이 클래스로 wrap 한다. 본 PR 은 골격만 정의 (jsonl 1개 sink 라 실질적으로 동일).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass
class UsageEvent:
    """LLM 호출 1건의 사용량 이벤트.

    PM-4 의 ``llm_usage_logs`` 테이블과 1:1 대응.

    Attributes:
        request_id: 이 호출의 UUID. ``llm_usage_logs.request_id`` 와 join 키.
            ``ExtractionMetaRef.request_id`` 와도 연결 — ADR-0003 §G-1.
        parent_request_id: 재시도 chain 에서 직전 실패 요청 ID. 첫 시도면 None.
        model: 실제 사용 모델 ID (예: "claude-sonnet-4-20250514").
        purpose: 호출 목적 식별자. 호출자가 지정.
            예: "extract_text" | "extract_pdf_vision" | "extract_pdf_text".
        input_tokens: 입력 토큰 수.
        output_tokens: 출력 토큰 수.
        cache_read_tokens: prompt cache 에서 읽은 토큰 수 (0 이면 캐시 미사용).
        latency_ms: 호출 시작 ~ 응답까지 경과 시간 (ms).
        status: 호출 결과.
            "success" | "schema_invalid" | "timeout" | "network_error" |
            "rate_limited" | "other"
        error_class: 예외 클래스명 (실패 시). 성공 시 None.
        created_at: 이벤트 생성 시각 (UTC, timezone-aware).
        tenant_id: 테넌트 ID. P0-2b DB sink 가 사용. jsonl sink 는 그냥 기록.
            멀티테넌트 강제는 repository 레이어 — 여기서는 그대로 기록만.
        workspace_id: 워크스페이스 ID. tenant_id 와 동일 정책.
    """

    request_id: UUID
    model: str
    purpose: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    status: str
    created_at: datetime
    parent_request_id: UUID | None = None
    cache_read_tokens: int = 0
    error_class: str | None = None
    tenant_id: UUID | None = None
    workspace_id: UUID | None = None


class UsageSink(Protocol):
    """LLM 사용량 이벤트 기록 프로토콜.

    모든 sink (jsonl / DB / 기타) 는 이 프로토콜을 구현한다.
    소비자 (AnthropicStructuredLLMClient) 는 이 프로토콜만 의존한다 — 구체 구현에
    의존하지 않음.

    P0-2b 에서 DB sink 추가 시 이 인터페이스로 plug-in.
    """

    async def record(self, event: UsageEvent) -> None:
        """사용량 이벤트를 비동기로 기록.

        Args:
            event: 기록할 LLM 호출 이벤트.

        Note:
            구현체는 기록 실패 시 예외를 밖으로 전파해선 안 된다 (LLM 호출 자체가
            성공해야 하므로). 예외는 내부에서 log 하고 무시.
        """
        ...


@dataclass
class MultiplexUsageSink:
    """여러 sink 에 동시에 기록하는 멀티플렉서.

    P0-2b 에서 DB sink 추가 시:
        jsonl_sink = JsonlUsageSink(...)
        db_sink = DbUsageSink(...)
        client = AnthropicStructuredLLMClient(
            sink=MultiplexUsageSink(sinks=[jsonl_sink, db_sink])
        )

    현재 (P0-2a): jsonl sink 1개라 MultiplexUsageSink 와 JsonlUsageSink 동작 동일.
    골격만 정의해 P0-2b 확장 경로를 열어둠.
    """

    sinks: list[UsageSink] = field(default_factory=list)

    async def record(self, event: UsageEvent) -> None:
        """모든 sink 에 순차 기록. 각 sink 실패는 독립 처리 (다음 sink 에 영향 없음)."""
        import logging

        logger = logging.getLogger(__name__)
        for sink in self.sinks:
            try:
                await sink.record(event)
            except Exception as exc:  # noqa: BLE001
                # sink 실패가 호출 실패로 전파되면 안 됨
                logger.warning("UsageSink.record 실패 (무시): %s", exc)
