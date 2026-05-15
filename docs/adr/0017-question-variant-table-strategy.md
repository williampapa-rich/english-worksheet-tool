# ADR 0017 — Question / VariantQuestion 단일 테이블 vs 별 테이블

- **상태(Status)**: Accepted
- **작성일**: 2026-05-10
- **결정일**: 2026-05-15 (PM Dennis — D1=(a) 단일 테이블 + variant_kind discriminator / D3 하이브리드 (행 최신 상태 + history 테이블) / D5 다단계 derive 허용 / D6 cascade SET NULL / D8 Phase 3 진입 전 1회 마이그레이션)
- **작성자**: architect
- **결정자**: PM (Dennis)
- **유형**: Phase 3 진입 차단 ADR — `Question` / `VariantQuestion` 의 *물리 모델*
  (테이블 분리 / 단일 테이블 / link 테이블) 결정. 본 ADR 은 *코드 변경 0* — 후속 PR
  에서 `shared/schemas/question.py` 진화 + Alembic 마이그레이션 (필요 시).
- **범위**: Phase 3 (변형문제) 진입 시점의 `Question` 물리 모델 + qa-validator 결과
  저장 위치 + 변형의 변형 (다단계 derive) 허용 여부 + cascade 정책. 본 ADR 은 v0.1
  의 *논리 결정* (단일 모델 + `variant_kind` discriminator + `derived_from_question_id`)
  을 그대로 유지할지 / 진화시킬지 결정.
- **관련 문서**:
  - `CLAUDE.md` v0.10.1 §1.3 (콘텐츠 자산화), §2.1 Phase 3 (변형문제 5개 + 정답 유일성
    검증), §6.2 (변형 유형은 별 카테고리가 아니라 기존 24 type 의 sub-form / 파생 —
    새 type 도입 안 함), §7.6 qa-validator (정답 유일성 검증 별도 LLM call), §11 Open
    Questions — "Question / VariantQuestion 단일 테이블 vs 별 테이블 — Phase 3 진입 전
    ADR (audit §4-5)"
  - `docs/schema-coverage-audit.md` §3.2 Gap J (VariantQuestion 표현 없음 → audit §4-5
    권고: 단일 테이블 + `variant_kind` discriminator), §4.2 Question 권고 (24 type
    enum 흡수 + `variant_kind` discriminator + `origin_question_id`)
  - `docs/adr/0001-canonical-schema-philosophy.md` (스키마 진화 — 새 필드 추가 위주,
    기존 필드 변경 지양 + breaking change 마이그레이션 필수)
  - `docs/adr/0002-content-model-v0_1.md` (v0.1 콘텐츠 모델 결정)
  - `docs/adr/0016-vocabulary-master-global-dedup.md` (별 ADR — 어휘 변형 LLM 컨텍스트
    source 정합)
  - `shared/schemas/question.py` — 현재 v0.1 모델 (`Question` 단일 클래스 +
    `VariantKind` enum + `derived_from_question_id: EntityId | None` +
    `_validate_variant_consistency` model_validator). 그러나 **물리 모델 결정은
    유보** — Pydantic 모델 차원의 *논리* 만 박혀있고 ORM / Alembic 이 어떻게 매핑할지
    미정.

---

## Context (배경)

### 1. CLAUDE.md §6.2 핵심 전제 — 변형 유형은 별 카테고리가 아니다

CLAUDE.md §6.2:

> **핵심 전제**: 변형 유형이라는 별도 카테고리는 없다. 모든 문제 유형은 기존
> `exam-generator`의 24개 유형 중 하나에 속한다. Phase 3의 "변형문제"도 기존 유형의
> 파생일 뿐, 새 유형이 아니다.

즉 *원본* 과 *변형* 은 **같은 24개 `QuestionType` enum 값** 을 공유한다. 이게 본 ADR
의 출발점 — type enum 이 두 곳에서 참조되어야 하는 모델 (별 테이블) 은 의미가 약하다.

### 2. v0.1 schema (논리) 의 현재 상태

`shared/schemas/question.py` (v0.1) 은 audit §4.2 권고 + CLAUDE.md §6.2 정정에 따라
**단일 Pydantic 모델** 로 출시했다:

