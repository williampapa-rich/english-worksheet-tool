# Template Rendering — 외부 템플릿 분석 및 통합 검토

- **작성일**: 2026-05-06
- **작성자**: Claude (PM 검토 대기)
- **상태**: Accepted (PM 결정 완료, 2026-05-06) — Stage 0 진행, ADR-0011 은 Stage 1 진입 시 승격
- **목적**: `~/Downloads/템플릿/` 으로 받은 외부 워크시트 템플릿 3종을 분석하고,
  현재 진행 중인 Phase 1 (구문분석 에디터) 과 **병렬 진행 가능성** 을 평가한다.
- **관련 문서**:
  - `CLAUDE.md` v0.7 §2.1 Phase 2 DoD, §3.5 (annotation HWPX 매핑)
  - `docs/adr/0008-phase-1-output-format.md` (HTML→PDF 전환 결정 — 본 분석의 출발점)
  - `docs/adr/0010-split-mark-pseudo-element-rendering.md` (annotation HTML 렌더링)
  - `shared/schemas/worksheet.py` (Worksheet / Branding / WorksheetItem)

---

## 1. 받은 자산 요약

`/Users/81070/Downloads/템플릿/` 에 다음 4개 파일:

| 파일 | 종류 | 용도 |
|---|---|---|
| `README.md` | 문서 | 데이터 계약 + Playwright PDF 가이드 + 폰트 정책 |
| `classic.html` | Jinja2 템플릿 | Style 1 — 수능 모의고사 톤 (Noto Serif KR) |
| `modern.html` | Jinja2 템플릿 | Style 2 — 모던 미니멀 (Fraunces 디스플레이) |
| `playful.html` | Jinja2 템플릿 | Style 3 — 친근한 학원 핸드아웃 (배너 + 카드) |

**핵심 특성**:
- Jinja2 + CSS print stylesheet (`@page` 사용) 기반
- A4 portrait/landscape 토글 (`worksheet.orientation`)
- CSS 변수 (`--theme`, `--ink`, `--muted` 등) 로 디자인 토큰 노출 → `academy.theme_color` 인라인 주입
- 외부 CDN 폰트 (Pretendard / Noto Serif KR / Fraunces / Tabler Icons)
- `q.content_html | safe` 로 구문분석 마크업 HTML 슬롯
- Playwright headless Chromium 으로 PDF 렌더 (가이드까지 README 에 포함)

## 2. 우리 시스템과의 align

### 2.1 ADR-0008 과의 정합성 — 매우 높음

ADR-0008 (2026-05-04) 에서 Phase 1 출력 경로를 **HWPX 텍스트 재현 → HTML/PDF (브라우저
print 렌더링)** 로 전환했다. 받은 템플릿은 정확히 이 결정을 따른 형태:

- ✅ HTML + CSS print stylesheet
- ✅ A4 페이지 사이즈 / 마진 / 가로세로 모드
- ✅ Playwright headless 렌더 가이드
- ✅ `q.content_html | safe` 로 annotation split-mark 렌더링 ADR (번호 미확정, 향후 작성) 산출 HTML 그대로 주입 가능

→ **재구현 불필요**. CLAUDE.md §3.6 "No Reinventing the Wheel" 원칙에 따라 **이 템플릿
세트를 채택** 하는 게 올바름.

### 2.2 `shared/schemas/worksheet.py` 와의 갭

> **Stage 1 갱신 (2026-05-07)**: 본 표의 갭은 **ADR-0010** (`docs/adr/0010-worksheet-output-parameters.md`)
> 에서 schema 변경 결정 — `Worksheet.{subtitle, orientation, instruction}` +
> `WorksheetItem.label` + `Branding.academy_name` 추가, `student.*` 와 `page_number`/
> `total_pages` 는 schema 외.

받은 템플릿의 데이터 계약 vs 현재 schema:

| 템플릿 변수 | 현재 schema 필드 | 갭 |
|---|---|---|
| `academy.name` | ❌ (없음) | Tenant 또는 Workspace 레벨 필드 신규 필요 |
| `academy.theme_color` | `Branding.primary_color` | ✅ (이름 매핑만) |
| `academy.logo_url` | `Branding.logo_url` | ✅ |
| `worksheet.title` | `Worksheet.title` | ✅ |
| `worksheet.subtitle` | ❌ | 신규 필드 (예: "Week 04") |
| `worksheet.page_number / total_pages` | ❌ | 렌더 시점 계산 (schema 외) |
| `worksheet.orientation` | ❌ | 신규 필드 (`portrait` / `landscape`) |
| `student.name / class_name / date` | ❌ | 출력물 헤더 영역 — Worksheet 자체 메타 |
| `instruction` | ❌ | 신규 필드 — 워크시트 지시문 |
| `questions[].number` | (계산) | `WorksheetItem.order + 1` 매핑 |
| `questions[].label` | ❌ | 신규 필드 (예: "관계절이 포함된 문장") |
| `questions[].content_html` | (렌더 산출) | annotation 렌더러 산출물 |

