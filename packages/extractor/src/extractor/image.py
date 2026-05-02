"""이미지 입력 추출 경로 — Claude Vision 사용.

ADR-0003 §D-3.1 의 ``Extractor`` 프로토콜 conformance.
``packages/llm/`` 의 ``ImageInput`` 형태로 Vision payload 를 전달.

PM-1 결정: 단일 이미지 입력에도 ``list[ExtractionResult]`` 반환 — 한 이미지에 N개
지문 (예: 시험지 한 페이지에 18-30번 문항) 포함 가능.

PM-5 / PM-6: 자료에 보이는 한글 해석 / 어휘 박스가 있으면 함께 추출. 실유저 default
는 영어만 / 문제만 — translation=None / vocabulary=[] 가 정상.

CLAUDE.md §8.3 강제:
  Anthropic SDK 직접 호출 금지. 모든 LLM 호출은 packages/llm/ 경유.
"""

from __future__ import annotations

from llm.client import ImageInput, StructuredLLMClient
from llm.prompt import PromptSpec

from extractor.errors import EmptyInputError, UnsupportedMediaTypeError
from extractor.normalizer import RawExtractionResponse, make_llm_meta, normalize
from shared.schemas.extraction import ExtractionResult

# 지원 media_type 목록 — Anthropic Vision 지원 형식 교집합
# image/gif 는 Anthropic 에서 지원하지만 시험지 이미지 맥락 외라 제외
# image/heic 등 비표준 형식은 별도 변환 후 재시도 안내
_SUPPORTED_MEDIA_TYPES: frozenset[str] = frozenset({"image/png", "image/jpeg", "image/webp"})

# 기본 프롬프트 템플릿 ID — docs/prompts/extract-image-v0.md
_DEFAULT_PROMPT_TEMPLATE_ID = "extract-image-v0"


async def extract_from_image(
    image_bytes: bytes,
    media_type: str,
    *,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = _DEFAULT_PROMPT_TEMPLATE_ID,
) -> list[ExtractionResult]:
    """이미지 (시험지 사진 / 스크린샷) → ExtractionResult 리스트.

    ADR-0003 §D-3.2 — CLAUDE.md §8.3 강제:
      모든 LLM 호출은 StructuredLLMClient 를 통한다. Anthropic SDK 직접 호출 금지.

    ADR-0003 §D-3.6 — sentinel UUID:
      출력 Passage / Question / Translation / Vocabulary 의 tenant_id / workspace_id 는
      uuid.UUID(int=0) sentinel 로 채워진다. API 레이어가 model_copy 로 실제 값 주입.

    PM-1: 단일 이미지 입력도 list 반환. 이미지에 N개 지문이 있으면 N개의 ExtractionResult.
    PM-5: 자료에 보이는 것만 추출 — 이미지에 번역/어휘 박스가 보이면 포함, 생성 X.
    PM-6: 자료에 없으면 translation=None, vocabulary=[] — 에러가 아닌 정상.

    Args:
        image_bytes: 이미지 raw bytes. 빈 bytes 면 ``EmptyInputError``.
        media_type: ``image/png`` / ``image/jpeg`` / ``image/webp`` 만 지원.
            다른 값이면 ``UnsupportedMediaTypeError``.
        llm_client: ``StructuredLLMClient`` 구현체 (Vision 입력 지원).
            테스트에서 mock 주입 가능.
        prompt_template_id: 사용할 프롬프트 템플릿 ID (docs/prompts/ 기준).
            기본값: "extract-image-v0".

    Returns:
        list[ExtractionResult]: PM-1 결정 — 단일 입력도 list, 길이 >= 1.

    Raises:
        EmptyInputError: ``image_bytes`` 가 비어있음.
        UnsupportedMediaTypeError: ``media_type`` 이 지원 목록에 없음.
        ExtractionError: QuestionType 매핑 실패 등 정규화 중 복구 불가 오류.
        LLMSchemaValidationError: LLM structured output 검증 실패 (재시도 소진).
        LLMTimeoutError: LLM 호출 타임아웃 (재시도 소진).
        LLMNetworkError: 네트워크 / 5xx 에러 (재시도 소진).
        PermanentLLMError: API 키 무효 등 영구 에러.
    """
    # 1. 입력 유효성 검사 — LLM 호출 전 fast fail
    if not image_bytes:
        raise EmptyInputError("입력 이미지가 비어있습니다. 이미지 bytes 를 전달하세요.")

    if media_type not in _SUPPORTED_MEDIA_TYPES:
        raise UnsupportedMediaTypeError(media_type)

    # 2. 프롬프트 명세 구성 — 입력은 이미지로만 전달, 텍스트 변수 없음
    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={},  # Vision 입력 전용 — 텍스트 변수 사용 안 함
    )

    # 3. Vision 이미지 페이로드 구성
    image_input = ImageInput(data=image_bytes, media_type=media_type)

    # 4. LLM 호출 — Vision 입력 (CLAUDE.md §8.3 강제)
    # Anthropic SDK 직접 호출 금지 — llm_client 를 통한다.
    llm_result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=RawExtractionResponse,
        images=[image_input],
        purpose="extract_image",
    )

    # 5. ExtractionMetaRef 생성
    llm_meta = make_llm_meta(
        request_id=llm_result.request_id,
        model=llm_result.model,
        prompt_template_id=prompt_template_id,
    )

    # 6. 정규화 — RawExtractionResponse → list[ExtractionResult] (P0-3 normalizer 재사용)
    return normalize(llm_result.data, llm_meta=llm_meta)
