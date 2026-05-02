# ADR 0005 — SQLModel 매핑 패턴 (ORM ↔ Pydantic 통합 전략)

- **상태(Status)**: Proposed
- **작성일**: 2026-05-02
- **작성자**: backend-dev agent
- **유형**: 신규 결정 (P0-1 DB 마이그레이션 진입 전 확정 필요)
- **관련 문서**:
  - `docs/adr/0001-canonical-schema-philosophy.md` (5경계 척추 원칙)
  - `docs/adr/0002-content-model-v0.1.md` (Pydantic 모델 현황)
  - `docs/adr/0003-phase-0-extraction-pipeline.md` §D-3.4, §D-3.6, §PM-2
  - `CLAUDE.md` §3.1, §3.3, §3.6
  - `shared/schemas/common.py` (`WorkspaceScopedEntity` 베이스)

---

## Context (배경)

ADR-0003 §PM-2 에서 **SQLModel** 채택이 확정됐다. SQLModel 은 Pydantic v2 + SQLAlchemy
2.x 를 통합한 라이브러리로, tiangolo (FastAPI 저자) 가 개발했다. 이 결정의 근거:

- `shared/schemas/` 의 Pydantic 모델이 5경계 척추 (ADR-0001) — LLM 출력 / FastAPI /
  ORM / 에디터 / 렌더러 — 를 동시에 담당해야 한다.
- SQLModel 은 `SQLModel(table=True)` 선언 하나로 Pydantic 모델과 SQLAlchemy ORM 이
  같은 클래스에 공존한다.
- FastAPI 와의 통합이 1급 지원 (FastAPI 문서 공식 예시).

그러나 PM-2 는 "SQLModel 채택" 까지만 결정했다. **"기존 `shared/schemas/` 의 순수 Pydantic
모델과 SQLModel ORM 을 어떻게 연결할 것인가"** 는 아직 미결이다. 특히:

1. 현재 `shared/schemas/` 의 `WorkspaceScopedEntity` 가 `pydantic.BaseModel` 을 베이스로
   한다. 이를 그대로 두고 ORM 을 분리할지, SQLModel 로 올려탈지.
2. ADR-0003 §D-3.6 의 sentinel UUID (`uuid.UUID(int=0)`) 검증을 repository 레이어에서
   어떻게 강제할지.
3. Repository 패턴의 generic typing, async 강제, 트랜잭션 경계 책임이 SQLModel 위에서
   어떻게 구체화되는지.
4. Alembic autogenerate 와 SQLModel 의 알려진 호환성 이슈.
5. JSON 컬럼 (`SourceMeta` 같은 nested Pydantic 모델) 처리 방식.

본 ADR 은 이 7개 결정을 P0-1 진입 전에 확정한다.

---

## Decisions (결정)

### D-5.1 — `shared/schemas/` Pydantic 모델과 SQLModel ORM 의 관계: **패턴 B (이중 클래스)**

**채택: 이중 클래스 — `shared/schemas/` 의 Pydantic 모델은 순수 Pydantic 유지,
ORM 클래스는 `apps/api/src/worksheet_api/models/` 에 별도 SQLModel 클래스로 작성.**

#### 패턴 비교

| 패턴 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 단일 클래스** | `shared/schemas/passage.py` 의 `Passage` 를 `SQLModel(table=True)` 로 변환. ORM = Pydantic = API 스키마 동일 객체. | 변환 코드 없음. 진정한 "단일 척추". | `shared/schemas/` 가 SQLModel 에 의존 — 이 디렉토리는 `packages/extractor/`, 에디터, 렌더러도 import. SQLModel + sqlalchemy 가 `shared/` 의 전이적 의존성이 됨. `table=True` 는 `__tablename__` / 컬럼 제약 등 ORM 전용 필드를 강제. `extra="forbid"` 와 충돌 가능성 있음. |
| **B. 이중 클래스** (채택) | Pydantic 모델은 `shared/schemas/` 에 유지. SQLModel ORM 은 `apps/api/` 에 별도 클래스. 변환은 `Passage.model_validate(orm.model_dump())` 또는 `from_orm`. | `shared/schemas/` 가 SQLModel 의존성 없음 — `packages/` 전체가 가벼운 Pydantic 만 import. ORM 표현 자유도 (인덱스, DB 제약, 관계 등) 최대. | 변환 코드 boilerplate. 두 모델 간 드리프트 위험. |
| **C. SQLModel 분리 패턴** | `PassageBase(SQLModel)` + `Passage(PassageBase, table=True)` + `PassageRead(PassageBase)`. tiangolo 공식 권장 패턴. | Create/Read 스키마 분리가 명시적. | `shared/schemas/` 를 tiangolo 패턴으로 전부 재구성해야 함 — 현재 Pydantic 기반 모델 (ADR-0002 로 확정) 을 깨트린다. architect 영역. |