```python
class Question(WorkspaceScopedEntity):
    type: QuestionType                                  # 24개 enum (원본/변형 공유)
    variant_kind: VariantKind = VariantKind.ORIGINAL    # 변형 유형 discriminator
    derived_from_question_id: EntityId | None = None    # 변형이면 NOT NULL (validator 강제)
    # ... 24 type 의 모든 sub-form 필드 (sub_passages / given_sentence / summary / ...)
    # ... LLM 자가검증 메타 (plan / naturalness_check / referent_assignments)
    # ... qa-validator 메타 (uniqueness_validated / uniqueness_validator_note)
```

`_validate_variant_consistency` model_validator 는 `variant_kind == ORIGINAL` ↔
`derived_from_question_id == None` 정합을 강제한다 — *Pydantic 차원* 에서 논리 모델
완성.

그러나 **ORM / 물리 테이블 결정은 유보 상태** — `apps/api/.../models/question_orm.py`
가 아직 작성되지 않았고 (Phase 3 진입 시점에 작성), Alembic 도 `questions` 테이블을
만들지 않았다 (Phase 0~2 는 Question 영속화 대상 아님).

### 3. Phase 3 진입 시 추가되는 시맨틱 — qa-validator + 변형 메타

CLAUDE.md §2.1 Phase 3 DoD + §7.6 qa-validator:

- 변형 유형 5개 이상 (어휘 / 어법 / 빈칸 / 어순 / 주제·요지 등).
- **정답 유일성 자동 검증 (qa-validator agent 가 별도 LLM call)** — 결과를 *어디에*
  저장하는가가 본 ADR 의 핵심 결정 항목.
- 변형 결과가 다시 정규화된 Question 으로 들어가서 Phase 1, 2 파이프라인과 호환.

v0.1 의 `uniqueness_validated` / `uniqueness_validator_note` 가 이미 박혀있다 (audit-
review-domain §4.1 권고). 단 이 두 필드는 *원본* 에도 *변형* 에도 동일하게 존재 — 별
테이블 분리 시 이 필드들이 양쪽에 중복되거나 한 곳에만 박힘 (DRY 위반).

### 4. 변형의 *고유* 메타 — 별 테이블 분리의 정당화 후보

별 테이블 (`Question` / `VariantQuestion` 분리) 가 정당화되려면 *변형만의 메타* 가
충분히 많아야 한다. 후보:

| 메타 후보 | 변형만? | 비고 |
|---|---|---|
| `derived_from_question_id` | 변형만 | 자명. 단 nullable FK 1개 — 단일 테이블이라도 비용 0. |
| `variant_kind` | 양쪽 (단일 enum) | `ORIGINAL` 이 enum 값으로 들어가 양쪽 표현. |
| LLM 변형 생성 메타 (어휘 후보 list / 시도 횟수 등) | 변형만 | *생성 과정* 메타 — Phase 3 LLM 호출 trace. 별 테이블이면 깔끔하지만 단일 테이블 nullable 로도 가능. |
| qa-validator 결과 (uniqueness_validated 등) | 양쪽 | 원본도 검증 가능 (입력 자료 자체에 정답 모호성 있을 수 있음). 별 테이블 시 양쪽 중복 필드. |
| 변형 검증 상태 (사용자 채택 / 거부) | 변형만 | 변형 *workflow* 메타 — 사용자가 LLM 변형 결과를 채택/거부. 단순 `bool` 또는 `enum`. |
| 원본 reference range (지문 위치 / 마커 인덱스) | 변형만 | 변형이 *원본의 어느 부분을 변경했는가* 표시. 단순 string 또는 JSON. |

→ *변형만의 메타* 는 3~5 필드 수준. **테이블 분리를 정당화할 만큼 크지 않다**.

### 5. ADR-0013 / ADR-0015 와의 정합 — Pydantic discriminated union 가능성

ADR-0013 D5-a 의 *LLM output 별 schema vs domain schema 분리* 패턴은 Phase 3 변형
LLM output 에도 적용 가능 — 단 그건 LLM 호출 *어댑터* 의 책임이지 영속 모델 분리와는
별 issue.

`Question` 의 *읽기 시점* 분기 (원본/변형 다른 화면 표시) 는 Pydantic v2 의
**discriminated union** 으로 깔끔히 처리 가능:

```python
# 가설 — 본 ADR 권장 안 (a) 채택 시 v0.2 schema 의 표현 가능성
QuestionRead = Annotated[
    Union[OriginalQuestionRead, VariantQuestionRead],
    Field(discriminator="variant_kind"),
]
```

