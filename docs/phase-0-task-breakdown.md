# Phase 0 작업 분해 — PR 단위 / 의존성 / DoD

- **작성자**: architect agent
- **작성일**: 2026-05-02
- **상태**: Phase 0 진입 전 합의용 (PM 검토 후 backend-dev 가 작업 시작)
- **관련 문서**:
  - `CLAUDE.md` §2.1 (Phase 0 DoD), §9 (Sprint 0 — 종료됨)
  - `docs/adr/0003-phase-0-extraction-pipeline.md` (모듈 경계 결정)
  - `docs/adr/0001-canonical-schema-philosophy.md`
  - `docs/adr/0002-content-model-v0.1.md`
  - `shared/schemas/` v0.1

---

## 1. Phase 0 잔여 DoD (재명시)

CLAUDE.md §2.1 Phase 0 DoD 5개 중 잔여 3개:

- **(2)** Vision LLM 추출 파이프라인 — PDF / 이미지 / 텍스트 1건씩 정규화된 객체 반환.
- **(3)** DB 에 Passage 저장/조회.
- **(4)** 멀티테넌트 스키마 (`tenant_id`) + 인증 stub.

이 3개를 PR 8~10개로 분해한다.

---

## 2. PR 단위 작업 리스트

각 PR 항목 형식:

- **ID** — 본 문서 내 식별자.
- **담당 agent** — backend-dev / frontend-dev / qa-validator / architect / code-reviewer.
- **입력 (의존)** — 어느 PR / 결정사항이 머지된 후 시작 가능한가.
- **DoD** — 어떻게 끝났다고 판단하는가.
- **크기** — S (≤300 LOC, ≤1일) / M (≤700 LOC, 1~2일) / L (>700 LOC 또는 외부 검증
  필수, 2~4일).
- **PR 단위 분리 고려 사항** — review burden 분산 / rollback 가능성.

---

### P0-1. DB 마이그레이션 — 도메인 테이블 일괄 추가

- **담당**: backend-dev
- **입력**: ADR-0003 머지, `shared/schemas/` v0.1 (이미 머지됨)
- **DoD**:
  - `apps/api/alembic/versions/` 에 새 마이그레이션 1개 추가.
  - 새 테이블: `passages`, `questions`, `vocabulary`, `translations`,
    `syntax_annotations`. `worksheets` / `worksheet_items` 는 Phase 1+ 로 미루므로
    본 PR 범위 밖 (`shared/schemas/worksheet.py` 는 이미 있지만 DB 매핑은 후속).
  - 모든 테이블에 `tenant_id` (FK → tenants.id, NOT NULL), `workspace_id` (FK →
    workspaces.id, NOT NULL), `created_at`, `updated_at` 컬럼.
  - `passages.source` 는 JSONB 컬럼 (Pydantic `SourceMeta` 직렬화 형태).
  - `questions.passage_id` (FK → passages.id, NOT NULL).
  - `questions.derived_from_question_id` (FK → questions.id, nullable).
  - `vocabulary.passage_id` (FK → passages.id, nullable — audit §4-3 의 Phase 2+
    글로벌화 여지).
  - `translations.passage_id` (FK → passages.id, NOT NULL).
  - `syntax_annotations.passage_id` (FK → passages.id, NOT NULL).
  - 인덱스: 모든 도메인 테이블에 `(tenant_id, workspace_id)` 복합 인덱스 +
    `passage_id` 컬럼 보유 테이블에는 `(tenant_id, passage_id)` 추가 인덱스.
  - `apps/api/src/worksheet_api/models/` 에 ORM 모델 5개 추가
    (`passage.py`, `question.py`, `vocabulary.py`, `translation.py`,
    `syntax_annotation.py`).
  - `models/__init__.py` 에서 export.
  - `alembic upgrade head` / `downgrade -1` 양방향 동작.
  - 단위 테스트: 빈 DB → upgrade → 다시 downgrade 순환 1회 통과.