#### 채택 사유

ADR-0001 의 5경계 척추 원칙을 지키되, **의존성 방향을 지킨다**:

- `packages/extractor/`, `packages/llm/`, `packages/hwpx_renderer/` 는 `shared/schemas/`
  만 import. SQLModel / SQLAlchemy 는 이 패키지들의 관심사가 아니다.
- `apps/api/` 는 `shared/schemas/` 에 의존. `apps/api/src/worksheet_api/models/` 의
  ORM 클래스는 Pydantic 모델을 "DB 표현" 으로 변환하는 얇은 어댑터다.
- 변환 boilerplate 는 Repository 의 `_to_domain` / `_from_domain` 두 메서드로 집중.
  호출부는 변환을 모른다.

패턴 A 는 매력적이지만 `shared/schemas/` 를 "ORM-aware" 하게 만들어 CLAUDE.md §5 의
의존성 방향을 위반한다 (`packages/` 전체가 SQLAlchemy 를 전이적 의존성으로 끌어안음).
패턴 C 는 architect 영역인 `shared/schemas/` 를 현 PR 에서 재구성해야 한다 — 본 ADR
의 제약 위반.

#### ORM 클래스 위치 및 네이밍 컨벤션

```
apps/api/src/worksheet_api/models/
├── __init__.py
├── base.py           # SQLModelBase (SQLModel + 공통 컬럼)
├── tenant.py         # TenantORM, WorkspaceORM
├── passage.py        # PassageORM
├── question.py       # QuestionORM
└── ...
```

- ORM 클래스명 = `{DomainModel}ORM` 패턴 (예: `PassageORM`). 도메인 모델 `Passage` 와
  구분.
- 변환:
  ```python
  # ORM → 도메인
  passage: Passage = Passage.model_validate(passage_orm.model_dump())

  # 도메인 → ORM
  passage_orm: PassageORM = PassageORM.model_validate(passage.model_dump())
  ```
- `model_dump()` / `model_validate()` 는 Pydantic v2 표준. SQLModel 은 Pydantic v2
  상속이므로 ORM 클래스도 동일 메서드를 가진다.

#### architect 에게 권고 사항

`shared/schemas/common.py` 의 `WorkspaceScopedEntity` 에 다음이 있으면 이중 클래스
패턴의 변환이 단순해진다:

```python
# shared/schemas/common.py 에 추가 권고 (architect PR 로 처리)
class WorkspaceScopedEntity(TenantScopedEntity):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,  # SQLModel ORM → Pydantic 변환 지원
    )
```

`from_attributes=True` 는 `model_validate(orm_instance)` 호출 시 ORM 객체의 어트리뷰트를
읽어 Pydantic 모델로 변환한다. **본 ADR 은 이 변경을 권고할 뿐 직접 수정하지 않는다.**
architect 에게 후속 PR 요청.

---

### D-5.2 — `tenant_id` / `workspace_id` sentinel UUID 검증: **`WorkspaceScopedORMBase` mixin + Repository write 이중 방어**

ADR-0003 §D-3.6 결정:
- extractor 출력은 `tenant_id = uuid.UUID(int=0)` (sentinel) 으로 채움.
- API 레이어가 `model_copy` 로 실제 값 주입.
- Repository write 시 sentinel 검증 → 발견 시 `ValidationError` raise.

이를 SQLModel 위에서 구현하는 방식:

#### ORM base mixin