**갭 요약**: schema 변경 4건 정도 — `subtitle`, `orientation`, `instruction`,
`WorksheetItem.label`. `student.*` 와 `academy.name` 은 schema 도입 vs 렌더 시점 주입
중 결정 필요 (학생별 발급은 Phase 2 DoD 범위 밖일 수도).

### 2.3 Branding 매핑

```
shared.schemas.worksheet.Branding         → 템플릿 academy
  logo_url           → academy.logo_url
  primary_color      → academy.theme_color
  secondary_color    → (현 템플릿 미사용 — playful 의 color-mix 가 자동 생성)
```

→ **매핑 어댑터 1개** 만 있으면 즉시 호환. `secondary_color` 는 일단 보관 (Phase 2 후
디자인 확장 시 사용).

## 3. 병렬 진행 가능성 평가

### 3.1 코드/스키마 레벨 — 충돌 거의 없음

| 영역 | 에디터 (Phase 1, 진행 중) | 템플릿 렌더링 (Phase 2 선행) |
|---|---|---|
| 주요 schema | `SyntaxAnnotation` | `Worksheet`, `Branding`, `WorksheetItem` |
| 주요 코드 | `packages/editor/`, `apps/web/src/pages/EditorPoc*` | `apps/api/` (FastAPI 라우트) + `shared/templates/worksheet/` (신규) |
| LLM 의존 | 없음 (사용자 입력 기반) | 없음 (이미 정규화된 Passage 사용) |
| HWPX 렌더러 | ADR-0008 로 deprecate 진행 | 사용 안 함 |

→ **schema 변경 4건 + Worksheet 라우트 + 템플릿 디렉토리 추가** 조합. 에디터 작업과 파일
경로가 거의 안 겹친다.

### 3.2 진짜 병목 — 와이프 검수 capacity

- **Phase 1 baseline 검수** (구문분석 에디터 산출 HTML/PDF) 가 우선순위 1
- **Phase 2 템플릿 디자인 검수** (3종 중 1종 픽 + 학원 컬러 / 로고 적용) 가 우선순위 2
- 둘 다 와이프 시간을 요구 → 동시에 들이대면 검수 부하 + 컨텍스트 분산

**권고**: 검토/구현 작업은 병렬 진행하되, **와이프 검수는 직렬** — Phase 1 baseline OK
받은 후 Phase 2 검수 들어간다.

### 3.3 Phase 1 → Phase 2 의 자연스러운 연결고리

받은 템플릿이 `q.content_html | safe` 슬롯을 가지고 있고, 이게 **에디터의 annotation
split-mark 렌더링 ADR (번호 미확정, 향후 작성) 산출 HTML 과 정확히 같은 자리** 다. 즉:

```
[Phase 1 산출]                                [Phase 2 템플릿]
Tiptap 에디터 → split-mark HTML  ──────→  q.content_html
                                          (classic/modern/playful 어디든)
```

→ 에디터 산출 HTML 의 CSS 스타일이 템플릿 안에서 그대로 동작하는지 **호환성 PoC 1건**
이 Phase 1 ↔ Phase 2 의 자연스러운 bridge. 이건 의존성이 아니라 **상호 검증 기회**.

## 4. 권고 — 단계별 접근

안정성 우선이므로 **현재 Phase 1 작업을 흔들지 않는 순서** 로:

### Stage 0 — 자산 도입 (즉시 가능, 위험 낮음)

- [ ] 받은 템플릿 3종을 `shared/templates/worksheet/` 에 그대로 도입 (수정 없이)
- [ ] README 의 데이터 계약을 `docs/template-data-contract.md` 로 파생 (schema 매핑 표
  포함)
- [ ] PR: 새 디렉토리 + 파일 추가만, 코드 변경 0

→ **에디터 작업 영향 0**. 단순 자산 import.

### Stage 1 — Schema 갭 해소 (Phase 1 baseline 후)

- [ ] ADR 신규 — "Worksheet 출력 파라미터 확장" (subtitle, orientation, instruction,
  WorksheetItem.label, student/academy 메타 위치 결정)
- [ ] `shared/schemas/worksheet.py` 마이그레이션 + Alembic
- [ ] Branding ↔ academy 매핑 어댑터 (`packages/template_renderer/` 신설)

### Stage 2 — 렌더 파이프라인 PoC

- [ ] FastAPI 라우트: `GET /worksheets/{id}/preview?style={classic|modern|playful}` →
  Jinja2 렌더 HTML
- [ ] FastAPI 라우트: `POST /worksheets/{id}/export.pdf` → Playwright 변환 → PDF
  binary 응답