단 *물리 모델* (DB 테이블) 은 단일 테이블이고, *읽기 DTO* 만 discriminated union
표현 — *동일 물리 모델 / 다른 표현* 패턴 (NRTW 정합).

---

## Decision (결정)

### D1. 도입 방식 — 권장안: (a) 단일 `Question` 테이블 + `variant_kind` discriminator

**3가지 안 검토 + 권장**:

#### (a) [권장] 단일 `Question` 테이블 + `variant_kind` + `derived_from_question_id` (self-FK nullable)

```
Question (단일 테이블 — v0.1 schema 그대로 영속화)
  - id (UUID)
  - tenant_id, workspace_id (FK)
  - passage_id (FK)
  - type (QuestionType enum, 24개)
  - variant_kind (VariantKind enum)
    - ORIGINAL: 원본
    - VOCABULARY_SWAP / GRAMMAR_SWAP / BLANK_INFERENCE / THEME_REWORD /
      ORDER_SHUFFLE / ... (Phase 3 enum 보강)
  - derived_from_question_id (self-FK, NULLABLE)
    - variant_kind == ORIGINAL: NULL
    - variant_kind != ORIGINAL: NOT NULL (DB CHECK 제약 + Pydantic validator)
  - ... 모든 sub-form 필드 (v0.1 그대로)
  - uniqueness_validated (bool), uniqueness_validator_note (str | None)
  - variant_metadata (JSONB | NULL) — 변형만의 작은 메타 (Context 4)
```

**장점**:
- **CLAUDE.md §6.2 정합** — 24 type enum 1곳 참조 + 변형이 type 을 공유.
- v0.1 Pydantic 모델 그대로 영속화 → ADR-0001 의 *canonical schema 1개의 SSOT* 원칙
  유지.
- self-FK 1개 + nullable 컬럼 몇 개 — 스키마 단순.
- 자가 cascade 처리 (D4) 가 self-FK 한 곳만 정의하면 끝.
- 통계 / 검색 쿼리 단순 (`SELECT * FROM questions WHERE passage_id = ? AND
  variant_kind = 'ORIGINAL'`).
- Pydantic v2 discriminated union 으로 *읽기 DTO* 분기 가능 (Context 5).

**단점**:
- *변형만의 메타* 가 NULLABLE column (또는 JSONB) 으로 저장 — 원본 행에서는 항상 null.
  단 5필드 미만이면 무시 가능 비용.
- Phase 3 변형 추가 시 NULLABLE column 이 늘어날 가능성 — *변형만의 큰 메타* 필요해
  지면 별 1:1 테이블 (`question_variant_metadata`) 분리 옵션 (D2-c).

#### (b) [대안] 별 `Question` / `VariantQuestion` 테이블 + 24 type enum 양쪽 참조

```
Question (원본만)
  - id, tenant_id, workspace_id, passage_id, type (24 enum)
  - sub-form 필드 (모두)
  - uniqueness_validated, uniqueness_validator_note

VariantQuestion (변형만)
  - id, tenant_id, workspace_id
  - origin_question_id (FK → questions.id, NOT NULL)
  - type (24 enum, 같은 enum 양쪽 참조)
  - variant_kind (variant only enum — ORIGINAL 제외)
  - sub-form 필드 (모두 — 원본과 동일)
  - LLM 변형 생성 메타 (생성 trace)
  - 사용자 채택/거부 상태
  - uniqueness_validated, uniqueness_validator_note
```

**장점**:
- *변형만의 메타* 가 자연스러운 위치.
- 변형이 *원본 없이도 존재할 수 있는 lifecycle* (예: LLM 이 생성했다가 거부된 변형 — orphan)
  가능.
- 검색 / 권한 분리 (예: 변형은 사용자 워크플로우 테이블, 원본은 콘텐츠 자산 테이블).

**단점**:
- **CLAUDE.md §6.2 위반 가능성** — 24 type enum 이 양쪽 테이블에서 참조 → DRY 위반은
  아니지만 *enum 변경* 시 양쪽 ORM / Alembic / 테스트 수정. 변경 비용 늘어남.
- sub-form 필드 (`given_sentence` / `sub_passages` / `summary` / `inline_choices` /
  `choice_format` / `choice_matrix` / `referent_assignments` ...) 가 *양쪽 테이블에
  중복* — 약 15~20 필드. v0.1 Pydantic 모델의 *2배 ORM 매핑* 비용.
