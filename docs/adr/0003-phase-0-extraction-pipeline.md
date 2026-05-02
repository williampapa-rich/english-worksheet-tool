# ADR 0003 — Phase 0 추출 파이프라인 경계 / 의존성 / 영속화 책임

- **상태(Status)**: Accepted (PM 머지 승인 2026-05-02)
- **작성일**: 2026-05-02
- **작성자**: architect agent
- **유형**: 신규 결정 (Phase 0 진입 전 기반 마련)
- **관련 문서**:
  - `CLAUDE.md` §2.1 (Phase 0 DoD), §3.1, §3.4 (PDF 처리 분기), §3.6 (No Reinventing
    the Wheel), §8.3 (LLM 호출 규칙)
  - `docs/adr/0001-canonical-schema-philosophy.md`
  - `docs/adr/0002-content-model-v0.1.md`
  - `docs/schema-coverage-audit.md`
  - `shared/schemas/passage.py`, `shared/schemas/question.py`

---

## Context (배경)

Phase 0 DoD (CLAUDE.md §2.1) 의 잔여 작업 3개:

1. Vision LLM 을 사용한 추출 파이프라인 — PDF / 이미지 / 텍스트 1건씩 정규화된
   `Passage + Question` 객체 반환.
2. DB 에 Passage 저장/조회 (현재 `tenants` / `workspaces` 만 마이그레이션됨).
3. 멀티테넌트 스키마 (`tenant_id`) 박힘, 인증 stub.

이 셋을 동시에 만족하려면 **추출 파이프라인의 모듈 경계, LLM 래퍼와의 결합 방식,
영속화의 책임 위치, 멀티테넌트 강제 지점, 에러/재시도 정책** 을 미리 결정해야 한다.

특히 다음 함정을 회피해야 한다.

- **LLM SDK 직접 호출의 산재**: extractor 안에서 Anthropic SDK 직접 호출하면
  CLAUDE.md §8.3 위반. 모든 LLM 호출은 `packages/llm/` 을 거쳐야 한다.
- **extractor 가 DB write 수행**: 영속화 책임이 분산되면 트랜잭션 경계가 모호해지고
  멀티테넌트 누락 위험. `tenant_id` 검증 지점이 한 곳에 모이지 않으면 audit 가
  필요하다.
- **PDF 처리 분기의 무분별한 LLM fallback**: 텍스트 레이어가 있는 PDF 까지 Vision
  LLM 으로 보내면 비용이 폭증한다. 반대로 너무 보수적이면 스캔본을 정상 텍스트로
  오해해 빈 결과가 나온다.

본 ADR 은 이 6개 결정을 **단일 PR 단위로 일괄 확정** 한다 (개별 분리하면 backend-dev
가 작업을 시작할 수 없음).

---

## Decisions (결정)

### D-3.1 — `packages/extractor/` 내부 구조: 입력 타입별 모듈 + 공통 `Extractor` 프로토콜

```
packages/extractor/
├── src/
│   └── extractor/
│       ├── __init__.py         # 공개 API (extract_from_text / _image / _pdf)
│       ├── base.py             # Extractor 프로토콜 + ExtractionResult / ExtractionRequest
│       ├── text.py             # 텍스트 입력 어댑터
│       ├── image.py            # 이미지 입력 어댑터 (Vision 경유)
│       ├── pdf.py              # PDF 입력 어댑터 (PyMuPDF + Vision fallback 분기)
│       └── normalizer.py       # LLM 출력 → Passage/Question 정규화 (마커 후처리 등)
├── tests/
└── pyproject.toml
```

- 공통 인터페이스: `Extractor` 프로토콜 (typing.Protocol).
  ```python
  class Extractor(Protocol):
      async def extract(self, request: ExtractionRequest) -> ExtractionResult: ...
  ```
  - `ExtractionRequest`: 입력 페이로드 (text/bytes/path) + 입력 타입 + 옵션
    (예: pdf 강제 vision flag).
  - `ExtractionResult`: `passage: Passage` + `questions: list[Question]` + `meta`
    (사용 모델, latency, 토큰, fallback 발생 여부 등).
  - 둘 다 Pydantic 모델 — `shared/schemas/` 와 같은 척추 위.
- 호출부 (API 레이어, CLI, 테스트) 는 입력 타입을 분기해 적절한 함수를 호출한다.
  `extract_from_text(text)` / `extract_from_image(image_bytes)` / `extract_from_pdf(pdf_bytes)`.
- 어댑터끼리는 직접 의존하지 않는다 (예: pdf 가 image 를 직접 import 안 함). 공통
  필요 로직은 `normalizer.py` 또는 `packages/llm/` 으로 위치.

#### 채택 사유

