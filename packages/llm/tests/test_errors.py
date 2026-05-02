"""에러 계층 테스트.

ADR-0003 §D-3.5 에러 분류 검증.
"""

from __future__ import annotations

from llm.errors import (
    LLMError,
    LLMNetworkError,
    LLMRateLimitError,
    LLMSchemaValidationError,
    LLMTimeoutError,
    PermanentLLMError,
    RetryableLLMError,
)


class TestErrorHierarchy:
    """에러 계층 구조 검증."""

    def test_llm_error_is_exception(self) -> None:
        assert issubclass(LLMError, Exception)

    def test_permanent_is_llm_error(self) -> None:
        assert issubclass(PermanentLLMError, LLMError)

    def test_retryable_is_llm_error(self) -> None:
        assert issubclass(RetryableLLMError, LLMError)

    def test_network_is_retryable(self) -> None:
        assert issubclass(LLMNetworkError, RetryableLLMError)

    def test_rate_limit_is_retryable(self) -> None:
        assert issubclass(LLMRateLimitError, RetryableLLMError)

    def test_timeout_is_retryable(self) -> None:
        assert issubclass(LLMTimeoutError, RetryableLLMError)

    def test_schema_validation_is_retryable(self) -> None:
        assert issubclass(LLMSchemaValidationError, RetryableLLMError)


class TestPermanentLLMError:
    def test_can_instantiate(self) -> None:
        err = PermanentLLMError("API 키 없음")
        assert str(err) == "API 키 없음"

    def test_is_not_retryable(self) -> None:
        assert not issubclass(PermanentLLMError, RetryableLLMError)


class TestLLMRateLimitError:
    def test_retry_after_none_by_default(self) -> None:
        err = LLMRateLimitError("rate limit")
        assert err.retry_after_seconds is None

    def test_retry_after_set(self) -> None:
        err = LLMRateLimitError("rate limit", retry_after_seconds=30.0)
        assert err.retry_after_seconds == 30.0


class TestLLMSchemaValidationError:
    def test_validation_error_stored(self) -> None:
        err = LLMSchemaValidationError(
            "schema 위반",
            validation_error="field required",
            raw_response={"key": "val"},
        )
        assert err.validation_error == "field required"
        assert err.raw_response == {"key": "val"}

    def test_raw_response_none_allowed(self) -> None:
        err = LLMSchemaValidationError("schema 위반", validation_error="err")
        assert err.raw_response is None

    def test_catch_as_retryable(self) -> None:
        err = LLMSchemaValidationError("schema 위반", validation_error="e")
        assert isinstance(err, RetryableLLMError)
