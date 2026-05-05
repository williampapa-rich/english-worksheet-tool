"""ORM 모델 패키지.

Alembic autogenerate 가 모든 모델을 감지하려면 이 파일에서 모든 ORM 클래스를
import 해야 한다 (ADR-0005 §D-5.4 함정 #2).

패턴:
  - ``Tenant`` / ``Workspace``: Sprint 0 기존 SQLAlchemy DeclarativeBase 기반.
  - 나머지 도메인 ORM: SQLModel(table=True) 기반 (ADR-0005 §D-5.1 이중 클래스).

Cross-metadata FK 해소:
  Sprint 0 의 Tenant / Workspace 는 ``Base.metadata``, Phase 0 도메인 ORM 은
  ``SQLModel.metadata`` 로 분리됨. SQLModel ORM 의 FK (``passages.tenant_id`` →
  ``tenants.id`` 등) 가 `repository.create` 등에서 동적으로 resolve 될 때 다른
  metadata 의 테이블을 못 찾아 NoReferencedTableError 가 발생한다.

  해결: import 시점에 Base.metadata 의 tenants / workspaces Table 객체를
  SQLModel.metadata 에도 attach 한다 (같은 Table 객체를 두 metadata 가 공유).
  이렇게 하면 alembic 은 단일 metadata (`SQLModel.metadata`) 만으로도 모든 테이블을
  감지할 수 있고, repository 의 cross-metadata FK 도 정상 resolve 된다.
"""

from sqlmodel import SQLModel

# Sprint 0 기존 모델 (DeclarativeBase 기반 — 기존 마이그레이션과 연결됨)
from worksheet_api.db import Base
from worksheet_api.models.llm_usage_log import LlmUsageLogORM

# Phase 0 도메인 모델 (SQLModel table=True 기반)
from worksheet_api.models.passage import PassageORM
from worksheet_api.models.question import QuestionORM
from worksheet_api.models.syntax_annotation import SyntaxAnnotationORM
from worksheet_api.models.tenant import Tenant, Workspace
from worksheet_api.models.translation import TranslationORM
from worksheet_api.models.user_preference import UserPreferenceORM
from worksheet_api.models.vocabulary import VocabularyORM

# Base.metadata 의 tenants / workspaces 를 SQLModel.metadata 에도 attach.
# import 부수 효과 — 본 모듈을 import 하면 자동으로 cross-metadata FK 가 해소됨.
for _tbl_name in ("tenants", "workspaces"):
    if _tbl_name in Base.metadata.tables and _tbl_name not in SQLModel.metadata.tables:
        SQLModel.metadata._add_table(  # noqa: SLF001 — SQLAlchemy 공인 패턴
            _tbl_name, None, Base.metadata.tables[_tbl_name]
        )

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
    "UserPreferenceORM",
]
