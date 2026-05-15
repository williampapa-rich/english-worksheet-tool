"""정답 유일성 검증 LLM call 모듈 (Phase 3 활성화).

CLAUDE.md §7.6 ("Phase 3 시작 시 활성화"):
  검증 LLM call 은 변형 생성 LLM call 과 분리한다.
  자기확증 편향 방지 — 같은 모델이 자기 출력을 "맞다"고 판정하지 않도록
  별 프롬프트 + 별 structured output 을 사용한다.

docs/variant-type-catalog.md §3.6 qa-validator 검증 시나리오:
  variant_kind 별 검증 카테고리 매핑 기반.

사용 패턴 (API 라우트에서):
    result = await validate_question_uniqueness(
        question=saved_variant,
        passage=passage,
        client=llm_client,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
    )
    # result: QAValidationResult — passed / note / validator_model 채워짐

비용 고려 (CLAUDE.md §7.6 비용 관리):
  변형 생성 1회 + 검증 1회 = 2회 LLM call per request.
  캐싱 비활성 — 변형 결과가 매번 다름.
  Phase 4 비용 모니터링 영역.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from llm.client import StructuredLLMClient
from llm.errors import LLMSchemaValidationError, LLMTimeoutError, PermanentLLMError
from llm.prompt import PromptSpec
from pydantic import BaseModel, Field

from shared.schemas.qa_validation_result import QAValidationResult
from shared.schemas.question import Question, VariantKind

logger = logging.getLogger(__name__)

# ─── 프롬프트 템플릿 ID ────────────────────────────────────────────────────────
QA_UNIQUENESS_PROMPT_ID = "qa-validator-uniqueness-v0"

# ─── qa-validator 버전 — 프롬프트/알고리즘 버전 추적 (회귀 테스트용) ─────────
QA_VALIDATOR_VERSION = "v0.1"

# ─── variant_kind 별 추가 검증 체크 텍스트 (프롬프트 {{variant_kind_check}} 치환) ──
_VARIANT_KIND_CHECKS: dict[str, str] = {
    VariantKind.VOCABULARY_SWAP: (
        "V1 (vocabulary_swap) specific checks:\n"
        "- Does the swapped word (the incorrect choice) clearly violate the passage meaning "
        "when the whole passage is understood? (If the incorrectness is borderline → flag)\n"
        "- Can any of the 4 appropriate words also be considered contextually wrong? "
        "(If yes → uniqueness failure — multiple answers)\n"
        "- Is the swapped word clearly distinguishable from the 4 appropriate words "
        "without relying on dictionary look-up of obscure synonyms?\n"
        "- Does the swap word belong to the same part of speech as the original? "
        "(POS mismatch = structural error)"
    ),
    VariantKind.GRAMMAR_SWAP: (
        "V3 (grammar_swap) specific checks:\n"
        "- Is the swapped error a CLEAR, unambiguous grammar violation? "
        "(애매한 stylistic 차이 or native speaker 가 수용 가능한 형태 → NOT a valid error → "
        "uniqueness failure)\n"
        "- Are the 4 correct candidates each genuinely correct in their grammatical context? "
        "(If any of the 4 'correct' candidates is itself questionable → structural error)\n"
        "- Do the 5 candidates test DIFFERENT grammar categories "
        "(verb_form / agreement / infinitive_gerund / relative_pronoun / preposition / "
        "participle / pronoun)? "
        "(If any two candidates test the same rule → category diversity failure)\n"
        "- Is the error the ONLY wrong choice among the 5? "
        "(If another candidate could also be considered an error → uniqueness failure)"
    ),
    VariantKind.TOPIC_MAIN_IDEA_SWAP: (
        "V6 (topic_main_idea_swap) specific checks:\n"
        "- Does the correct answer align precisely with the passage thesis?\n"
        "- Are the distractors clearly differentiated: too-narrow / too-broad / "
        "opposite-conclusion / plausible-unrelated?\n"
        "- Does the answer format match the question type "
        "(Korean sentence for main_idea_22, English noun phrase for theme_23, "
        "English title for title_24)?"
    ),
    VariantKind.BLANK_INFERENCE: (
        "V5 (blank_inference) specific checks:\n"
        "- Is the blank position clearly supported by surrounding context clues in the passage?\n"
        "- Does the correct answer fit the blank such that the passage makes clear logical sense?\n"
        "- Can any distractor also fill the blank without contradiction? "
        "(If yes → uniqueness failure)\n"
        "- Is the correct answer phrase literally present in the passage? "
        "(Literal repetition = too easy, flag as quality concern)"
    ),
    VariantKind.VOCABULARY_INLINE: (
        "V2 (vocabulary_inline) specific checks:\n"
        "- For each inline box (A), (B), (C): is exactly one option clearly correct in context?\n"
        "- Could the wrong option in any box also be contextually acceptable? "
        "(If yes → uniqueness failure for that box)\n"
        "- Does the combination answer in the 5-choice list match the inline_choices answers?"
    ),
    VariantKind.GRAMMAR_INLINE: (
        "V4 (grammar_inline) specific checks:\n"
        "- For each inline box (A), (B), (C): is exactly one option grammatically correct?\n"
        "- Is the grammar rule being tested clear and unambiguous?\n"
        "- Could a native English speaker reasonably choose the wrong option? "
        "(If yes → naturalness concern / gray-zone)"
    ),
    VariantKind.ORDER_SHUFFLE: (
        "V7 (order_shuffle) specific checks:\n"
        "- Does the correct paragraph order have clear cohesive cues "
        "(discourse connectors, pronoun references, topic continuity)?\n"
        "- Are there enough cues to rule out ALL four wrong orders? "
        "(If not → uniqueness failure)\n"
        "- Is the answer distribution plausible (not always choice ①)?"
    ),
    VariantKind.SENTENCE_INSERTION_SHIFT: (
        "V8 (sentence_insertion_shift) specific checks:\n"
        "- 주어진 문장의 단서 (대명사 referent / 접속사) 가 정답 위치 앞 문장에 명확히 있는가?\n"
        "- 다른 4개 위치 삽입 시 문맥 흐름이 깨지는가? "
        "(If not → uniqueness failure — the given sentence could fit multiple positions)\n"
        "- 정답 위치 뒤 문장과의 연결도 자연스러운가 "
        "(not just the sentence before the correct position)?\n"
        "- given_sentence 가 body_with_markers 에서 완전히 제거되었는가 "
        "(remnants of the extracted sentence = structural error)?"
    ),
    VariantKind.SUMMARY_BLANK_SWAP: (
        "V10 (summary_blank_swap) specific checks:\n"
        "- For blank (A): is exactly one candidate word the clear, unambiguous correct choice "
        "given the passage thesis? Could any distractor fill (A) without contradiction? "
        "(If yes → uniqueness failure for (A))\n"
        "- For blank (B): is exactly one candidate word the clear, unambiguous correct choice? "
        "Could any distractor fill (B) without contradiction? "
        "(If yes → uniqueness failure for (B))\n"
        "- Does the full summary sentence (with correct (A)/(B) filled in) accurately "
        "compress the passage thesis — not too narrow, not too broad, not a verbatim copy?\n"
        "- Are the 'swap' distractor (A)/(B) roles clearly wrong when reversed?\n"
        "- Are the 'wrong_a', 'wrong_b', 'both_wrong' distractors plausible but clearly "
        "incorrect in context?"
    ),
    VariantKind.IRRELEVANT_SENTENCE_INJECT: (
        "V9 (irrelevant_sentence_inject) specific checks:\n"
        "- 주입된 문장이 본문의 논리 흐름을 명백히 단절시키는가? "
        "(애매한 경우 — 약간 관련 있어 보이는 문장 → uniqueness failure)\n"
        "- 주입된 문장 주변의 4개 정상 문장 간 응결 단서(대명사 referent / 접속사 / 논리 전개)가 "
        "보존되어 있는가? (정상 4개 문장이 흐름 단절되면 structural error)\n"
        "- 주입된 문장이 본문과 lexical similarity (어휘 공유)를 갖추어 "
        "단순 어휘 차이만으로 쉽게 식별되지 않는가? "
        "(너무 쉬운 경우 — vocabulary 만으로 즉시 식별 가능 → quality concern)\n"
        "- 다른 4개 위치에서 주입 문장이 흐름에 자연스럽게 맞지 않는가? "
        "(만약 다른 위치에서도 무관하게 보이면 → 문제 구조 결함)"
    ),
}

_DEFAULT_VARIANT_KIND_CHECK = (
    "General uniqueness check: verify that exactly one choice is correct "
    "and no other choice can be reasonably defended based on the passage."
)


# ─── LLM output schema ────────────────────────────────────────────────────────


class UniquenessValidationOutput(BaseModel):
    """qa-validator LLM 구조화 출력 schema.

    docs/prompts/qa-validator-uniqueness-v0.md 출력 schema 와 1:1 대응.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
        필요한 필드만 사용.
    """

    passed: bool = Field(
        ...,
        description=(
            "True = 정답이 유일함 (검증 통과). "
            "False = 다른 선택지도 정답 가능하거나 정답이 없음 (검증 실패)."
        ),
    )
    note: str = Field(
        ...,
        description=(
            "통과/실패 사유. 실패 시 어느 선택지가 왜 정답으로 해석 가능한지 구체적으로 기술. "
            "통과 시 간략히 확인 사유 기술 (예: '정답이 thesis 와 정확히 일치, 오답 4개 각각 명확히 틀림')."
        ),
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description=(
            "검증 자신감. "
            "'high' = 확신 (명확한 정답/오답 구분). "
            "'medium' = 보통 (경계 케이스 있음). "
            "'low' = 불확실 (도메인 지식 부족 또는 passage 모호)."
        ),
    )


# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _build_choices_text(choices: list[str]) -> str:
    """선택지 리스트를 번호 붙인 문자열로 변환."""
    lines = []
    for i, choice in enumerate(choices, start=1):
        lines.append(f"  {i}. {choice}")
    return "\n".join(lines)


def _get_variant_kind_check(variant_kind: VariantKind) -> str:
    """variant_kind 에 맞는 추가 검증 체크 텍스트 반환."""
    return _VARIANT_KIND_CHECKS.get(variant_kind, _DEFAULT_VARIANT_KIND_CHECK)


# ─── 메인 함수 ────────────────────────────────────────────────────────────────


async def validate_question_uniqueness(
    *,
    question: Question,
    passage_text: str,
    client: StructuredLLMClient,
    tenant_id: UUID | None = None,
    workspace_id: UUID | None = None,
    prompt_template_id: str = QA_UNIQUENESS_PROMPT_ID,
    validator_version: str = QA_VALIDATOR_VERSION,
) -> QAValidationResult:
    """변형 Question 의 정답 유일성을 별도 LLM call 로 검증한다.

    CLAUDE.md §7.6: 검증은 별도 LLM call 로 — 변형 생성 LLM 과 분리.

    정답 유일성 검증 = 5지선다 중 정답 1개가 유일한가? 다른 선지가 정답이 될
    가능성이 있는가? (카탈로그 v0.4 §3.6 검증 기준)

    에러 처리:
      LLM 호출 실패 / schema 검증 실패 시 graceful degradation:
        passed=False, note="validator_error: <reason>".
      검증 LLM 실패는 비치명 — 변형 생성 자체는 이미 성공한 상태.

    Args:
        question: 검증 대상 변형 Question (variant_kind != ORIGINAL 이어야 의미 있음).
        passage_text: 연결된 Passage.body_text.
        client: StructuredLLMClient 구현체 (CLAUDE.md §8.3 강제).
        tenant_id: 사용량 로그에 기록할 테넌트 ID (선택).
        workspace_id: 사용량 로그에 기록할 워크스페이스 ID (선택).
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``qa-validator-uniqueness-v0``.
        validator_version: 프롬프트/알고리즘 버전 (회귀 추적용).

    Returns:
        QAValidationResult — passed / note / validator_model / validator_version 채워짐.
        tenant_id / workspace_id / question_id 는 호출자가 채워야 함
        (sentinel UUID 패턴 아님 — 호출자가 이미 ID 알고 있음).
    """
    answer_text = ""
    if question.choices and 1 <= question.answer <= len(question.choices):
        answer_text = question.choices[question.answer - 1]

    choices_text = _build_choices_text(question.choices) if question.choices else "(선택지 없음)"
    variant_kind_check = _get_variant_kind_check(question.variant_kind)

    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={
            "passage_text": passage_text,
            "question_type": str(question.type),
            "variant_kind": str(question.variant_kind),
            "question_text": question.question_text or "(지시문 없음)",
            "choices_text": choices_text,
            "answer": str(question.answer),
            "answer_text": answer_text,
            "explanation": question.explanation or "(해설 없음)",
            "variant_kind_check": variant_kind_check,
        },
    )

    try:
        result = await client.extract_structured(
            prompt=prompt,
            response_model=UniquenessValidationOutput,
            purpose="qa_validator_uniqueness",
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            # 낮은 temperature — 검증은 결정적이어야 함
            temperature=0.1,
        )
        llm_out = result.data
        used_model: str | None = result.model

        return QAValidationResult(
            # tenant_id / workspace_id / question_id 는 호출자(라우트)가 채움
            tenant_id=question.tenant_id,
            workspace_id=question.workspace_id,
            question_id=question.id,
            validated_at=datetime.now(UTC),
            passed=llm_out.passed,
            validator_note=(f"[{llm_out.confidence}] {llm_out.note}"),
            validator_model=used_model,
            validator_version=validator_version,
        )

    except (LLMSchemaValidationError, LLMTimeoutError, PermanentLLMError) as exc:
        logger.warning(
            "qa-validator LLM 호출 실패 (graceful degradation): question_id=%s, error=%s",
            question.id,
            exc,
        )
        return QAValidationResult(
            tenant_id=question.tenant_id,
            workspace_id=question.workspace_id,
            question_id=question.id,
            validated_at=datetime.now(UTC),
            passed=False,
            validator_note=f"validator_error: {type(exc).__name__}: {exc}",
            validator_model=None,
            validator_version=validator_version,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "qa-validator 예상치 못한 오류 (graceful degradation): question_id=%s, error=%s",
            question.id,
            exc,
        )
        return QAValidationResult(
            tenant_id=question.tenant_id,
            workspace_id=question.workspace_id,
            question_id=question.id,
            validated_at=datetime.now(UTC),
            passed=False,
            validator_note=f"validator_error: {type(exc).__name__}: {exc}",
            validator_model=None,
            validator_version=validator_version,
        )
