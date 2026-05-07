"""GeminiStructuredLLMClient — google-genai SDK 래퍼.

CLAUDE.md §8.3 강제 사항:
  모든 LLM 호출은 이 패키지를 거쳐야 한다. 직접 google-genai 호출 금지.

ADR-0003 §D-3.2 명세 — StructuredLLMClient Protocol 준수.

Gemini structured output 패턴 (Anthropic tool_use 와 다름):
  config = GenerateContentConfig(
      response_mime_type="application/json",
      response_schema=PydanticModel,
  )
  → SDK 가 자동으로 JSON 검증된 Pydantic 인스턴스 반환.

모델 ID:
  GEMINI_MODEL 환경변수 우선. 기본값 "gemini-2.5-flash-lite" (Free tier 대상).

Anthropic 과의 차이점:
  - Vision: image bytes 를 inline_data 로 직접 전달 (Anthropic 의 base64 와 동일).
  - Retry: SDK 자체 retry 끔 (None) — packages/llm/retry.py 가 담당.
  - Token usage: response.usage_metadata 에서 추출.
  - Schema: Pydantic 모델을 그대로 response_schema 로 받음 (json_schema 변환 자동).
  - 캐싱: 미사용 (Anthropic 의 cache_read_tokens 는 항상 0).
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError

from llm.client import ImageInput
from llm.errors import (
    LLMNetworkError,
    LLMRateLimitError,
    LLMSchemaValidationError,
    LLMTimeoutError,
    PermanentLLMError,
)
from llm.prompt import PromptSpec
from llm.retry import with_retry
from llm.sinks.base import UsageEvent, UsageSink
from llm.usage import StructuredLLMResult, TokenUsage

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# 기본 모델 ID — 환경변수 GEMINI_MODEL 로 override.
# Gemini 2.5 Flash Lite — Free tier 대상, 검수 단계 비용 ~$0.
_DEFAULT_MODEL = "gemini-2.5-flash-lite"

# LLM 호출 기본 타임아웃 (초)
_DEFAULT_TIMEOUT_SECONDS: float = 60.0

# 기본 최대 출력 토큰
_DEFAULT_MAX_TOKENS: int = 4096


class GeminiStructuredLLMClient:
    """Google Gemini SDK 기반 StructuredLLMClient 구현.

    CLAUDE.md §8.3: 모든 LLM 호출의 단일 경로 (Anthropic 과 함께).

    Args:
        api_key: Gemini API 키. None 이면 환경변수 GOOGLE_API_KEY 또는
            GEMINI_API_KEY 에서 읽음.
        model: 모델 ID. None 이면 환경변수 GEMINI_MODEL 또는 기본값.
        timeout: 호출 타임아웃 (초, 기본 60).
        sink: 사용량 기록 sink. None 이면 사용량 기록 안 함.
        max_tokens: 최대 출력 토큰 (기본 4096).
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        sink: UsageSink | None = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._api_key = (
            api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        )
        self._model = model or os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL)
        self._timeout = timeout
        self._sink = sink
        self._max_tokens = max_tokens
        # _client 는 lazy init — API 키 없이 객체 생성 가능 (테스트 등)
        self.__client: object | None = None

    def _get_client(self) -> object:
        """google-genai Client lazy 초기화.

        Raises:
            PermanentLLMError: GOOGLE_API_KEY 가 설정되지 않은 경우.
        """
        if self.__client is None:
            if not self._api_key:
                raise PermanentLLMError(
                    "GOOGLE_API_KEY (또는 GEMINI_API_KEY) 환경변수가 설정되지 "
                    "않았습니다. .env 또는 환경변수에 추가하세요."
                )
            try:
                from google import genai
            except ImportError as exc:
                raise PermanentLLMError(
                    "google-genai 패키지가 설치되지 않았습니다. "
                    "uv add google-genai 으로 설치하세요."
                ) from exc

            # SDK 자체 retry 는 끔 (None) — retry.py 가 담당.
            self.__client = genai.Client(api_key=self._api_key)
        return self.__client

    async def extract_structured[T: BaseModel](
        self,
        *,
        prompt: PromptSpec,
        response_model: type[T],
        images: list[ImageInput] | None = None,
        max_retries: int = 2,
        temperature: float = 0.2,
        purpose: str = "default",
        tenant_id: UUID | None = None,
        workspace_id: UUID | None = None,
    ) -> StructuredLLMResult[T]:
        """structured output LLM 호출 (재시도 포함).

        ADR-0003 §D-3.2 / §D-3.5 명세 준수 — Anthropic 클라이언트와 동일 시그니처
        + 동일 retry / sink 패턴.
        """
        root_request_id = uuid4()
        rendered_prompt = prompt.render()

        async def _single_call(
            current_prompt: str,
            current_parent_id: UUID | None,
        ) -> StructuredLLMResult[T]:
            """단일 LLM 호출 (재시도 없음)."""
            request_id = uuid4() if current_parent_id is not None else root_request_id
            start_ms = int(time.monotonic() * 1000)
            status = "success"
            error_class: str | None = None

            try:
                result = await self._call_gemini(
                    prompt_text=current_prompt,
                    response_model=response_model,
                    images=images,
                    temperature=temperature,
                    request_id=request_id,
                    parent_request_id=current_parent_id,
                )
                elapsed_ms = int(time.monotonic() * 1000) - start_ms
                return StructuredLLMResult(
                    data=result.data,
                    raw_response=result.raw_response,
                    usage=result.usage,
                    model=result.model,
                    elapsed_ms=elapsed_ms,
                    request_id=request_id,
                    parent_request_id=current_parent_id,
                )
            except LLMSchemaValidationError:
                status = "schema_invalid"
                error_class = "LLMSchemaValidationError"
                raise
            except LLMTimeoutError:
                status = "timeout"
                error_class = "LLMTimeoutError"
                raise
            except LLMRateLimitError:
                status = "rate_limited"
                error_class = "LLMRateLimitError"
                raise
            except LLMNetworkError:
                status = "network_error"
                error_class = "LLMNetworkError"
                raise
            except PermanentLLMError:
                status = "other"
                error_class = "PermanentLLMError"
                raise
            finally:
                elapsed_ms = int(time.monotonic() * 1000) - start_ms
                if self._sink is not None:
                    await self._record_usage(
                        request_id=request_id,
                        parent_request_id=current_parent_id,
                        purpose=purpose,
                        elapsed_ms=elapsed_ms,
                        status=status,
                        error_class=error_class,
                        tenant_id=tenant_id,
                        workspace_id=workspace_id,
                    )

        # schema 위반 재시도 시 에러를 프롬프트에 첨부하는 fn 팩토리
        schema_prompt_text = rendered_prompt
        current_parent: UUID | None = None

        def make_call_fn(
            prompt_text: str, par_id: UUID | None
        ) -> Callable[[], Awaitable[StructuredLLMResult[T]]]:
            async def _fn() -> StructuredLLMResult[T]:
                return await _single_call(prompt_text, par_id)

            return _fn

        def get_schema_retry_fn(
            validation_error: str,
        ) -> Callable[[], Awaitable[StructuredLLMResult[T]]]:
            nonlocal current_parent
            new_parent = root_request_id
            current_parent = new_parent
            amended_prompt = (
                f"{schema_prompt_text}\n\n"
                f"[이전 응답이 schema 위반입니다. 반드시 지정된 schema 를 따르세요.]\n"
                f"오류: {validation_error}"
            )
            return make_call_fn(amended_prompt, new_parent)

        return await with_retry(
            make_call_fn(schema_prompt_text, current_parent),
            max_retries=max_retries,
            get_schema_retry_prompt=get_schema_retry_fn,
        )

    async def _call_gemini[T: BaseModel](
        self,
        *,
        prompt_text: str,
        response_model: type[T],
        images: list[ImageInput] | None,
        temperature: float,
        request_id: UUID,
        parent_request_id: UUID | None,
    ) -> StructuredLLMResult[T]:
        """실제 Gemini API 호출 (재시도 없음).

        google-genai SDK 의 response_schema 패턴:
          config = GenerateContentConfig(
              response_mime_type="application/json",
              response_schema=PydanticModel,
          )
          → response.parsed 가 검증된 Pydantic 인스턴스.

        Raises:
            PermanentLLMError: API 키 무효, 토큰 한도 초과.
            LLMSchemaValidationError: structured output 검증 실패.
            LLMTimeoutError: 타임아웃.
            LLMRateLimitError: rate limit.
            LLMNetworkError: 네트워크 / 5xx.
        """
        from google.genai import errors as genai_errors
        from google.genai import types as genai_types

        client = self._get_client()

        # 메시지 contents 구성 — Vision 입력 있으면 image part 추가
        parts: list[object] = []
        if images:
            for img in images:
                # google-genai 는 inline_data part 패턴
                parts.append(
                    genai_types.Part.from_bytes(
                        data=img.data,
                        mime_type=img.media_type,
                    )
                )
        parts.append(prompt_text)

        config = genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_model,
            temperature=temperature,
            max_output_tokens=self._max_tokens,
            # google-genai 의 retry / timeout 설정. SDK 자체 retry 끔.
            http_options=genai_types.HttpOptions(timeout=int(self._timeout * 1000)),
        )

        try:
            start_ms = int(time.monotonic() * 1000)
            # google-genai 는 동기 SDK 위주지만 aio 네임스페이스로 async 지원.
            response = await client.aio.models.generate_content(  # type: ignore[attr-defined]
                model=self._model,
                contents=parts,
                config=config,
            )
            elapsed_ms = int(time.monotonic() * 1000) - start_ms

        except genai_errors.APIError as exc:
            # google-genai 의 통합 에러. status code 로 분기.
            code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            msg = str(exc)
            if code == 401 or code == 403:
                raise PermanentLLMError(f"Gemini 인증 실패 (API 키 확인): {msg}") from exc
            if code == 429:
                raise LLMRateLimitError(
                    f"Gemini rate limit: {msg}", retry_after_seconds=None
                ) from exc
            if code == 408 or "timeout" in msg.lower():
                raise LLMTimeoutError(f"Gemini API 타임아웃: {msg}") from exc
            if code is not None and code >= 500:
                raise LLMNetworkError(f"Gemini 서버 오류 ({code}): {msg}") from exc
            if code == 400:
                raise PermanentLLMError(f"Gemini 요청 오류 (재시도 불가): {msg}") from exc
            # 그 외 — 네트워크 추정
            raise LLMNetworkError(f"Gemini API 오류: {msg}") from exc
        except TimeoutError as exc:
            raise LLMTimeoutError(f"Gemini API 타임아웃: {exc}") from exc

        # response.parsed: SDK 가 response_schema 를 사용해 자동 파싱.
        # 일부 버전은 .parsed 가 None 이면 .text 의 raw JSON 을 직접 검증.
        parsed: T | None = None
        if hasattr(response, "parsed") and response.parsed is not None:
            try:
                # SDK 가 dict/list/PydanticModel 중 하나로 반환할 수 있음.
                if isinstance(response.parsed, response_model):
                    parsed = response.parsed
                elif isinstance(response.parsed, dict):
                    parsed = response_model.model_validate(response.parsed)
                else:
                    # list 등 — 우선 dict 시도, 실패 시 raw JSON
                    parsed = response_model.model_validate(response.parsed)
            except ValidationError as exc:
                raise LLMSchemaValidationError(
                    f"Gemini 응답이 schema 를 위반했습니다: {exc}",
                    validation_error=str(exc),
                    raw_response={"parsed": str(response.parsed)},
                ) from exc

        if parsed is None:
            # fallback: .text 의 raw JSON 파싱.
            raw_text = getattr(response, "text", None) or ""
            if not raw_text:
                raise LLMSchemaValidationError(
                    "Gemini 응답이 비어있습니다 (parsed=None, text=empty).",
                    validation_error="empty response",
                    raw_response={},
                )
            try:
                raw_dict = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                raise LLMSchemaValidationError(
                    f"Gemini 응답이 유효한 JSON 이 아닙니다: {exc}",
                    validation_error=str(exc),
                    raw_response={"text": raw_text},
                ) from exc
            try:
                parsed = response_model.model_validate(raw_dict)
            except ValidationError as exc:
                raise LLMSchemaValidationError(
                    f"Gemini 응답이 schema 를 위반했습니다: {exc}",
                    validation_error=str(exc),
                    raw_response=raw_dict,
                ) from exc

        # token usage 추출
        usage_meta = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage_meta, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage_meta, "candidates_token_count", 0) or 0
        cache_read_tokens = getattr(usage_meta, "cached_content_token_count", 0) or 0

        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
        )

        # raw_response — 디버그 용. response 객체를 dict 로 변환하면 무거우므로
        # 핵심 메타만 기록.
        raw_response: dict[str, object] = {
            "model": self._model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

        return StructuredLLMResult(
            data=parsed,
            raw_response=raw_response,
            usage=usage,
            model=self._model,
            elapsed_ms=elapsed_ms,
            request_id=request_id,
            parent_request_id=parent_request_id,
        )

    async def _record_usage(
        self,
        *,
        request_id: UUID,
        parent_request_id: UUID | None,
        purpose: str,
        elapsed_ms: int,
        status: str,
        error_class: str | None,
        tenant_id: UUID | None,
        workspace_id: UUID | None,
    ) -> None:
        """사용량 이벤트를 sink 에 기록 (실패 시 로그하고 무시).

        AnthropicStructuredLLMClient._record_usage 와 동일 패턴.
        """
        if self._sink is None:
            return
        event = UsageEvent(
            request_id=request_id,
            parent_request_id=parent_request_id,
            model=self._model,
            purpose=purpose,
            input_tokens=0,  # finally 블록에서는 토큰 정보 없음 — 0으로 기록
            output_tokens=0,
            cache_read_tokens=0,
            latency_ms=elapsed_ms,
            status=status,
            error_class=error_class,
            created_at=datetime.now(UTC),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        try:
            await self._sink.record(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning("UsageSink.record 실패 (무시): %s", exc)
