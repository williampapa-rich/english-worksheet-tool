"""Cross-type variant 호환성 매트릭스 (카탈로그 v0.5).

24개 QuestionType 간의 변환 가능 여부를 그룹 기반 규칙으로 정의한다.
'compatible' / 'conditional' / 'incompatible' 3단계 레벨 반환.
"""

from __future__ import annotations

from shared.schemas.question import QuestionType

# ─── 유형 그룹 정의 ────────────────────────────────────────────────────────────

# G1 추론
_G1: frozenset[str] = frozenset(
    {
        QuestionType.PURPOSE_18,
        QuestionType.MOOD_19,
        QuestionType.ASSERTION_20,
        QuestionType.UNDERLINE_IMPLICATION_21,
        QuestionType.GIST_22,
        QuestionType.THEME_23,
        QuestionType.TITLE_24,
    }
)

# G2 사실
_G2: frozenset[str] = frozenset(
    {
        QuestionType.FIGURE_MATCH_26,
        QuestionType.NOTICE_27,
        QuestionType.NOTICE_28,
    }
)

# G3 어휘/어법
_G3: frozenset[str] = frozenset(
    {
        QuestionType.GRAMMAR_29,
        QuestionType.VOCABULARY_30,
    }
)

# G4 빈칸추론
_G4: frozenset[str] = frozenset(
    {
        QuestionType.BLANK_PHRASE_31,
        QuestionType.BLANK_CLAUSE_32,
        QuestionType.BLANK_CLAUSE_33,
        QuestionType.BLANK_CLAUSE_34,
    }
)

# G5 논리
_G5: frozenset[str] = frozenset(
    {
        QuestionType.IRRELEVANT_SENTENCE_35,
        QuestionType.ORDER_36,
        QuestionType.ORDER_37,
        QuestionType.INSERTION_38,
        QuestionType.INSERTION_39,
    }
)

# G6 장문
_G6: frozenset[str] = frozenset(
    {
        QuestionType.SUMMARY_40,
        QuestionType.LONG_SET_41_42,
        QuestionType.LONG_SET_43_45,
    }
)

_ALL_GROUPS: list[frozenset[str]] = [_G1, _G2, _G3, _G4, _G5, _G6]


def _group_of(qt: str) -> frozenset[str] | None:
    for g in _ALL_GROUPS:
        if qt in g:
            return g
    return None


# ─── 한국어 라벨 매핑 ──────────────────────────────────────────────────────────

_LABELS: dict[str, str] = {
    QuestionType.PURPOSE_18: "목적(18)",
    QuestionType.MOOD_19: "심경/분위기(19)",
    QuestionType.ASSERTION_20: "주장(20)",
    QuestionType.UNDERLINE_IMPLICATION_21: "밑줄-함의(21)",
    QuestionType.GIST_22: "요지(22)",
    QuestionType.THEME_23: "주제(23)",
    QuestionType.TITLE_24: "제목(24)",
    QuestionType.CHART_25: "도표(25)",
    QuestionType.FIGURE_MATCH_26: "그림-일치(26)",
    QuestionType.NOTICE_27: "안내문-불일치(27)",
    QuestionType.NOTICE_28: "안내문-일치(28)",
    QuestionType.GRAMMAR_29: "어법(29)",
    QuestionType.VOCABULARY_30: "어휘(30)",
    QuestionType.BLANK_PHRASE_31: "빈칸-구(31)",
    QuestionType.BLANK_CLAUSE_32: "빈칸-절(32)",
    QuestionType.BLANK_CLAUSE_33: "빈칸-절(33)",
    QuestionType.BLANK_CLAUSE_34: "빈칸-절(34)",
    QuestionType.IRRELEVANT_SENTENCE_35: "무관문장(35)",
    QuestionType.ORDER_36: "순서배열(36)",
    QuestionType.ORDER_37: "순서배열(37)",
    QuestionType.INSERTION_38: "문장삽입(38)",
    QuestionType.INSERTION_39: "문장삽입(39)",
    QuestionType.SUMMARY_40: "요약문(40)",
    QuestionType.LONG_SET_41_42: "장문세트(41-42)",
    QuestionType.LONG_SET_43_45: "장문독해(43-45)",
}


# ─── 호환성 레벨 결정 ──────────────────────────────────────────────────────────

