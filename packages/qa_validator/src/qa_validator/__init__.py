"""qa-validator 공개 API.

Phase 0: Validator 프로토콜 + ValidationResult + NoOpValidator (항상 통과).
Phase 3: UniquenessValidationOutput + validate_question_uniqueness 활성화.

사용 예시 (Phase 0 — API 핸들러):
    from qa_validator import NoOpValidator, Validator, ValidationResult

    validator: Validator = NoOpValidator()
    result: ValidationResult = await validator.validate(question)

사용 예시 (Phase 3 — 변형 라우트):
    from qa_validator import validate_question_uniqueness

    qa_result = await validate_question_uniqueness(
        question=saved_variant,
        passage_text=passage.body_text,
        client=llm_client,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
    )
"""

from qa_validator.base import ValidationResult, Validator
from qa_validator.stub import NoOpValidator
from qa_validator.uniqueness import UniquenessValidationOutput, validate_question_uniqueness

__all__ = [
    "NoOpValidator",
    "UniquenessValidationOutput",
    "ValidationResult",
    "Validator",
    "validate_question_uniqueness",
]
