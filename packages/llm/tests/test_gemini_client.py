"""GeminiStructuredLLMClient 단위 테스트 — mock SDK 사용.

실제 Gemini API 호출 없이 response_schema 패턴 + Pydantic 검증을 확인.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llm.errors import LLMSchemaValidationError, PermanentLLMError
from llm.gemini_client import GeminiStructuredLLMClient
from llm.prompt import PromptSpec
from pydantic import BaseModel


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


def _write_prompt(prompts_dir: Path, name: str, body: str) -> None:
    """frontmatter + body 형식으로 프롬프트 파일 작성."""
    (prompts_dir / f"{name}.md").write_text(
        f"---\nmodel_hint: gemini-2.5-flash-lite\nversion: 0\n---\n{body}\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_extract_structured_success(prompts_dir: Path) -> None:
    """response.parsed 가 SimpleResponse 인스턴스 → 정상 반환."""
    _write_prompt(prompts_dir, "test-prompt", "Hello world")

    mock_response = MagicMock()
    mock_response.parsed = SimpleResponse(title="hello", count=42)
    mock_response.text = '{"title": "hello", "count": 42}'
    mock_response.usage_metadata = MagicMock(
        prompt_token_count=10,
        candidates_token_count=5,
        cached_content_token_count=0,
    )

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    client = GeminiStructuredLLMClient(api_key="test-key")
    with patch.object(client, "_get_client", return_value=mock_client):
        result = await client.extract_structured(
            prompt=PromptSpec(template_id="test-prompt"),
            response_model=SimpleResponse,
        )

    assert result.data.title == "hello"
    assert result.data.count == 42
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5


@pytest.mark.asyncio
async def test_extract_structured_dict_parsed(prompts_dir: Path) -> None:
    """response.parsed 가 dict 인 경우 → model_validate."""
    _write_prompt(prompts_dir, "test-prompt", "Hello world")

    mock_response = MagicMock()
    mock_response.parsed = {"title": "hello", "count": 42}
    mock_response.text = '{"title": "hello", "count": 42}'
    mock_response.usage_metadata = MagicMock(
        prompt_token_count=10,
        candidates_token_count=5,
        cached_content_token_count=0,
    )

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    client = GeminiStructuredLLMClient(api_key="test-key")
    with patch.object(client, "_get_client", return_value=mock_client):
        result = await client.extract_structured(
            prompt=PromptSpec(template_id="test-prompt"),
            response_model=SimpleResponse,
        )

    assert result.data.title == "hello"


@pytest.mark.asyncio
async def test_extract_structured_text_fallback(prompts_dir: Path) -> None:
    """response.parsed=None 이면 .text 의 raw JSON fallback 파싱."""
    _write_prompt(prompts_dir, "test-prompt", "Hello world")

    mock_response = MagicMock()
    mock_response.parsed = None
    mock_response.text = '{"title": "fallback", "count": 1}'
    mock_response.usage_metadata = MagicMock(
        prompt_token_count=10,
        candidates_token_count=5,
        cached_content_token_count=0,
    )

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    client = GeminiStructuredLLMClient(api_key="test-key")
    with patch.object(client, "_get_client", return_value=mock_client):
        result = await client.extract_structured(
            prompt=PromptSpec(template_id="test-prompt"),
            response_model=SimpleResponse,
        )

    assert result.data.title == "fallback"
    assert result.data.count == 1


@pytest.mark.asyncio
async def test_extract_structured_invalid_json_fallback(prompts_dir: Path) -> None:
    """parsed=None + text 가 invalid JSON → LLMSchemaValidationError."""
    _write_prompt(prompts_dir, "test-prompt", "Hello world")

    mock_response = MagicMock()
    mock_response.parsed = None
    mock_response.text = "not valid json"
    mock_response.usage_metadata = MagicMock(
        prompt_token_count=10,
        candidates_token_count=5,
        cached_content_token_count=0,
    )

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    client = GeminiStructuredLLMClient(api_key="test-key")
    with patch.object(client, "_get_client", return_value=mock_client):
        with pytest.raises(LLMSchemaValidationError):
            await client.extract_structured(
                prompt=PromptSpec(template_id="test-prompt"),
                response_model=SimpleResponse,
                max_retries=0,
            )


def test_no_api_key_raises_permanent_error() -> None:
    """API 키 없이 _get_client() → PermanentLLMError."""
    client = GeminiStructuredLLMClient(api_key=None)
    # 환경변수도 비워둠
    import os

    saved_google = os.environ.pop("GOOGLE_API_KEY", None)
    saved_gemini = os.environ.pop("GEMINI_API_KEY", None)
    try:
        client._api_key = None  # ensure clean state
        with pytest.raises(PermanentLLMError, match="GOOGLE_API_KEY"):
            client._get_client()
    finally:
        if saved_google:
            os.environ["GOOGLE_API_KEY"] = saved_google
        if saved_gemini:
            os.environ["GEMINI_API_KEY"] = saved_gemini


def test_default_model_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """GEMINI_MODEL 환경변수 없으면 default = gemini-2.5-flash-lite."""
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    client = GeminiStructuredLLMClient(api_key="dummy")
    assert client._model == "gemini-2.5-flash-lite"