```python
# apps/api/src/worksheet_api/models/base.py

import uuid
from sqlmodel import SQLModel, Field as SQLField
from shared.schemas.common import EntityId

SENTINEL_UUID = uuid.UUID(int=0)

class WorkspaceScopedORMBase(SQLModel):
    """workspace 스코프 ORM 공통 컬럼.

    tenant_id / workspace_id 는 NOT NULL. sentinel UUID 검증은
    BaseRepository.create / update 에서 수행.
    """
    tenant_id: EntityId = SQLField(
        ...,
        foreign_key="tenants.id",
        nullable=False,
        index=True,
    )
    workspace_id: EntityId = SQLField(
        ...,
        foreign_key="workspaces.id",
        nullable=False,
        index=True,
    )
```

#### DB 레벨 CHECK constraint 여부

- **채택 안 함**: PostgreSQL `CHECK (tenant_id != '00000000-0000-0000-0000-000000000000')`
  constraint 를 추가하는 대안을 검토했지만 기각.
  - 기각 사유: Alembic autogenerate 가 표현식 CHECK constraint 를 제대로 감지하지 못하는
    알려진 이슈. 수동 마이그레이션 작성 부담 증가. application 레이어 검증으로 충분한 v0.1
    규모.
  - 재검토 시점: Phase 4 (PostgreSQL RLS 도입 ADR) 때 DB 레벨 방어 강화 가능.

#### Repository 검증 지점 (의사 코드)

```python
# apps/api/src/worksheet_api/repositories/base.py

SENTINEL_UUID = uuid.UUID(int=0)

class BaseRepository(Generic[TORM, TDomain]):
    def _validate_tenant_context(self, domain: TDomain) -> None:
        """sentinel UUID 누수 방어.

        tenant_id 또는 workspace_id 가 sentinel 이면 코드 버그.
        ValidationError 로 즉시 중단.
        """
        if getattr(domain, "tenant_id", None) == SENTINEL_UUID:
            raise ValueError(
                f"tenant_id 가 sentinel UUID 다 — API 레이어가 주입을 누락했다. "
                f"entity={type(domain).__name__}"
            )
        if getattr(domain, "workspace_id", None) == SENTINEL_UUID:
            raise ValueError(
                f"workspace_id 가 sentinel UUID 다 — API 레이어가 주입을 누락했다. "
                f"entity={type(domain).__name__}"
            )

    async def create(self, domain: TDomain) -> TDomain:
        self._validate_tenant_context(domain)
        # ... ORM 변환 → DB insert
```

---

### D-5.3 — Repository 패턴 인터페이스: **`BaseRepository[TORM, TDomain]` generic + async + session commit-free**

ADR-0003 §D-3.4 의 "API 핸들러 = 트랜잭션 1건" 결정을 구체화한다.

#### 인터페이스 설계

```python
# apps/api/src/worksheet_api/repositories/base.py

from typing import Generic, TypeVar
from uuid import UUID
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel
from shared.schemas.common import EntityId

TORM = TypeVar("TORM", bound=SQLModel)
TDomain = TypeVar("TDomain", bound=BaseModel)


class TenantContext:
    """API 핸들러가 주입하는 테넌트 컨텍스트."""
    tenant_id: EntityId
    workspace_id: EntityId


class BaseRepository(Generic[TORM, TDomain]):
    """기본 repository — tenant_id / workspace_id 필터 강제.

    session 은 주입받는다. commit 은 호출부 (API 핸들러) 책임.
    트랜잭션 경계는 API 핸들러의 ``async with session.begin()`` 으로 관리.
    """

    orm_class: type[TORM]      # 서브클래스가 선언
    domain_class: type[TDomain]  # 서브클래스가 선언

    def __init__(self, session: AsyncSession, ctx: TenantContext) -> None:
        self.session = session
        self.ctx = ctx

    async def create(self, domain: TDomain) -> TDomain: ...
    async def get(self, id: EntityId) -> TDomain | None: ...
    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TDomain]: ...
    async def update(self, id: EntityId, domain: TDomain) -> TDomain: ...
    async def delete(self, id: EntityId) -> None: ...
```

#### 핵심 결정 사항

- **commit 금지**: Repository 는 `session.add()` / `session.flush()` 까지만. `commit()`
  은 API 핸들러의 `async with session.begin():` 블록 종료 시 자동으로 수행. ADR-0003
  §D-3.4 재확인.
- **async 강제**: 모든 메서드 `async def`. SQLModel 의 `AsyncSession` 사용. sync 세션은
  테스트 픽스쳐에서만 허용.
