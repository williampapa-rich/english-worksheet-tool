"""packages/extractor — PDF/이미지/텍스트 → 정규화된 Passage+Question 추출 패키지.

CLAUDE.md §8.3 강제:
  모든 LLM 호출은 packages/llm/ 를 거친다.
  Anthropic SDK 직접 호출 금지.

ADR-0003 §D-3.1: 입력 타입별 모듈 + 공통 Extractor 프로토콜.
ADR-0003 §D-3.3: PDF 처리 분기 (PyMuPDF + Vision fallback).
ADR-0003 §D-3.6: sentinel UUID 패턴.

공개 API:
  - Extractor: 프로토콜 (Protocol) — 모든 입력 타입의 공통 인터페이스.
  - extract_from_text: 텍스트 입력 추출 함수 (P0-3).
  - extract_from_image: 이미지 입력 추출 함수 (P0-4, Claude Vision).
  - extract_from_pdf: PDF 입력 추출 함수 (P0-5, PyMuPDF + Vision fallback).
  - SENTINEL_UUID: sentinel UUID 상수 (uuid.UUID(int=0)).
  - is_sentinel: sentinel UUID 여부 확인 함수.
  - 에러: EmptyInputError, ExtractionError, PdfParseError, UnsupportedMediaTypeError.
  - 정규화 Raw 스키마 (extractor 내부, 테스트용):
    RawExtractionResponse, RawExtractionItem, RawPassage, RawQuestion,
    RawTranslation, RawVocabulary.
  - PDF 휴리스틱 상수:
    MIN_CHARS_PER_PAGE, MIN_ENGLISH_ALPHA_RATIO, MAX_BROKEN_UNICODE_RATIO,
    MIN_DENSITY_CHARS_PER_PAGE, VISION_DPI.
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
from extractor.pdf import (
    MAX_BROKEN_UNICODE_RATIO,
    MIN_CHARS_PER_PAGE,
    MIN_DENSITY_CHARS_PER_PAGE,
    MIN_ENGLISH_ALPHA_RATIO,
    VISION_DPI,
    extract_from_pdf,
)
from extractor.text import extract_from_text

__all__ = [
    # 프로토콜
    "Extractor",
    # 함수
    "extract_from_text",
    "extract_from_image",
    "extract_from_pdf",
    "is_sentinel",
    "make_llm_meta",
    "normalize",
    # 상수
    "SENTINEL_UUID",
    # PDF 휴리스틱 상수
    "MIN_CHARS_PER_PAGE",
    "MIN_ENGLISH_ALPHA_RATIO",
    "MAX_BROKEN_UNICODE_RATIO",
    "MIN_DENSITY_CHARS_PER_PAGE",
    "VISION_DPI",
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