- Phase 1/2 의 워크시트 렌더 코드 (현재 Question 1종만 가정) 가 *원본/변형 양쪽 처리*
  로 진화 — 분기 비용.
- `uniqueness_validated` 같은 양쪽 공통 메타가 *각 테이블에 중복* 정의.
- 변형이 *원본 의 변형* (다단계 derive — D5) 인 케이스 표현 어색 — VariantQuestion
  의 self-FK 또는 origin → variant 외에 variant → variant 의 별 FK 컬럼.

→ 변형의 *고유 메타* 가 3~5 필드 수준 (Context 4) 이라면 별 테이블 분리의 비용 >
이득. 권장 안 함.

#### (c) [대안] `Question` + `QuestionVariant` link 테이블 (M:N)

```
Question (모든 문제 — 원본/변형 모두 단일 테이블, (a) 와 동일)
QuestionVariantLink (link 테이블)
  - origin_question_id (FK → questions.id)
  - variant_question_id (FK → questions.id)
  - variant_kind (enum)
  - PRIMARY KEY (origin, variant)
```

**장점**:
- 변형이 *여러 원본 결합* 표현 가능 (M:N — 예: 두 원본의 어휘를 합친 변형).
- 하나의 변형이 *여러 원본의 파생* 표현 가능.

**단점**:
- 도메인이 *진짜* M:N 인가? — Phase 3 의 변형 5종 (어휘/어법/빈칸/어순/주제) 모두 *1:1
  derive* (한 원본 → 한 변형). M:N 시나리오는 가설일 뿐 실수요 없음.
- link 테이블 추가 + JOIN 비용 (변형 1개 fetch 시 link → questions 두 번 hop).
- (a) 의 self-FK 단순함을 잃음.

→ 도메인이 M:N 아니면 비용만 추가. 권장 안 함.

**최종 권장**: **(a) 단일 `Question` 테이블 + `variant_kind` discriminator + self-FK
nullable**. v0.1 Pydantic 모델 그대로 영속화.

### D2. 24 type enum 흡수 정합

#### D2-a. enum 단일 정의 위치

`shared/schemas/question.py` 의 `QuestionType` enum 1곳 — 원본/변형 *공통 참조*.

별 테이블 (안 (b)) 채택 시에도 enum 정의는 1곳 — 단 *enum 변경 영향 면적* (ORM /
Alembic / 테스트 / type guard) 이 양쪽으로 확장. 단일 테이블 (안 (a)) 은 영향 면적
*1배*.

#### D2-b. variant_kind enum 보강 시점

`VariantKind` enum 의 v0.1 정의:

```python
ORIGINAL, VOCABULARY_SWAP, GRAMMAR_SWAP, BLANK_INFERENCE, THEME_REWORD, ORDER_SHUFFLE
```

domain-expert 의 `docs/variant-type-catalog.md` 결과로 보강 (별 후속 PR — `shared/
schemas/question.py` 주석 명시). 본 ADR 은 enum 값 결정 영역 아님.

#### D2-c. variant 만의 메타 — JSONB vs 별 1:1 테이블

권장 안 (a) 의 `variant_metadata: JSONB | NULL` 후보 vs `question_variant_metadata`
별 1:1 테이블:

| 옵션 | 장점 | 단점 |
|---|---|---|
| JSONB column | 스키마 변경 없이 추가 메타 자유. NULL 행 (원본) 비용 거의 0. | 스키마 강제 약함 — Pydantic v2 모델로 검증하더라도 DB 차원에서는 unstructured. |
| 별 1:1 테이블 | 스키마 강제. 메타 lifecycle 분리. | JOIN 비용 + 마이그레이션 복잡. |

**권장**: JSONB (v0.1) — 메타가 작고 (3~5 필드) 정착 안 됐으므로. Phase 3 종료 후
메타가 큰 lifecycle (예: LLM 생성 trace 가 PII 추적 대상) 으로 진화하면 별 1:1 테이블
승격.

### D3. qa-validator 결과 저장 위치 (CLAUDE.md §7.6 정합)

핵심 결정: qa-validator 의 정답 유일성 검증 결과를 어디에 저장하는가?

#### D3-a. [권장] Question 행 자체 (`uniqueness_validated` / `uniqueness_validator_note`)

