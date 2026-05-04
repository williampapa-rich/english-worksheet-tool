"""폰트 metric 측정 — 라벨 수평 align 보정 (P1-8b fix 2).

라벨 단락은 본문과 분리된 단락이라 본문 단어 위/아래 정렬을 위해 leading whitespace
개수를 폰트 metric 으로 산출해야 한다. pillow ImageFont.getlength() 로 글자 폭을
실측한다.

CLAUDE.md §3.6: pillow 는 폰트 metric 측정의 사실상 표준 라이브러리.
직접 TrueType 파서 작성 회피.

폰트 fallback 정책 (Phase 1 baseline):
    macOS Times New Roman → Times → 시스템 default. 폰트 파일 번들링은 라이센스
    영향 (CLAUDE.md §11 Open Question, 매핑 카탈로그 §6 #5) — Phase 1 에서는 시스템
    fallback 으로 baseline. Phase 2/3 에서 폰트 번들링 ADR 결정 시 교체.

정확도 한계:
    - 시스템 폰트가 없으면 pillow default 비트맵 폰트 fallback — 측정값이 실제 한컴
      렌더링과 어긋날 수 있음. 라벨이 ±1단어 범위 안에서 흔들릴 수 있다.
    - 한글 라벨 ("동격" 등) 은 한글 폰트 metric 이 다름 — TNR 로 측정 시 한글 글자
      폭이 0 또는 부정확. 라벨 텍스트가 ASCII 가 아니면 라벨 폰트 size 의 1.0em 으로
      보수 추정.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from PIL import ImageFont

logger = logging.getLogger(__name__)

# ── 폰트 후보 경로 ────────────────────────────────────────────────────────────
# 본문 / 라벨 모두 Times New Roman 또는 Times 사용 (라틴 영문 기준).
# 한글 라벨은 한글 폰트가 별도이므로 본 모듈에서는 polyfill 처리.
_FONT_CANDIDATES: list[str] = [
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/Library/Fonts/Times New Roman.ttf",
    "/System/Library/Fonts/Times.ttc",
    # Linux fallback
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/TTF/times.ttf",
]


@lru_cache(maxsize=8)
def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """주어진 size 로 폰트 객체를 로드 (캐시)."""
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError as e:
                logger.warning("Font load failed: %s — %s", path, e)
                continue
    logger.warning(
        "No system font found among candidates; falling back to pillow default. "
        "Label horizontal align may be inaccurate."
    )
    return ImageFont.load_default()


def _is_ascii(text: str) -> bool:
    return all(ord(c) < 128 for c in text)


def _measure(text: str, size: int) -> float:
    """텍스트의 폭을 pillow 픽셀 단위로 측정. 비-ASCII 는 size 의 1.0em 근사."""
    if not text:
        return 0.0
    font = _load_font(size)
    if not _is_ascii(text):
        # 한글/한자 등 — TNR 폰트가 글리프 미보유 시 0 반환 위험.
        # 보수적으로 size 의 1.0em (대략 한글 한 글자 폭) 로 근사.
        return float(size) * len(text)
    return float(font.getlength(text))


# ── 공개 API ─────────────────────────────────────────────────────────────────


# pt 단위 (HWP unit / 100): 본문 = 10pt, 라벨 = 7pt.
BODY_FONT_SIZE_PT = 10
LABEL_FONT_SIZE_PT = 7


def label_leading_spaces(
    body_prefix: str,
    body_size_pt: int = BODY_FONT_SIZE_PT,
    label_size_pt: int = LABEL_FONT_SIZE_PT,
) -> int:
    """라벨이 본문 ``body_prefix`` 끝 위치 위에 정렬되도록 라벨 단락에 채울 공백 수 산출.

    원리:
        1. 본문 charPr (body_size_pt) 로 ``body_prefix`` 폭 측정.
        2. 라벨 charPr (label_size_pt) 의 공백 1개 폭 측정.
        3. (1) ÷ (2) 정수 내림 = 라벨 단락 leading whitespace 개수.

    pixel 단위 align 은 보장되지 않음 (라벨 폰트 공백 폭이 정확히 본문 prefix 폭의
    약수가 아닐 수 있음). Phase 1 baseline — 라벨이 anchor 단어 가까이 오면 OK.

    빈 prefix → 0 반환 (라벨이 단락 좌측에 그대로).
    """
    if not body_prefix:
        return 0

    body_width_px = _measure(body_prefix, body_size_pt)
    label_space_px = _measure(" ", label_size_pt)

    if label_space_px <= 0:
        logger.warning("Label space width is zero — leading_spaces calculation skipped.")
        return 0

    return max(0, int(body_width_px / label_space_px))
