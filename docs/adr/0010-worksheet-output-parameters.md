# ADR 0010 — Worksheet 출력 파라미터 확장 (subtitle / orientation / instruction / item.label / academy_name)

- **상태(Status)**: Proposed
- **작성일**: 2026-05-07
- **결정일**: TBD (PM 검토 대기)
- **작성자**: architect
- **결정자**: PM (Dennis)
- **유형**: template-renderer 트랙 Stage 1 schema 갭 해소 — `shared/schemas/worksheet.py`
  필드 추가만, ORM / Alembic / 어댑터는 후속 PR.
- **범위**: Pydantic 모델 확장 + ADR + 분석 문서 cross-reference. 마이그레이션 / 렌더
  어댑터 / FastAPI 라우트는 본 ADR 의 결정에 따라 backend-dev 가 후속 PR 에서 진행.
- **관련 문서**:
  - `CLAUDE.md` v0.7 §1.4 (비-목표 — 학생별 발급 ≠ 콘텐츠 생성), §3.1 (canonical schema),
    §6.1 (핵심 엔티티)
  - `docs/template-rendering-analysis.md` §2.2 (schema 갭 표), §5 (PM 결정 5건)
  - `packages/template_renderer/templates/playful.html` (실데이터 계약 — MVP 채택)
  - `packages/template_renderer/README.md` (데이터 계약 스펙)
  - `docs/adr/0001-canonical-schema-philosophy.md` (스키마 진화 원칙 — breaking change
    최소화, 새 필드 추가 위주)
  - `docs/adr/0002-content-model-v0_1.md` (Worksheet 1차 정의)
  - `docs/adr/0008-phase-1-output-format.md` (HWPX → HTML/PDF 출력 전환)

---

## Context (배경)

### 1. Stage 0 자산 도입 — 데이터 계약이 schema 를 앞서 나감

PR #40 (커밋 `a3f24f6`, 2026-05-06) 에서 외부 워크시트 템플릿 3종 (`classic` / `modern` /
`playful`) 을 `packages/template_renderer/templates/` 에 자산으로 도입했다. 이 템플릿이
Jinja2 변수로 기대하는 데이터 계약 (README.md `데이터 계약` 섹션) 은 다음과 같다.

| 카테고리 | 변수 | 현재 schema |
|---|---|---|
| academy | `name`, `theme_color`, `logo_url` | `Branding.{primary_color, logo_url}` 일부만 |
| worksheet | `title`, `subtitle`, `orientation`, `page_number`, `total_pages` | `Worksheet.title` 만 |
| student | `name`, `class_name`, `date` | 없음 |
| body | `instruction`, `questions[].number`, `questions[].label`, `questions[].content_html` | `WorksheetItem.{passage_id, order}` 만 |

ADR-0001 의 "canonical schema 가 시스템의 척추" 원칙상 **렌더링 시점에 임시 dict 로
끼워 넣는 방식은 채택할 수 없다** (어댑터 1번 필요한 건 인정하지만, 데이터의 source of
truth 는 schema 여야 함).

### 2. PM 결정 (`docs/template-rendering-analysis.md` §5)

