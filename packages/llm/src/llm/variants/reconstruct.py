"""Stage 1: 원본 Question 정답으로 본문 복원.

Cross-type variant 생성의 첫 단계 — 원본 문제가 본문에 가한 변형
(빈칸, 마커, 문장 제거, 단락 분리 등) 을 정답을 사용해 되돌린다.

카탈로그 v0.5 §3.2 복원 규칙 구현:
  - PASSTHROUGH: 본문 이미 완전 — 변형 없이 그대로 반환.
  - BLANK_FILL: `______` 를 정답 선택지로 채움.
  - MARKER_REMOVE (underline): `_..._` 마커 제거, 내부 텍스트 유지.
  - MARKER_REMOVE (grammar/vocab): ①~⑤ 마커 + 언더스코어 제거.
  - IRRELEVANT_REMOVE: 무관 문장 (정답 번호) 제거 + ①~⑤ 마커 제거.
  - ORDER_REORDER: (A)/(B)/(C) 단락을 정답 순서로 재배열 + 라벨 제거.
  - INSERTION_INSERT: 정답 위치에 주어진 문장 삽입 + ①~⑤ 마커 제거.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel

from shared.schemas.passage import Passage
from shared.schemas.question import Question, QuestionType

# ─── 빈칸 표기 (수능 표준 6개 언더스코어) ─────────────────────────────────────
_BLANK_RE = re.compile(r"_{6,}")

# ─── 원문자 마커 (①②③④⑤) ─────────────────────────────────────────────────
_CIRCLED_DIGITS = "①②③④⑤"
_CIRCLED_MARKER_RE = re.compile(r"[①②③④⑤]")

# ─── grammar/vocab 인라인 마커: _단어_ 또는 _(A) word/word_ 형태 ──────────────
# 언더스코어로 감싸인 구문 — 내부 텍스트만 남기고 마커 제거
_UNDERSCORE_MARKER_RE = re.compile(r"_([^_]+)_")

# ─── 순서 배열 단락 라벨 (A)/(B)/(C) ──────────────────────────────────────────
_ORDER_LABEL_RE = re.compile(r"\(([ABC])\)\s*")


class ReconstructionMethod(StrEnum):
    PASSTHROUGH = "passthrough"  # passage already complete
    BLANK_FILL = "blank_fill"  # fill ______ with answer
    MARKER_REMOVE = "marker_remove"  # remove underline/circled markers
    IRRELEVANT_REMOVE = "irrelevant_remove"  # remove irrelevant sentence
    ORDER_REORDER = "order_reorder"  # reorder (A)/(B)/(C) segments
    INSERTION_INSERT = "insertion_insert"  # insert sentence at answer position


class ReconstructedPassage(BaseModel):
    text: str
    method: ReconstructionMethod
    source_question_type: str


# ─── 유형별 메서드 매핑 ────────────────────────────────────────────────────────

# PASSTHROUGH 적용 type 집합
_PASSTHROUGH_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.PURPOSE_18,
        QuestionType.MOOD_19,
        QuestionType.ASSERTION_20,
        QuestionType.GIST_22,
        QuestionType.THEME_23,
        QuestionType.TITLE_24,
        QuestionType.FIGURE_MATCH_26,
        QuestionType.NOTICE_27,
        QuestionType.NOTICE_28,
        QuestionType.SUMMARY_40,
        QuestionType.LONG_SET_41_42,
        QuestionType.LONG_SET_43_45,
    }
)

_BLANK_FILL_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.BLANK_PHRASE_31,
        QuestionType.BLANK_CLAUSE_32,
        QuestionType.BLANK_CLAUSE_33,
        QuestionType.BLANK_CLAUSE_34,
    }
)

_MARKER_REMOVE_UNDERLINE_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.UNDERLINE_IMPLICATION_21,
    }
)

_MARKER_REMOVE_GRAMMAR_VOCAB_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.GRAMMAR_29,
        QuestionType.VOCABULARY_30,
    }
)

_IRRELEVANT_REMOVE_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.IRRELEVANT_SENTENCE_35,
    }
)

_ORDER_REORDER_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.ORDER_36,
        QuestionType.ORDER_37,
    }
)

_INSERTION_INSERT_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.INSERTION_38,
        QuestionType.INSERTION_39,
    }
)


def reconstruction_method_for_type(question_type: str) -> ReconstructionMethod:
    """Map question type to its reconstruction method.

    Args:
        question_type: QuestionType enum value string (e.g. 'blank_phrase_31').

    Returns:
        ReconstructionMethod for the given type.

    Raises:
        ValueError: If question_type is not a known QuestionType.
    """
    try:
        qt = QuestionType(question_type)
    except ValueError as exc:
        raise ValueError(f"알 수 없는 QuestionType: '{question_type}'.") from exc

    if qt in _PASSTHROUGH_TYPES:
        return ReconstructionMethod.PASSTHROUGH
    if qt in _BLANK_FILL_TYPES:
        return ReconstructionMethod.BLANK_FILL
    if qt in _MARKER_REMOVE_UNDERLINE_TYPES:
        return ReconstructionMethod.MARKER_REMOVE
    if qt in _MARKER_REMOVE_GRAMMAR_VOCAB_TYPES:
        return ReconstructionMethod.MARKER_REMOVE
    if qt in _IRRELEVANT_REMOVE_TYPES:
        return ReconstructionMethod.IRRELEVANT_REMOVE
    if qt in _ORDER_REORDER_TYPES:
        return ReconstructionMethod.ORDER_REORDER
    if qt in _INSERTION_INSERT_TYPES:
        return ReconstructionMethod.INSERTION_INSERT

    # CHART_25 (비활성) — fallback to PASSTHROUGH
    return ReconstructionMethod.PASSTHROUGH


# ─── 내부 복원 헬퍼 ────────────────────────────────────────────────────────────


def _passthrough(body_text: str) -> str:
    return body_text


def _blank_fill(body_text: str, question: Question) -> str:
    """빈칸 `______` 를 정답 선택지로 채운다.

    answer 는 1-based. choices 가 비었거나 answer 범위를 벗어나면 빈칸을 그대로 둔다.
    """
    if not question.choices or not (1 <= question.answer <= len(question.choices)):
        return body_text

    correct_choice = question.choices[question.answer - 1]
    # 첫 번째 빈칸만 채움 (빈칸추론 문제는 빈칸이 1개)
    result, substitutions = _BLANK_RE.subn(correct_choice, body_text, count=1)
    if substitutions == 0:
        # 본문에 빈칸 마커가 없으면 원문 반환
        return body_text
    return result


def _marker_remove_underline(body_text: str) -> str:
    """underline_implication_21: `_..._` 마커 제거, 내부 텍스트 보존."""
    return _UNDERSCORE_MARKER_RE.sub(r"\1", body_text)


def _marker_remove_grammar_vocab(body_text: str) -> str:
    """grammar_29 / vocabulary_30: ①~⑤ 원문자 + 언더스코어 마커 제거.

    처리 순서:
      1. `_phrase_` → phrase (언더스코어 마커 제거).
      2. ①②③④⑤ 원문자 제거.
    """
    text = _UNDERSCORE_MARKER_RE.sub(r"\1", body_text)
    text = _CIRCLED_MARKER_RE.sub("", text)
    # 원문자 제거 후 남는 연속 공백 정리
    text = re.sub(r"  +", " ", text)
    return text.strip()


def _irrelevant_remove(body_text: str, question: Question) -> str:
    """irrelevant_sentence_35: 정답 위치의 무관 문장을 제거하고 ①~⑤ 마커를 제거한다.

    본문 구조 가정:
      - ① 문장1 ② 문장2 ③ 문장3 ④ 문장4 ⑤ 문장5 형태.
      - answer (1-based) 번째 원문자 뒤에 오는 문장이 무관 문장.
      - 문장 경계는 원문자 위치로 구분.

    처리:
      1. 원문자 위치로 본문을 분할 → (마커 이전 도입부, 문장1, 문장2, ...).
      2. answer 번째 문장 제거.
      3. 나머지 문장 합치고 원문자 제거.
    """
    # 원문자로 분할: 첫 원문자 전 부분 = intro, 이후 각 원문자부터 다음 원문자까지
    parts = _CIRCLED_MARKER_RE.split(body_text)
    # parts[0] = 원문자 이전 텍스트 (도입부 또는 빈 문자열)
    # parts[1..] = 각 원문자 뒤 텍스트 조각

    sentences = parts[1:]  # 문장 조각 리스트 (1-indexed로 매핑: sentences[0] = 첫 번째 문장)

    if not sentences:
        # 원문자가 없으면 마커 제거만
        return _CIRCLED_MARKER_RE.sub("", body_text).strip()

    answer_idx = question.answer - 1  # 0-based

    if 0 <= answer_idx < len(sentences):
        sentences.pop(answer_idx)

    # 도입부 + 남은 문장 합치기
    intro = parts[0].rstrip()
    body = " ".join(s.strip() for s in sentences if s.strip())

    if intro and body:
        return f"{intro} {body}"
    return intro or body


def _order_reorder(body_text: str, question: Question) -> str:
    """paragraph_order_36 / 37: (A)/(B)/(C) 단락을 정답 순서로 재배열한다.

    본문 구조 가정:
      - 도입 단락 + (A) ... (B) ... (C) ... 형태.
      - question.choices 의 정답 항목에 "(B)-(A)-(C)" 형태 순서 정보 포함.
      - 또는 question.sub_passages 에 [(A) 텍스트, (B) 텍스트, (C) 텍스트] 저장.

    처리 순서:
      1. sub_passages 가 있으면 그것을 사용 (이미 분할됨).
      2. 없으면 body_text 에서 (A)/(B)/(C) 단락 직접 분리.
      3. 정답 선택지에서 순서 파싱.
      4. 순서대로 재조합 + 라벨 제거.
    """
    # 도입부 추출: 첫 번째 (A)/(B)/(C) 라벨 이전 텍스트
    first_label_match = _ORDER_LABEL_RE.search(body_text)
    intro = body_text[: first_label_match.start()].strip() if first_label_match else ""

    # (A)/(B)/(C) 단락 분리
    if question.sub_passages:
        # sub_passages 는 list[list[str]] — 각 내부 list 가 단락 문장들
        segments: dict[str, str] = {}
        labels = ["A", "B", "C"]
        for i, sp in enumerate(question.sub_passages[:3]):
            label = labels[i] if i < len(labels) else str(i)
            segments[label] = " ".join(sp) if isinstance(sp, list) else str(sp)
    else:
        # body_text 에서 직접 분리
        segments = _extract_abc_segments(body_text)

    if not segments:
        # 분리 실패 — 라벨만 제거하고 반환
        return _ORDER_LABEL_RE.sub("", body_text).strip()

    # 정답 선택지에서 순서 파싱 (예: "(B)-(A)-(C)" → ["B", "A", "C"])
    order = _parse_order_from_choices(question)

    if not order:
        # 순서 파싱 실패 — 원래 순서 A→B→C
        order = sorted(segments.keys())

    # 재조합
    ordered_parts = [segments[label] for label in order if label in segments]
    body = " ".join(p.strip() for p in ordered_parts if p.strip())

    if intro and body:
        return f"{intro} {body}"
    return intro or body


def _extract_abc_segments(body_text: str) -> dict[str, str]:
    """body_text 에서 (A)/(B)/(C) 단락 텍스트를 추출한다."""
    segments: dict[str, str] = {}
    # (A), (B), (C) 위치로 분할
    split_positions: list[tuple[str, int, int]] = []
    for m in _ORDER_LABEL_RE.finditer(body_text):
        split_positions.append((m.group(1), m.start(), m.end()))

    for i, (label, _start, end) in enumerate(split_positions):
        next_start = split_positions[i + 1][1] if i + 1 < len(split_positions) else len(body_text)
        segments[label] = body_text[end:next_start].strip()

    return segments


def _parse_order_from_choices(question: Question) -> list[str]:
    """choices[answer-1] 에서 순서를 파싱한다.

    형태 예: "(B)-(A)-(C)", "B-A-C", "(B) - (A) - (C)"
    """
    if not question.choices or not (1 <= question.answer <= len(question.choices)):
        return []

    correct_choice = question.choices[question.answer - 1]
    # 알파벳 A/B/C 를 순서대로 추출
    labels = re.findall(r"\b([ABC])\b", correct_choice)
    if len(labels) == 3 and set(labels) == {"A", "B", "C"}:
        return labels
    return []


def _insertion_insert(body_text: str, question: Question) -> str:
    """sentence_insertion_38 / 39: 정답 위치에 주어진 문장을 삽입한다.

    본문 구조 가정:
      - ① 문장1 ② 문장2 ③ 문장3 ④ 문장4 ⑤ 문장5 형태.
      - question.given_sentence 에 삽입할 문장 저장.
      - answer (1-based) 번째 원문자 앞에 삽입.

    처리:
      1. 원문자로 본문 분할.
      2. 정답 위치에 given_sentence 삽입.
      3. 원문자 마커 제거.
    """
    given = (question.given_sentence or "").strip()
    if not given:
        # given_sentence 없으면 마커 제거만
        return _CIRCLED_MARKER_RE.sub("", body_text).strip()

    # 원문자 위치로 분할
    parts = _CIRCLED_MARKER_RE.split(body_text)
    # parts[0] = 첫 원문자 이전 (도입부)
    # parts[1..] = 각 원문자 이후 텍스트

    sentences = list(parts[1:])  # 원문자 뒤 문장 조각들 (0-based)

    answer_idx = question.answer - 1  # 0-based 삽입 위치 (이 인덱스 앞에 삽입)

    # 삽입: answer_idx 번째 문장 앞에 given 삽입
    # 원문자 위치 기준: ① 앞에 삽입 → answer_idx=0 이면 sentences 앞에 삽입
    if 0 <= answer_idx <= len(sentences):
        sentences.insert(answer_idx, given)
    else:
        sentences.append(given)

    intro = parts[0].rstrip()
    body = " ".join(s.strip() for s in sentences if s.strip())

    if intro and body:
        return f"{intro} {body}"
    return intro or body


# ─── 공개 엔트리포인트 ─────────────────────────────────────────────────────────


def reconstruct_passage(passage: Passage, question: Question) -> ReconstructedPassage:
    """원본 Question 의 정답을 사용해 Passage 본문을 복원한다.

    Cross-type variant 생성 Stage 1 — 원본 문제 유형에 따라 적절한 복원 방법을
    선택하고 완전한 본문 텍스트를 반환한다.

    Args:
        passage: 원본 Passage (body_text, paragraphs 사용).
        question: 원본 Question (type, answer, choices, given_sentence, sub_passages 사용).

    Returns:
        ReconstructedPassage — 복원된 텍스트 + 사용된 방법 + 원본 type.

    Note:
        paragraphs 가 있으면 joined text 를 복원 대상으로 사용한다.
        paragraphs 가 없으면 body_text 를 그대로 사용.
    """
    body = (" ".join(passage.paragraphs) if passage.paragraphs else passage.body_text).strip()

    method = reconstruction_method_for_type(str(question.type))

    match method:
        case ReconstructionMethod.PASSTHROUGH:
            text = _passthrough(body)
        case ReconstructionMethod.BLANK_FILL:
            text = _blank_fill(body, question)
        case ReconstructionMethod.MARKER_REMOVE:
            qt = QuestionType(str(question.type))
            if qt in _MARKER_REMOVE_UNDERLINE_TYPES:
                text = _marker_remove_underline(body)
            else:
                text = _marker_remove_grammar_vocab(body)
        case ReconstructionMethod.IRRELEVANT_REMOVE:
            text = _irrelevant_remove(body, question)
        case ReconstructionMethod.ORDER_REORDER:
            text = _order_reorder(body, question)
        case ReconstructionMethod.INSERTION_INSERT:
            text = _insertion_insert(body, question)
        case _:
            text = body

    return ReconstructedPassage(
        text=text,
        method=method,
        source_question_type=str(question.type),
    )