_LEVEL_COMPATIBLE = "compatible"
_LEVEL_CONDITIONAL = "conditional"
_LEVEL_INCOMPATIBLE = "incompatible"


def compatibility_level(source_type: str, target_type: str) -> str:
    """두 QuestionType 간의 변환 호환성 레벨을 반환한다.

    Args:
        source_type: 원본 QuestionType 값 (e.g. 'blank_phrase_31').
        target_type: 목표 QuestionType 값.

    Returns:
        'compatible' | 'conditional' | 'incompatible'

    Rules (카탈로그 v0.5 §호환성):
      - 같은 type → compatible (self-conversion).
      - → G6 → incompatible (장문 세트 생성 불가).
      - G1 ↔ G1 → compatible.
      - G1 → G3/G4/G5 → compatible.
      - G1 → G2 → conditional.
      - G2 → G1 → conditional.
      - G2 ↔ G2 → compatible.
      - G3 → non-G6 → conditional.
      - G4 → G1/G4/G5 → compatible.
      - G4 → G2/G3 → conditional.
      - G5 → G1/G4 → compatible.
      - G5 ↔ G5 → conditional.
      - G5 → G2/G3 → conditional.
      - G6 → non-G6 → conditional.
    """
    if source_type == target_type:
        return _LEVEL_COMPATIBLE

    src_group = _group_of(source_type)
    tgt_group = _group_of(target_type)

    # 알 수 없는 유형 (예: CHART_25 비활성)
    if src_group is None or tgt_group is None:
        return _LEVEL_INCOMPATIBLE

    # → G6 불가
    if tgt_group is _G6:
        return _LEVEL_INCOMPATIBLE

    # G1 계열 규칙
    if src_group is _G1:
        if tgt_group is _G1:
            return _LEVEL_COMPATIBLE
        if tgt_group in (_G3, _G4, _G5):
            return _LEVEL_COMPATIBLE
        if tgt_group is _G2:
            return _LEVEL_CONDITIONAL
        return _LEVEL_CONDITIONAL

    # G2 계열 규칙
    if src_group is _G2:
        if tgt_group is _G2:
            return _LEVEL_COMPATIBLE
        if tgt_group is _G1:
            return _LEVEL_CONDITIONAL
        return _LEVEL_CONDITIONAL

    # G3 계열 규칙
    if src_group is _G3:
        return _LEVEL_CONDITIONAL

    # G4 계열 규칙
    if src_group is _G4:
        if tgt_group in (_G1, _G4, _G5):
            return _LEVEL_COMPATIBLE
        return _LEVEL_CONDITIONAL

    # G5 계열 규칙
    if src_group is _G5:
        if tgt_group in (_G1, _G4):
            return _LEVEL_COMPATIBLE
        if tgt_group is _G5:
            return _LEVEL_CONDITIONAL
        return _LEVEL_CONDITIONAL

    # G6 계열 규칙
    if src_group is _G6:
        return _LEVEL_CONDITIONAL

    return _LEVEL_INCOMPATIBLE


def is_compatible(source_type: str, target_type: str) -> bool:
    """변환이 가능(compatible 또는 conditional)한지 여부를 반환한다.

    Args:
        source_type: 원본 QuestionType 값.
        target_type: 목표 QuestionType 값.

    Returns:
        True if level is 'compatible' or 'conditional', False if 'incompatible'.
    """
    return compatibility_level(source_type, target_type) != _LEVEL_INCOMPATIBLE


def compatible_target_types(source_type: str) -> list[dict]:
    """주어진 source_type 과 호환 가능한 모든 target type 목록을 반환한다.

    incompatible 유형은 제외한다. 같은 source_type 자신은 포함하지 않는다.

    Args:
        source_type: 원본 QuestionType 값.

    Returns:
        list of {'type': str, 'label': str, 'level': str}
        level 은 'compatible' 또는 'conditional'.
        type 을 기준으로 정렬.
    """
    results: list[dict] = []

    for qt in QuestionType:
        target = qt.value
        if target == source_type:
            continue
        level = compatibility_level(source_type, target)
        if level == _LEVEL_INCOMPATIBLE:
            continue
        results.append(
            {
                "type": target,
                "label": _LABELS.get(target, target),
                "level": level,
            }
        )

    return sorted(results, key=lambda x: x["type"])