`student.*` 는 schema 도입하지 않는다 (PM 결정 #5) — 학생 이름/반/날짜는 인쇄 후 손기입.
CLAUDE.md §1.4 비-목표 ("학생 성적 관리") 인접 영역 확장 회피. **렌더 시점에 빈 dict 만
주입한다** — schema 변경 0.

`page_number` / `total_pages` 는 페이지 단위 메타로 schema 의 콘텐츠 데이터가 아님 —
렌더 시점 (Playwright 후처리 또는 Jinja2 컨텍스트 주입) 에 계산.

### 3. 스키마 진화 원칙 (ADR-0001)

- Breaking change 금지 — 기존 필드 변경 / 제거 X.
- 새 필드는 모두 nullable / default 값 보유 — 기존 row / 기존 호출자 호환.
- `Worksheet.kind` 는 `STUDENT` / `TEACHER` / `SYNTAX_ANALYSIS` / `VARIANT_SET` 4종.
  새 필드는 모든 kind 에서 의미 있어야 한다 (또는 어떤 kind 에서만 의미 있는지 docstring
  에 명시).

---

## Decision (결정)

### D1. 신규 필드 4건 (필수)

| # | 위치 | 필드 | 타입 | default | max_length | 매핑 (템플릿 변수) |
|---|---|---|---|---|---|---|
| 1 | `Worksheet` | `subtitle` | `str \| None` | `None` | 255 | `worksheet.subtitle` |
| 2 | `Worksheet` | `orientation` | `WorksheetOrientation` | `PORTRAIT` | — | `worksheet.orientation` |
| 3 | `Worksheet` | `instruction` | `str \| None` | `None` | 2000 | `instruction` |
| 4 | `WorksheetItem` | `label` | `str \| None` | `None` | 255 | `questions[].label` |

#### 1. `Worksheet.subtitle: str | None`

- **의미**: 워크시트 부제. 예시: `"Week 04"`, `"Mock Exam #2"`, `"2025 1학기 중간"`.
- **모든 kind 에서 의미 있음** — 학생용 / 교사용 / 구문분석 / 변형문제집 모두 부제는 자연스러움.
- **max_length=255**: `title` 과 동일. 더 길 이유 없음.
- **nullable**: 부제 없는 워크시트 (Phase 0 fixture 등) 호환.

#### 2. `Worksheet.orientation: WorksheetOrientation`

- **신규 enum**: `WorksheetOrientation(StrEnum)` — `"portrait"` / `"landscape"`.
- **default=PORTRAIT**: 기존 row 마이그레이션 시 NULL 또는 미지정 → `portrait` (한국 영어
  학원 워크시트 디폴트).
- **모든 kind 에서 의미 있음** — landscape 는 좌우 비교 레이아웃 / 긴 문장 유지에 유용.
  syntax_analysis kind 도 landscape 가 분석표를 본문 옆에 배치할 때 유리.
- **enum 선택 이유**: free-form `str` 은 silent drift 위험 (예: `"horizontal"` /
  `"land"` 등). Pydantic v2 `StrEnum` 으로 schema 레벨에서 차단.
- **default 가 non-None 인 유일한 신규 필드**: 다른 3개는 nullable string. orientation 은
  렌더 시 반드시 값이 필요 (CSS `@page size` 분기) — None 허용하면 매번 fallback
  로직 작성 필요.

#### 3. `Worksheet.instruction: str | None`

- **의미**: 워크시트 지시문 (예: `"다음 문장을 읽고 어법상 어색한 부분을 고치시오."`).
  playful 템플릿의 `.instruction` 박스에 표시.
- **max_length=2000**: 다중 문장 지시문 허용. exam-generator 의 `instruction` 필드와
  동일 제약.
- **kind 별 의미**: STUDENT / TEACHER / VARIANT_SET 에서 자연스러움. SYNTAX_ANALYSIS 는
  보통 지시문이 짧거나 없으므로 nullable 적절.

#### 4. `WorksheetItem.label: str | None`

- **의미**: 항목 1개의 라벨. 예시: `"관계절이 포함된 문장"`, `"빈칸 추론 — 주제"`.
  playful 템플릿의 `.q-label` (`<span class="q-label">`) 슬롯에 표시.
- **max_length=255**.
- **kind 별 의미**:
  - STUDENT: 항목별 분류 라벨 (예: "필수 어휘 5개").
  - TEACHER: 출제 의도 / 난이도 라벨.
  - SYNTAX_ANALYSIS: 분석 포커스 (예: "분사구문").
  - VARIANT_SET: 변형 유형 (예: "어휘 교체"). VariantQuestion 의 `variant_kind` 와
    별도 — 후자는 도메인 enum, 본 필드는 자유 텍스트 디스플레이용.
- **nullable**: 라벨 없이 번호만 노출하는 케이스도 자연스러움.

### D2. 신규 enum — `WorksheetOrientation`

```python
class WorksheetOrientation(StrEnum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"
```

- StrEnum (Python 3.12+) — JSON 직렬화 시 문자열 그대로, `worksheet.orientation` 템플릿
  변수와 1:1 매핑 (별도 변환 없음).
- 기존 enum (`WorksheetKind`) 과 같은 파일 (`shared/schemas/worksheet.py`) 에 배치.

### D3. `academy.name` — Branding 에 `academy_name` 추가 (채택)

`docs/template-rendering-analysis.md` §2.2 에서 미정 항목으로 남았던 `academy.name` 의
배치 결정. 3가지 후보 검토:

#### 후보 A — `Workspace.name` 재사용

- **장점**: 추가 컬럼 0. 이미 존재하는 필드.
- **단점**:
  - `Workspace.name` 은 **운영용 라벨** (예: `"고3 수능반"`, `"중3 내신반"`). 학원 브랜드명이
    아님.
  - 한 학원 안에 여러 Workspace 가 있으면 (현 단계 멀티테넌트 구조 전제 — `WorkspaceScopedEntity`
    의 의미) Workspace 마다 학원명이 동일해야 하는 강제 — Workspace 운영 의미 훼손.
  - 검색/필터/UI 라벨 용도와 출력물 헤더 용도 충돌.
- **결론**: 탈락.

#### 후보 B — `Branding.academy_name` 추가 (**채택**)

- **장점**:
  - `Branding` 은 이미 출력물의 customer-facing presentation 그룹 (logo, color). 학원명은
    같은 카테고리 — 응집도 높음.
  - `Worksheet.branding` 이 default_factory `Branding()` 으로 즉시 사용 가능.
  - 한 Workspace 안의 Worksheet 마다 다른 브랜딩 (예: 다른 학원 이름 with 같은 강사) 도
    이론상 가능 — Phase 4 멀티테넌트 활성화 후 유스케이스 호환.
  - schema 진화 비용 최소 — 기존 row 호환 (nullable).
- **단점**:
  - 같은 Workspace 의 모든 Worksheet 가 보통 같은 학원명을 가질 텐데, Worksheet 마다
    `branding.academy_name` 을 채우는 게 중복. → 어댑터 / 기본값 주입 로직으로 해소
    가능 (Stage 1-2 어댑터 PR 책임).
- **결론**: **채택**. `Worksheet.branding.academy_name: str | None` (max_length=255,
  default=None).

#### 후보 C — Tenant / Workspace 모델에 `display_name` 추가

- **장점**: 학원 브랜드는 보통 학원 단위 (Tenant) 또는 강의실 단위 (Workspace) 에 묶인다.
- **단점**:
  - Tenant / Workspace 는 인프라 엔티티 — 출력 정보를 거기 두면 도메인 경계 모호.
  - Stage 1 schema 변경 범위가 Tenant 까지 번지면 마이그레이션 영향 광범위.
  - Phase 4 OAuth 도입 시 Tenant schema 가 흔들릴 가능성 — 출력 메타까지 묶이면 변경
    파급 큼.
- **결론**: 탈락 (Phase 4 에서 별 ADR 로 다루는 게 안전).

**최종 결정**: 후보 B. `Branding` 에 `academy_name` 추가.

### D4. `student.*` — 도입 안 함 (PM 결정 #5 인용)

`docs/template-rendering-analysis.md` §5 #5 의 PM 결정을 그대로 인용.

> "학생 이름/반/날짜는 인쇄 후 학생이 손으로 기입. 콘텐츠 생성 ≠ 학생별 발급. CLAUDE.md
> §1.4 비-목표 ('학생 성적 관리') 와 인접 영역 확장 회피."

- `Worksheet` / `WorksheetItem` 어디에도 `student_*` 필드 추가 X.
- 렌더 시점에 어댑터가 빈 dict (`{"name": "", "class_name": "", "date": ""}`) 만 주입.
  Stage 1-2 어댑터 PR 의 명시적 책임.
- 학생별 발급 요구가 실제로 생기면 Phase 4 에서 `WorksheetIssue` 또는 별 발급 이력
  엔티티로 처리 (현 schema 에 끼워 넣지 않음).

### D5. `worksheet.page_number` / `worksheet.total_pages` — 렌더 시점 계산

페이지 단위 메타. schema 의 콘텐츠 데이터가 아니다.

- Playwright 가 PDF 변환 시 자동 페이지 분할 — 정확한 페이지 수는 렌더 시점에만 결정.
- Jinja2 컨텍스트 주입 시 `worksheet.page_number = 1` / `worksheet.total_pages = 1` (단일
  HTML 1페이지 가정) 으로 우선 채움. 실제 PDF 다중 페이지가 되면 Stage 2 PoC 에서 CSS
  `counter()` 또는 Playwright `header_template` 으로 처리.
- schema 변경 X.

### D6. Branding 매핑 — 어댑터 책임 (Stage 1-2 후속 PR)

매핑 결정 (`docs/template-rendering-analysis.md` §2.3 인용):

| `Branding` 필드 | 템플릿 변수 |
|---|---|
| `logo_url` | `academy.logo_url` |
| `primary_color` | `academy.theme_color` |
| `secondary_color` | (현 템플릿 미사용 — 보관) |
| `academy_name` (D3 신규) | `academy.name` |

`secondary_color` 의 docstring 보강 — **현 템플릿 미사용. Phase 2 디자인 확장용 보관**.
필드 자체는 유지 (제거 = breaking change, ADR-0001 위반).

playful 템플릿의 `--theme-soft` / `--theme-mid` 는 `color-mix(in srgb, ...)` 로 자동
생성 (Chromium 111+) — `secondary_color` 사용 안 함. WeasyPrint 등 다른 PDF 엔진 전환
시 `secondary_color` 활성화 가능 (Phase 2 결정).

매핑 어댑터는 **본 PR 범위 밖** — `packages/template_renderer/` 의 후속 PR
(`worksheet_to_template_context()` 같은 함수) 에서 처리.

### D7. Migration 영향

- **`worksheets` 테이블**: `subtitle` (varchar(255), nullable), `orientation`
  (varchar(16), NOT NULL, default `'portrait'`), `instruction` (text, nullable) 컬럼
  추가. `branding` 이 JSONB 컬럼이면 schema 변경 없이 `academy_name` 자동 수용 (현
  ORM 매핑이 JSONB 인지 backend-dev 확인 필요).
- **`worksheet_items` 테이블**: `label` (varchar(255), nullable) 컬럼 추가.
- **기존 row 호환**: 모두 nullable 또는 default 값 보유. 마이그레이션 후 기존 row 의
  `orientation` 은 `'portrait'` 로 채움.
- **실제 Alembic revision 작성은 본 PR 범위 밖** — 후속 backend-dev PR 책임.

### D8. kind 와의 직교성

신규 4필드 + 1필드 (`Branding.academy_name`) 는 모든 `WorksheetKind` 값 (STUDENT /
TEACHER / SYNTAX_ANALYSIS / VARIANT_SET) 에서 의미 있음. kind 별 default 권고는 어댑터
책임 — schema 자체는 직교성 유지.

특수 케이스 docstring 메모:
- `instruction`: SYNTAX_ANALYSIS 에서는 보통 빈 값.
- `WorksheetItem.label`: VARIANT_SET 에서는 `variant_kind` 의 displayed text 와 중복
  가능성 — 어댑터가 default 채우거나 `variant_kind` 에서 파생할지 후속 결정.

---

## Consequences (결과)

### 긍정적 결과

1. **데이터 계약 = schema** — 템플릿 Jinja2 변수와 `shared/schemas/worksheet.py` 의
   1:1 매핑 (academy.* / worksheet.* / questions[].* 모든 영구 데이터). ADR-0001 의
   canonical schema 원칙 충족.
2. **모든 신규 필드 nullable / default** — 기존 row / 기존 fixture / Phase 0 데이터
   호환. Breaking change 0.
3. **`student.*` 추가 안 함** — CLAUDE.md §1.4 비-목표 (학생별 발급) 인접 영역 확장 회피.
   schema bloat 방지.
4. **`Branding.academy_name`** — 출력물 customer-facing 그룹 응집도 유지. Tenant /
   Workspace schema 흔들지 않음 (Phase 4 영향 최소).
5. **`WorksheetOrientation` enum** — silent drift 차단 + Pydantic 레벨 validation +
   Playwright `landscape` 파라미터 분기에 정확한 source.

### 부정적 결과 / 리스크

1. **`Branding.academy_name` 중복 입력** — 같은 Workspace 의 모든 Worksheet 가 같은
   학원명을 가지면 매번 채우기 번거로움. 어댑터 / 기본값 주입으로 완화 (Stage 1-2 후속
   PR 책임).
2. **`Worksheet.orientation` default 가 `PORTRAIT`** — 기존 row 마이그레이션 시 일괄
   `portrait` 로 채움. landscape 가 default 인 fixture 가 향후 추가되면 명시적으로
   `LANDSCAPE` 지정 필요.
3. **`WorksheetItem.label` 의 의미 중복 가능성 (VARIANT_SET kind)** — `variant_kind`
   enum 과 동일 정보가 displayed text 로 들어가면 silent drift 위험. 어댑터에서
   `label = variant_kind.label` 식 파생 정책을 후속 PR 에서 결정.
4. **마이그레이션 실행 비용** — 기존 row 가 거의 없는 Phase 0 단계라 비용 미미. Phase 1+
   누적 데이터가 늘면 일괄 default 채움 시간 증가하지만 컬럼 수준 ALTER 라 실용적 문제
   없음.

### 후속 작업 (별 PR)

- **PR 후속 1 (backend-dev)**: Alembic revision 작성 — `worksheets.subtitle` /
  `orientation` / `instruction` + `worksheet_items.label` + (`branding` JSONB 매핑이면)
  자동 / (별 컬럼이면) `branding_academy_name`. 마이그레이션 시 `orientation` default
  `'portrait'` 백필.
- **PR 후속 2 (backend-dev)**: ORM 모델 (`apps/api/.../models/worksheet.py`) 필드 추가.
- **PR 후속 3 (backend-dev / architect 협업)**: `packages/template_renderer/` 의
  `worksheet_to_template_context()` 어댑터 — `Worksheet` + `Branding` →
  `{"academy": ..., "worksheet": ..., "student": ..., "questions": ...}` 변환.
  - `student` 는 빈 dict 주입 (PM 결정 #5).
  - `page_number` / `total_pages` 는 1 / 1 default (Stage 2 PoC 에서 정밀화).
  - `Branding.secondary_color` 는 미사용 (현 템플릿 미참조).
- **PR 후속 4 (backend-dev)**: FastAPI 라우트 — `GET /worksheets/{id}/preview?style=playful`
  → Jinja2 렌더 HTML / `POST /worksheets/{id}/export.pdf` → Playwright PDF.

### CLAUDE.md / phase 문서 갱신

본 PR 에서는 안 함. PR 후속 4 머지 시점에 CLAUDE.md §3 ADR Lite 또는 §11 Open
Questions 에서 Stage 1 완료 표기.

---

## 대안 검토 요약

| 항목 | 채택 | 탈락 후보 |
|---|---|---|
| `academy.name` 위치 | `Branding.academy_name` (D3) | `Workspace.name` 재사용 / Tenant.display_name |
| `student.*` 도입 | 도입 안 함 (D4) | `Worksheet.student_name/class/date` 추가 |
| `orientation` 타입 | `StrEnum` (D2) | `str` (drift 위험) / `bool is_landscape` (확장성 X) |
| `page_number/total_pages` | 렌더 시점 계산 (D5) | schema 필드 추가 |
| `secondary_color` | docstring 보강만, 필드 유지 (D6) | 제거 (breaking) / 기본 활용 |

---

## 결정 기록

| 날짜 | 상태 | 결정자 | 비고 |
|---|---|---|---|
| 2026-05-07 | Proposed | architect | template-renderer 트랙 Stage 1 — schema 갭 4건 + `academy_name` 위치 결정 + `student.*` 도입 안 함 / `page_number,total_pages` 렌더 시점 처리 명시 |