- **크기**: M (~500 LOC: ORM 5개 + 마이그레이션 1개 + 테스트).
- **분리 고려**:
  - 5 테이블을 1 PR 로 — 도메인 일관성 (멀티테넌트 / FK / 인덱스 표준) 한 번에 검증.
  - 분리하면 review burden 분산되지만 inter-FK (passage ← question 등) 가 PR 간
    걸쳐 머지 순서 의존이 발생.
  - **결정**: 1 PR. 단 ORM 도구 선정 (SQLModel / pydantic-sqlalchemy / imperative)
    이슈가 ADR-0001 §Consequences 에 미결로 남아있음. 본 PR 에서 backend-dev 가
    선정 + ADR-0005 (별 PR) 작성.

#### 결정 필요 (PR 시작 전)

- ADR-0001 §Consequences "후속 결정 트리거" — SQLAlchemy 매핑 도구 선정 (SQLModel /
  pydantic-sqlalchemy / imperative). backend-dev 가 ADR-0005 로 결정 후 본 PR 시작.

---

### P0-2a. `packages/llm/` — Core (client + retry + prompt + jsonl sink)

- **담당**: backend-dev
- **입력**: ADR-0003 머지 (인터페이스 합의). **DB 의존 없음** — P0-1 머지 안 기다림.
- **DoD**:
  - `packages/llm/src/llm/` 모듈 구조:
    - `client.py` — `StructuredLLMClient` 프로토콜 + `AnthropicStructuredLLMClient`
      구현체.
    - `prompt.py` — `PromptSpec` (`docs/prompts/` 마크다운 + frontmatter 로딩 + 변수
      바인딩).
    - `errors.py` — `LLMSchemaValidationError`, `LLMTimeoutError`, `PermanentLLMError`
      등 예외 계층.
    - `retry.py` — 지수 백오프 (max 2 재시도, jitter ±25%).
    - `usage.py` — `TokenUsage`, `StructuredLLMResult` 모델.
    - `sinks/jsonl.py` — `JsonlUsageSink` (PM-4 의 백업 sink). 첫 sink 는 jsonl 만.
    - `sinks/base.py` — `UsageSink` 프로토콜 (DB sink 가 P0-2b 에서 추가 가능하도록).
  - exam-generator `app/llm/anthropic.py` 의 `tool_use input_schema` 패턴 그대로 흡수
    (CLAUDE.md §3.6).
  - `docs/prompts/` 에 디렉토리 생성 + 첫 프롬프트 (P0-3 의 텍스트 추출용) 1개.
  - 환경변수: `ANTHROPIC_API_KEY` 필수, 누락 시 명확한 에러.
  - 단위 테스트:
    - `StructuredLLMClient` mock 으로 호출자 (extractor 등) 가 사용 가능 검증.
    - 재시도 로직 (mock 으로 schema validation 실패 1회 → 성공 시나리오).
    - structured output 정상 파싱.
    - jsonl sink 가 호출 1건당 1줄 기록 검증.
  - 통합 테스트 — *실제 Anthropic API 호출 1건* — `pytest -m integration` 으로 분리,
    CI 에서는 skip (API key 필요).
- **크기**: M (~650 LOC: client + retry + prompt + sink + 테스트).
- **분리 고려**: P0-2b (DB sink) 와 분리한 이유는 의존성 그래프 §3 참고. Core 가 DB
  의존 없이 머지되면 P0-3 (text extractor) 차단 즉시 해제.

### P0-2b. `packages/llm/` — DB sink (`llm_usage_logs` 기록)

- **담당**: backend-dev
- **입력**: P0-2a 머지 + P0-1 머지 (`llm_usage_logs` 테이블 존재).
- **DoD**:
  - `packages/llm/src/llm/sinks/db.py` 추가 — `DbUsageSink` 가 `UsageSink` 프로토콜
    구현. SQLAlchemy session 받아서 `llm_usage_logs` 에 insert.
  - `MultiplexUsageSink` (또는 단순 list 기반 dispatch) — DB sink + jsonl sink 둘 다
    동시 기록. DB 실패 시 jsonl 은 계속 기록 (안전망).
  - LLM client 가 sink 를 의존성 주입 — `client = AnthropicStructuredLLMClient(sink=...)`.
  - 단위 테스트: DB sink mock + jsonl sink fake → 양쪽 동시 기록 검증, DB 실패 시
    jsonl 기록 유지 검증.
