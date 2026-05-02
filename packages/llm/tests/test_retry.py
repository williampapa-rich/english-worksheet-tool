"""retry.py 테스트 — 재시도 정책 검증.

ADR-0003 §D-3.5 명세:
  - 네트워크 실패 1회 → 성공
  - schema 위반 1회 → 재시도 (fn 교체) → 성공
  - timeout 2회 → raise
  - PermanentLLMError → 즉시 raise (재시도 없음)
  - schema 위반 2회 → raise (1회만 허용)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from llm.errors import (
    LLMNetworkError,
    LLMSchemaValidationError,
    LLMTimeoutError,
    PermanentLLMError,
)
from llm.retry import with_retry


class TestRetryNetworkError:
    async def test_network_error_then_success(self) -> None:
        """네트워크 실패 1회 → 성공."""
        call_count = 0

        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMNetworkError("연결 실패")
            return "success"

        result = await with_retry(fn, max_retries=2)
        assert result == "success"
        assert call_count == 2

    async def test_network_error_exhausted(self) -> None:
        """네트워크 에러 max_retries 소진 → raise."""
        call_count = 0

        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMNetworkError("항상 실패")

        with pytest.raises(LLMNetworkError):
            await with_retry(fn, max_retries=2)

        assert call_count == 3  # 1 + 2회 재시도


class TestRetryTimeout:
    async def test_timeout_twice_raises(self) -> None:
        """타임아웃 max_retries 소진 → raise."""
        call_count = 0

        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMTimeoutError("타임아웃")

        with pytest.raises(LLMTimeoutError):
            await with_retry(fn, max_retries=2)
        assert call_count == 3


class TestRetryPermanentError:
    async def test_permanent_error_no_retry(self) -> None:
        """PermanentLLMError → 즉시 raise, 재시도 없음."""
        call_count = 0

        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            raise PermanentLLMError("API 키 무효")

        with pytest.raises(PermanentLLMError):
            await with_retry(fn, max_retries=2)
        assert call_count == 1  # 재시도 없음


class TestRetrySchemaValidation:
    async def test_schema_error_once_then_success_with_fn_replacement(self) -> None:
        """schema 위반 1회 → fn 교체 재시도 → 성공."""
        call_count = 0
        retry_fn_used = False

        async def original_fn() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMSchemaValidationError("schema 위반", validation_error="field required")

        async def retry_fn() -> str:
            nonlocal retry_fn_used
            retry_fn_used = True
            return "success_after_schema_retry"

        def get_schema_retry_fn(
            validation_error: str,
        ) -> Callable[[], Awaitable[str]]:
            return retry_fn

        result = await with_retry(
            original_fn,
            max_retries=2,
            get_schema_retry_prompt=get_schema_retry_fn,
        )
        assert result == "success_after_schema_retry"
        assert retry_fn_used

    async def test_schema_error_twice_raises(self) -> None:
        """schema 위반 2회 → raise (schema retry 는 1회만)."""
        schema_retry_count = 0

        async def always_schema_error() -> str:
            nonlocal schema_retry_count
            schema_retry_count += 1
            raise LLMSchemaValidationError("항상 schema 위반", validation_error="err")

        with pytest.raises(LLMSchemaValidationError):
            await with_retry(always_schema_error, max_retries=2)

        # 첫 시도 + 1회 schema retry = 2회 호출
        assert schema_retry_count == 2

    async def test_schema_error_then_success_no_fn_replacement(self) -> None:
        """fn 교체 없이 schema 위반 1회 → 동일 fn 재시도 → 성공."""
        call_count = 0

        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMSchemaValidationError("schema 위반", validation_error="err")
            return "success"

        result = await with_retry(fn, max_retries=2)
        assert result == "success"
        assert call_count == 2


class TestRetryDelayCalculation:
    async def test_zero_retries_no_retry(self) -> None:
        """max_retries=0 이면 재시도 없음."""
        call_count = 0

        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            raise LLMNetworkError("실패")

        with pytest.raises(LLMNetworkError):
            await with_retry(fn, max_retries=0)
        assert call_count == 1

    async def test_success_on_first_try(self) -> None:
        """첫 시도 성공 → 재시도 없음."""

        async def fn() -> str:
            return "ok"

        result = await with_retry(fn, max_retries=2)
        assert result == "ok"