- **`tenant_id` / `workspace_id` 자동 필터**:
  ```python
  async def list(self, ...) -> list[TDomain]:
      stmt = (
          select(self.orm_class)
          .where(self.orm_class.tenant_id == self.ctx.tenant_id)
          .where(self.orm_class.workspace_id == self.ctx.workspace_id)
          .limit(limit)
          .offset(offset)
      )
  ```
  `ctx` 를 주입받으므로 필터 누락이 구조적으로 불가능.
- **복잡 쿼리**: Repository 메서드 안에서 `select()` + raw SQLAlchemy 표현식 사용
  허용. SQLModel 의 한계를 우회하되 ORM 세션 컨텍스트는 유지.

#### 검토한 대안

- **A. Generic 없이 각 Repository 독립 작성**: 반복 코드 폭증, tenant_id 필터 누락
  위험. 기각.
- **B. SQLModel 의 `select()` 헬퍼만 사용, BaseRepository 없음**: 작은 프로젝트에서
  단순하지만 tenant_id 강제를 각 쿼리마다 수동으로 해야 함. 기각.

---

### D-5.4 — Alembic 통합: **autogenerate 사용 + SQLModel import path 명시 + 알려진 이슈 대응**

#### `alembic/env.py` metadata import

```python
# alembic/env.py

from sqlmodel import SQLModel

# ORM 모델을 모두 import 해야 autogenerate 가 테이블을 인식한다.
# 모델 import 를 빠트리면 autogenerate 가 테이블 삭제 마이그레이션을 생성할 수 있다.
import worksheet_api.models  # noqa: F401 — side-effect import (전체 ORM 등록)

target_metadata = SQLModel.metadata
```

- `SQLModel.metadata` 는 SQLAlchemy 의 `MetaData` 와 동일 — Alembic 이 그대로 인식.
- ORM 모델 파일 전체를 반드시 import 해야 autogenerate 가 작동함 (SQLModel 및 SQLAlchemy
  공통 요구사항).

#### autogenerate 사용 여부

**autogenerate 사용** — 단, 알려진 이슈를 인지하고 대응한다.

**SQLModel + Alembic autogenerate 알려진 이슈** (2024년 현재 SQLModel 0.0.21+):

1. `Enum` 타입 컬럼이 autogenerate 에서 잘못 감지돼 불필요한 `ALTER TYPE` 이 반복
   생성되는 경우 있음.
   - 대응: 마이그레이션 파일 생성 후 **반드시 human review**. Enum 관련 마이그레이션이
     중복 생성되면 수동 삭제.
2. SQLModel 의 `Field(sa_column=...)` 패턴 사용 시 autogenerate 가 컬럼을 놓치는 경우
   있음.
   - 대응: `sa_column` 사용 컬럼은 autogenerate 후 diff 확인 필수.
3. `server_default` 표현식이 autogenerate 에서 불일치로 잡히는 경우.
   - 대응: `include_symbol` / `compare_server_default=False` 옵션으로 필요시 비교 비활성화.

**결론**: autogenerate 를 사용하되, **CI 파이프라인에서 `alembic check` 실행** (마이그레이션
누락 감지). 생성된 마이그레이션 파일은 PR 에서 human review 후 머지.

#### 기존 Sprint 0 마이그레이션 전환 여부

현재 `tenants` / `workspaces` 테이블은 plain SQLAlchemy `Table()` 또는 `op.create_table()`
로 작성됐을 가능성이 높다. P0-1 진입 시 확인 후:

- ORM 클래스 (`TenantORM`, `WorkspaceORM`) 를 SQLModel 로 작성.
- 신규 테이블 마이그레이션은 autogenerate 로 생성.
- 기존 마이그레이션 파일은 수정하지 않음 (이미 적용된 이력). 새 마이그레이션으로 차이만
  처리.

---

### D-5.5 — 타입 변환 / serialization 경계: **Repository 내부의 `_to_orm` / `_to_domain` 집중**

