"""shared.schemas — 시스템의 척추(Pydantic v2 도메인 모델).

본 패키지는 다음 5개 경계의 single source of truth다 (CLAUDE.md §3.1):
  1. LLM structured output (Anthropic SDK + Pydantic)
  2. FastAPI request/response
  3. DB ORM 모델의 source of truth
  4. 에디터 초기 상태 (React/Tiptap)
  5. 출력 렌더러 입력 (HWPX/PDF)

설계 원칙:
  - 모든 도메인 엔티티는 ``tenant_id`` + ``workspace_id`` (Workspace 자체 제외) 필수.
  - timezone-aware ``datetime`` (UTC) — ``datetime.utcnow`` 사용 금지.
  - 새 필드 추가 위주, breaking change는 ADR + 마이그레이션 동반.

본 패키지는 **순수 Pydantic** 으로만 구성된다. SQLAlchemy ORM 동기화는
``apps/api`` 의 backend-dev 책임 (CLAUDE.md §7.2 권한 분리).

관련 문서:
  - ``docs/adr/0001-canonical-schema-philosophy.md``
  - ``docs/adr/0002-content-model-v0_1.md``
"""

from shared.schemas.annotation import (
    AnnotationCategory,
    AnnotationKind,
    AnnotationSpan,
    SpanFormat,
    SyntaxAnnotation,
)
from shared.schemas.common import (
    BaseEntity,
    EntityId,
    TenantScopedEntity,
    TimestampMixin,
    WorkspaceScopedEntity,
    utc_now,
)
from shared.schemas.extraction import (
    ExtractionMetaRef,
    ExtractionRequest,
    ExtractionResult,
)
from shared.schemas.llm_usage import (
    LlmUsageLog,
    LlmUsageStatus,
)
from shared.schemas.passage import (
    Passage,
    SourceMeta,
    SourceProvider,
    TargetGrade,
)
from shared.schemas.question import (
    ChoiceFormat,
    ChoiceMatrix,
    InlineChoice,
    InlineChoiceKind,
    Question,
    QuestionPlan,
    QuestionType,
    SubQuestion,
    VariantKind,
)
from shared.schemas.tenant import Tenant, Workspace
from shared.schemas.translation import Translation, TranslationCreatedBy
from shared.schemas.user_preference import (
    SentenceRolePresetValue,
    UserPreference,
    UserPreferencePatchInput,
)
from shared.schemas.vocabulary import Vocabulary, VocabularySelectedBy
from shared.schemas.worksheet import (
    Branding,
    Worksheet,
    WorksheetItem,
    WorksheetKind,
    WorksheetOrientation,
)

__all__ = [
    # annotation
    "AnnotationCategory",
    "AnnotationKind",
    "AnnotationSpan",
    "SpanFormat",
    "SyntaxAnnotation",
    # common
    "BaseEntity",
    "EntityId",
    "TenantScopedEntity",
    "TimestampMixin",
    "WorkspaceScopedEntity",
    "utc_now",
    # extraction
    "ExtractionMetaRef",
    "ExtractionRequest",
    "ExtractionResult",
    # llm_usage
    "LlmUsageLog",
    "LlmUsageStatus",
    # passage
    "Passage",
    "SourceMeta",
    "SourceProvider",
    "TargetGrade",
    # question
    "ChoiceFormat",
    "ChoiceMatrix",
    "InlineChoice",
    "InlineChoiceKind",
    "Question",
    "QuestionPlan",
    "QuestionType",
    "SubQuestion",
    "VariantKind",
    # tenant
    "Tenant",
    "Workspace",
    # translation
    "Translation",
    "TranslationCreatedBy",
    # user_preference
    "SentenceRolePresetValue",
    "UserPreference",
    "UserPreferencePatchInput",
    # vocabulary
    "Vocabulary",
    "VocabularySelectedBy",
    # worksheet
    "Branding",
    "Worksheet",
    "WorksheetItem",
    "WorksheetKind",
    "WorksheetOrientation",
]
