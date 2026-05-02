"""통합 테스트 — 실제 Anthropic API 호출.

``@pytest.mark.integration`` 마커 사용.
CI 에서는 skip: ``uv run pytest -m "not integration"``

실행 조건:
  - ANTHROPIC_API_KEY 환경변수 필수
  - 인터넷 연결 필요
  - 비용 발생 (input/output 토큰)

로컬 실행:
  ANTHROPIC_API_KEY=sk-... uv run pytest packages/llm/tests/test_integration.py -m integration -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from llm.client import AnthropicStructuredLLMClient
from llm.prompt import PromptSpec
from pydantic import BaseModel


# 통합 테스트용 간단 response 모델
class PassageSummary(BaseModel):
    """짧은 영어 지문 요약 구조."""

    main_topic: str
    word_count: int
    is_english: bool


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def set_prompts_dir(prompts_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMPTS_DIR", str(prompts_dir))


@pytest.mark.integration
async def test_real_anthropic_call(prompts_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """실제 Anthropic API 호출 1건 — structured output 검증.

    ANTHROPIC_API_KEY 환경변수 필수. 없으면 skip.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY 환경변수 없음 — 통합 테스트 skip")

    # 임시 프롬프트 파일 생성
    (prompts_dir / "integration-test.md").write_text(
        "---\ndescription: 통합 테스트용\n---\n"
        "Analyze the following English passage and provide structured information.\n\n"
        "Passage: {{text}}\n\n"
        "Count the words and identify the main topic.",
        encoding="utf-8",
    )

    client = AnthropicStructuredLLMClient(api_key=api_key)
    prompt = PromptSpec(
        template_id="integration-test",
        variables={
            "text": (
                "Climate change poses significant challenges to global ecosystems. "
                "Rising temperatures affect biodiversity and weather patterns worldwide."
            )
        },
    )

    result = await client.extract_structured(
        prompt=prompt,
        response_model=PassageSummary,
        purpose="integration_test",
        temperature=0.1,
        max_retries=1,
    )

    # 기본 구조 검증
    assert isinstance(result.data, PassageSummary)
    assert result.data.is_english is True
    assert result.data.word_count > 0
    assert len(result.data.main_topic) > 0
    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens > 0
    assert result.elapsed_ms > 0
    assert result.request_id is not None
    assert result.model is not None