- **Extractor 프로토콜이 있는 이유**: 추출 결과 형태가 모든 입력 타입에서 동일해야
  (Passage + Question[]) 후속 파이프라인이 단순. 프로토콜은 명시적 계약.
- **함수 직접 노출과의 양립**: 호출부는 함수 호출이 가독성 우수, 내부에서는 프로토콜
  덕에 mock/swap 용이. 양쪽 다 채택.

#### 검토한 대안

- **A. 단일 `Extractor` 클래스 + 입력 타입 dispatch**: 한 클래스가 텍스트/이미지/PDF
  모두 처리. → 기각: 입력 타입별 의존성 (PyMuPDF, Vision) 이 한 클래스에 응축되어
  test/mocking 부담 ↑.
- **B. 함수만 export, 프로토콜 없음**: 가장 간단. → 기각: `ExtractionResult` 형태가
  세 어댑터에서 미묘하게 갈릴 위험. 프로토콜로 강제하는 게 lock-in 비용 거의 0.

---

### D-3.2 — LLM 래퍼와의 경계: extractor → `packages/llm/` 단방향 의존, 직접 SDK 금지

`packages/extractor/` 는 Anthropic SDK 를 **직접 import 하지 않는다**. 모든 LLM
호출은 `packages/llm/` 의 인터페이스를 거친다. CLAUDE.md §8.3 강제.

#### `packages/llm/` 인터페이스 형태

```python
# packages/llm/src/llm/client.py 권고

class StructuredLLMClient(Protocol):
    """structured output 전용 인터페이스. extractor / variant 생성 / qa-validator 모두 사용."""

    async def extract_structured[T: BaseModel](
        self,
        *,
        prompt: PromptSpec,           # docs/prompts/ 의 마크다운 + 변수 바인딩
        response_model: type[T],      # Pydantic 모델 타입 (예: ExtractedPassageResponse)
        images: list[ImageInput] | None = None,  # Vision 입력 (PNG/JPEG bytes + media_type)
        max_retries: int = 2,
        temperature: float = 0.2,
    ) -> StructuredLLMResult[T]: ...


@dataclass
class StructuredLLMResult[T: BaseModel]:
    data: T
    raw_response: dict           # 원 응답 (디버깅 / usage_log)
    usage: TokenUsage            # input/output/total 토큰
    model: str                   # 실제 사용 모델 ID
    elapsed_ms: int
```

- `PromptSpec`: 프롬프트 템플릿 ID + 변수 dict. 템플릿은 `docs/prompts/` 의
  마크다운 + frontmatter 로 버전 관리 (CLAUDE.md §8.3).
- `response_model`: Pydantic v2 모델. exam-generator `app/llm/anthropic.py` 의
  `tool_use input_schema=Model.model_json_schema()` 패턴 그대로 흡수
  (ADR-0001 §References).
- `ImageInput`: Vision 입력. base64 인코딩 + media_type 은 LLM 래퍼 내부에서 처리.
- 재시도 / 백오프 / 토큰 카운팅은 LLM 래퍼 내부 책임. extractor 는 모른다.
- LLM 래퍼는 stateless. 호출 로그는 별도 sink (file / DB) 로 빠짐 — 본 ADR 범위 외.

#### 채택 사유

- **단방향 의존**: extractor 가 LLM SDK 를 import 하면 다음 폭발: Vision 호출 패턴이
  variant 생성 / qa-validator 코드와 분기되며 동시 진화 불가능 → 어디선가 prompt
  drift / 토큰 카운트 누락 / 재시도 정책 차이 발생. 단방향으로 묶어 한 곳에서 관리.
- **structured output 패턴 재활용**: exam-generator 의 검증된 패턴 (`anthropic.py:31-64`)
  을 그대로 흡수. CLAUDE.md §3.6 No Reinventing the Wheel 부합.
- **테스트 단순화**: extractor 테스트는 `StructuredLLMClient` 를 mock 하면 끝.
  실제 LLM 호출은 `packages/llm/` 통합 테스트에서만.

#### 검토한 대안

- **A. extractor 가 anthropic SDK 직접 호출**: 가장 짧은 경로. → 기각: §8.3 위반,
  variant 생성 / qa-validator 와의 코드 중복.
- **B. LLM 호출을 한 줄짜리 함수로 노출 (`call_claude(prompt, ...)` )**: → 기각:
  structured output / Vision / 재시도 / 토큰 카운팅 등 옵션이 많아 한 줄 함수의 인자
  표면이 폭발.
- **C. instructor / outlines 같은 외부 structured output 라이브러리 도입**:
  → 기각: Anthropic SDK 의 tool_use 패턴 + Pydantic 자체 검증으로 충분 (CLAUDE.md
  §3.6, ADR-0001 §Alternatives §C). exam-generator 의 검증 결과 의존성 추가가
  부담.

---

