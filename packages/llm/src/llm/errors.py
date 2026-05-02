"""LLM 패키지 예외 계층.

ADR-0003 §D-3.5 재시도 정책에서 정의된 에러 분류를 구현한다.

계층:
  LLMError (기반)
    ├── PermanentLLMError          — 재시도 불가 (API 키 무효, 토큰 한도 초과)
    ├── RetryableLLMError (기반)   — 재시도 가능
    │     ├── LLMNetworkError      — 네트워크 / 5xx
    │     ├── LLMRateLimitError    — rate limit
    │     ├── LLMTimeoutError      — 타임아웃
    │     └── LLMSchemaValidationError — structured output schema 위반

모든 소비자 (extractor / variant 생성 / qa-validator) 는 이 계층만 보면 됨.
직접 anthropic SDK 예외를 catch 하지 않는다 — packages/llm/ 내부에서 변환.
"""

from __future__ import annotations


class LLMError(Exception):
    """LLM 패키지 기반 예외. 모든 LLM 관련 예외는 이 클래스를 상속한다."""


class PermanentLLMError(LLMError):
    """재시도 불가 영구 에러.

    대표 케이스:
      - ANTHROPIC_API_KEY 미설정 / 무효 (401)
      - 컨텍스트 토큰 한도 초과 (400 context_length_exceeded)
      - 요청 형식 자체 오류 (400, 모델이 없는 등)

    ADR-0003 §D-3.5: 이 에러는 retry.py 가 즉시 re-raise 한다.
    """


class RetryableLLMError(LLMError):
    """재시도 가능한 일시적 에러 기반 클래스.

    ADR-0003 §D-3.5: 지수 백오프 후 최대 max_retries 회 재시도.
    """


class LLMNetworkError(RetryableLLMError):
    """네트워크 실패 / 5xx 서버 에러.

    대표 케이스:
      - httpx / anthropic SDK 의 ConnectError, ReadTimeout
      - Anthropic 서버 500 / 503
    """


class LLMRateLimitError(RetryableLLMError):
    """rate limit (429) 에러.

    ADR-0003 §D-3.5: 지수 백오프 후 재시도. retry-after 헤더가 있으면
    그 값을 존중하도록 retry.py 에서 처리.
    """

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class LLMTimeoutError(RetryableLLMError):
    """LLM 호출 타임아웃.

    ADR-0003 §D-3.5: 1회 재시도. 2회째도 실패 시 최종 raise.
    """


class LLMSchemaValidationError(RetryableLLMError):
    """structured output 이 Pydantic schema 를 위반한 경우.

    ADR-0003 §D-3.5: 1회 재시도 허용. 재시도 시 프롬프트에
    "이전 응답이 schema 위반: <error>" 첨부 (LLM 자가 교정 유도).
    2회째도 실패 시 PermanentLLMError 로 변환하지 않고 그대로 raise.

    Attributes:
        validation_error: 원래 Pydantic ValidationError 문자열 표현.
        raw_response: LLM 이 반환한 원 응답 (디버깅용).
    """

    def __init__(
        self,
        message: str,
        *,
        validation_error: str,
        raw_response: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.validation_error = validation_error
        self.raw_response = raw_response