v0.1 schema 그대로 — 단일 컬럼 2개 (bool + str). 검증 *상태* 만 기록.

**장점**:
- v0.1 그대로 — schema 변경 0.
- *현재 상태* 만 알면 충분 — 매번 재검증 시 덮어쓰기.

**단점**:
- *재검증 history* 보존 안 됨 (검증 N회 시도 했는데 마지막 1회 결과만 남음).
- LLM 호출 trace (cost / model / prompt version) 보존 안 됨 — 비용 모니터링 별 issue.

#### D3-b. [대안] 별 `qa_validation_results` 테이블 (검증 history 보존)

```
qa_validation_results
  - id (UUID)
  - question_id (FK)
  - validated_at (timestamp)
  - result (PASS / FAIL / TIMEOUT)
  - note (str)
  - llm_model, llm_cost (USD)
  - prompt_template_id
  - request_id (LLM 호출 ID)
```

**장점**:
- 검증 history + 비용 trace 보존.
- ADR-0013 D8 (`llm_usage_logs`) 패턴과 정합 — 같은 trace 모델.

**단점**:
- Question 의 *최신 검증 상태* 조회 시 join + LATEST aggregation 필요.

#### D3-c. [권장 — 하이브리드] Question 행에 *최신 상태* + 별 테이블에 *history*

- `Question.uniqueness_validated` / `uniqueness_validator_note` (v0.1) — 캐시.
- `qa_validation_results` 테이블 — history + 비용 trace.

**장점**:
- 캐시 (Question.uniqueness_*) 로 단순 쿼리, history 가 필요한 경우만 별 테이블 join.
- ADR-0013 D8 의 `llm_usage_logs` 패턴 재사용.

**단점**:
- 캐시 정합 (Question.uniqueness_validated 갱신 누락 시 stale) — race 조건 주의.

→ Phase 3 진입 시 D3-a (v0.1 그대로) 시작 + 비용 모니터링 ADR (CLAUDE.md §11 — Phase 3
진입 전 별 ADR) 결정 시 D3-c 로 승격. **본 ADR 의 default 권장은 D3-a**.

### D4. shared/schemas/question.py 영향 (설계만, 코드 작성 X)

#### D4-a. v0.1 schema 변경 0 — Pydantic 모델 그대로

권장 안 (a) 채택 시 `shared/schemas/question.py` 변경 0. 단 *주석 보강* — ORM / Alembic
의 *물리 매핑 정책* 명시:

> **물리 매핑 정책 (ADR-0017 권장 안 (a))**:
>   - 단일 `questions` 테이블 + `variant_kind` discriminator.
>   - `derived_from_question_id` 는 self-FK NULLABLE.
>   - `variant_metadata: JSONB | NULL` 컬럼 (Phase 3 진입 시 신규).

#### D4-b. Pydantic discriminated union 도입 — *읽기 DTO* 만

권장 안 (a) 채택 시 *물리 모델* 은 단일 테이블이지만 *읽기 DTO* 분기 표현 가능:

```python
# shared/schemas/question.py — Phase 3 진입 시 추가 (선택)
class OriginalQuestionRead(Question):
    variant_kind: Literal[VariantKind.ORIGINAL] = VariantKind.ORIGINAL
    derived_from_question_id: Literal[None] = None

class VariantQuestionRead(Question):
    variant_kind: Annotated[VariantKind, Field(...)]   # ORIGINAL 제외
    derived_from_question_id: EntityId

QuestionRead = Annotated[
    Union[OriginalQuestionRead, VariantQuestionRead],
    Field(discriminator="variant_kind"),
]
```

이 도입은 Phase 3 의 *프론트엔드* 또는 *Worksheet 렌더* 가 분기 표현 필요할 때만.
ADR 본 결정에는 영향 없음.

#### D4-c. ORM 매핑 — SQLAlchemy single-table inheritance vs 단순 컬럼

SQLAlchemy 의 *single-table inheritance* 는 복잡 — 단순 컬럼 (`variant_kind` enum)
+ Pydantic 차원 분기로 충분. backend-dev 가 ORM 작성 시 ADR-0005 (SQLAlchemy 매핑
패턴) 정합으로 결정.

### D5. 변형의 변형 — 다단계 derive 허용 여부

#### 케이스: A (원본) → B (어휘 변형) → C (B의 어법 변형)

