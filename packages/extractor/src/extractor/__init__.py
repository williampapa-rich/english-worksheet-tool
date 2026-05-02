"""packages/extractor — PDF/이미지/텍스트 → 정규화된 Passage+Question 추출 패키지.

CLAUDE.md §8.3 강제:
  모든 LLM 호출은 packages/llm/ 를 거친다.
  Anthropic SDK 직접 호출 금지.

ADR-0003 §D-3.1: 입력 타입별 모듈 + 공통 Extractor 프로토콜.
ADR-0003 §D-3.6: sentinel UUID 패턴.

공개 API:
  - Extractor: 프로토콜 (Protocol) — 모든 입력 타입의 공통 인터페이스.
  - extract_from_text: 텍스트 입력 추출 함수 (P0-3).
  - extract_from_image: 이미지 입력 추출 함수 (P0-4, Claude Vision).
  - SENTINEL_UUID: sentinel UUID 상수 (uuid.UUID(int=0)).
  - is_sentinel: sentinel UUID 여부 확인 함수.
  - 에러: EmptyInputError, ExtractionError, PdfParseError, UnsupportedMediaTypeError.
  - 정규화 Raw 스키마 (extractor 내부, 테스트용):
    RawExtractionResponse, RawExtractionItem, RawPassage, RawQuestion,
    RawTranslation, RawVocabulary.
"""

from extractor.base import SENTINEL_UUID, Extractor, is_sentinel
from extractor.errors import (
    EmptyInputError,
    ExtractionError,
    PdfParseError,
    UnsupportedMediaTypeError,
)
from extractor.image import extract_from_image
from extractor.normalizer import (
    RawExtractionItem,
    RawExtractionResponse,
    RawPassage,
    RawQuestion,
    RawTranslation,
    RawVocabulary,
    make_llm_meta,
    normalize,
)
from extractor.text import extract_from_text

__all__ = [
    # 프로토콜
    "Extractor",
    # 함수
    "extract_from_text",
    "extract_from_image",
    "is_sentinel",
    "make_llm_meta",
    "normalize",
    # 상수
    "SENTINEL_UUID",
    # Raw 스키마 (extractor 내부 — 테스트 / 확장용)
    "RawExtractionResponse",
    "RawExtractionItem",
    "RawPassage",
    "RawQuestion",
    "RawTranslation",
    "RawVocabulary",
    # 에러
    "EmptyInputError",
    "ExtractionError",
    "PdfParseError",
    "UnsupportedMediaTypeError",
]
