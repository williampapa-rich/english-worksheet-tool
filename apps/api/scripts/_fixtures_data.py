"""Phase 1 검수용 fixture 데이터 정의.

데이터 정의와 시드 로직의 분리 — 향후 fixture 추가/수정 시 이 파일만 편집.

offset 계산: body_text.find(phrase) 로 동적 계산 — 본문 1글자 수정에도 자동 동기화.
오타나 찾을 수 없는 phrase 는 시드 시점에 ValueError 로 즉시 실패.

7종 annotation (AnnotationKind):
  - top_label, bottom_label, highlight, bracket, arrow, inline_note, underline

fixture 3건 각각 5~7종을 포함해 모든 종류의 HWPX 렌더링을 검증 가능하게.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


# ─── fixture passage_id (고정 UUID) ─────────────────────────────────────────

FIXTURE_1_ID = uuid.UUID("00000000-0000-0000-0000-000000000101")
FIXTURE_2_ID = uuid.UUID("00000000-0000-0000-0000-000000000102")
FIXTURE_3_ID = uuid.UUID("00000000-0000-0000-0000-000000000103")


# ─── Span 헬퍼 ───────────────────────────────────────────────────────────────


def _span(body_text: str, phrase: str, nth: int = 1) -> dict[str, Any]:
    """phrase 의 nth 번째 등장 위치로 CharacterOffsetV1Span dict 를 반환.

    Args:
        body_text: 검색 대상 본문.
        phrase: 찾을 문구 (정확히 일치해야 함 — 대소문자 포함).
        nth: 몇 번째 등장을 반환할지 (1-based, 기본 1 = 첫 번째).

    Returns:
        AnnotationSpan (CharacterOffsetV1Span) 형태의 dict.

    Raises:
        ValueError: phrase 가 body_text 에 없거나 nth 번째가 없을 때.
    """
    start = -1
    search_from = 0
    for _ in range(nth):
        start = body_text.find(phrase, search_from)
        if start == -1:
            raise ValueError(
                f"Fixture 데이터 오류: '{phrase}' 의 {nth}번째 등장을 찾을 수 없음.\n"
                f"본문 앞 100자: {body_text[:100]!r}"
            )
        search_from = start + 1

    end = start + len(phrase)
    return {"span_format": "character_offset_v1", "start": start, "end": end}


def _target_span(body_text: str, phrase: str, nth: int = 1) -> dict[str, Any]:
    """화살표 도착점 span — _span 과 동일 로직, 명시적 이름."""
    return _span(body_text, phrase, nth=nth)


# ─── fixture 데이터 구조 ─────────────────────────────────────────────────────


@dataclass
class AnnotationSpec:
    """시드할 annotation 1건의 명세.

    kind, category, span 은 필수. 나머지는 kind 별 선택.
    arrow 는 arrow_target_span 이 필수 (SyntaxAnnotation validator 강제).

    span_nth: phrase 가 본문에 여러 번 등장할 때 몇 번째를 사용할지 (1-based).
              기본 1 = 첫 번째 등장.
    """

    kind: str
    category: str | None
    span_phrase: str  # body_text.find() 로 offset 계산할 구문
    color_index: int | None = None
    text: str | None = None
    bracket_style: str | None = None
    arrow_target_phrase: str | None = None  # arrow kind 일 때 도착점 구문
    span_nth: int = 1  # phrase 가 여러 번 나올 때 몇 번째를 사용할지 (1-based)
    annotation_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FixtureSpec:
    """Passage + annotation 명세 1건."""

    passage_id: uuid.UUID
    title: str
    body_text: str
    paragraphs: list[str]
    topic_tags: list[str]
    target_grade: str
    annotations: list[AnnotationSpec]


# ─── Fixture 1: 어법 변형 — AI 의사결정 투명성 ──────────────────────────────

_F1_BODY = (
    "The widespread adoption of artificial intelligence has raised concerns about "
    "transparency in decision-making processes. "
    "As algorithms become more complex, even their creators find it difficult to explain "
    "why a particular outcome was reached, which challenges the traditional notion of accountability."
)

FIXTURE_1 = FixtureSpec(
    passage_id=FIXTURE_1_ID,
    title="AI 의사결정 투명성",
    body_text=_F1_BODY,
    paragraphs=[_F1_BODY],
    topic_tags=["AI", "투명성", "어법", "가목적어"],
    target_grade="high_3",
    annotations=[
        # 1. top_label — 주어구
        AnnotationSpec(
            kind="top_label",
            category="phrase",
            span_phrase="The widespread adoption of artificial intelligence",
            text="주어구",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000101"),
        ),
        # 2. bottom_label — 동사 V 표시
        AnnotationSpec(
            kind="bottom_label",
            category="sentence_role",
            span_phrase="has raised",
            text="V",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000102"),
        ),
        # 3. highlight — 가목적어 구문 강조
        AnnotationSpec(
            kind="highlight",
            category="note",
            span_phrase="find it difficult to explain",
            color_index=1,
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000103"),
        ),
        # 4. underline — 가목적어 it 밑줄 (본문에 "it" 이 2회 등장 — 2번째가 가목적어)
        AnnotationSpec(
            kind="underline",
            category="note",
            span_phrase="it",
            span_nth=2,
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000104"),
        ),
        # 5. bracket — 부사절 괄호
        AnnotationSpec(
            kind="bracket",
            category="clause",
            span_phrase="As algorithms become more complex",
            bracket_style="()",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000105"),
        ),
        # 6. top_label — 관계절 라벨
        AnnotationSpec(
            kind="top_label",
            category="clause",
            span_phrase="which challenges the traditional notion of accountability",
            text="관계절",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000106"),
        ),
        # 7. inline_note — 가목적어/진목적어 선택지 노트
        AnnotationSpec(
            kind="inline_note",
            category="note",
            span_phrase="it difficult",
            text="(it / them)",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000107"),
        ),
    ],
)


# ─── Fixture 2: 빈칸 추론 — 기억의 재구성 본질 ─────────────────────────────

_F2_BODY = (
    "Researchers have long debated whether memory functions as a faithful recording "
    "of past events or as a reconstructive process shaped by present beliefs. "
    "Recent neuroimaging studies suggest that the act of recalling a memory activates "
    "the same neural pathways as the original experience, but with subtle modifications each time. "
    "This finding implies that every recollection is, in a sense, a new creation."
)

FIXTURE_2 = FixtureSpec(
    passage_id=FIXTURE_2_ID,
    title="기억의 재구성 본질",
    body_text=_F2_BODY,
    paragraphs=[_F2_BODY],
    topic_tags=["기억", "신경과학", "빈칸추론", "명사절"],
    target_grade="high_3",
    annotations=[
        # 1. top_label — 명사절(목적어) 라벨
        AnnotationSpec(
            kind="top_label",
            category="clause",
            span_phrase=(
                "whether memory functions as a faithful recording "
                "of past events or as a reconstructive process shaped by present beliefs"
            ),
            text="명사절(목적어)",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000201"),
        ),
        # 2. bracket — 분사구 괄호
        AnnotationSpec(
            kind="bracket",
            category="phrase",
            span_phrase="shaped by present beliefs",
            bracket_style="[]",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000202"),
        ),
        # 3. bottom_label — 주어 S 표시
        AnnotationSpec(
            kind="bottom_label",
            category="sentence_role",
            span_phrase="Recent neuroimaging studies",
            text="S",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000203"),
        ),
        # 4. bottom_label — 동사 V 표시
        AnnotationSpec(
            kind="bottom_label",
            category="sentence_role",
            span_phrase="suggest",
            text="V",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000204"),
        ),
        # 5. highlight — 비교구문 강조
        AnnotationSpec(
            kind="highlight",
            category="note",
            span_phrase="the same neural pathways as the original experience",
            color_index=3,
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000205"),
        ),
        # 6. inline_note — 삽입구 노트
        AnnotationSpec(
            kind="inline_note",
            category="note",
            span_phrase="in a sense",
            text="(삽입구)",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000206"),
        ),
        # 7. highlight — 빈칸 영역 강조 (creation 을 빈칸으로 상정)
        AnnotationSpec(
            kind="highlight",
            category="note",
            span_phrase="creation",
            color_index=4,
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000207"),
        ),
    ],
)


# ─── Fixture 3: 어휘 변형 다중 매트릭스 — 소셜 네트워크와 소비자 행동 ────────

_F3_BODY = (
    "Economists often (A) [overlook / emphasize] the role of social networks "
    "in shaping consumer behavior. "
    "While traditional models (B) [assume / reject] that individuals make rational "
    "choices independently, real-world data reveal that purchasing decisions are heavily "
    "(C) [influenced / isolated] by peer recommendations and online reviews."
)

FIXTURE_3 = FixtureSpec(
    passage_id=FIXTURE_3_ID,
    title="소셜 네트워크와 소비자 행동",
    body_text=_F3_BODY,
    paragraphs=[_F3_BODY],
    topic_tags=["경제", "소비자행동", "어휘변형", "다중선택지"],
    target_grade="high_2",
    annotations=[
        # 1. top_label — 선택지 A 라벨
        AnnotationSpec(
            kind="top_label",
            category="other",
            span_phrase="(A) [overlook / emphasize]",
            text="선택지 A",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000301"),
        ),
        # 2. top_label — 선택지 B 라벨
        AnnotationSpec(
            kind="top_label",
            category="other",
            span_phrase="(B) [assume / reject]",
            text="선택지 B",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000302"),
        ),
        # 3. top_label — 선택지 C 라벨
        AnnotationSpec(
            kind="top_label",
            category="other",
            span_phrase="(C) [influenced / isolated]",
            text="선택지 C",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000303"),
        ),
        # 4. bracket — 부사절 괄호
        AnnotationSpec(
            kind="bracket",
            category="clause",
            span_phrase=(
                "While traditional models (B) [assume / reject] that individuals "
                "make rational choices independently"
            ),
            bracket_style="()",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000304"),
        ),
        # 5. bottom_label — 명사절(목적어) 라벨
        AnnotationSpec(
            kind="bottom_label",
            category="clause",
            span_phrase="that individuals make rational choices independently",
            text="명사절",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000305"),
        ),
        # 6. highlight — 핵심 어휘 강조
        AnnotationSpec(
            kind="highlight",
            category="note",
            span_phrase="peer recommendations and online reviews",
            color_index=5,
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000306"),
        ),
        # 7. arrow — purchasing decisions → peer recommendations (의미 관계)
        AnnotationSpec(
            kind="arrow",
            category="phrase",
            span_phrase="purchasing decisions",
            arrow_target_phrase="peer recommendations",
            annotation_id=uuid.UUID("10000000-0000-0000-0000-000000000307"),
        ),
    ],
)


# ─── 전체 fixture 목록 ───────────────────────────────────────────────────────

ALL_FIXTURES: list[FixtureSpec] = [FIXTURE_1, FIXTURE_2, FIXTURE_3]
