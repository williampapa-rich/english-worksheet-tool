"""지수 백오프 재시도 정책.

ADR-0003 §D-3.5 명세:
  - 베이스 1초, 지수 2배, jitter ±25%
  - max 2회 재시도 = 최악 1+2+4 = 7초
  - 재시도 대상: 네트워크 / 5xx / rate limit / timeout / schema validation 실패 (1회)
  - 재시도 안 함: PermanentLLMError → 즉시 raise

schema validation 실패 시 재시도 동작:
  1회 재시도 허용. ``RetryState.schema_retry_used`` 플래그로 추적.
  2회째 schema validation 실패도 LLMSchemaValidationError raise (PermanentLLMError 로 변환 안 함).

Anthropic SDK 자체 재시도 disable (ADR-0003 §D-3.5) — client.py 에서
``AsyncAnthropic(max_retries=0)`` 로 생성해야 함. 여기서는 직접 제어.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from llm.errors import (
    LLMSchemaValidationError,
    PermanentLLMError,
    RetryableLLMError,
)

logger = logging.getLogger(__name__)

# 재시도 설정 상수
_BASE_DELAY_SECONDS: float = 1.0
_EXPONENT: float = 2.0
_JITTER_FACTOR: float = 0.25  # ±25%
_DEFAULT_MAX_RETRIES: int = 2


def _calc_delay(attempt: int) -> float:
    """attempt 번째 재시도의 대기 시간 계산 (jitter 포함).

    attempt=0: base=1s
    attempt=1: base=2s
    attempt=2: base=4s

    Args:
        attempt: 0-indexed 재시도 회차 (0 = 첫 재시도 전 대기).

    Returns:
        jitter 가 적용된 대기 시간 (초).
    """
    base = _BASE_DELAY_SECONDS * (_EXPONENT**attempt)
    jitter = base * _JITTER_FACTOR * (2 * random.random() - 1)
    return max(0.0, base + jitter)


async def with_retry[T](
    fn: Callable[..., Awaitable[T]],
    *,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    schema_error_context: str | None = None,
    get_schema_retry_prompt: Callable[[str], Callable[..., Awaitable[T]]] | None = None,
) -> T:
    """지수 백오프로 fn 을 최대 max_retries 회 재시도.

    ADR-0003 §D-3.5 정책 그대로:
      - RetryableLLMError → 지수 백오프 후 재시도
      - PermanentLLMError → 즉시 re-raise (재시도 없음)
      - LLMSchemaValidationError (RetryableLLMError 의 하위) →
          schema_retry_used=False 면 1회 허용, 그 이후는 re-raise

    Args:
        fn: 실행할 비동기 함수 (0-arity callable).
        max_retries: 최대 재시도 횟수 (기본 2).
        schema_error_context: 무시됨. 하위 호환 보존용.
        get_schema_retry_prompt: schema 위반 재시도 시 다른 fn 로 교체할 경우
            사용. ``validation_error_str → new_fn`` 팩토리. None 이면 동일 fn 재사용.

    Returns:
        fn 의 성공 반환값.

    Raises:
        PermanentLLMError: 영구 에러 발생 시.
        RetryableLLMError (포함 하위 클래스): max_retries 소진 후에도 실패 시.
    """
    schema_retry_used = False
    last_exc: Exception | None = None

    # attempt 0 = 첫 시도, attempt 1..max_retries = 재시도
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except PermanentLLMError:
            # 즉시 re-raise — 재시도 없음
            raise
        except LLMSchemaValidationError as exc:
            last_exc = exc
            if schema_retry_used:
                # schema 위반 재시도는 1회만 허용
                logger.warning(
                    "schema validation 실패 — 재시도 이미 소진. validation_error=%s",
                    exc.validation_error,
                )
                raise
            schema_retry_used = True
            logger.warning(
                "schema validation 실패 (attempt=%d) — 1회 재시도 허용. validation_error=%s",
                attempt,
                exc.validation_error,
            )
            # schema 위반 재시도 시 fn 교체 (프롬프트에 에러 첨부)
            if get_schema_retry_prompt is not None:
                fn = get_schema_retry_prompt(exc.validation_error)
            delay = _calc_delay(attempt)
            await asyncio.sleep(delay)
        except RetryableLLMError as exc:
            last_exc = exc
            if attempt >= max_retries:
                logger.error(
                    "재시도 소진 (max_retries=%d). 최종 에러: %s",
                    max_retries,
                    exc,
                )
                raise
            delay = _calc_delay(attempt)
            logger.warning(
                "LLM 호출 실패 (attempt=%d/%d, delay=%.2fs): %s",
                attempt,
                max_retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    # 이 지점에 도달하면 안 되지만 mypy 를 위해 raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("with_retry: 도달 불가 코드 경로")  # pragma: no cover
