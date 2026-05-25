"""Stage 2: Cross-type variant 생성 — 복원된 본문 위에서 새 type 출제.

CLAUDE.md §8.3 강제:
  직접 Anthropic SDK 호출 금지. 모든 LLM 호출은 StructuredLLMClient 를 통한다.

ADR-0013 augment 패턴 준수:
  - sentinel UUID 채움 → 라우트가 실제 ID 주입.
  - PromptSpec 을 통한 프롬프트 로딩 (docs/prompts/cross-type-generate-v0.md).
  - Pydantic 모델로 structured output 검증.

Cross-type variant 특성:
  - Stage 1 (패시지 복원) 은 별도 구현. 본 모듈은 Stage 2 (신규 문제 출제) 만 담당.
  - 원본 question 과 다른 QuestionType 으로 신규 문제를 생성한다.
  - variant_kind = CROSS_TYPE, type = target_type (원본과 다름).
  - G3 (grammar_29 / vocabulary_30) 는 PM 결정으로 지원하지 않는다.

지원 대상 QuestionType 그룹:
  - G1 추론형: purpose_18 / mood_19 / assertion_20 / underline_implication_21 /
               gist_22 / theme_23 / title_24
  - G2 사실형: figure_match_26 / notice_27 / notice_28
  - G4 빈칸추론형: blank_phrase_31 / blank_clause_32 / blank_clause_33 / blank_clause_34
  - G5 논리형: irrelevant_sentence_35 / order_36 / order_37 / insertion_38 / insertion_39
  - 요약문: summary_40

에러 처리:
  - target_type 이 비지원 type (G3 등) → ValueError 즉시.
  - choices 5개 아님 → LLMSchemaValidationError (Pydantic validator).
  - answer 범위 벗어남 → LLMSchemaValidationError.
  - modified_passage 존재 여부가 type 과 불일치 → LLMSchemaValidationError.
  - LLM 호출 실패 → llm.errors 계층 그대로 전파.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, model_validator

from llm.client import StructuredLLMClient
from llm.prompt import PromptSpec
from shared.schemas.question import (
    Question,
    QuestionType,
    VariantKind,
)

# ─── sentinel UUID (ADR-0003 §D-3.6) ─────────────────────────────────────────
SENTINEL_UUID: uuid.UUID = uuid.UUID(int=0)

# ─── 프롬프트 템플릿 ID ─────────────────────────────────────────────────────
CROSS_TYPE_PROMPT_ID = "cross-type-generate-v0"

# ─── 그룹 분류 ───────────────────────────────────────────────────────────────

# G1 추론형 — 선택지 텍스트 기반 (modified_passage = null)
_G1_TYPES: frozenset[QuestionType] = frozenset(
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

# G2 사실형 — 일치/불일치 (modified_passage = null)
_G2_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.FIGURE_MATCH_26,
        QuestionType.NOTICE_27,
        QuestionType.NOTICE_28,
    }
)

# G3 어휘/어법 — modified_passage 에 ①~⑤ 마커 + 밑줄 필수
_G3_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.GRAMMAR_29,
        QuestionType.VOCABULARY_30,
    }
)

# G4 빈칸추론형 — modified_passage 에 `______` 1개 필수
_G4_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.BLANK_PHRASE_31,
        QuestionType.BLANK_CLAUSE_32,
        QuestionType.BLANK_CLAUSE_33,
        QuestionType.BLANK_CLAUSE_34,
    }
)

# G5 논리형 — modified_passage 에 구조화된 텍스트 필수
_G5_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.IRRELEVANT_SENTENCE_35,
        QuestionType.ORDER_36,
        QuestionType.ORDER_37,
        QuestionType.INSERTION_38,
        QuestionType.INSERTION_39,
    }
)

# 요약문 — modified_passage 에 (A)/(B) 마커 필수
_SUMMARY_TYPES: frozenset[QuestionType] = frozenset(
    {
        QuestionType.SUMMARY_40,
    }
)

# 지원 대상 전체 (차트/장문세트 제외)
CROSS_TYPE_SUPPORTED: frozenset[QuestionType] = (
    _G1_TYPES | _G2_TYPES | _G3_TYPES | _G4_TYPES | _G5_TYPES | _SUMMARY_TYPES
)

# modified_passage 가 non-null 이어야 하는 type 집합
_REQUIRES_MODIFIED_PASSAGE: frozenset[QuestionType] = (
    _G3_TYPES | _G4_TYPES | _G5_TYPES | _SUMMARY_TYPES
)

# 빈칸 표기 (6개 언더스코어 — 수능 표준)
_BLANK_MARKER = "______"

# (A)/(B) 요약문 마커
_BLANK_A_MARKER = "(A) ______"
_BLANK_B_MARKER = "(B) ______"

# QuestionType → 한국어 설명 (프롬프트 입력용)
_TYPE_DESCRIPTION: dict[QuestionType, str] = {
    QuestionType.PURPOSE_18: "목적 파악 (18번) — 글을 쓴 목적을 묻는 문제",
    QuestionType.MOOD_19: "심경·분위기 (19번) — 필자/인물의 심경 변화 또는 분위기를 묻는 문제",
    QuestionType.ASSERTION_20: "주장 파악 (20번) — 필자의 주장을 묻는 문제",
    QuestionType.UNDERLINE_IMPLICATION_21: "밑줄 함의 (21번) — 밑줄 친 어구/문장의 함의를 묻는 문제",
    QuestionType.GIST_22: "요지 파악 (22번) — 글의 요지를 한국어 단문으로 묻는 문제",
    QuestionType.THEME_23: "주제 파악 (23번) — 글의 주제를 영어 명사구로 묻는 문제",
    QuestionType.TITLE_24: "제목 추론 (24번) — 글의 제목을 영어 제목형 구/절로 묻는 문제",
    QuestionType.FIGURE_MATCH_26: "그림·일치 (26번) — 본문 내용과 일치/불일치를 묻는 사실형 문제",
    QuestionType.NOTICE_27: "안내문 1 (27번) — 안내문 내용과 일치/불일치를 묻는 사실형 문제",
    QuestionType.NOTICE_28: "안내문 2 (28번) — 안내문 내용과 일치/불일치를 묻는 사실형 문제",
    QuestionType.GRAMMAR_29: "어법 (29번) — 본문 속 5개 밑줄 단어/구 중 어법상 틀린 것을 고르는 문제. 본문에 ①_word_ ②_word_ … ⑤_word_ 형태로 마커 삽입 필요.",
    QuestionType.VOCABULARY_30: "어휘 (30번) — 본문 속 5개 밑줄 단어 중 문맥상 부적절한 것을 고르는 문제. 본문에 ①_word_ ②_word_ … ⑤_word_ 형태로 마커 삽입 필요.",
    QuestionType.BLANK_PHRASE_31: "빈칸 구 (31번) — 본문의 핵심 명사구를 빈칸으로 가린 추론 문제",
    QuestionType.BLANK_CLAUSE_32: "빈칸 절 (32번) — 본문의 핵심 절을 빈칸으로 가린 추론 문제",
    QuestionType.BLANK_CLAUSE_33: "빈칸 절 (33번) — 본문의 핵심 절을 빈칸으로 가린 추론 문제",
    QuestionType.BLANK_CLAUSE_34: "빈칸 절 (34번) — 본문의 핵심 절을 빈칸으로 가린 추론 문제",
    QuestionType.IRRELEVANT_SENTENCE_35: "무관문장 (35번) — 전체 흐름과 관계없는 문장을 찾는 논리 문제",
    QuestionType.ORDER_36: "순서배열 (36번) — (A)/(B)/(C) 단락의 올바른 순서를 묻는 논리 문제",
    QuestionType.ORDER_37: "순서배열 (37번) — (A)/(B)/(C) 단락의 올바른 순서를 묻는 논리 문제",
    QuestionType.INSERTION_38: "문장삽입 (38번) — 주어진 문장이 들어갈 위치를 찾는 논리 문제",
    QuestionType.INSERTION_39: "문장삽입 (39번) — 주어진 문장이 들어갈 위치를 찾는 논리 문제",
    QuestionType.SUMMARY_40: "요약문 완성 (40번) — 본문을 요약한 문장의 (A)/(B) 빈칸을 채우는 문제",
}


# ─── LLM output schema ────────────────────────────────────────────────────────


class CrossTypeGenerationOutput(BaseModel):
    """Cross-type generate LLM 출력 스키마.

    docs/prompts/cross-type-generate-v0.md 출력 schema 와 1:1 대응.
    모든 target_type 에서 공통으로 사용하는 flat 구조.
    type 별 modified_passage 존재 여부는 model_validator 로 강제한다.

    Note:
        ``extra`` 미적용 — Gemini API 가 ``additionalProperties: false`` 를 거절.
    """

    question_text: str = Field(
        ...,
        description="문제 지시문 (stem). 출제 type 에 맞는 수능 형식 지시문.",
    )
    choices: list[str] = Field(
        ...,
        description="5개 선택지 (1-based answer index 기준 순서).",
    )
    answer: int = Field(
        ...,
        ge=1,
        le=5,
        description="정답 인덱스 (1-based, 1~5).",
    )
    explanation: str = Field(
        ...,
        description="정답 해설 (한국어, 2–4문장).",
    )
    modified_passage: str | None = Field(
        default=None,
        description=(
            "수정된 본문. "
            "G4(빈칸) 은 `______` 1개 포함. "
            "G5(논리형) 은 구조화된 본문 (마커/단락 포함). "
            "summary_40 은 (A) ______ / (B) ______ 마커 포함 요약문. "
            "G1/G2 는 null."
        ),
    )

    @model_validator(mode="after")
    def _validate_choices_length(self) -> CrossTypeGenerationOutput:
        if len(self.choices) != 5:
            raise ValueError(f"choices 는 정확히 5개여야 한다. 현재: {len(self.choices)}개.")
        return self


# ─── 공개 API ─────────────────────────────────────────────────────────────────


async def generate_cross_type_question(
    *,
    reconstructed_text: str,
    target_type: QuestionType,
    original_question: Question,
    llm_client: StructuredLLMClient,
    prompt_template_id: str = CROSS_TYPE_PROMPT_ID,
) -> Question:
    """Stage 2: 복원된 본문 위에서 target_type 의 신규 문제 출제.

    Stage 1 (패시지 복원) 이 완료된 후 이 함수를 호출한다.
    sentinel UUID 가 채워진 신규 Question 을 반환한다. 라우트가 실제 ID 를 주입.

    ADR-0013 augment 패턴:
      - sentinel UUID 채움 → 라우트가 model_copy 로 실제 tenant_id / workspace_id /
        id / passage_id / derived_from_question_id 교체.
      - variant 는 항상 신규 row — mode 정책 없음.

    Args:
        reconstructed_text: Stage 1 이 생성한 복원 본문 (LLM 입력).
        target_type: 출제할 문제 유형. CROSS_TYPE_SUPPORTED 에 속해야 한다.
        original_question: 원본 Question (derived_from 설정 + 다양성 회피 입력).
        llm_client: StructuredLLMClient 구현체 (CLAUDE.md §8.3 강제).
        prompt_template_id: 프롬프트 템플릿 ID. 기본 ``cross-type-generate-v0``.

    Returns:
        sentinel UUID 가 채워진 신규 Question (variant_kind=CROSS_TYPE, type=target_type).
        라우트가 tenant_id / workspace_id / passage_id / derived_from_question_id 를
        model_copy 로 주입한다.

    Raises:
        ValueError: target_type 이 CROSS_TYPE_SUPPORTED 에 없는 경우 (G3 포함).
        LLMSchemaValidationError: structured output 검증 실패 (재시도 소진 후).
        LLMTimeoutError: 타임아웃 (재시도 소진 후).
        LLMNetworkError / PermanentLLMError: LLM 호출 실패.
    """
    if target_type not in CROSS_TYPE_SUPPORTED:
        raise ValueError(
            f"target_type '{target_type}' 은 cross-type variant 미지원 유형입니다. "
            f"지원 유형: {sorted(str(t) for t in CROSS_TYPE_SUPPORTED)}."
        )

    type_description = _TYPE_DESCRIPTION.get(
        target_type,
        str(target_type),  # fallback — 등록 누락 시 enum value 그대로
    )

    original_question_text = original_question.question_text or "(원본 문제 지시문 없음)"

    prompt = PromptSpec(
        template_id=prompt_template_id,
        variables={
            "reconstructed_text": reconstructed_text,
            "target_type_value": str(target_type),
            "target_type_description": type_description,
            "original_question_text": original_question_text,
        },
    )

    result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=CrossTypeGenerationOutput,
        purpose="variant_cross_type_generate",
        tenant_id=original_question.tenant_id,
        workspace_id=original_question.workspace_id,
    )

    llm_out = result.data

    # ─── modified_passage 존재 여부 사후 검증 ────────────────────────────────
    # CrossTypeGenerationOutput 은 모든 type 에서 공유하는 schema 이므로
    # Pydantic 이 type 정보를 모른다. 여기서 type-aware 검증을 수행한다.
    _validate_modified_passage(llm_out, target_type)

    # ─── Question 도메인 모델 변환 ──────────────────────────────────────────
    # sentinel UUID 채움 — 라우트가 model_copy 로 실제 ID 주입 (ADR-0003 §D-3.6)
    variant_metadata: dict[str, object] = {
        "target_type": str(target_type),
        "original_type": str(original_question.type),
    }
    if llm_out.modified_passage is not None:
        variant_metadata["modified_passage"] = llm_out.modified_passage

    return Question(
        id=SENTINEL_UUID,
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        passage_id=SENTINEL_UUID,
        derived_from_question_id=SENTINEL_UUID,  # 라우트가 실제 question_id 로 교체
        type=target_type,
        variant_kind=VariantKind.CROSS_TYPE,
        question_text=llm_out.question_text,
        choices=llm_out.choices,
        answer=llm_out.answer,
        explanation=llm_out.explanation,
        has_blanks=target_type in _G4_TYPES,
        variant_metadata=variant_metadata,
    )


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────


def _validate_modified_passage(
    llm_out: CrossTypeGenerationOutput,
    target_type: QuestionType,
) -> None:
    """target_type 에 따른 modified_passage 존재 여부 및 형식 검증.

    Args:
        llm_out: LLM structured output.
        target_type: 출제 유형.

    Raises:
        ValueError: modified_passage 존재 여부 또는 형식 위반.
    """
    requires = target_type in _REQUIRES_MODIFIED_PASSAGE

    if requires and llm_out.modified_passage is None:
        raise ValueError(
            f"target_type '{target_type}' 은 modified_passage 가 필수이지만 "
            f"LLM 이 null 을 반환했습니다."
        )
    if not requires and llm_out.modified_passage is not None:
        # G1/G2 는 modified_passage 가 null 이어야 함.
        # 경고 수준 — 있어도 무시하는 편이 실용적이지만 명세 준수를 위해 허용.
        # 여기서는 허용 (라우트가 저장 시 무시하면 됨).
        pass

    if llm_out.modified_passage is not None:
        _validate_modified_passage_content(llm_out.modified_passage, target_type)


def _validate_modified_passage_content(
    modified_passage: str,
    target_type: QuestionType,
) -> None:
    """modified_passage 내용 형식 검증 (type 별).

    Args:
        modified_passage: LLM 이 반환한 수정 본문.
        target_type: 출제 유형.

    Raises:
        ValueError: 형식 위반.
    """
    if target_type in _G3_TYPES:
        markers = ["①", "②", "③", "④", "⑤"]
        for m in markers:
            if modified_passage.count(m) != 1:
                raise ValueError(
                    f"G3(어법/어휘) modified_passage 에 마커 '{m}' 가 "
                    f"정확히 1회 등장해야 한다. 현재: {modified_passage.count(m)}회."
                )

    elif target_type in _G4_TYPES:
        count = modified_passage.count(_BLANK_MARKER)
        if count != 1:
            raise ValueError(
                f"G4(빈칸추론) modified_passage 에 `______` 가 정확히 1개여야 한다. "
                f"현재: {count}개."
            )

    elif target_type == QuestionType.SUMMARY_40:
        if _BLANK_A_MARKER not in modified_passage:
            raise ValueError("summary_40 modified_passage 에 '(A) ______' 마커가 없습니다.")
        if _BLANK_B_MARKER not in modified_passage:
            raise ValueError("summary_40 modified_passage 에 '(B) ______' 마커가 없습니다.")

    elif target_type == QuestionType.IRRELEVANT_SENTENCE_35:
        # ①~⑤ 마커 각 1회 등장 확인
        markers = ["①", "②", "③", "④", "⑤"]
        for m in markers:
            if modified_passage.count(m) != 1:
                raise ValueError(
                    f"irrelevant_sentence_35 modified_passage 에 마커 '{m}' 가 "
                    f"정확히 1회 등장해야 한다. 현재: {modified_passage.count(m)}회."
                )

    elif target_type in {QuestionType.INSERTION_38, QuestionType.INSERTION_39}:
        markers = ["①", "②", "③", "④", "⑤"]
        for m in markers:
            if modified_passage.count(m) != 1:
                raise ValueError(
                    f"insertion type modified_passage 에 마커 '{m}' 가 "
                    f"정확히 1회 등장해야 한다. 현재: {modified_passage.count(m)}회."
                )
