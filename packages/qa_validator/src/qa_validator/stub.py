"""Phase 0 의 placeholder 검증기 — 모든 Question 을 통과시킴.

Phase 3 에서 LLM 기반 검증기로 교체된다. API 핸들러 / extractor 가 Validator
프로토콜에만 의존하므로 swap 시점에 호출자 코드 변경 없음.

CLAUDE.md §7.6 (Phase 3 활성화 기준):
  - 변형 유형 5개 이상 지원 시 활성화.
  - 정답 유일성 자동 검증은 별도 LLM call (생성 LLM 과 검증 LLM 분리).
  - 자기확증 편향 방지: 같은 모델이 자기 출력을 "맞다"고 판정하지 않도록
    별 컨텍스트 또는 별 모델 사용.
"""

from __future__ import annotations

from qa_validator.base import ValidationResult
from shared.schemas.question import Question


class NoOpValidator:
    """모든 Question 에 대해 ``ValidationResult(uniqueness_validated=True)`` 반환.

    Phase 0 의 stub. CI / 로컬 테스트에서 always-pass 동작.

    Phase 3 swap 경로:
        1. ``packages/qa_validator/src/qa_validator/llm_validator.py`` 에 실제 검증기 작성.
        2. FastAPI ``Depends(get_validator)`` 팩토리에서 환경 변수 / 설정에 따라
           ``NoOpValidator`` 또는 ``LlmValidator`` 반환.
        3. API 핸들러는 ``Validator`` 프로토콜에만 의존하므로 핸들러 코드 변경 없음.
        4. 검증 결과를 ``Question.uniqueness_validated`` / ``uniqueness_validator_note``
           에 반영하는 어댑터는 Phase 3 ADR 에서 결정.
    """

    async def validate(self, question: Question) -> ValidationResult:
        """질문을 검증한다 (Phase 0: 항상 통과).

        Args:
            question: 검증 대상 Question. Phase 0 에서는 실제로 읽지 않음.

        Returns:
            ValidationResult(uniqueness_validated=True, validator_note=None).
        """
        # Phase 0: question 내용에 관계없이 항상 통과.
        # PM-6 가정 (CLAUDE.md §7 PM-6): translation is None / vocabulary == [] 는 에러가 아님.
        # Phase 3 에서 이 자리에 LLM call 이 들어온다.
        return ValidationResult(
            uniqueness_validated=True,
            validator_note=None,
        )