- **크기**: S (~200 LOC).
- **분리 고려**: P0-2a 와 합칠 수 있으나 P0-1 머지 의존이 P0-2a 의 P0-3 차단 해제를
  지연시킴. 분리가 critical path 를 짧게 함.

---

### P0-3. Extractor — 텍스트 입력 경로

- **담당**: backend-dev
- **입력**: P0-2 머지 (`packages/llm/`)
- **DoD**:
  - `packages/extractor/src/extractor/` 모듈 구조:
    - `base.py` — `Extractor` 프로토콜 + `ExtractionRequest` / `ExtractionResult`
      Pydantic 모델.
    - `text.py` — `extract_from_text(text: str, ...) -> ExtractionResult`.
    - `normalizer.py` — LLM 출력 → `Passage` / `Question` 정규화 (마커 inline 보존,
      ADR-0004 결정 전이므로 v0.1 은 raw 보존).
  - LLM prompt: `docs/prompts/extract-text-v0.md` — 영어 지문 텍스트 입력 → Passage
    + Question 추출.
  - `tenant_id` / `workspace_id` 는 sentinel UUID (ADR-0003 D-3.6) 로 채움.
  - 단위 테스트:
    - mock LLM client → 정상 추출 결과 검증.
    - 빈 입력 → `EmptyInputError`.
    - LLM 응답이 `Question.type` enum 위반 → `LLMSchemaValidationError` propagate.
  - 통합 테스트 (integration mark): 짧은 영어 지문 1건 → 실제 LLM 호출 → 결과 schema
    검증.
- **크기**: M (~400 LOC).
- **분리 고려**: P0-3/4/5 를 한 PR 로 합치면 review 부담 큼 — 분리 권고. text 가 가장
  단순하므로 base/normalizer/Extractor 프로토콜은 P0-3 PR 에 포함.

---

### P0-4. Extractor — 이미지 입력 경로 (Claude Vision)

