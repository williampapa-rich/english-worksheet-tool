"""StructuredLLMClient 프로토콜 + AnthropicStructuredLLMClient 구현.

CLAUDE.md §8.3 강제 사항:
  모든 LLM 호출은 이 패키지를 거쳐야 한다.
  extractor / variant 생성 / qa-validator 모두 이 인터페이스를 사용한다.
  직접 anthropic SDK 호출 금지.

ADR-0003 §D-3.2 명세 그대로 구현.

exam-generator app/llm/anthropic.py 의 검증된 tool_use input_schema 패턴 흡수
(CLAUDE.md §3.6 No Reinventing the Wheel):
  tools=[{"name": TOOL_NAME, "input_schema": Model.model_json_schema()}]
  tool_choice={"type": "tool", "name": TOOL_NAME}

Anthropic SDK 자체 재시도 disable (ADR-0003 §D-3.5):
  AsyncAnthropic(max_retries=0) 로 생성 — retry 는 retry.py 가 담당.

모델 ID:
  ANTHROPIC_MODEL 환경변수 우선. 기본값은 "claude-sonnet-4-6" (2026-05-02 기준
  안정 Sonnet 4.x). 모델 ID 확인이 필요하면 ANTHROPIC_MODEL 환경변수로 명시 설정 권고.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError

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
    pass

logger = logging.getLogger(__name__)

# Anthropic tool_use 강제 패턴에서 사용하는 도구 이름
# exam-generator 에서 검증된 패턴 흡수
_TOOL_NAME = "emit_structured_output"

# 기본 모델 ID — 환경변수 ANTHROPIC_MODEL 로 override
# 2026-05-02 기준 안정 Sonnet 4.x: claude-sonnet-4-6
# 모델 ID 가 확실하지 않으면 환경변수로 명시 설정 권고
_DEFAULT_MODEL = "claude-sonnet-4-6"

# LLM 호출 기본 타임아웃 (초)
_DEFAULT_TIMEOUT_SECONDS: float = 60.0

# 기본 최대 출력 토큰
_DEFAULT_MAX_TOKENS: int = 4096


@dataclass
class ImageInput:
    """Vision LLM 입력 이미지.

    Attributes:
        data: 이미지 raw bytes (PNG/JPEG/WEBP/GIF).
        media_type: MIME type. 예: "image/png", "image/jpeg", "image/webp".
    """

    data: bytes
    media_type: str


class StructuredLLMClient(Protocol):
    """structured output 전용 LLM 클라이언트 프로토콜.

    ADR-0003 §D-3.2 명세. extractor / variant 생성 / qa-validator 모두 사용.

    소비자는 이 프로토콜에만 의존한다. AnthropicStructuredLLMClient 를 직접 import
    하지 않아도 되고, 테스트에서 mock 구현을 주입할 수 있다.
    """

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
        """structured output 을 반환하는 LLM 호출.

        Args:
            prompt: 프롬프트 명세 (template_id + variables).
            response_model: 응답을 파싱할 Pydantic 모델 타입.
            images: Vision 입력 이미지 목록. None 이면 텍스트 전용 호출.
            max_retries: 최대 재시도 횟수 (기본 2).
            temperature: 모델 temperature (기본 0.2 — 구조화 출력에 낮게 설정).
            purpose: 호출 목적 (usage log 에 기록). 예: "extract_text".
            tenant_id: 사용량 로그에 기록할 테넌트 ID (선택).
            workspace_id: 사용량 로그에 기록할 워크스페이스 ID (선택).

        Returns:
            StructuredLLMResult[T]: 검증된 Pydantic 모델 + 사용량 정보.

        Raises:
            PermanentLLMError: API 키 무효 / 토큰 한도 초과 등 영구 에러.
            LLMSchemaValidationError: structured output 검증 실패 (재시도 소진 후).
            LLMTimeoutError: 타임아웃 (재시도 소진 후).
            LLMNetworkError: 네트워크 / 5xx 에러 (재시도 소진 후).
        """
        ...


class AnthropicStructuredLLMClient:
    """Anthropic SDK 기반 StructuredLLMClient 구현.

    CLAUDE.md §8.3: 모든 LLM 호출의 단일 경로.
    exam-generator app/llm/anthropic.py 의 검증된 tool_use 패턴 흡수.

    Args:
        api_key: Anthropic API 키. None 이면 환경변수 ANTHROPIC_API_KEY 에서 읽음.
        model: 모델 ID. None 이면 환경변수 ANTHROPIC_MODEL 또는 기본값.
        timeout: 호출 타임아웃 (초, 기본 60).
        sink: 사용량 기록 sink. None 이면 사용량 기록 안 함.
        max_tokens: 최대 출력 토큰 (기본 4096).

    Example:
        client = AnthropicStructuredLLMClient()
        result = await client.extract_structured(
            prompt=PromptSpec(template_id="extract-text-v0", variables={"text": "..."}),
            response_model=MyModel,
            purpose="extract_text",
        )
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
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._model = model or os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL)
        self._timeout = timeout
        self._sink = sink
        self._max_tokens = max_tokens
        # _client 는 lazy init — API 키 없이 객체 생성 가능 (테스트 등)
        self.__client = None

    def _get_client(self) -> object:  # returns AsyncAnthropic (lazy import)
        """AsyncAnthropic 클라이언트 lazy 초기화.

        Raises:
            PermanentLLMError: ANTHROPIC_API_KEY 가 설정되지 않은 경우.
        """
        if self.__client is None:
            if not self._api_key:
                raise PermanentLLMError(
                    "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다. "
                    ".env 또는 환경변수에 ANTHROPIC_API_KEY 를 추가하세요."
                )
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:
                raise PermanentLLMError(
                    "anthropic 패키지가 설치되지 않았습니다. "
                    "uv add anthropic>=0.40.0 으로 설치하세요."
                ) from exc

            # ADR-0003 §D-3.5: SDK 자체 재시도 disable — retry.py 가 담당
            self.__client = AsyncAnthropic(
                api_key=self._api_key,
                max_retries=0,
                timeout=self._timeout,
            )
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

        ADR-0003 §D-3.2 / §D-3.5 명세 구현.
        """
        # 첫 시도 request_id — 재시도 chain 의 root
        root_request_id = uuid4()
        parent_id: UUID | None = None

        rendered_prompt = prompt.render()

        async def _single_call(
            current_prompt: str,
            current_parent_id: UUID | None,
        ) -> StructuredLLMResult[T]:
            """단일 LLM 호출 (재시도 없음)."""
            nonlocal parent_id
            request_id = uuid4() if current_parent_id is not None else root_request_id
            start_ms = int(time.monotonic() * 1000)
            status = "success"
            error_class: str | None = None

            try:
                result = await self._call_anthropic(
                    prompt_text=current_prompt,
                    response_model=response_model,
                    images=images,
                    temperature=temperature,
                    request_id=request_id,
                    parent_request_id=current_parent_id,
                )
                elapsed_ms = int(time.monotonic() * 1000) - start_ms
                result = StructuredLLMResult(
                    data=result.data,
                    raw_response=result.raw_response,
                    usage=result.usage,
                    model=result.model,
                    elapsed_ms=elapsed_ms,
                    request_id=request_id,
                    parent_request_id=current_parent_id,
                )
                return result
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

        # 스키마 위반 시 프롬프트에 에러 첨부 팩토리
        def get_schema_retry_fn(
            validation_error: str,
        ) -> Callable[[], Awaitable[StructuredLLMResult[T]]]:
            nonlocal current_parent
            # 재시도 시 parent_id 는 root_request_id (첫 실패 요청)
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

    async def _call_anthropic[T: BaseModel](
        self,
        *,
        prompt_text: str,
        response_model: type[T],
        images: list[ImageInput] | None,
        temperature: float,
        request_id: UUID,
        parent_request_id: UUID | None,
    ) -> StructuredLLMResult[T]:
        """실제 Anthropic API 호출 (재시도 없음).

        exam-generator app/llm/anthropic.py:31-64 의 tool_use 패턴 그대로.

        Raises:
            PermanentLLMError: API 키 무효, 토큰 한도 초과.
            LLMSchemaValidationError: structured output 검증 실패.
            LLMTimeoutError: 타임아웃.
            LLMRateLimitError: rate limit.
            LLMNetworkError: 네트워크 / 5xx.
        """
        import anthropic

        client = self._get_client()

        # 메시지 content 구성 — Vision 입력 있으면 image block 추가
        content: list[dict] = []  # type: ignore[type-arg]
        if images:
            import base64

            for img in images:
                encoded = base64.standard_b64encode(img.data).decode("ascii")
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.media_type,
                            "data": encoded,
                        },
                    }
                )
        content.append({"type": "text", "text": prompt_text})

        try:
            start_ms = int(time.monotonic() * 1000)
            msg = await client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=temperature,
                # tool_use 강제 패턴 — exam-generator 검증 패턴 흡수
                tools=[
                    {
                        "name": _TOOL_NAME,
                        "description": (
                            "Emit structured output matching the given schema exactly."
                        ),
                        "input_schema": response_model.model_json_schema(),
                    }
                ],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[{"role": "user", "content": content}],
            )
            elapsed_ms = int(time.monotonic() * 1000) - start_ms

        except anthropic.AuthenticationError as exc:
            raise PermanentLLMError(f"Anthropic 인증 실패 (API 키 확인): {exc}") from exc
        except anthropic.PermissionDeniedError as exc:
            raise PermanentLLMError(f"Anthropic 권한 거절: {exc}") from exc
        except anthropic.BadRequestError as exc:
            # 토큰 한도 초과 등
            raise PermanentLLMError(f"Anthropic 요청 오류 (재시도 불가): {exc}") from exc
        except anthropic.RateLimitError as exc:
            retry_after: float | None = None
            # SDK 응답 헤더에서 retry-after 추출 시도
            if hasattr(exc, "response") and exc.response is not None:
                ra = exc.response.headers.get("retry-after")
                if ra:
                    try:
                        retry_after = float(ra)
                    except ValueError:
                        pass
            raise LLMRateLimitError(
                f"Anthropic rate limit: {exc}", retry_after_seconds=retry_after
            ) from exc
        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError(f"Anthropic API 타임아웃: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMNetworkError(f"Anthropic 네트워크 연결 실패: {exc}") from exc
        except anthropic.InternalServerError as exc:
            raise LLMNetworkError(f"Anthropic 서버 오류 (5xx): {exc}") from exc
        except anthropic.APIStatusError as exc:
            # 그 외 4xx/5xx
            if exc.status_code >= 500:
                raise LLMNetworkError(f"Anthropic 서버 오류: {exc}") from exc
            raise PermanentLLMError(f"Anthropic API 오류: {exc}") from exc

        # tool_use 블록에서 structured output 추출 + Pydantic 검증
        raw_input: dict | None = None  # type: ignore[type-arg]
        for block in msg.content:
            if block.type == "tool_use" and block.name == _TOOL_NAME:
                raw_input = dict(block.input)  # type: ignore[arg-type]
                break

        if raw_input is None:
            raise LLMSchemaValidationError(
                f"Anthropic 응답에 '{_TOOL_NAME}' tool_use 블록이 없습니다: {msg.content}",
                validation_error=f"tool_use block '{_TOOL_NAME}' not found",
                raw_response={"content": str(msg.content)},
            )

        try:
            parsed = response_model.model_validate(raw_input)
        except ValidationError as exc:
            raise LLMSchemaValidationError(
                f"LLM 응답이 schema 를 위반했습니다: {exc}",
                validation_error=str(exc),
                raw_response=raw_input,
            ) from exc

        usage = msg.usage
        token_usage = TokenUsage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        )

        return StructuredLLMResult(
            data=parsed,
            raw_response=raw_input,
            usage=token_usage,
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
        """사용량 이벤트를 sink 에 기록 (실패 시 로그하고 무시)."""
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


# 타입 힌트 전용 import
from collections.abc import Awaitable, Callable  # noqa: E402
