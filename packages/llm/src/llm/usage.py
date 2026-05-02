"""LLM 호출 결과 및 토큰 사용량 모델.

ADR-0003 §D-3.2 의 ``StructuredLLMResult`` 명세를 구현한다.
PM-4 의 usage_log 테이블과 join 할 수 있도록 ``request_id`` 를 UUID 로 관리.

``ExtractionMetaRef.request_id`` (shared/schemas/extraction.py) 와 join 키:
  ``StructuredLLMResult.request_id == ExtractionMetaRef.request_id``
  즉 LLM 호출 1건을 ExtractionResult 에서 역추적 가능.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pydantic import BaseModel


@dataclass
class TokenUsage:
    """LLM 호출 1회의 토큰 사용량.

    Attributes:
        input_tokens: 입력 토큰 수 (시스템 + 사용자 메시지 포함).
        output_tokens: 출력 토큰 수.
        cache_read_tokens: 캐시에서 읽은 토큰 수 (Anthropic prompt cache).
            캐시 미사용 시 0.
    """

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """입력 + 출력 토큰 합계 (캐시 읽기 포함)."""
        return self.input_tokens + self.output_tokens + self.cache_read_tokens


@dataclass
class StructuredLLMResult[T: BaseModel]:
    """structured output LLM 호출 1회의 완전한 결과 컨테이너.

    ADR-0003 §D-3.2 명세 그대로.

    Attributes:
        data: 검증된 Pydantic 모델 인스턴스 (T).
        raw_response: Anthropic SDK 원 응답 dict (디버깅 / sink 입력).
        usage: 토큰 사용량 (input/output/cache_read).
        model: 실제 사용된 모델 ID (예: "claude-sonnet-4-20250514").
        elapsed_ms: 호출 시작 ~ 응답 완료까지 경과 시간 (ms).
        request_id: 이 호출의 고유 식별자.
            ``ExtractionMetaRef.request_id`` 및 ``llm_usage_logs.request_id`` 와 join.
        parent_request_id: 재시도 체인에서 이전 요청 ID.
            첫 시도면 None. 재시도 시 직전 실패 요청의 request_id 를 담음.
    """

    data: T
    raw_response: dict  # type: ignore[type-arg]
    usage: TokenUsage
    model: str
    elapsed_ms: int
    request_id: UUID = field(default_factory=uuid4)
    parent_request_id: UUID | None = None