- **담당**: backend-dev
- **입력**: P0-3 머지 (base / normalizer 공유)
- **DoD**:
  - `packages/extractor/src/extractor/image.py` 추가.
  - `extract_from_image(image_bytes: bytes, media_type: str, ...) -> ExtractionResult`.
  - LLM 래퍼의 Vision 입력 패턴 사용 — `ImageInput(bytes, media_type)`.
  - LLM prompt: `docs/prompts/extract-image-v0.md` — 이미지 (영어 시험지 1문제) →
    Passage + Question 추출. Vision 특수 가이드 (예: "이미지 안의 모든 영어 텍스트를
    OCR 한 후 정규화") 포함.
  - 지원 media type: `image/png`, `image/jpeg`, `image/webp`. 그 외는 `UnsupportedMediaTypeError`.
  - 단위 테스트:
    - mock LLM client → Vision payload 가 정확히 전달되었는지 검증.
    - unsupported media type → 적절한 예외.
  - 통합 테스트: `tests/fixtures/sample_image.png` (1문제 영어 시험지 캡처) → 실제 Vision
    호출 → 결과 검증.
- **크기**: M (~350 LOC).
- **분리 고려**: P0-5 (PDF) 와 합치면 600+ LOC — 별 PR 권고.

---

### P0-5. Extractor — PDF 입력 경로 (PyMuPDF + Vision fallback)

- **담당**: backend-dev
- **입력**: P0-3 + P0-4 머지 (text + image 양쪽 어댑터 공유)
- **DoD**:
  - `packages/extractor/src/extractor/pdf.py` 추가.
  - `extract_from_pdf(pdf_bytes: bytes, *, force_vision: bool = False) -> ExtractionResult`.
  - PyMuPDF 로 1차 텍스트 추출 → ADR-0003 D-3.3 의 4종 휴리스틱 → 통과 시
    `extract_from_text` 호출, 미통과 시 `extract_from_image` 호출 (PDF 의 첫 페이지를
    이미지로 변환).
  - 휴리스틱 임계값을 모듈 상수로 노출 (`MIN_CHARS_PER_PAGE = 50` 등).
  - `force_vision=True` 일 때 PyMuPDF 우회.
  - 단위 테스트:
    - 정상 텍스트 레이어 PDF (fixture) → 텍스트 경로 진입 검증.
    - 텍스트 레이어 없는 PDF (fixture) → Vision 경로 진입.
    - corrupt PDF → `PdfParseError` raise.
    - `force_vision=True` 일 때 PyMuPDF 호출 없이 Vision 으로 직행 검증.
  - 통합 테스트: `tests/fixtures/sample_text.pdf`, `sample_scan.pdf` 2종 → 각각
    적절한 경로로 진입 + 결과 schema 검증.
- **크기**: L (~700 LOC + fixture PDF 수집).
- **분리 고려**: PyMuPDF 의존성이 본 PR 에서 처음 추가됨 (CLAUDE.md §8.4 — 라이브러리
  도입 PR 규칙). PR description 에 검토한 대안 (pdfplumber / pdfminer.six / pypdf)
  + 채택 사유 명시 (ADR-0003 D-3.3 references).

#### Fixture 수집 의존

- 통합 테스트 fixture 2종 — 평가원 PDF (텍스트 레이어 있음) + 학교 내신 스캔본 (텍스트
  없음). PM 또는 와이프가 sample 1개씩 제공해야 함. 본 PR 시작 전 PM 에게 요청.

---

### P0-6. Repository 레이어 (멀티테넌트 강제)

- **담당**: backend-dev
- **입력**: P0-1 머지 (DB 테이블 / ORM 존재)
- **DoD**:
  - `apps/api/src/worksheet_api/repositories/` 디렉토리 생성.
    - `base.py` — `BaseRepository` 추상 클래스. `__init__(session, tenant_id, workspace_id)`.
      모든 query/write 에 `tenant_id` + `workspace_id` 필터 자동 주입.
    - `passage.py` — `PassageRepository` (`create`, `get`, `list`, `delete`).
    - `question.py` — `QuestionRepository`.
    - (vocabulary / translation / syntax_annotation 은 Phase 0 에서 read-only 가
      안전 — write 는 Phase 2/1 에서. 본 PR 은 read-only 메서드만.)
  - `TenantContext` Pydantic 모델 + `get_tenant_context` FastAPI Depends 함수.
    환경변수 `MVP_TENANT_ID` / `MVP_WORKSPACE_ID` 에서 stub 으로 읽음. 누락 시 명확한
    에러.
  - **sentinel UUID 검증**: `BaseRepository.create()` 가 입력 객체의
    `tenant_id == uuid.UUID(int=0)` 또는 `tenant_id != self._tenant_id` 일 때 raise.
  - 단위 테스트:
    - 같은 DB 에 두 tenant 의 Passage 저장 → 각 repository 로 조회 시 격리 검증.
    - sentinel UUID 그대로 create 시도 → 예외 raise 검증.
    - `tenant_id` mismatch (사용자가 다른 테넌트의 passage 가져오려 시도) → 예외.
- **크기**: M (~500 LOC).
- **분리 고려**: P0-7 (API 엔드포인트) 와 묶을 수 있으나 분리 권고 — repository 패턴
  검증이 다음 PR 들의 fundamental 한 의존.

---

### P0-7. API 엔드포인트 — `POST /passages/extract`, `GET /passages/{id}`

- **담당**: backend-dev
- **입력**: P0-3, P0-4, P0-5, P0-6 머지 (extractor 3종 + repository).
- **DoD**:
  - `apps/api/src/worksheet_api/routers/passages.py` 신규.
  - `POST /passages/extract` — request body:
    - `kind: Literal["text", "image", "pdf"]`.
    - `payload: str | bytes` (kind 에 따라).
    - `force_vision: bool = False` (kind == "pdf" 에서만 의미 있음 — ADR-0003 D-3.3).
    - `media_type: Optional[str]` (kind == "image" 에서 필요).
  - 핸들러: ADR-0003 D-3.4 / D-3.6 흐름 — extractor 호출 → tenant 주입 → 단일
    트랜잭션 영속화 → `ExtractedPassageResponse` 반환.
  - `GET /passages/{passage_id}` — `PassageResponse` (Passage + 관계된 Question 리스트
    포함).
  - 에러 매핑 (ADR-0003 D-3.5):
    - `LLMSchemaValidationError` → 502.
    - `LLMTimeoutError` → 504.
    - `EmptyInputError` / `UnsupportedMediaTypeError` → 422.
    - `PdfParseError` → 422.
  - 단위 테스트: mock extractor + repository → 각 경로 동작 검증.
  - 통합 테스트: 실제 DB + mock LLM 으로 end-to-end (POST 후 GET 으로 조회).
- **크기**: M (~500 LOC).

#### 결정 필요 (PR 시작 전)

- ADR-0003 §PM 결정 — `force_vision` 옵션 노출 위치. 위 DoD 는 body field 가정.

---

### P0-8. qa-validator stub (Phase 0 수준)

- **담당**: qa-validator
- **입력**: P0-7 머지 (Question 이 DB 에 들어가는 흐름이 존재).
- **DoD**:
  - `packages/qa_validator/src/qa_validator/` 디렉토리 생성 (skeleton 만).
    - `base.py` — `Validator` 프로토콜 + `ValidationResult` Pydantic 모델.
    - `stub.py` — `NoOpValidator` 가 모든 Question 에 대해 `uniqueness_validated=True`,
      `validator_note=None` 반환 (Phase 0 수준).
  - API 핸들러 (P0-7) 에서 추출 결과 영속화 직전에 `Validator.validate(question)` 호출.
    Phase 0 의 `NoOpValidator` 는 항상 통과.
  - Phase 3 진입 시 실제 검증기로 교체 가능한 형태로 의존성 주입 (FastAPI Depends).
  - 단위 테스트: NoOpValidator 가 호출되고 결과가 Question 의 `uniqueness_validated` 에
    반영되는지 검증.
- **크기**: S (~200 LOC).
- **분리 고려**: P0-7 PR 안에 같이 둘 수 있으나, qa-validator 의 인터페이스가 향후
  Phase 3 의 척추가 되므로 별 PR 로 명시.

---

### P0-9. 통합 smoke test + 운영 문서

- **담당**: backend-dev
- **입력**: P0-1 ~ P0-8 모두 머지.
- **DoD**:
  - `apps/api/tests/integration/test_phase_0_smoke.py` — Phase 0 DoD 의 *3개 입력
    타입 각 1건* 으로 end-to-end smoke:
    1. `POST /passages/extract` (kind=text, fixture 영어 지문 1개) → 200, DB 저장
       검증, GET 조회 검증.
    2. 동일하지만 kind=image (fixture 이미지).
    3. 동일하지만 kind=pdf (fixture PDF).
  - `docs/phase-0-runbook.md` — 와이프가 직접 실행할 수 있는 단계 (현실적으로는 PM 이
    실행) — 환경변수 셋업 + curl 예시 + 결과 검증 방법.
  - PR 머지 시 Phase 0 DoD 5개 모두 충족.
- **크기**: S (~300 LOC + runbook).

---

## 3. 의존성 그래프

```
ADR-0003 (머지됨) ──┬─→ P0-0  (architect — ExtractionResult 스키마, S)
                   │     │
                   ├─→ P0-1  (DB + llm_usage_logs 마이그레이션)
                   │     │     │
                   │     │     └────→ P0-2b (LLM DB sink)
                   │     │              │
                   ├─→ P0-2a (LLM core + jsonl sink) ──┘
                   │     │
                   │     └─[P0-0 + P0-2a 머지 후]→ P0-3 (extractor — text)
                   │                                  │
                   │                                  ├─→ P0-4 (extractor — image)
                   │                                  │     │
                   │                                  │     └─→ P0-5 (extractor — pdf)
                   │                                  │           │
                   P0-1 ──────────────────────────→ P0-6 (repositories)
                                                       │
                                                       └─→ P0-7 (API) ──→ P0-8 (qa-validator stub)
                                                              │            │
                                                              │            └─→ P0-9 (smoke test + runbook)
                                                              │
                                                              └─[P0-2b 권고]
```

### 병렬 가능 구간

- **ADR-0003 머지 직후**:
  - P0-0 (architect — schema), P0-1 (backend-dev — DB), P0-2a (backend-dev — LLM
    core) 동시 진행 가능. 인력 1명이라 순차 진행이 현실적이지만 **P0-0 은 S 사이즈
    이므로 가장 먼저 머지 권고** (P0-3 차단 해제용).
- **P0-1 머지 후**:
  - P0-2b (DB sink) 와 P0-6 (repositories) 동시 진행 가능.
- **P0-3 머지 직후**:
  - P0-4 (image) 와 P0-6 (repositories — 아직 안 했다면) 동시 진행 가능.

### 차단 (Critical Path)

```
ADR-0003 → P0-0  → P0-3 → P0-5 → P0-7 → P0-9
  (머지)   (schema) (text)  (pdf)  (API)  (smoke)

병렬:
  ADR-0003 → P0-1 → P0-6 → P0-7
  ADR-0003 → P0-2a ─┐
  P0-1 ─────────────┴→ P0-2b → (P0-7 합류, 권고)
```

- **P0-2b (DB sink) 는 P0-7 (API) 머지 전에 합쳐지는 것이 권고** — API 운영 시작 시점부터
  llm_usage_logs DB 기록이 활성화되어야 프라이싱 분석이 끊김 없음. 단 P0-2b 가 늦더라도
  jsonl sink 는 P0-2a 부터 동작하므로 데이터 손실은 없음.
- P0-5 (PDF) 가 가장 무거운 단일 PR. fixture PDF 수집이 PR 시작 전 필수.

---

## 4. 작업별 입력 / 결정 의존 표

| ID | 차단 PR | 차단 ADR | 차단 PM 결정 | 차단 외부 의존 |
|---|---|---|---|---|
| P0-0 | (없음) | ADR-0003 | PM-5 (확정) | (없음) |
| P0-1 | (없음) | ADR-0001, ADR-0003, ADR-0005 (SQLAlchemy 매핑 도구) | PM-2 (확정 — SQLModel) | (없음) |
| P0-2a | (없음) | ADR-0003 | PM-4 (확정 — DB+jsonl) | `ANTHROPIC_API_KEY` 환경 |
| P0-2b | P0-1, P0-2a | ADR-0003 | PM-4 (확정) | (없음) |
| P0-3 | P0-0, P0-2a | ADR-0003 | PM-5 (확정) | (없음) |
| P0-4 | P0-3 | ADR-0003 | PM-1 (확정) | sample 이미지 fixture 1개 |
| P0-5 | P0-3, P0-4 | ADR-0003 | PM-1, PM-3 (모두 확정) | sample PDF 2종 fixture |
| P0-6 | P0-1 | ADR-0003 | (없음) | (없음) |
| P0-7 | P0-3, P0-4, P0-5, P0-6 (+ P0-2b 권고) | ADR-0003 | PM-3 (확정) | (없음) |
| P0-8 | P0-7 | (없음) | (없음) | (없음) |
| P0-9 | P0-1 ~ P0-8 모두 | (없음) | (없음) | 와이프의 실 사용 환경 |

---

## 5. PR 단위 review 부담 분배

| ID | 크기 | review 초점 | reviewer (1차) |
|---|---|---|---|
| P0-0 | S | `ExtractionResult` 스키마 v0.1 적합성 / docstring (PM-6 가정 명시) | code-reviewer |
| P0-1 | M | 멀티테넌트 컬럼 / FK / 인덱스 / 마이그레이션 양방향 / `llm_usage_logs` 인덱스 | code-reviewer |
| P0-2a | M | LLM SDK 의존성 위치 / structured output 패턴 / 재시도 정책 / sink 프로토콜 | code-reviewer + architect (인터페이스 적합성) |
| P0-2b | S | DB sink 의 트랜잭션 경계 / 실패 시 jsonl fallback 동작 | code-reviewer |
| P0-3 | M | extractor / LLM 경계 (`packages/llm/` 단방향 의존 검증) / sentinel UUID 사용 | code-reviewer |
| P0-4 | M | Vision 입력 처리 / media type 분기 | code-reviewer |
| P0-5 | L | PyMuPDF 휴리스틱 / Vision fallback / fixture 검증 | code-reviewer + PM (의사 결정 임계값 검토) |
| P0-6 | M | 멀티테넌트 enforcement / sentinel UUID 차단 / repository 패턴 | code-reviewer |
| P0-7 | M | 트랜잭션 경계 / tenant context 주입 / 에러 매핑 / sentinel 응답 누수 | code-reviewer + architect (D-3.4/D-3.6 부합) |
| P0-8 | S | Phase 3 인터페이스 향후 호환성 | architect |
| P0-9 | S | 실제 사용 흐름 검증 | PM (와이프 사용 가능성 평가) |

---

## 6. 후속 작업 — schema 갭 후보 (ADR-0003 §G-1~G-5 참조)

본 작업 분해 작성 중 발견한 `shared/schemas/` v0.1 갭 후보. 일부는 PM 결정으로
구체화되어 **새 PR (P0-0)** 로 P0-3 차단 항목이 됨.

| 갭 ID | 항목 | 처리 시점 | 처리 PR |
|---|---|---|---|
| G-1 | Passage 의 추출 출처 메타 (`extraction_meta`) | P0-2 의 `usage_log` 형태 확정 후 | P0-2 머지 후 별 schema PR |
| G-2 | Question 의 `extraction_status` (complete/partial/failed) | P0-3 ~ P0-5 추출 시 LLM 출력 품질 분포 관찰 후 | Phase 0 후반 또는 P0-8 |
| G-3 | 다중 지문 PDF 처리 — `extract_from_pdf` 가 list 반환 | **PM-1 으로 확정** | P0-5 의 시그니처에 직접 반영 (별 schema PR 불필요) |
| G-4 | 이미지의 다중 지문 처리 | **PM-1 으로 확정 (G-3 와 통합)** | P0-4 의 시그니처에 직접 반영 (별 schema PR 불필요) |
| G-5 | `ExtractionResult` 가 Translation / Vocabulary 도 담음 | **PM-5 영향 — P0-3 차단 항목** | **P0-0 신규** (architect, `shared/schemas/extraction.py` 신설). P0-1 / P0-2 와 병렬 가능. |

### P0-0. `ExtractionResult` 스키마 신설 (architect, S, P0-3 차단)

PM-5 (추출 스코프 옵션 B — 자료에 보이는 것 추출) 결정에 따라 추출 결과 컨테이너
스키마를 정의.

- 산출물: `shared/schemas/extraction.py`
  ```python
  class ExtractionResult(BaseModel):
      passage: Passage
      questions: list[Question]
      translation: Optional[Translation]
      vocabulary: list[Vocabulary]      # 빈 list 허용 (실유저 입력의 default)
      extraction_meta: ExtractionMetaRef  # G-1 통합 — request_id, model, extracted_at
  ```
- DoD:
  - `shared/schemas/extraction.py` 작성 + `__init__.py` export.
  - `ExtractionMetaRef` 도 같은 파일 또는 `shared/schemas/llm.py` 신설 (architect 판단).
  - 스키마 단위 테스트 — `translation is None` / `vocabulary == []` valid 확인.
  - PM-6 가정 명시 docstring (실유저 입력의 default 는 비어있다).
- 의존: ADR-0003 머지.
- 후속 차단 해제: P0-3 (텍스트 추출 PR).
- PR 크기: S.

---

## 7. PM 결정 (확정 — 2026-05-02)

ADR-0003 §"PM 결정 (확정)" 과 동일. 본 작업 분해의 §2 (PR 리스트), §3 (의존성 그래프),
§4 (의존 표), §5 (review 부담), §6 (schema 갭) 모두 본 결정을 반영해 갱신 완료.

| # | 항목 | 결정 | 본 분해에 미치는 영향 |
|---|---|---|---|
| PM-1 | Phase 0 *1건* 정의 | 다중 지문 / 다중 파일 허용. 출력 `list[ExtractionResult]`. | P0-3 / P0-4 / P0-5 의 시그니처 모두 list 반환. G-3 / G-4 (§6) 자동 해결. |
| PM-2 | SQLAlchemy 매핑 도구 | **SQLModel** | P0-1 진입 전 backend-dev 가 ADR-0005 작성 (SQLModel 위에서 sentinel UUID 검증 / repository 패턴 명시). |
| PM-3 | `force_vision` 노출 위치 | request body 의 옵셔널 필드 (default false) | P0-7 (API) 의 request 모델에 반영. P0-5 의 PDF extractor 가 동일 인자 받음. |
| PM-4 | `usage_log` 보관 정책 | DB 테이블 (`llm_usage_logs`) + jsonl 백업 sink | P0-1 마이그레이션에 `llm_usage_logs` 테이블 추가. P0-2 의 LLM 래퍼가 DB write + jsonl 동시 기록. |
| PM-5 | 추출 스코프 | 옵션 B — 자료에 보이는 것만 (Translation / Vocabulary 포함, 생성은 안 함) | **G-5 신규 PR (`shared/schemas/extraction.py` 신설) 가 P0-3 차단 항목으로 추가** (§6 참고). P0-3 / P0-4 / P0-5 의 추출 출력에 translation / vocabulary 포함. |
| PM-6 | 운영 가정 (실유저 입력 분포) | 영어만 / 문제만 (한글 해석 없음) 이 default. translation / vocabulary 비어있는 게 정상. | qa-validator stub (P0-8) 의 유효성 규칙: `translation is None` / `vocabulary == []` 는 에러 아님. fixture set 에 "영어만" 케이스 의도적 포함. |
| PM-7 | Fixture 경로 | `admin/fixtures/extractor/{pdf/text-layer, pdf/scanned, image, text}/` PM 수집 중. | P0-3 / P0-4 / P0-5 진입 전 backend-dev 가 fixture 가용성 확인. |

---

## 8. 다음 행동

ADR-0003 + 본 작업 분해 PR 머지 후:

- **architect**: P0-0 (`shared/schemas/extraction.py` 신설) 즉시 시작. P0-3 차단
  해제용 S 사이즈 PR.
- **backend-dev**: ADR-0005 (SQLModel 위 매핑 패턴) 작성 → P0-1 (DB + `llm_usage_logs`)
  과 P0-2a (LLM core + jsonl sink) 동시 시작 가능. P0-2b (DB sink) 는 P0-1 머지 후.
  P0-3 시작 전 fixture 가용성 확인.
- **PM**: §7 의 PM-7 (fixture 자료) 수집 진행. 각 폴더에 "풀세트" 와 "영어만" 양쪽
  포함 (PM-6 가정 검증용).
- **frontend-dev**: Phase 0 는 UI 없음. Phase 1 진입 전 ADR-0004 (Annotation span
  식별 방식) 공동 작성을 위해 Tiptap PoC (Sprint 0 작업 #7) 결과를 architect 와
  공유.
- **qa-validator**: P0-7 머지까지 대기. 그 사이 Phase 3 의 검증 인터페이스 후보 안을
  `docs/qa-validator-design-draft.md` 로 사전 작성 가능 (선택).
- **code-reviewer**: P0-0 PR 부터 즉시 review 사이클 진입. 체크리스트는 ADR-0003
  D-3.6 (sentinel UUID 차단), CLAUDE.md §3.6 (라이브러리 도입 사유), §7.7 의 표준
  체크리스트.