### D-3.3 — PDF 처리 분기 로직: PyMuPDF 1차 시도 → 휴리스틱 trigger 시 Vision fallback

```python
# packages/extractor/src/extractor/pdf.py 권고 의사 코드

async def extract_from_pdf(pdf_bytes: bytes, *, force_vision: bool = False) -> ExtractionResult:
    if force_vision:
        return await _extract_via_vision(pdf_bytes)

    text_layer = pymupdf_extract(pdf_bytes)
    if _is_extractable(text_layer):
        return await _extract_via_text(text_layer)
    return await _extract_via_vision(pdf_bytes)


def _is_extractable(text_layer: PdfTextLayer) -> bool:
    """텍스트 레이어가 사용 가능한지 판단. False 면 Vision fallback."""
    # 휴리스틱 (보수적 — 의심스러우면 Vision):
    # 1. 페이지당 평균 문자 수 < 50  → False (스캔본 가능성)
    # 2. 영어 알파벳 비율 < 30%      → False (이미지 PDF 의 OCR 노이즈 또는 비-영어)
    # 3. 깨진 unicode (PUA / replacement char) 비율 > 5%  → False
    # 4. 페이지 수 > 텍스트 길이 / 200 (1페이지당 200자 미만)  → False
    ...
```

- **항상 Vision 검증 안 함** — 비용 이유. 휴리스틱이 통과하면 텍스트만 사용.
- **`force_vision: bool` 옵션** — 호출부가 강제할 수 있음 (예: 와이프가 "이거 잘 안
  나왔으니 Vision 으로 다시" 누름). API 엔드포인트의 query param 또는 body field 로
  노출.
- **휴리스틱 임계값은 상수로 노출** — `extractor.pdf` 모듈 상수. 향후 운영 중
  튜닝 가능.

#### 채택 사유

- **CLAUDE.md §3.4 명시 분기 그대로**: "텍스트 레이어 있는 PDF → PyMuPDF, 스캔본 →
  Vision". 본 ADR 은 *판단 기준* 만 구체화.
- **휴리스틱 4종 — 보수성 명시**: 의심스러우면 Vision 으로 가는 방향 (false negative
  보다 false positive 가 더 위험 — 빈 결과가 사용자에게 노출되면 도구 신뢰도 ↓).
- **PyMuPDF 단독 사용 — CLAUDE.md §3.6 §3.4 명시**: 대안 (pdfplumber / pdfminer.six
  / pypdf) 중 PyMuPDF 가 한국어 PDF 처리에서 가장 안정. exam-generator 도 동일 라이브러리
  사용 (audit §1.6 — `app/llm/pdf.py`). lock-in 위험 < 일관성 이득.

#### 검토한 대안

- **A. 항상 Vision (텍스트 레이어 무시)**: → 기각: 비용. 평가원 PDF 처럼 깨끗한
  텍스트 레이어가 있는 자료가 다수.
- **B. 항상 PyMuPDF 만, Vision fallback 없음**: → 기각: 스캔본 자료 (학교 내신 기출 —
  CLAUDE.md §10.1) 를 처리 못 함.
- **C. PyMuPDF 결과를 Vision 으로 *교차 검증***: → 기각: 모든 PDF 가 Vision 호출 1회
  발생 → 비용 ×2. 가치 입증 안 됨.
- **D. pdfplumber 또는 pdfminer.six**: → 기각: 한국어 폰트 / 박스 / 매트릭스 표
  처리에서 PyMuPDF 가 우위. exam-generator 의 운영 검증.

---

### D-3.4 — 영속화 책임: extractor 는 read-only, API 레이어가 트랜잭션 + 영속화 담당

`packages/extractor/` 는 **DB write 를 수행하지 않는다**. 호출 결과는 in-memory
`ExtractionResult` 객체로 반환되고, **API 레이어 (`apps/api/`) 의 service /
repository 가 영속화** 한다.

```python
# apps/api/src/worksheet_api/routers/passages.py 권고 의사 코드

@router.post("/passages/extract", response_model=ExtractedPassageResponse)
async def extract_passage(
    body: ExtractRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),  # tenant_id / workspace_id 주입
    db: AsyncSession = Depends(get_db),
) -> ExtractedPassageResponse:
    # 1. extractor 호출 — DB 무관, 순수 추출
    result = await extractor.extract(body.to_request())

    # 2. tenant_id / workspace_id 주입 (extractor 가 모르는 정보)
    passage = result.passage.model_copy(update={
        "tenant_id": tenant_ctx.tenant_id,
        "workspace_id": tenant_ctx.workspace_id,
    })
    questions = [
        q.model_copy(update={
            "tenant_id": tenant_ctx.tenant_id,
            "workspace_id": tenant_ctx.workspace_id,
        }) for q in result.questions
    ]

    # 3. 단일 트랜잭션으로 영속화
    async with db.begin():
        passage_repo = PassageRepository(db, tenant_ctx)
        question_repo = QuestionRepository(db, tenant_ctx)
        saved_passage = await passage_repo.create(passage)
        for q in questions:
            await question_repo.create(q.model_copy(update={"passage_id": saved_passage.id}))

    return ExtractedPassageResponse(passage=saved_passage, questions=questions)
```

- **트랜잭션 경계**: API 핸들러 1건 = DB 트랜잭션 1건. `async with db.begin()` 로
  명시.
- **rollback**: 추출은 성공했지만 DB 저장이 실패하면 트랜잭션 롤백, 추출 결과는 응답에
  포함 안 됨 (HTTP 500). LLM 호출은 외부 부수 효과이므로 retry 책임은 없음 (이미
  완료된 것). 비용은 sunk.
- **이상적 (Phase 1+ 검토)**: 추출 결과를 임시 staging 테이블에 저장 → 사용자가 검수
  → confirm 시 정식 영속화. v0.1 은 단순 즉시 영속화로 출시.

#### 채택 사유

- **단일 책임**: extractor 는 "입력 → 정규화" 만 책임. DB 는 API 레이어 또는 service
  레이어 책임. 테스트가 단순해지고, extractor 를 CLI / 배치 / 다른 컨텍스트에서 재사용
  가능.
- **트랜잭션 경계 명확**: API 핸들러 1건 = 트랜잭션 1건 의 단순 모델. SQLAlchemy 2.x
  의 `async with db.begin()` 패턴 그대로 활용 (CLAUDE.md §3.6).
- **멀티테넌트 강제 지점이 한 곳에 모임** — D-3.6 참조.

#### 검토한 대안

- **A. extractor 가 DB write 까지**: → 기각: 단일 책임 위반, extractor 를 CLI / 테스트
  로 호출할 때 DB 의존성이 강제됨.
- **B. service 레이어 도입 (`apps/api/src/.../services/passage_service.py`)**:
  현 ADR 의 영속화 로직이 복잡해지면 그때 도입. v0.1 은 라우터에서 직접 repository
  사용 (premature abstraction 회피, CLAUDE.md §3.6 정신).

---

### D-3.5 — 에러 처리 / 재시도 정책

#### 계층별 책임

| 레이어 | 에러 종류 | 정책 |
|---|---|---|
| `packages/llm/` | 네트워크 / rate limit / 5xx | 지수 백오프 재시도 (max 2회 — `StructuredLLMClient.max_retries` 인자). Anthropic SDK 의 자체 재시도와 중복 안 되도록 SDK 측 disable. |
| `packages/llm/` | structured output 검증 실패 (Pydantic ValidationError) | LLM 측 응답이 schema 위반 — 1회 재시도 (프롬프트에 "이전 응답이 schema 위반: <error>" 첨부). 2회째도 실패 시 `LLMSchemaValidationError` raise. |
| `packages/llm/` | timeout (60초 기본) | 1회 재시도. 2회째도 실패 시 `LLMTimeoutError` raise. |
| `packages/extractor/` | LLM 호출 실패 (위 모두) | 그대로 propagate. extractor 는 자체 재시도 안 함 (이미 LLM 래퍼가 처리). |
| `packages/extractor/` | PyMuPDF 실패 (corrupt PDF 등) | `PdfParseError` raise. 자동 Vision fallback 안 함 (사용자가 `force_vision=True` 로 재시도). 단 D-3.3 의 휴리스틱은 정상 PyMuPDF 결과의 *품질* 만 본다 — 예외와 무관. |
| API 레이어 | 모든 위 예외 | 적절한 HTTP status 매핑: validation → 422, timeout → 504, schema → 502, 그 외 → 500. error response body 는 `{"error": "...", "kind": "...", "request_id": "..."}` 형태. |
| API 레이어 | DB 제약 위반 (tenant_id NULL 등) | 500 — 코드 버그. error log 로 알림. |

#### 재시도 백오프

- 베이스: 1초, 지수 (2배), jitter ±25%. max 2회 재시도 = 최악 1 + 2 + 4 = 7초.
- 토큰 한도 / API key invalid 같은 영구 에러는 재시도 없이 즉시 raise (`PermanentLLMError`).

#### 채택 사유

- **재시도는 LLM 래퍼에 응집** — extractor 는 "성공 또는 실패" 만 알면 됨. 재시도
  정책이 한 곳에 있어 운영 중 튜닝 단순.
- **structured output 검증 실패에 1회 재시도** — exam-generator 의 hotfix 7-3
  사례 (audit §2.4) — LLM 이 가끔 schema 위반. 1회 재시도로 회수율 ↑.
- **자동 Vision fallback 안 함** — D-3.3 의 휴리스틱은 *품질 판단*, fallback 트리거.
  PyMuPDF 가 raise 하는 케이스 (corrupt PDF) 는 사용자 의사 결정 영역이라 수동
  `force_vision=True` 로.

#### 검토한 대안

- **A. extractor 자체 재시도**: → 기각: LLM 래퍼와 중복, 정책 분산.
- **B. 무한 재시도 with circuit breaker**: → 기각: v0.1 사용량에서 과한 인프라.
  Phase 4 클라우드 진입 시 재검토.

---

### D-3.6 — 멀티테넌트: API 레이어가 `tenant_id` / `workspace_id` 강제 주입, extractor 는 모름

#### 흐름

```
HTTP 요청
   ↓ (헤더 / 쿠키 / 환경변수 stub)
[get_tenant_context()]  ← FastAPI Depends
   ↓ (TenantContext = { tenant_id, workspace_id, user_id })
API 핸들러
   ↓ (extractor.extract — TenantContext 주입 안 함)
extractor (tenant 무관, raw 추출)
   ↓ (Passage / Question — tenant_id / workspace_id 필드는 placeholder UUID 또는 비어있음)
API 핸들러
   ↓ (model_copy 로 tenant_id / workspace_id 주입)
Repository (tenant_id 필터 강제, write 시 검증)
   ↓
DB
```

- **`get_tenant_context()` 의존성**: FastAPI Depends 함수. v0.1 은 환경변수
  `MVP_TENANT_ID` / `MVP_WORKSPACE_ID` 에서 읽어 stub. Phase 4 에서 OAuth 토큰 파싱
  으로 교체.
- **extractor 는 `tenant_id` 모름**: extractor 의 출력 `Passage` / `Question` 은
  `WorkspaceScopedEntity` 를 상속하지만, extractor 가 만든 인스턴스는 placeholder
  UUID (예: `uuid.UUID(int=0)`) 또는 별도 `RawPassage` / `RawQuestion` 타입 사용.
- **결정**: v0.1 은 placeholder UUID 패턴 채택 — `Passage.tenant_id` 의 default
  를 `None` 허용으로 두지 않고, extractor 가 `uuid.UUID(int=0)` 같은 sentinel 값
  채움. API 레이어가 model_copy 로 실제 값 주입. 멀티테넌트 필드 자체는 모든 경계에서
  *NOT NULL* 유지 (스키마 일관성).
  - 단점: sentinel UUID 가 실수로 DB 까지 흘러가면 디버깅 어려움.
  - 대응: Repository 의 write 시점에서 sentinel 값 (`uuid.UUID(int=0)`) 검증 → 발견
    시 ValidationError raise.
  - 별 대안 (`RawPassage` / `RawQuestion` 별 타입) 은 두 모델을 별도 유지하는 비용이
    큼 — 5경계 척추 (ADR-0001) 위반 위험. 현 v0.1 에서는 sentinel + repository
    검증으로 갈음. Phase 1+ 에서 repository 패턴이 안정화되면 재검토.

#### 채택 사유

- **단일 강제 지점**: 모든 영속화는 repository 통과. repository 는 `TenantContext`
  를 주입받아 모든 쿼리/write 에 자동 필터. extractor 가 우회할 수 없음.
- **CLAUDE.md §3.3 정신 부합**: "스키마 레벨에선 처음부터 멀티테넌트". 모든 도메인
  엔티티 NOT NULL `tenant_id`. sentinel 우회는 repository 가 차단.

#### 검토한 대안

- **A. extractor 인자로 `TenantContext` 받기**: → 기각: extractor 가 인증/권한
  컨텍스트를 알게 됨. 단일 책임 위반. CLI / 배치 호출 시 dummy context 만들어야 함.
- **B. `Passage.tenant_id` Optional 허용**: → 기각: 스키마 척추 (NOT NULL) 깨짐.
  API 응답 / DB 어디서나 None 가능해져 멀티테넌트 enforcement 유실 위험.
- **C. 별도 `RawPassage` 타입 분리**: → 미래 검토 (Phase 1+).

---

## Consequences (결과)

### 긍정적 결과

- extractor 가 DB / 인증 / 재시도 없이 **순수 함수** 에 가까워져 테스트가 단순.
- LLM 호출이 한 곳 (`packages/llm/`) 에 응집되어 운영 중 비용 모니터링 / 캐싱 (CLAUDE.md
  §11 Open Question — Phase 3 진입 전) 이 한 곳에서 가능.
- 멀티테넌트 강제 지점이 API 레이어 + repository 두 곳으로 좁혀짐 — code-reviewer
  체크리스트 단순화.
- PDF 처리 분기 로직이 모듈 수준에 명시되어, 비용 / 정확도 튜닝이 한 파일 (`pdf.py`)
  에 집중.

### 부정적 결과 / 비용

- **sentinel UUID 패턴의 함정**: extractor 출력의 `tenant_id == uuid.UUID(int=0)` 을
  실수로 그대로 사용하면 멀티테넌트 누수. 대응: repository write 검증 + code-reviewer
  체크리스트 ("sentinel UUID 가 응답에 포함되지 않는가") 추가.
- **2-stage 트랜잭션 부재**: 추출은 성공했는데 DB write 실패 시 LLM 비용은 sunk.
  Phase 1+ 에서 staging 테이블 도입 검토.
- **`packages/llm/` 인터페이스의 lock-in**: `StructuredLLMClient` 프로토콜이 모든
  소비자 (extractor / variant / qa-validator) 에 노출되어 변경 시 영향 범위 큼.
  대응: 인터페이스 변경은 ADR 동반.

### 후속 결정 트리거

- **code-reviewer 체크리스트 갱신**: D-3.6 의 sentinel UUID 패턴은 누수 시 멀티테넌트
  격리 깨짐 → critical. `.claude/agents/code-reviewer.md` §2 (멀티테넌트 함정) 에
  "sentinel UUID 누수 / repository write 검증 존재 여부" 항목 추가됨 (본 ADR 머지와
  동시).
- **Annotation span 식별 방식 (CLAUDE.md §11, audit §4-4)**: 본 ADR 은 추출 시점에
  inline 마커 처리 *정책 미결*. ADR-0004 (Phase 1 진입 전) 와 통합 결정 필요.
- **마커/텍스트 분리 (audit Gap K, §4-6)**: 본 ADR 은 추출 결과의 마커 표현을
  결정하지 않음 — `normalizer.py` 의 동작이 ADR-0004 결정에 따라 갈림. 본 ADR 의
  `normalizer.py` placeholder 는 *마커 inline 보존* 으로 시작 (Pydantic 모델 v0.1 이
  중립이므로 무손실).
- **Phase 4 RLS 도입**: 본 ADR 의 repository 패턴은 RLS 와 호환.
- **추출 staging 테이블**: 와이프가 추출 결과 검수 → confirm 흐름이 필요해지면 도입.
  Phase 1 진입 시 frontend-dev 와 협의.

---

## Alternatives Considered (전체 대안 — 위 D-3.* 의 종합)

각 D-3.* 에 alternatives 명시. 핵심 패턴 (extractor / LLM 래퍼 분리, API 레이어
영속화, sentinel UUID 멀티테넌트 강제) 는 ADR-0001 의 5경계 척추 + CLAUDE.md §3.6
원칙의 자연스러운 귀결.

---

## 후속 작업 — schema 갭 후보 (현재 PR 에서 처리 안 함)

본 ADR 작성 중 발견한 `shared/schemas/` v0.1 의 갭 후보. **본 PR 에서는 schema 수정
안 함**. 별 후속 PR 로 처리.

### G-1. `Passage` / `Question` 에 추출 출처 메타가 없다

- 발견: `Passage.source: SourceMeta` 는 *사용자 보고 출처* (예: "이거 평가원 6월
  모의평가") 이지, *어떤 추출 호출에서 만들어졌는가* 메타는 없음.
- 영향: 디버깅 / 회귀 분석 / LLM 출력 캐싱 / 동일 입력 중복 추출 방지 어려움.
- 제안: `Passage.extraction_meta: ExtractionMetaRef | None` — `extraction_id` (LLM
  호출 1건의 ID), `model`, `prompt_template_id`, `extracted_at`. 또는 별도
  `extraction_logs` 테이블로 분리.
- 처리 시점: backend-dev 가 LLM 래퍼 구현 시 `usage_log` 형태로 확정 → schema 반영
  PR 별도.

### G-2. `Question.choices` 평탄 list 의 placeholder 처리

- 발견: extractor 가 텍스트 레이어 PDF 에서 `choices` 를 못 추출하는 경우 (마커가
  깨졌거나 OCR 노이즈) — 현 schema 는 `default_factory=list` 라 빈 리스트 OK 인데,
  의도가 "추출 실패" 인지 "선택지 없는 문제" 인지 구분 안 됨.
- 영향: qa-validator 의 정답 유일성 검증이 빈 choices 를 어떻게 다룰지 모호.
- 제안: `Question.extraction_status: Literal["complete", "partial", "failed"]`
  필드 추가 — 추출 단계의 자가 보고. 또는 빈 choices 를 명시적으로 *추출 실패* 로
  해석하는 규약 (스키마 변경 없음).
- 처리 시점: Phase 0 후반 또는 qa-validator stub 도입 시.

### G-3. PDF 의 다중 Passage 처리 — **PM-1 으로 확정 (다중 지문 / 다중 파일 허용)**

- 발견: 1 PDF 가 N 개 지문을 담는 경우 (예: 모의고사 1회분 = 28개 지문) — 1 호출 =
  1 Passage 가정 거절.
- 결정: `extract_from_pdf` 는 `list[ExtractionResult]` 반환. 다중 파일 입력 시
  파일별 결과를 평탄한 단일 리스트로 합침.
- 처리 시점: P0-5 (PDF 추출 PR) 에서 본 시그니처로 구현. schema 변경 불필요 —
  `ExtractionResult` 단일 객체 정의 그대로 두고 list 로 노출.

### G-4. 이미지 입력의 page / region 메타 부재 — **G-3 와 통합 (PM-1 으로 확정)**

- 결정: 이미지 입력도 동일하게 `list[ExtractionResult]` 반환. 한 이미지에 N개 지문
  있어도 분리 추출.
- 처리 시점: P0-4 (이미지 추출 PR).

### G-5. `ExtractionResult` 가 Translation / Vocabulary 도 포함해야 함 — **PM-5 영향**

- 발견: PM-5 (추출 스코프 옵션 B — 자료에 보이는 것 추출, 생성 안 함) 결정에 따라
  `ExtractionResult` 스키마는 `Passage + Question` 외에 **자료에 명시적으로 존재하는**
  Translation / Vocabulary 도 함께 담아야 함.
- 제안 스키마 (architect 권고):

  ```python
  class ExtractionResult(BaseModel):
      passage: Passage
      questions: list[Question]
      translation: Optional[Translation]    # 자료에 한글 해석 있으면
      vocabulary: list[Vocabulary]          # 자료에 어휘 박스 있으면, 없으면 빈 list
      extraction_meta: ExtractionMetaRef    # G-1 과 통합
  ```

- 영향: PM-6 의 "실유저 입력 default 는 영어만 / 한글 해석 없음" 가정상 `translation`
  은 거의 항상 `None`. `vocabulary` 도 거의 항상 빈 list. 이게 정상.
- 처리 시점: P0-3 (텍스트 추출 PR) 진입 전, architect 가 `shared/schemas/extraction.py`
  신설 PR 로 처리. backend-dev 차단 항목.

---

## PM 결정 (확정 — 2026-05-02)

PR 검토 시점에 PM 이 다음 항목을 확정. 본 ADR 의 결정 본문 (D-3.1 ~ D-3.6) 은
이 결정들과 정합한 형태로 이미 작성됨. 충돌 없음 확인.

### PM-1. Phase 0 *1건* 의 정의 — **다중 지문 / 다중 파일 허용**

- 입력: 파일 1개 또는 N개 + 텍스트 직접 입력 (혼합 가능).
- 출력: `list[ExtractionResult]` (한 파일에서 여러 Passage 추출 가능, 여러 파일
  결과는 평탄한 단일 리스트로 합침).
- 근거: 기출시험지가 한 페이지에 지문 N개, 페이지 M장의 형태가 일상.
- 영향: ADR §D-3.1 (Extractor 프로토콜 시그니처), §D-3.3 (PDF 페이지 분할 +
  지문 경계 탐지) 모두 본 결정과 정합. schema 갭 G-3 / G-4 는 동일하게 후속.

### PM-2. SQLAlchemy 매핑 도구 — **SQLModel 채택**

- 본 ADR 은 매핑 도구를 명시 결정하지 않았으나, P0-1 (DB 마이그레이션) 진입 전
  ADR-0005 로 별도 기록. PM 추천에 따라 SQLModel 채택.
- 근거: Pydantic v2 기반 → `shared/schemas/` 의 Pydantic 모델과 ORM 이 거의
  동일 객체. FastAPI 와의 통합도 1급.
- 한계: 복잡 쿼리는 SQLAlchemy raw 로 떨어져야 함. 현 프로젝트 규모에서는 수용.
- 후속: backend-dev 가 P0-1 시작 전 ADR-0005 작성, sentinel UUID 검증 / repository
  레이어의 `tenant_id` 강제 패턴을 SQLModel 위에 어떻게 구현할지 명시.

### PM-3. `force_vision` 옵션 노출 위치 — **request body 의 옵셔널 필드 (default false)**

- 환경변수 / query param 모두 거절. 매 요청마다 토글 가능해야 하고, POST body 가
  자연스러운 위치.
- 영향: ADR §D-3.3 의 PDF 분기 휴리스틱은 그대로 유지하되, `force_vision=true`
  이면 휴리스틱 우회하고 즉시 Vision 경로.

### PM-4. LLM 호출 로깅 — **DB 테이블 (`llm_usage_logs`) + jsonl 백업 sink**

- 1차 보관: DB 테이블 (운영 / 프라이싱 분석용 SQL 집계 1급 지원).
- 2차 (백업): 파일 sink 도 동시에 기록 (DB 장애 / 마이그레이션 안전망). 분석 도구는
  DB 우선, 파일은 fallback.
- 1차 스키마 (P0-1 마이그레이션에서 같이 박음):

  ```
  llm_usage_logs
    id (UUID PK)
    tenant_id (UUID, nullable — 시스템 호출 / pre-tenant 호출 허용)
    workspace_id (UUID, nullable)
    request_id (UUID, NOT NULL — 동일 요청 묶음)
    parent_request_id (UUID, nullable — 재시도 체인)
    model (str — 예: "claude-sonnet-4-...")
    purpose (str — 예: "extract_text", "extract_pdf_vision", "extract_pdf_text")
    input_tokens (int)
    output_tokens (int)
    cache_read_tokens (int, default 0)
    latency_ms (int)
    status (str — "success" | "schema_invalid" | "timeout" | "network_error" | "rate_limited" | "other")
    error_class (str, nullable)
    cost_usd (numeric, nullable — 추후 백필 가능)
    created_at (timestamptz)
  ```

- 인덱스: `(tenant_id, created_at)`, `(purpose, created_at)`.
- 영향: ADR §D-3.5 (LLM 래퍼 내부 재시도) 의 retry chain 이 `parent_request_id`
  로 추적 가능해야 함 — 본 컬럼 추가는 D-3.5 와 정합.

### PM-5. Phase 0 추출 스코프 — **자료에 보이는 것만 추출 (옵션 B), 생성 안 함**

- Passage / Question 외에 Translation / Vocabulary 도 **자료에 명시적으로 존재하면**
  추출. 자료에 없으면 비워둠 (Phase 2 의 LLM 생성 단계가 이후 채움).
- 근거: A (최소) 는 아잉카 자료의 해석/어휘를 버리는 낭비. C (풀 추출) 는 추출과
  생성을 섞어서 책임이 흐려짐. B 가 "보이는 건 다 캐치, 만들어내진 않는다" 로
  책임 명확.
- 영향: extractor 출력 스키마 `ExtractionResult` 가 `translation: Optional[...]`,
  `vocabulary: list[...]` (빈 리스트 허용) 를 포함해야 함. ADR §D-3.1 시그니처
  확장 필요 — schema 갭으로 처리 (G-5 신설 권고, 후속 작업 섹션 참고).

### PM-6. 운영 가정 — 실유저 입력 분포

- **아잉카 자료는 학습용 / 개발용 fixture**. 풀세트 (영어 + 한글 해석 + 어휘) 라
  추출 검증이 쉬움. 실유저 분포와 다름.
- **실유저 (와이프, 강사) 입력의 default 는 "영어만" 또는 "문제만 (한글 해석 없음)"**.
  자료에 한글 해석 / 어휘 박스가 없는 게 정상.
- 영향:
  1. 추출 결과의 `translation` / `vocabulary` 가 비어있는 게 **에러가 아닌 정상**.
     모든 후속 코드 (validator, qa-validator stub, UI 미리보기) 가 이를 전제.
  2. Fixture set 에 **"영어만 있는 자료" 를 의도적으로 포함** 해야 함 (PM 이 수집
     중인 fixture 에 반영). 아잉카 같은 풀세트만 있으면 실유저 케이스 커버 안 됨.
  3. **Phase 2 의 한글 해석 / 어휘 생성 단계가 사실상 모든 실사용에서 거의 항상
     작동해야 함** — 추출 단계에서 비어있는 게 default 이므로.

### PM-7. Fixture 자료 경로 — **PM 이 수집 중**

- 경로: `admin/fixtures/extractor/`
  - `pdf/text-layer/` — 텍스트 레이어 있는 PDF (아잉카 등)
  - `pdf/scanned/` — 스캔본 PDF (학교 내신지 등)
  - `image/` — 단일 이미지 (사진 / 스크린샷)
  - `text/` — `.txt` 직접 입력
- PM-6 의 가정에 따라 각 폴더에 "풀세트" 와 "영어만" 양쪽이 골고루 있어야 함.
- backend-dev 는 P0-3 / P0-4 / P0-5 진입 전 fixture 가용성 확인.

---

## References

- `CLAUDE.md` §2.1 (Phase 0 DoD), §3.1 (canonical schema), §3.4 (PDF 분기), §3.6
  (No Reinventing), §8.3 (LLM 호출), §8.4 (라이브러리 도입)
- `docs/adr/0001-canonical-schema-philosophy.md`
- `docs/schema-coverage-audit.md` §1.6 (exam-generator 의 LLM 어댑터 위치)
- exam-generator `app/llm/anthropic.py:31-64` (검증된 tool_use 패턴)
- exam-generator `app/llm/pdf.py` (PyMuPDF + Vision 분기 선례)
