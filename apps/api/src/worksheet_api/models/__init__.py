"""ORM 모델 패키지.

Alembic autogenerate 가 모든 모델을 감지하려면 이 파일에서 모든 ORM 클래스를
import 해야 한다 (ADR-0005 §D-5.4 함정 #2).

패턴:
  - ``Tenant`` / ``Workspace``: Sprint 0 기존 SQLAlchemy DeclarativeBase 기반.
  - 나머지 도메인 ORM: SQLModel(table=True) 기반 (ADR-0005 §D-5.1 이중 클래스).
  - Alembic env.py 는 두 metadata (Base.metadata + SQLModel.metadata) 를 모두 참조.
"""

# Sprint 0 기존 모델 (DeclarativeBase 기반 — 기존 마이그레이션과 연결됨)
# Phase 0 도메인 모델 (SQLModel table=True 기반)
from worksheet_api.models.llm_usage_log import LlmUsageLogORM
from worksheet_api.models.passage import PassageORM
from worksheet_api.models.question import QuestionORM
from worksheet_api.models.syntax_annotation import SyntaxAnnotationORM
from worksheet_api.models.tenant import Tenant, Workspace
from worksheet_api.models.translation import TranslationORM
from worksheet_api.models.vocabulary import VocabularyORM

__all__ = [
    # 기존
    "Tenant",
    "Workspace",
    # Phase 0 도메인 ORM
    "PassageORM",
    "QuestionORM",
    "VocabularyORM",
    "TranslationORM",
    "SyntaxAnnotationORM",
    "LlmUsageLogORM",
]