**옵션**:

- (i) [권장] 다단계 허용 — `C.derived_from_question_id = B.id`. self-FK chain 으로
  표현. 그래프 traverse 로 root 추적.
- (ii) 다단계 금지 — `derived_from_question_id` 가 *항상 ORIGINAL* 을 가리킨다 (전이 닫힘).

→ 권장: (i). 도메인 (어휘 변형 → 어법 변형 추가) 자연스러움. 단 *cycle 방지* 는
DB CHECK 제약 또는 application 차원 (insert 시 ancestry traversal — depth 제한 5단계
권장).

#### Cycle 방지

self-FK chain 의 cycle 위험:
- (i) DB 차원: PostgreSQL 은 `WITH RECURSIVE` CTE 만 cycle 검출. INSERT 시 자동 차단
  안 됨 → application 차원 검증 필요.
- (ii) Application 차원: insert 전 ancestry traversal — depth 5 도달 시 reject 또는
  cycle 검출 시 reject.

→ 권장: depth 제한 5단계 + cycle 검출 (application 차원). 별 backend chore.

### D6. cascade 정책 — 원본 question 삭제 시 variant 처리

#### 옵션:

- (i) [권장] **CASCADE** — 원본 삭제 시 모든 변형 자동 삭제. self-FK ON DELETE
  CASCADE.
- (ii) **SET NULL** — 원본 삭제 시 변형의 `derived_from_question_id` → NULL. 단
  Pydantic validator (variant 면 NOT NULL) 위반 → 충돌.
- (iii) **RESTRICT** — 원본 삭제 시 변형이 있으면 차단. 사용자가 변형 먼저 삭제해야
  원본 삭제 가능.
- (iv) **변형을 ORIGINAL 로 promote** — 변형이 *독립 콘텐츠 자산* 이라고 가정. 원본
  삭제 시 `variant_kind = ORIGINAL` + `derived_from_question_id = NULL` 자동 갱신.

**권장**: (i) CASCADE — 변형은 *원본의 파생 콘텐츠* 이지 독립 자산이 아니다 (CLAUDE.
md §6.2). 원본 삭제는 *그 origin context 전체 삭제* 의도 명확. 단 사용자가 *변형만
보존* 의도라면 (iv) promote 패턴이 별 라우트로 가능 (Phase 3 후 chore — `POST
/questions/{vid}/promote`).

### D7. Open Questions (결정 미루는 항목)

- [ ] **D2-c JSONB vs 별 1:1 테이블 변환 트리거** — Phase 3 종료 후 *변형만의 메타*
      가 PII / 비용 trace 등 큰 lifecycle 로 진화할 때 승격. 별 ADR.
- [ ] **D3 qa-validator 결과 저장 — D3-a vs D3-c 트리거** — 비용 모니터링 ADR
      (CLAUDE.md §11) 결정 시점. v0.1 은 D3-a 유지.
- [ ] **D5 depth 제한 정책** — 5단계 제한이 도메인적으로 충분한가? domain-expert
      검토.
- [ ] **D6 promote 패턴 (옵션 iv) 도입 시점** — 와이프가 *변형만 보존* 시나리오를 실제
      요청할 때.
- [ ] **변형 채택 / 거부 워크플로우 메타** (Context 4) — Phase 3 진입 후 첫 변형 생성
      PR 에서 결정. 본 ADR 은 자리만.

### D8. 도입 시점 — 권장 트리거

#### 권장 시점: **Phase 3 진입 *직전* — `questions` 테이블 첫 Alembic 마이그레이션과 동시**

이유:
- v0.1 Pydantic 모델은 이미 `derived_from_question_id` + `variant_kind` 박혀있음 →
  ORM / Alembic 만 추가하면 본 ADR 의 *물리 모델* 결정 즉시 반영.
- Phase 3 *첫* 변형 생성 PR 이전에 마이그레이션 끝나야 변형 LLM 코드가 단순.
- ADR-0016 (VocabularyMaster) 결정과 *순서 무관* — 두 ADR 은 직교 (어휘 자산 vs
  Question 물리 모델).

#### 비-대안: Phase 3 도중 (변형 생성 PR 머지 후) — retrofit 비용 큼

- Phase 3 첫 변형 PR 이 *물리 모델 가정* 으로 작성됨 → 본 ADR 결정이 그 가정과 다르면
  PR 일부 재작성.