- [ ] **Playwright 의존성 도입 PR** (CLAUDE.md §3.6 — 대안 검토 1개 이상: WeasyPrint
  / wkhtmltopdf / Chromium API 직접)
- [ ] 에디터 산출 HTML 1건을 `content_html` 에 주입해서 3종 템플릿 모두 렌더 — Phase 1
  ↔ Phase 2 호환성 검증

### Stage 3 — Web preview + customizing UI (Phase 2 본격 시작)

- [ ] 웹앱에 preview 라우트 (iframe 또는 server-rendered HTML 임베드)
- [ ] 학원 컬러 / 로고 변경 UI → Branding 모델 업데이트 → 즉시 미리보기 갱신
- [ ] PDF 다운로드 버튼

## 5. 결정된 사항 (PM, 2026-05-06)

| # | 항목 | 결정 | 근거 |
|---|---|---|---|
| 1 | 템플릿 디렉토리 위치 | **`packages/template_renderer/templates/`** | 프로젝트 내 통합 관리. CLAUDE.md §5 의 `packages/` 컨벤션 (`hwpx_renderer` 와 대칭, ADR-0008 deprecate 후 자연 대체). |
| 2 | PDF 변환 라이브러리 | **Playwright (headless Chromium)** | 산출물 품질 우선. playful.html 의 `color-mix(in srgb, ...)` 등 모던 CSS 완전 지원. README 가이드와 일치. 도입 PR 에 §3.6 대안 검토 (WeasyPrint / LibreOffice) 기록 필수. |
| 3 | 외부 폰트 정책 | **CDN 유지** (Pretendard / Noto Serif KR / Fraunces / Tabler Icons) | 사용자 활동 환경이 일반 인터넷 환경 — 사내망 proxy 차단 우려 없음. Stage 2 PoC 시 `wait_until` 정책만 검토. |
| 4 | 템플릿 개수 | **MVP 는 `playful` 1종**, `classic` / `modern` 은 보관 | CLAUDE.md §2.1 Phase 2 점진 개선 영역 ("다중 템플릿") 과 일치. 보관본은 디렉토리에 두되 라우트 노출 안 함 — 추가는 라우트만 연결. |
| 5 | `student.*` schema 도입 | **도입 안 함, 렌더 시점 파라미터** | 학생 이름/반/날짜는 인쇄 후 학생이 손으로 기입. 콘텐츠 생성 ≠ 학생별 발급. CLAUDE.md §1.4 비-목표 ("학생 성적 관리") 와 인접 영역 확장 회피. |

**5번 함의**: `Worksheet` schema 에서 `student_*` 필드 일절 추가 X. 렌더 API 는
`POST /worksheets/{id}/export.pdf` body 에 학생 메타 받는 옵션 자체를 두지 않거나
(가장 단순) 빈칸 출력만 지원. 학생별 개인화 요구가 실제로 생기면 Phase 4 에서
별도 발급 이력 모델로 처리.

## 6. 위험 / 주의사항

- **Playwright + 외부 폰트 CDN** 의존성: 폰트 CDN 응답 지연 시 PDF 렌더 hang. 사내망
  proxy 환경이면 더 위험. → 폰트 자가 호스팅 + `wait_until="load"` 로 완화.
- **`q.content_html | safe`** XSS: 에디터 산출은 신뢰 가능하지만, 사용자 직접 HTML 입력
  경로가 생기면 `bleach` 등 sanitizer 필요. Phase 2 시작 시 명시적 정책 결정.
- **CSS `color-mix` 호환성**: playful.html 이 사용 — Chromium 111+ 에서만 동작. 다른
  PDF 엔진 (WeasyPrint 등) 으로 전환 시 fallback 필요.
- **Tabler Icons 의존성** (playful.html): 외부 jsDelivr CDN. 자가 호스팅 권고.

## 7. 결론

**병렬 진행 가능 + 권장**. 단 실제 구현/검수는 단계별:

- ✅ **즉시 가능**: 받은 템플릿을 자산으로 도입 (Stage 0) — 에디터 작업 영향 0
- ✅ **즉시 가능**: 본 문서 + 데이터 계약 문서 + (선택) 렌더 ADR 초안 작성
- ⏳ **Phase 1 baseline 후**: Schema 갭 해소 + 렌더 파이프라인 PoC
- ⏳ **Phase 2 시작 후**: Web preview UI + customizing

**다음 액션**:
1. ✅ PM 결정 완료 (§5)
2. ▶️ Stage 0 PR — `packages/template_renderer/templates/` 에 3종 HTML + README 도입,
   코드 변경 0
3. ⏳ ADR-0011 승격은 **Stage 1 진입 시점** 으로 미룸 — Stage 2 PoC 결과 (Playwright
   실측, 폰트 동작, 에디터 산출 HTML 호환성) 를 ADR 에 반영하기 위해.