```
[packages/llm/ 출력]
     ↓ Pydantic 모델 (Passage)
[API 핸들러]
     ↓ model_copy(update={tenant_id, workspace_id})
[Repository.create(domain)]
     ↓ _to_orm(domain) — domain → ORM 변환
[SQLModel ORM (PassageORM)]
     ↓ session.add()
[PostgreSQL]

[Repository.get(id)]
     ↓ session.get(PassageORM, id)
[SQLModel ORM (PassageORM)]
     ↓ _to_domain(orm) — ORM → 도메인 변환
[Pydantic 모델 (Passage)]
     ↓
[API 핸들러 → FastAPI response]
```

#### 변환 메서드 설계

```python
class BaseRepository(Generic[TORM, TDomain]):
    def _to_orm(self, domain: TDomain) -> TORM:
        """도메인 Pydantic 모델 → SQLModel ORM 객체."""
        return self.orm_class.model_validate(domain.model_dump())

    def _to_domain(self, orm: TORM) -> TDomain:
        """SQLModel ORM 객체 → 도메인 Pydantic 모델."""
        return self.domain_class.model_validate(orm.model_dump())
```

- `model_dump()` / `model_validate()` 의 Pydantic v2 / SQLModel 공통 메서드 활용.
- JSON 컬럼 (D-5.6 참조) 이 있는 경우 `model_dump(mode="python")` 으로 nested 객체를
  보존해야 함 — 서브클래스에서 오버라이드 가능.
- boilerplate 최소화: 대부분의 모델은 `BaseRepository` 의 기본 구현으로 충분.
  특수 변환이 필요한 모델만 오버라이드.

#### LLM 출력 → API 응답 흐름에서 별도 "Read" 스키마 불필요

tiangolo 의 `PassageRead` 분리 패턴 (패턴 C) 은 이중 클래스 채택으로 인해 필요 없다.
API 응답 스키마 = `shared/schemas/` 의 Pydantic 모델 그대로. FastAPI 의
`response_model=Passage` 로 직접 사용.

---

### D-5.6 — JSON 컬럼 처리: **`sa_column=Column(JSONB)` + Pydantic `model_validator` 복원**

`Passage.source: SourceMeta` 같은 nested Pydantic 모델을 PostgreSQL JSONB 로 저장.

#### ORM 클래스 선언

```python
# apps/api/src/worksheet_api/models/passage.py

from typing import Any
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, Field as SQLField
from shared.schemas.passage import SourceMeta, TargetGrade
from shared.schemas.common import EntityId

class PassageORM(WorkspaceScopedORMBase, table=True):
    __tablename__ = "passages"

    body_text: str = SQLField(...)
    word_count: int = SQLField(ge=0)
    target_grade: str = SQLField(...)  # StrEnum → DB 는 str 저장

    # nested Pydantic 모델 → JSONB
    source: dict[str, Any] = SQLField(
        default={},
        sa_column=Column(JSONB, nullable=False),
    )
    topic_tags: list[str] = SQLField(
        default=[],
        sa_column=Column(JSONB, nullable=False),
    )
```

#### 변환 시 JSONB ↔ Pydantic 복원

- DB 에서 읽어올 때 `source` 는 `dict`. `_to_domain` 에서 `model_validate` 가
  `SourceMeta` 로 자동 복원 (Pydantic v2 nested 모델 역직렬화).
- `_to_orm` 에서 도메인 → ORM 변환 시 `model_dump(mode="python")` 으로 `SourceMeta` →
  `dict` 변환. `sa_column=Column(JSONB)` 이 그대로 받음.

#### 검토한 대안

- **A. `TypeDecorator` 커스텀 컬럼 타입**: Pydantic 모델 자동 직렬화/역직렬화. 구현 복잡도
  ↑. 라이브러리 미채택 (CLAUDE.md §3.6 직접 구현 시 근거 필요).
  - 기각 사유: `sa_column=Column(JSONB)` + `model_validate` 패턴으로 충분.
    `TypeDecorator` 도입 대비 추가 이득 없음.
- **B. `pydantic_jsonable_encoder` + TEXT 저장**: JSON 문자열로 직렬화 → TEXT 컬럼.
  JSONB 연산자 사용 불가. 기각.

---

### D-5.7 — 테스트 패턴: **pytest-asyncio + Docker PostgreSQL 통합 테스트 + SQLite in-memory 단위 테스트 병행**

#### 두 레벨 테스트

