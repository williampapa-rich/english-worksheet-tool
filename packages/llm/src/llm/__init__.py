"""packages/llm — Anthropic SDK 래퍼, 프롬프트 로딩, structured output 검증.

CLAUDE.md §8.3 강제:
  모든 LLM 호출은 이 패키지를 거쳐야 한다.
  extractor / variant 생성 / qa-validator 가 모두 이 패키지의 인터페이스를 사용한다.
  직접 anthropic SDK 호출 금지.

공개 API 표면:
  - StructuredLLMClient: 프로토콜 (테스트 mock / 다른 구현 주입 가능)
  - AnthropicStructuredLLMClient: 실제 Anthropic 구현
  - PromptSpec: 프롬프트 로딩 + 변수 치환
  - StructuredLLMResult: LLM 호출 결과 컨테이너
  - TokenUsage: 토큰 사용량
  - ImageInput: Vision 입력
  - UsageSink: 사용량 기록 프로토콜
  - JsonlUsageSink: JSONL 파일 sink (PM-4 백업 sink)
  - MultiplexUsageSink: 멀티 sink 결합 (P0-2b DB sink 추가 시 활용)
  - 에러 클래스: LLMError, PermanentLLMError, LLMSchemaValidationError 등
"""

from llm.client import AnthropicStructuredLLMClient, ImageInput, StructuredLLMClient
from llm.errors import (
    LLMError,
    LLMNetworkError,
    LLMRateLimitError,
    LLMSchemaValidationError,
    LLMTimeoutError,
    PermanentLLMError,
    RetryableLLMError,
)
from llm.prompt import PromptFrontmatter, PromptSpec
from llm.sinks import JsonlUsageSink, MultiplexUsageSink, UsageEvent, UsageSink
from llm.usage import StructuredLLMResult, TokenUsage

__all__ = [
    # 클라이언트
    "StructuredLLMClient",
    "AnthropicStructuredLLMClient",
    "ImageInput",
    # 프롬프트
    "PromptSpec",
    "PromptFrontmatter",
    # 결과 / 사용량
    "StructuredLLMResult",
    "TokenUsage",
    # sink
    "UsageSink",
    "UsageEvent",
    "JsonlUsageSink",
    "MultiplexUsageSink",
    # 에러
    "LLMError",
    "PermanentLLMError",
    "RetryableLLMError",
    "LLMNetworkError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMSchemaValidationError",
]
