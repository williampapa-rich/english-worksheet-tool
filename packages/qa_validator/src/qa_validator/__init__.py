"""qa-validator 공개 API.

Phase 0: Validator 프로토콜 + ValidationResult + NoOpValidator (항상 통과).
Phase 3: LlmValidator 가 추가됨. 이 __init__.py 에 export 추가.

사용 예시 (Phase 0 — API 핸들러):
    from qa_validator import NoOpValidator, Validator, ValidationResult

    validator: Validator = NoOpValidator()
    result: ValidationResult = await validator.validate(question)
"""

from qa_validator.base import ValidationResult, Validator
from qa_validator.stub import NoOpValidator

__all__ = [
    "NoOpValidator",
    "ValidationResult",
    "Validator",
]
