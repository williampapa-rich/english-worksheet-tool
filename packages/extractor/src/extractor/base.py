"""Extractor 프로토콜 + Sentinel UUID 헬퍼.

ADR-0003 §D-3.1 — 모든 입력 타입(text/image/pdf)의 공통 인터페이스.
ADR-0003 §D-3.6 — sentinel UUID 패턴.

sentinel UUID (uuid.UUID(int=0)):
  extractor 는 tenant_id / workspace_id 를 모른다. 추출 결과의 Passage / Question /
  Translation / Vocabulary 의 tenant_id / workspace_id 필드는 sentinel 값으로 채운다.
  API 레이어가 model_copy 로 실제 값 주입. repository write 시 sentinel 검출 + 차단.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from shared.schemas.extraction import ExtractionRequest, ExtractionResult

# sentinel UUID — ADR-0003 §D-3.6
# API 레이어가 실제 tenant_id / workspace_id 로 교체.
# repository write 시 sentinel 검출 → ValidationError raise (sentinel 누수 방지).
SENTINEL_UUID: uuid.UUID = uuid.UUID(int=0)


def is_sentinel(value: uuid.UUID) -> bool:
    """sentinel UUID 여부 확인.

    repository write 검증에서 사용. ``value == SENTINEL_UUID`` 이면 True.
    """
    return value == SENTINEL_UUID


class Extractor(Protocol):
    """모든 입력 타입(text/image/pdf)의 공통 인터페이스.

    ADR-0003 §D-3.1 명세.

    PM-1 결정에 따라 출력은 ``list[ExtractionResult]`` — 단일 지문 입력이라도
    길이 1 list 반환. 한 PDF 에 N개 지문이 있으면 N개의 ExtractionResult.
    """

    async def extract(self, request: ExtractionRequest) -> list[ExtractionResult]:
        """ExtractionRequest → 정규화된 ExtractionResult 리스트.

        Args:
            request: 입력 페이로드 (text/image/pdf).

        Returns:
            list[ExtractionResult]: PM-1 결정 — 단일 입력도 list 반환.

        Raises:
            EmptyInputError: 텍스트 입력이 비어있을 때.
            UnsupportedMediaTypeError: 지원하지 않는 이미지 MIME type.
            PdfParseError: PDF 파싱 실패 (corrupt 등).
            LLMSchemaValidationError: LLM structured output 검증 실패 (재시도 소진).
            LLMTimeoutError: LLM 호출 타임아웃 (재시도 소진).
            LLMNetworkError: LLM 네트워크 / 5xx 에러 (재시도 소진).
            PermanentLLMError: API 키 무효 등 영구 에러.
        """
        ...
