"""Repository 레이어 공개 API.

ADR-0003 §D-3.4, ADR-0005 §D-5.3 구현.
모든 도메인 repository 와 TenantContext / get_tenant_context Depends 를 export 한다.

P0-7 (API 엔드포인트) 에서:
    from worksheet_api.repositories import (
        PassageRepository,
        QuestionRepository,
        TenantContext,
        get_tenant_context,
    )
"""

from worksheet_api.repositories.base import BaseRepository
from worksheet_api.repositories.llm_usage_log import LlmUsageLogRepository
from worksheet_api.repositories.passage import PassageRepository
from worksheet_api.repositories.question import QuestionRepository
from worksheet_api.repositories.syntax_annotation import SyntaxAnnotationRepository
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context
from worksheet_api.repositories.translation import TranslationRepository
from worksheet_api.repositories.user_preference import ConflictError, UserPreferenceRepository
from worksheet_api.repositories.vocabulary import VocabularyRepository
from worksheet_api.repositories.worksheet import WorksheetRepository

__all__ = [
    "BaseRepository",
    "TenantContext",
    "get_tenant_context",
    "PassageRepository",
    "QuestionRepository",
    "TranslationRepository",
    "VocabularyRepository",
    "SyntaxAnnotationRepository",
    "LlmUsageLogRepository",
    "UserPreferenceRepository",
    "ConflictError",
    "WorksheetRepository",
]
