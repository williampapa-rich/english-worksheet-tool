"""PDF 입력 추출 경로 — PyMuPDF 1차 시도 후 Vision fallback.

ADR-0003 §D-3.3 의 4종 휴리스틱으로 텍스트 레이어 품질 판단:
  1. 페이지당 평균 문자 수 < 50  → False (스캔본 가능성)
  2. 영어 알파벳 비율 < 30%     → False (이미지 PDF OCR 노이즈 또는 비-영어)
  3. 깨진 unicode (PUA / replacement char) 비율 > 5%  → False
  4. 페이지당 평균 문자 수 < 200  → False (밀도 부족 — 1/2/3 과 별개 임계값)

판단이 보수적 — 의심스러우면 Vision 으로 fallback.
false negative 보다 false positive 가 사용자 신뢰도에 더 유해.

PM-1: 다중 지문 PDF 지원 — list[ExtractionResult] 반환.
  다중 페이지의 다중 지문이 일상 케이스 (모의고사 1회분 = 28개 지문 등).
PM-3: force_vision=True 옵션으로 휴리스틱 우회.

CLAUDE.md §8.3 강제:
  Anthropic SDK 직접 호출 금지. 모든 LLM 호출은 packages/llm/ 경유.
  extract_from_text / extract_from_image 를 통한다.

PyMuPDF 채택 사유 (CLAUDE.md §3.6 / §8.4):
  - 대안 검토: pdfplumber (레이아웃 우수, 한국어 폰트 매핑 미흡),
    pdfminer.six (텍스트만, 이미지 변환 별도), pypdf (메타/분할 위주).
  - exam-generator audit §1.6 에서 운영 검증됨 (app/llm/pdf.py).
  - 텍스트 추출 + PNG 변환 (Vision fallback) + 한국어 PDF 처리를 단일 라이브러리로.
  → PyMuPDF 채택.

DPI 200 채택 사유:
  - 150 이하: 소문자 구분 / 수식 / 취소선 OCR 정확도 저하.
  - 300 이상: 이미지 크기 ~2.25× → 토큰 비용 증가 (CLAUDE.md §3.4 비용 원칙).
  - 200: Vision 정확도와 토큰 비용의 균형점 (1:1 trade-off 경계).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Final

import fitz  # PyMuPDF — import name 은 fitz 가 표준
from llm.client import StructuredLLMClient

from extractor.errors import EmptyInputError, PdfParseError
from extractor.image import extract_from_image
from extractor.text import extract_from_text
from shared.schemas.extraction import ExtractionResult

# ─── 휴리스틱 임계값 — 모듈 상수로 노출, 향후 운영 튜닝 가능 ──────────────────
# ADR-0003 §D-3.3 에 명시된 값 그대로 채택.

# 휴리스틱 1: 페이지당 평균 문자 수 최소값 (단순 스캔본 감지)
MIN_CHARS_PER_PAGE: Final[int] = 50

# 휴리스틱 2: 영어 알파벳 비율 최소값 (이미지 PDF OCR 노이즈 / 비-영어 감지)
MIN_ENGLISH_ALPHA_RATIO: Final[float] = 0.30

# 휴리스틱 3: 깨진 unicode 비율 최대값 (PUA / replacement char)
MAX_BROKEN_UNICODE_RATIO: Final[float] = 0.05

# 휴리스틱 4: 페이지당 평균 문자 수 최소값 (밀도 기준 — 1번과 다른 임계값)
# 1번은 절대 최솟값(< 50), 4번은 콘텐츠 밀도 기준(< 200) — 양쪽 모두 통과해야 True
MIN_DENSITY_CHARS_PER_PAGE: Final[int] = 200

# Vision 변환 DPI — 200 권고 (정확도와 비용 균형)
VISION_DPI: Final[int] = 200

# 기본 프롬프트 ID
_DEFAULT_TEXT_PROMPT_ID: Final[str] = "extract-text-v0"
_DEFAULT_IMAGE_PROMPT_ID: Final[str] = "extract-image-v0"


@dataclass(frozen=True)
class _TextLayerQuality:
    """PDF 텍스트 레이어 품질 측정 결과.

    is_extractable() 이 True 이면 텍스트 경로로, False 이면 Vision 경로로 분기.
    """

    total_chars: int
    page_count: int
    english_alpha_ratio: float
    broken_unicode_ratio: float

    def is_extractable(self) -> bool:
        """4종 휴리스틱 모두 통과해야 True (AND 조건).

        보수적 판단 — 하나라도 실패하면 Vision fallback.
        """
        # 빈 문서
        if self.page_count == 0 or self.total_chars == 0:
            return False

        chars_per_page = self.total_chars / self.page_count

        # 휴리스틱 1: 페이지당 문자 수 < 50
        if chars_per_page < MIN_CHARS_PER_PAGE:
            return False

        # 휴리스틱 2: 영어 알파벳 비율 < 30%
        if self.english_alpha_ratio < MIN_ENGLISH_ALPHA_RATIO:
            return False

        # 휴리스틱 3: 깨진 unicode 비율 > 5%
        if self.broken_unicode_ratio > MAX_BROKEN_UNICODE_RATIO:
            return False

        # 휴리스틱 4: 밀도 기준 페이지당 문자 수 < 200
        if chars_per_page < MIN_DENSITY_CHARS_PER_PAGE:
            return False

        return True


async def extract_from_pdf(
    pdf_bytes: bytes,
    *,
    llm_client: StructuredLLMClient,
    force_vision: bool = False,
    text_prompt_template_id: str = _DEFAULT_TEXT_PROMPT_ID,
    image_prompt_template_id: str = _DEFAULT_IMAGE_PROMPT_ID,
) -> list[ExtractionResult]:
    """PDF → ExtractionResult 리스트.

    ADR-0003 §D-3.3 의 분기 로직:
      1. force_vision=True 이면 즉시 Vision 경로 (PM-3).
      2. PyMuPDF 로 텍스트 추출 시도.
      3. 4종 휴리스틱으로 품질 판단.
      4. 통과 → extract_from_text 호출 (저비용).
      5. 미통과 → PDF 각 페이지를 PNG 로 변환 후 extract_from_image 호출 (고비용).

    PM-1: 다중 페이지 / 다중 지문 PDF 지원.
      텍스트 경로: 전체 텍스트를 하나의 extract_from_text 로 처리 (LLM 이 지문 분리).
      Vision 경로: 페이지별 extract_from_image 후 결과를 평탄화.

    CLAUDE.md §8.3 강제:
      Anthropic SDK 직접 호출 금지. extract_from_text / extract_from_image 경유.

    Args:
        pdf_bytes: PDF raw bytes. 빈 bytes 면 EmptyInputError.
        llm_client: StructuredLLMClient 구현체 (Vision 지원 필요 — Vision 경로).
        force_vision: True 면 휴리스틱 우회, 즉시 Vision 경로 (PM-3).
        text_prompt_template_id: 텍스트 경로 프롬프트 템플릿 ID.
        image_prompt_template_id: Vision 경로 프롬프트 템플릿 ID.

    Returns:
        list[ExtractionResult]: PM-1 — 다중 지문 PDF 의 모든 지문 평탄화.
            단일 지문 PDF 도 길이 1 list 반환.

    Raises:
        EmptyInputError: pdf_bytes 비어있음.
        PdfParseError: PyMuPDF 파싱 실패 (corrupt / 암호화된 PDF).
            force_vision=True 로 우회 가능.
        LLMSchemaValidationError / LLMTimeoutError / ExtractionError:
            하위 어댑터에서 propagate.
    """
    if not pdf_bytes:
        raise EmptyInputError("입력 PDF 가 비어있습니다.")

    # PM-3: force_vision=True 면 휴리스틱 우회
    if force_vision:
        return await _extract_via_vision(pdf_bytes, llm_client, image_prompt_template_id)

    # PyMuPDF 1차 시도
    try:
        text_layer, page_count = _extract_text_layer(pdf_bytes)
    except Exception as exc:
        raise PdfParseError(
            f"PyMuPDF 가 PDF 파싱에 실패했습니다: {exc}. force_vision=True 로 재시도할 수 있습니다."
        ) from exc

    quality = _assess_quality(text_layer, page_count)
    if quality.is_extractable():
        # 텍스트 경로 — 저비용 (PyMuPDF 추출 텍스트 전달)
        return await extract_from_text(
            text_layer,
            llm_client=llm_client,
            prompt_template_id=text_prompt_template_id,
        )

    # 휴리스틱 미통과 — Vision fallback
    return await _extract_via_vision(pdf_bytes, llm_client, image_prompt_template_id)


def _extract_text_layer(pdf_bytes: bytes) -> tuple[str, int]:
    """PyMuPDF 로 모든 페이지 텍스트 추출.

    Args:
        pdf_bytes: PDF raw bytes.

    Returns:
        (전체 텍스트, 페이지 수) tuple.

    Raises:
        Exception: PyMuPDF 파싱 실패 (호출부에서 PdfParseError 로 래핑).
    """
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:  # type: ignore[call-overload]
        page_count = len(doc)
        pages_text = [page.get_text() for page in doc]
    return "\n\n".join(pages_text), page_count


def _assess_quality(text: str, page_count: int) -> _TextLayerQuality:
    """4종 휴리스틱 측정.

    Args:
        text: PyMuPDF 추출 전체 텍스트.
        page_count: PDF 페이지 수.

    Returns:
        _TextLayerQuality 인스턴스.
    """
    total_chars = len(text)

    if total_chars == 0 or page_count == 0:
        return _TextLayerQuality(
            total_chars=total_chars,
            page_count=page_count,
            english_alpha_ratio=0.0,
            broken_unicode_ratio=0.0,
        )

    # 영어 알파벳 비율 계산 — ASCII 알파벳 (a-z, A-Z)
    english_alpha_count = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    english_alpha_ratio = english_alpha_count / total_chars

    # 깨진 unicode 비율 계산
    # PUA (Private Use Area): U+E000..U+F8FF, U+F0000..U+FFFFF, U+100000..U+10FFFF
    # Replacement character: U+FFFD
    # Surrogate pair: U+D800..U+DFFF (Python str 에서는 거의 없지만 방어)
    broken_count = 0
    for ch in text:
        cp = ord(ch)
        category = unicodedata.category(ch)
        if (
            ch == "�"  # replacement character
            or (0xE000 <= cp <= 0xF8FF)  # BMP PUA
            or (0xF0000 <= cp <= 0xFFFFF)  # Plane 15 PUA
            or (0x100000 <= cp <= 0x10FFFF)  # Plane 16 PUA
            or category == "Cs"  # surrogate
        ):
            broken_count += 1
    broken_unicode_ratio = broken_count / total_chars

    return _TextLayerQuality(
        total_chars=total_chars,
        page_count=page_count,
        english_alpha_ratio=english_alpha_ratio,
        broken_unicode_ratio=broken_unicode_ratio,
    )


async def _extract_via_vision(
    pdf_bytes: bytes,
    llm_client: StructuredLLMClient,
    prompt_template_id: str,
) -> list[ExtractionResult]:
    """PDF 각 페이지를 PNG 로 변환 후 extract_from_image 호출.

    다중 페이지 PDF 의 경우 페이지별로 호출하고 결과를 평탄한 list 로 합침 (PM-1).

    Args:
        pdf_bytes: PDF raw bytes.
        llm_client: StructuredLLMClient 구현체.
        prompt_template_id: Vision 프롬프트 템플릿 ID.

    Returns:
        list[ExtractionResult]: 모든 페이지 결과 평탄화.
    """
    results: list[ExtractionResult] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:  # type: ignore[call-overload]
        for page in doc:
            pix = page.get_pixmap(dpi=VISION_DPI)
            png_bytes: bytes = pix.tobytes("png")
            page_results = await extract_from_image(
                png_bytes,
                "image/png",
                llm_client=llm_client,
                prompt_template_id=prompt_template_id,
            )
            results.extend(page_results)
    return results