| 레벨 | DB | 대상 | 속도 |
|---|---|---|---|
| 단위 테스트 | SQLite in-memory | Repository 의 sentinel 검증, 변환 로직 | 빠름 (CI 항상) |
| 통합 테스트 | Docker PostgreSQL | JSONB 컬럼, 실제 쿼리 필터, 마이그레이션 | 느림 (PR 머지 전) |

#### SQLite in-memory 제약 인지

SQLite 는 JSONB 를 모른다. `sa_column=Column(JSONB)` 컬럼을 SQLite 로 테스트하려면
별도 처리가 필요하다 (JSON → TEXT fallback). 이런 복잡성 때문에 JSON 컬럼을 포함하는
테스트는 반드시 PostgreSQL 로 실행한다.

#### pytest-asyncio + async session 픽스쳐

```python
# apps/api/tests/conftest.py (의사 코드)

import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

@pytest_asyncio.fixture
async def pg_engine() -> AsyncEngine:
    """Docker compose 로 띄운 PostgreSQL 에 연결."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def session(pg_engine: AsyncEngine) -> AsyncSession:
    """각 테스트마다 rollback 으로 격리."""
    async with AsyncSession(pg_engine) as session:
        async with session.begin():
            yield session
            await session.rollback()
```

#### transaction rollback 기반 격리

- 각 테스트는 트랜잭션을 시작하고 종료 시 rollback. DB 상태가 다음 테스트에 영향 없음.
- `session.begin()` + `yield` + `rollback()` 패턴.

#### 검토한 대안

- **A. 항상 Docker PostgreSQL**: SQLite 없이 통일. 단점: CI 가 느림, 로컬 테스트 마다
  Docker 필요. 기각 (단위 테스트가 불필요하게 무거워짐).
- **B. 항상 SQLite in-memory**: 빠르지만 JSONB / 배열 연산 등 PostgreSQL 고유 기능
  테스트 불가. 기각 (프로덕션 DB 와 괴리 발생).
- **C. testcontainers-python**: Docker 컨테이너를 Python 에서 직접 관리. 단점:
  testcontainers 의존성 추가, CI 세팅이 복잡. compose 기반이 더 단순. 기각.

---

## Consequences (결과)

### 긍정적 결과

- `shared/schemas/` 가 SQLModel / SQLAlchemy 에 의존하지 않으므로 `packages/extractor/`,
  `packages/llm/`, `packages/hwpx_renderer/` 의 의존성 그래프가 가볍다.
- Repository 의 `_validate_tenant_context` 가 sentinel UUID 누수를 구조적으로 차단 —
  ADR-0003 §D-3.6 의 보완 구현.
- `BaseRepository[TORM, TDomain]` generic 이 `tenant_id` 필터를 모든 쿼리에 자동 적용.
  code-reviewer 의 tenant_id 체크리스트 (CLAUDE.md §7.7) 를 구조적으로 만족.
- SQLModel 의 Pydantic v2 상속으로 `model_dump()` / `model_validate()` 가 ORM ↔ Pydantic
  변환에 그대로 사용 가능 — boilerplate 최소.

### 부정적 결과 / 비용

- **이중 클래스 drfit 위험**: `shared/schemas/passage.py` 의 `Passage` 와
  `models/passage.py` 의 `PassageORM` 이 필드가 달라지면 runtime 에 변환 실패.
  대응: CI 에서 `Passage.model_json_schema()` 와 `PassageORM` 의 컬럼 목록 비교
  assertion 테스트 (P0-1 에서 추가).
- **Alembic autogenerate 수동 review 부담**: D-5.4 의 알려진 이슈로 모든 autogenerate
  결과를 PR 에서 사람이 검토해야 함.
- **JSONB 컬럼이 있는 모델은 SQLite 단위 테스트 불가**: Docker PostgreSQL 통합 테스트만
  사용 — CI 가 약간 느려짐.
- **`from_attributes=True` 추가 필요**: `shared/schemas/common.py` 의 `WorkspaceScopedEntity`
  에 `from_attributes=True` 가 없으면 `model_validate(orm_instance)` 호출 시 실패.
  architect PR 에서 처리. P0-1 진입 전 필요.

### 후속 결정 트리거

- **architect PR 필요**: `shared/schemas/common.py` 에 `from_attributes=True` 추가.
  P0-1 차단 항목.
