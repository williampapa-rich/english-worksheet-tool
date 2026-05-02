"""qa-validator 의 척추 — Phase 3 진입 시 NoOpValidator → 실제 검증기로 swap.

ADR-0003 §G-2 (Question.extraction_status) 와 향후 통합 — 검증 결과를
Question 의 metadata 또는 별 필드로 보존할지는 Phase 3 ADR 에서 결정.

현재 Question 에는 ``uniqueness_validated`` / ``uniqueness_validator_note`` 자리가
이미 마련되어 있다 (question.py audit-review-domain §4.1). Phase 3 에서 실제 검증기가
활성화될 때 ValidationResult 필드와 Question 필드를 매핑하는 어댑터를 작성한다.

Phase 0 에서는 *인터페이스 자리만* 잡음. 실제 검증 로직 (정답 유일성 / LLM 자가 검증)
은 Phase 3.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from shared.schemas.question import Question


class ValidationResult(BaseModel):
    """단일 Question 의 검증 결과.

    Phase 0: 모든 필드가 stub 값.
    Phase 3+: uniqueness_validated / validator_note / confidence_score 등에 실제 값.

    Question 모델의 ``uniqueness_validated`` / ``uniqueness_validator_note`` 필드와의
    관계: Phase 3 에서 실제 검증기가 ValidationResult 를 반환하면, 호출자(API 핸들러)가
    이 결과를 Question 필드에 반영한다. 매핑 방식은 Phase 3 ADR 에서 결정.
    """

    model_config = ConfigDict(extra="forbid")

    uniqueness_validated: bool = True
    """정답 유일성 검증 통과 여부.

    Phase 0: 항상 True (NoOpValidator).
    Phase 3+: LLM 검증기가 복수 정답 / 정답 없음을 탐지하면 False.
    """

    validator_note: str | None = None
    """검증자 코멘트 / 의심 사유.

    Phase 0: 항상 None.
    Phase 3+: 실패 사유 또는 경고 메시지 (예: "선지 ②와 ④ 모두 정답 가능").
    """

    # 향후 확장 예약 (Phase 3 ADR 에서 결정):
    # confidence_score: float | None = None
    # alternative_answers: list[str] = Field(default_factory=list)


@runtime_checkable
class Validator(Protocol):
    """Question 검증 프로토콜.

    Phase 0: NoOpValidator 만 존재 (항상 통과).
    Phase 3: LLM 기반 정답 유일성 검증기 swap.

    CLAUDE.md §7.6 — Phase 3 진입 시 FastAPI Depends 로 의존성 주입:
    ``Depends(get_validator)`` 팩토리에서 환경 변수 또는 설정에 따라
    NoOpValidator 또는 실제 검증기를 반환. 호출자(API 핸들러)는 프로토콜에만
    의존하므로 swap 시 호출자 코드 변경 없음.
    """

    async def validate(self, question: Question) -> ValidationResult:
        """Question 1건을 검증하고 ValidationResult 를 반환한다.

        Args:
            question: 검증 대상 Question.

        Returns:
            ValidationResult — Phase 0 에서는 항상 통과.
        """
        ...