→ **Phase 3 진입 전 (변형 LLM 코드 작성 *전*)** 마이그레이션. PM 결정.

### D9. Phase 별 변경 비용

| 도입 시점 | 변경 비용 | 비고 |
|---|---|---|
| Phase 2-edit 종료 직후 (Phase 3 진입 전) | 낮음 — 신규 테이블 1건 + Pydantic 모델 영속화 | 권장 ✓ |
| Phase 3 첫 변형 PR 과 동시 | 중 — 변형 LLM + 마이그레이션 + 테스트 동시 → 분리 권장 | 차선 |
| Phase 3 종료 후 | 높음 — 운영 데이터 backfill (variant_kind=ORIGINAL 채움) + 변형 PR retrofit | 회피 |

---

## Consequences (결과)

### 긍정적 결과

1. **CLAUDE.md §6.2 정합** — 24 type enum 1곳 참조 + 변형이 type 공유.
2. **v0.1 Pydantic 모델 그대로 영속화** — ADR-0001 *canonical schema 1개의 SSOT*
   원칙 유지.
3. **자가 cascade 처리** (D6 CASCADE) — self-FK 1곳만 정의.
4. **Pydantic discriminated union 으로 *읽기 DTO* 분기 가능** — 동일 물리 모델 / 다른
   표현 패턴 (NRTW 정합).
5. **Phase 3 진입 전 마이그레이션 단순** — 신규 테이블 1건 + 컬럼 추가만.
6. **schema 변경 0** — 본 ADR 채택 시 `shared/schemas/question.py` 코드 수정 없음
   (주석 보강만).

### 부정적 결과 / 리스크

1. **NULLABLE column 다수** — `variant_kind != ORIGINAL` 일 때만 의미 있는 컬럼 (현재는
   `derived_from_question_id` 1개, Phase 3 진입 시 `variant_metadata` 추가 가능). 단
   5필드 미만이면 무시 가능.
2. **변형의 *고유* 메타 lifecycle 변화 시 retrofit** — JSONB 가 정착 후 강 schema 가
   필요해지면 별 1:1 테이블 승격 (D2-c). 본 ADR 은 그 트리거를 명시.
3. **다단계 derive cycle 위험** — application 차원 검증 (D5). 별 backend chore.
4. **CASCADE 의도 불일치 위험** — 원본 삭제 시 변형 보존 의도 사용자가 있을 수 있음.
   완화: promote 패턴 (D6 iv) 별 라우트 — Phase 3 후 chore.
5. **qa-validator history 보존 부재** (D3-a) — Phase 3 비용 모니터링 ADR 결정 시 D3-c
   로 승격.

---

## 후속

본 ADR 결정 (Accepted) 후:

1. **architect** — `shared/schemas/question.py` 주석 보강 PR (D4-a — 물리 매핑 정책
   명시). 코드 변경 0.
2. **backend-dev** — Alembic 마이그레이션 1건 (`questions` 테이블 + `variant_metadata
   JSONB` + self-FK ON DELETE CASCADE + UNIQUE index 등). ORM `QuestionORM` 추가.
3. **backend-dev** — application 차원 cycle 검출 (D5) + depth 5 제한.
4. **domain-expert** — `docs/variant-type-catalog.md` 재작성 → `VariantKind` enum 보강
   (별 후속 PR — D2-b).
5. **qa-validator agent** — Phase 3 진입 시 활성. D3-a (v0.1 그대로) 로 시작 + 비용
   모니터링 ADR 결정 시 D3-c 승격.
6. **code-reviewer** — Alembic 의 멀티테넌트 격리 / sentinel UUID 차단 / cascade
   정합 검토.
7. **CLAUDE.md** — §11 Open Questions 의 *Question / VariantQuestion 단일 테이블 vs
   별 테이블* 항목에 본 ADR 링크 추가 (Accepted 시점에 close 표시).

---

## 결정 기록

| 날짜 | 상태 | 결정자 | 비고 |
|---|---|---|---|
| 2026-05-10 | Proposed | architect | Phase 3 진입 차단 ADR 2/2 — Question / VariantQuestion 단일 테이블 결정. 권장: 단일 테이블 (a) + `variant_kind` discriminator + self-FK NULLABLE + `variant_metadata JSONB`. PM 결정 대기 — D1/D3/D5/D6/D8 5개 항목. |
