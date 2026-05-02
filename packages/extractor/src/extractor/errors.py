"""extractor 패키지 전용 예외 계층.

ADR-0003 §D-3.5 에서 정의된 extractor 레이어의 에러 정책:
  - extractor 는 LLM 래퍼의 에러를 그대로 propagate (자체 재시도 없음).
  - 입력 유효성 문제는 자체 예외로 명시.
  - PDF 파싱 실패는 자동 Vision fallback 없이 PdfParseError raise.
"""

from __future__ import annotations


class ExtractorError(Exception):
    """extractor 패키지 예외 기반 클래스."""


class EmptyInputError(ExtractorError):
    """입력이 비어있거나 공백만 있을 때.

    ``extract_from_text`` 에 빈 문자열 또는 공백만 전달된 경우.
    API 레이어는 이를 422 Unprocessable Entity 로 매핑한다.
    """


class PdfParseError(ExtractorError):
    """PDF 파싱 실패 (corrupt 또는 암호화된 PDF 등).

    ADR-0003 §D-3.5 에 따라 자동 Vision fallback 없이 raise.
    사용자가 ``force_vision=True`` 로 재시도할 수 있다.
    API 레이어는 이를 422 Unprocessable Entity 로 매핑한다.
    """


class UnsupportedMediaTypeError(ExtractorError):
    """지원하지 않는 이미지 MIME type.

    지원 타입: ``image/png``, ``image/jpeg``, ``image/webp``.
    API 레이어는 이를 422 Unprocessable Entity 로 매핑한다.
    """

    def __init__(self, media_type: str) -> None:
        super().__init__(
            f"지원하지 않는 media_type: '{media_type}'. "
            "지원 타입: image/png, image/jpeg, image/webp."
        )
        self.media_type = media_type


class ExtractionError(ExtractorError):
    """정규화 또는 추출 중 일반 에러.

    LLM 출력이 예상치 못한 형태이거나 정규화 중 복구 불가 오류가 발생할 때.
    """
