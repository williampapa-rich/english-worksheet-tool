"""텍스트 입력 추출 어댑터 — P0-3 핵심 산출물.

ADR-0003 §D-3.1 / §D-3.2 / §D-3.6 준수:
  - CLAUDE.md §8.3: Anthropic SDK 직접 호출 금지. 모든 LLM 호출은 packages/llm/ 경유.
  - ADR-0003 §D-3.2: extractor 는 StructuredLLMClient 프로토콜에만 의존.
  - ADR-0003 §D-3.6: sentinel UUID 로 tenant_id / workspace_id 채움.
  - ADR-0003 §D-3.1: 출력은 list[ExtractionResult] (PM-1).

PM 결정:
  - PM-1: 다중 지문 가능 — 단일 입력도 list 반환.
  - PM-5: 자료에 보이는 것만 추출 (translation / vocabulary 포함, 생성 X).
  - PM-6: 자료에 없으면 translation=None / vocabulary=[] (정상).
"""

from __future__ import annotations

from llm.client import StructuredLLMClient
from llm.prompt import PromptSpec

from extractor.errors import EmptyInputError
from extractor.normalizer import RawExtractionResponse, make_llm_meta, normalize
from shared.schemas.extraction import ExtractionResult

# 기본 프롬프트 템플릿 ID — docs/prompts/extract-text-v0.md
_DEFAULT_PROMPT_TEMPLATE_ID = "extract-text-v0"


async def extract_from_text(
    text: str,
    *,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = _DEFAULT_PROMPT_TEMPLATE_ID,
) -> list[ExtractionResult]:
    """영어 지문 / 시험지 텍스트 → 정규화된 ExtractionResult 리스트.

    ADR-0003 §D-3.2 — CLAUDE.md §8.3 강제:
      모든 LLM 호출은 StructuredLLMClient 를 통한다. Anthropic SDK 직접 호출 금지.

    ADR-0003 §D-3.6 — sentinel UUID:
      출력 Passage / Question / Translation / Vocabulary 의 tenant_id / workspace_id 는
      uuid.UUID(int=0) sentinel 로 채워진다. API 레이어가 model_copy 로 실제 값 주입.

    PM-1: 단일 입력도 list 반환. 자료에 N개 지문이 있으면 N개의 ExtractionResult.
    PM-5: 자료에 보이는 것만 추출 — translation / vocabulary 포함, 생성 X.
    PM-6: 자료에 없으면 translation=None, vocabulary=[] — 에러가 아닌 정상.

    Args:
        text: 영어 지문 또는 시험지 텍스트 (UTF-8).
        llm_client: StructuredLLMClient 구현체 (테스트에서 mock 주입 가능).
        prompt_template_id: 사용할 프롬프트 템플릿 ID (docs/prompts/ 기준).
            기본값: "extract-text-v0".

    Returns:
        list[ExtractionResult]: PM-1 결정 — 단일 입력도 list, 길이 >= 1.

    Raises:
        EmptyInputError: 입력 텍스트가 비어있거나 공백만 있을 때.
        ExtractionError: QuestionType 매핑 실패 등 정규화 중 복구 불가 오류.
        LLMSchemaValidationError: LLM structured output 검증 실패 (재시도 소진).
        LLMTimeoutError: LLM 호출 타임아웃 (재시도 소진).
        LLMNetworkError: 네트워크 / 5xx 에러 (재시도 소진).
        PermanentLLMError: API 키 무효 등 영구 에러.
    """
    if not text.strip():
        raise EmptyInputError(
            "입력 텍스트가 비어있습니다. 영어 지문 또는 시험지 텍스트를 입력하세요."
        )

    # 1. 프롬프트 명세 구성
    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={"input_text": text},
    )

    # 2. LLM 호출 — structured output (CLAUDE.md §8.3 강제)
    # Anthropic SDK 직접 호출 금지 — llm_client 를 통한다.
    llm_result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=RawExtractionResponse,
        purpose="extract_text",
    )

    # 3. ExtractionMetaRef 생성 (ADR-0003 §G-1)
    llm_meta = make_llm_meta(
        request_id=llm_result.request_id,
        model=llm_result.model,
        prompt_template_id=prompt_template_id,
    )

    # 4. 정규화 — RawExtractionResponse → list[ExtractionResult]
    return normalize(llm_result.data, llm_meta=llm_meta)