- **Phase 4 DB 레벨 방어 재검토**: sentinel UUID CHECK constraint 및 PostgreSQL RLS
  도입 ADR.
- **복잡 쿼리 패턴 문서화**: Repository 기본 메서드로 부족한 쿼리 (예: 다중 JOIN,
  집계) 가 나오면 별도 query 모듈 또는 `execute` 직접 호출 패턴 ADR.

---

## Alternatives Considered (종합)

각 D-5.* 에 alternatives 명시. 핵심 기각 패턴:

- **패턴 A (단일 클래스)**: `shared/` 의 의존성 오염 — 가장 큰 이유로 기각.
- **SQLModel 대신 pydantic-sqlalchemy**: 2023년 이후 유지보수 불활성. SQLModel 이
  더 넓은 커뮤니티 + tiangolo 지속 관리. CLAUDE.md §3.6 "검증된 라이브러리 우선".
- **SQLModel 대신 imperative mapping (SQLAlchemy 직접)**: Pydantic 모델과 ORM 의 완전
  분리가 가능하지만 boilerplate 가 가장 많음. SQLModel 의 `model_validate` 기반 변환에
  비해 이점 없음. 기각.

---

## 후속 작업 (P0-1 의 입력)

P0-1 (DB 마이그레이션 + 영속화 구현) 진입 시 본 ADR 의 결정이 다음 순서로 사용된다:

1. **D-5.4**: `alembic/env.py` 에 `SQLModel.metadata` + ORM import path 설정. 기존
   `tenants` / `workspaces` 마이그레이션 확인 후 SQLModel ORM 클래스 추가.
2. **D-5.1**: `apps/api/src/worksheet_api/models/` 디렉토리 신설. `TenantORM`,
   `WorkspaceORM`, `PassageORM` 작성. (architect PR — `from_attributes=True` 추가 —
   먼저 머지된 상태여야 함.)
3. **D-5.2**: `WorkspaceScopedORMBase` + `SENTINEL_UUID` 상수 정의.
4. **D-5.3**: `BaseRepository` generic 구현. `PassageRepository` 서브클래스 작성.
5. **D-5.6**: `PassageORM.source` JSONB 컬럼 선언. `_to_orm` / `_to_domain` 오버라이드.
6. **D-5.7**: `apps/api/tests/conftest.py` pytest-asyncio + async session 픽스쳐.
   sentinel UUID 검증 단위 테스트 + PassageRepository 통합 테스트 작성.

---

## PM 결정 필요 항목

없음 — 본 ADR 의 7개 결정은 기존 PM-2, ADR-0001, ADR-0003 의 확정된 결정을 구체화한
것으로, 추가 PM 판단이 필요한 미결 사항은 없다.

단, 다음 사항은 P0-1 작업 중 발견 시 PM 에스컬레이션 후보:

- `shared/schemas/` 의 Pydantic 모델이 SQLModel 으로의 전환 필요성이 강해지는 케이스
  발생 시 (예: lazy loading, 복잡한 관계 표현이 이중 클래스 패턴으로 감당 불가) →
  패턴 A 재검토 여부 PM 결정.
- SQLModel 0.0.x 버전의 미해결 버그가 P0-1 구현에서 블로킹으로 작용할 경우 →
  imperative mapping 으로 전환 여부 PM 결정.

---

## References

- `docs/adr/0001-canonical-schema-philosophy.md` (5경계 척추)
- `docs/adr/0003-phase-0-extraction-pipeline.md` §D-3.4 (영속화 책임), §D-3.6 (sentinel
  UUID), §PM-2 (SQLModel 채택 확정)
- `shared/schemas/common.py` (`WorkspaceScopedEntity` 현황)
- [SQLModel 공식 문서](https://sqlmodel.tiangolo.com/) — Alembic 통합, 관계 선언
- [SQLModel GitHub Issues](https://github.com/tiangolo/sqlmodel/issues) — Alembic
  autogenerate Enum 이슈 (#112, #216 등)
- [Alembic 공식 문서](https://alembic.sqlalchemy.org/) — `env.py` metadata 설정
- [pytest-asyncio 공식 문서](https://pytest-asyncio.readthedocs.io/) — async fixture 패턴
