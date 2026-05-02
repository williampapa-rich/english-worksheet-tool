"""AnthropicStructuredLLMClient 테스트 — mock SDK 사용.

실제 Anthropic API 호출 없이 tool_use 패턴, Vision 입력, structured output 파싱을 검증.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llm.client import AnthropicStructuredLLMClient, ImageInput
from llm.errors import (
    LLMSchemaValidationError,
    PermanentLLMError,
)
from llm.prompt import PromptSpec
from pydantic import BaseModel


# 테스트용 response 모델
class SimpleResponse(BaseModel):
    title: str
    count: int


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def set_prompts_dir(prompts_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMPTS_DIR", str(prompts_dir))


@pytest.fixture
def simple_prompt(prompts_dir: Path) -> PromptSpec:
    (prompts_dir / "test-prompt.md").write_text(
        "---\n---\nExtract info from: {{text}}", encoding="utf-8"
    )
    return PromptSpec(template_id="test-prompt", variables={"text": "Hello world"})


def _make_mock_message(tool_input: dict) -> MagicMock:  # type: ignore[type-arg]
    """tool_use 블록을 포함한 mock Anthropic 응답 생성."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit_structured_output"
    block.input = tool_input

    msg = MagicMock()
    msg.content = [block]
    msg.usage = MagicMock()
    msg.usage.input_tokens = 100
    msg.usage.output_tokens = 50
    msg.usage.cache_read_input_tokens = 0
    return msg


class TestAnthropicClientInit:
    def test_missing_api_key_raises_on_call(
        self, simple_prompt: PromptSpec, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """API 키 없으면 실제 호출 시 PermanentLLMError."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        client = AnthropicStructuredLLMClient(api_key=None)

        with pytest.raises(PermanentLLMError, match="ANTHROPIC_API_KEY"):
            client._get_client()

    def test_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """환경변수에서 API 키 읽기."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        client = AnthropicStructuredLLMClient()
        assert client._api_key == "sk-test-key"

    def test_model_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """환경변수에서 모델 ID 읽기."""
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-custom-model")
        client = AnthropicStructuredLLMClient()
        assert client._model == "claude-custom-model"


class TestExtractStructured:
    async def test_normal_call_returns_model(self, simple_prompt: PromptSpec) -> None:
        """정상 호출 → 파싱된 Pydantic 모델 반환."""
        mock_msg = _make_mock_message({"title": "테스트", "count": 5})

        with patch("anthropic.AsyncAnthropic") as MockAnthropic:
            mock_instance = AsyncMock()
            mock_instance.messages.create = AsyncMock(return_value=mock_msg)
            MockAnthropic.return_value = mock_instance

            client = AnthropicStructuredLLMClient(api_key="sk-test")
            result = await client.extract_structured(
                prompt=simple_prompt,
                response_model=SimpleResponse,
                purpose="test_extract",
            )

        assert result.data.title == "테스트"
        assert result.data.count == 5
        assert result.usage.input_tokens == 100
        assert result.usage.output_tokens == 50

    async def test_result_has_request_id(self, simple_prompt: PromptSpec) -> None:
        """결과에 request_id UUID 가 있음."""
        mock_msg = _make_mock_message({"title": "x", "count": 1})

        with patch("anthropic.AsyncAnthropic") as MockAnthropic:
            mock_instance = AsyncMock()
            mock_instance.messages.create = AsyncMock(return_value=mock_msg)
            MockAnthropic.return_value = mock_instance

            client = AnthropicStructuredLLMClient(api_key="sk-test")
            result = await client.extract_structured(
                prompt=simple_prompt,
                response_model=SimpleResponse,
            )

        assert result.request_id is not None
        assert result.parent_request_id is None  # 첫 시도

    async def test_vision_call_includes_image_block(self, simple_prompt: PromptSpec) -> None:
        """Vision 입력 → 메시지에 image block 포함."""
        mock_msg = _make_mock_message({"title": "vision", "count": 1})
        captured_messages: list[Any] = []

        async def fake_create(**kwargs: Any) -> Any:
            captured_messages.append(kwargs.get("messages", []))
            return mock_msg

        with patch("anthropic.AsyncAnthropic") as MockAnthropic:
            mock_instance = AsyncMock()
            mock_instance.messages.create = fake_create
            MockAnthropic.return_value = mock_instance

            client = AnthropicStructuredLLMClient(api_key="sk-test")
            image = ImageInput(data=b"\x89PNG\r\n", media_type="image/png")
            await client.extract_structured(
                prompt=simple_prompt,
                response_model=SimpleResponse,
                images=[image],
            )

        # 메시지 content 에 image block 이 있는지 확인
        content = captured_messages[0][0]["content"]
        image_blocks = [b for b in content if b.get("type") == "image"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["source"]["media_type"] == "image/png"

    async def test_schema_validation_failure_raises(self, simple_prompt: PromptSpec) -> None:
        """tool_use 입력이 schema 위반 → LLMSchemaValidationError."""
        # count 가 str 인 잘못된 응답
        mock_msg = _make_mock_message({"title": "x", "count": "not-a-number"})

        with patch("anthropic.AsyncAnthropic") as MockAnthropic:
            mock_instance = AsyncMock()
            mock_instance.messages.create = AsyncMock(return_value=mock_msg)
            MockAnthropic.return_value = mock_instance

            client = AnthropicStructuredLLMClient(api_key="sk-test")
            with pytest.raises(LLMSchemaValidationError):
                await client.extract_structured(
                    prompt=simple_prompt,
                    response_model=SimpleResponse,
                    max_retries=0,  # 재시도 없이 즉시 실패 확인
                )

    async def test_no_tool_use_block_raises(self, simple_prompt: PromptSpec) -> None:
        """tool_use 블록 없는 응답 → LLMSchemaValidationError."""
        msg = MagicMock()
        msg.content = []  # 빈 content
        msg.usage = MagicMock()
        msg.usage.input_tokens = 0
        msg.usage.output_tokens = 0
        msg.usage.cache_read_input_tokens = 0

        with patch("anthropic.AsyncAnthropic") as MockAnthropic:
            mock_instance = AsyncMock()
            mock_instance.messages.create = AsyncMock(return_value=msg)
            MockAnthropic.return_value = mock_instance

            client = AnthropicStructuredLLMClient(api_key="sk-test")
            with pytest.raises(LLMSchemaValidationError):
                await client.extract_structured(
                    prompt=simple_prompt,
                    response_model=SimpleResponse,
                    max_retries=0,
                )
