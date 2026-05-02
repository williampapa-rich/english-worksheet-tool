"""통합 테스트 — 실제 Anthropic API 호출.

@pytest.mark.integration 마킹.
실제 ANTHROPIC_API_KEY 가 필요하며 CI 에서는 skip.

실행 방법:
  uv run pytest packages/extractor/tests/test_integration.py -m integration -v

PM-7: fixture 자료 경로 → admin/fixtures/extractor/text/
  PM-6 가정에 따라 "영어만" 케이스와 "풀세트" 케이스 양쪽 커버.
  현재는 inline fixture 문자열 사용 (admin/fixtures/ 수집 전 단계).
"""

from __future__ import annotations

import os

import pytest

# admin/fixtures/extractor/text/ 가 수집되면 여기서 로드
# 현재는 inline 문자열 fixture 사용 (PM-7 fixture 수집 전)
ENGLISH_ONLY_FIXTURE = """\
In 2023, researchers at a university in Seoul conducted an experiment
to determine how exercise affects memory retention. Participants
were divided into two groups: one group exercised for 30 minutes
before studying, while the other studied without exercise. The
results showed that the exercise group retained 25% more information
after one week compared to the control group.

18. What is the main purpose of this passage?
① To explain the benefits of physical activity
② To describe a scientific study on exercise and memory
③ To recommend a specific exercise routine for students
④ To compare different study methods
⑤ To discuss the importance of university research
"""

FULL_SET_FIXTURE = """\
Humans have long wondered why we dream. Scientists have proposed
several theories. One popular theory suggests that dreams help
consolidate memories from the day. Another theory proposes that
dreaming allows the brain to process emotions and stress.

꿈을 꾸는 이유에 대해 인간은 오랫동안 궁금해했습니다. 과학자들은 여러 가지
이론을 제안했습니다.

어휘:
consolidate 통합하다, 강화하다 (v.)
propose 제안하다 (v.)
"""


@pytest.mark.integration
class TestExtractFromTextIntegration:
    """실제 Anthropic API 호출 통합 테스트."""

    @pytest.mark.asyncio
    async def test_english_only_returns_valid_result(self) -> None:
        """영어만 있는 자료 → ExtractionResult 검증.

        PM-6: translation=None, vocabulary=[] 가 정상.
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY 환경변수 없음 — 통합 테스트 skip")

        from extractor.text import extract_from_text
        from llm.client import AnthropicStructuredLLMClient

        client = AnthropicStructuredLLMClient(api_key=api_key)
        results = await extract_from_text(ENGLISH_ONLY_FIXTURE, llm_client=client)

        assert len(results) >= 1, "최소 1개 ExtractionResult 반환"

        result = results[0]
        assert result.passage is not None
        assert result.passage.body_text.strip() != "", "passage body_text 비어있지 않음"
        assert result.passage.word_count > 0, "word_count > 0"

        # PM-6 검증: translation / vocabulary 비어있어도 에러 아님
        assert result.translation is None or isinstance(result.translation.text, str)
        assert isinstance(result.vocabulary, list)

        # ExtractionMetaRef 검증
        assert result.extraction_meta is not None
        assert result.extraction_meta.model != ""

        # sentinel UUID 검증 (API 레이어가 아직 교체 안 함)
        from extractor.base import SENTINEL_UUID

        assert result.passage.tenant_id == SENTINEL_UUID
        assert result.passage.workspace_id == SENTINEL_UUID

    @pytest.mark.asyncio
    async def test_questions_extracted(self) -> None:
        """시험지 형태 자료 → 1개 이상 Question 추출.

        PM-5: 자료에 문제가 있으면 추출.
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY 환경변수 없음 — 통합 테스트 skip")

        from extractor.text import extract_from_text
        from llm.client import AnthropicStructuredLLMClient

        client = AnthropicStructuredLLMClient(api_key=api_key)
        results = await extract_from_text(ENGLISH_ONLY_FIXTURE, llm_client=client)

        # 18번 문제가 있는 자료이므로 questions 가 있어야 함
        all_questions = [q for r in results for q in r.questions]
        assert len(all_questions) >= 1, "1개 이상 Question 추출"
