# Stage F3 — 회귀 Spec 활성화 + Cleanup 보고서

**날짜**: 2026-05-15
**브랜치**: `feat/stage-f3-cleanup`
**ADR**: ADR-0018 Stage F3

---

## 1. F3-a: 회귀 Spec 강화 결과

### 변경 파일

| 파일 | 변경 내용 |
|---|---|
| `apps/web/tests/e2e/wrap_parity_stage_f3.spec.ts` | **신규** — F3 정식 회귀 spec |
| `apps/web/tests/e2e/wrap_parity_stage_f1.spec.ts` | 유지 (F1 구조 검증 spec) |
| `apps/web/tests/e2e/wrap_parity_stage_f2.spec.ts` | 유지 (F2 mark DOM 정합 spec) |
| `apps/web/tests/e2e/wrap_parity.spec.ts` | 유지 (Coffee fixture 기반 에디터↔PDF) |

### wrap_parity_stage_f3.spec.ts 설계

**F1/F2 spec 위상**: ad-hoc 진단용 (mark DOM 존재 여부, 구조 smoke test).
**F3 spec 위상**: 정식 회귀 안전망 (wrap 위치 실질 검증).

#### 핵심 변경: assertion 강화

| 항목 | F1/F2 (이전) | F3 (강화) |
|---|---|---|
| C1 | `toContain("eliminating")` | 첫 줄 텍스트가 "These" 로 시작 + "eliminating" 포함 (두 렌더러 동일) |
| C2 | `typeof togetherY === "number"` (타입만) | `getWordLineNumber()` — 줄 번호 직접 비교 `expect(editorLineNum).toBe(serverLineNum)` |
| C3 | `toContain("Currently")` | `isWordOnFirstLine()` → `expect(onFirstLine).toBe(true)` + 줄 번호 = 0 단언 |

#### 추가된 헬퍼 함수

```typescript
// 단어가 몇 번째 줄(0-indexed)에 있는지 반환
async function getWordLineNumber(locator, word): Promise<number | null>

// 단어가 첫 번째 줄에 있는지 확인
async function isWordOnFirstLine(locator, word): Promise<boolean>
```

**측정 방식**: `getBoundingClientRect` + computed `line-height` → `(타겟 Y - 기준 Y) / lineH` 로 줄 번호 계산. 절대 Y 픽셀이 아니라 *상대 줄 번호*로 비교 — 두 페이지의 뷰포트 위치 차이를 제거.

#### 전역 assertion (F1-b 중요 항목 통합)

- C1/C2/C3/zero-waste 모두 `[data-error='true']` 없음
- zero-waste 7 단락 → 7개 `<p>` 태그
- C3: `data-bracket-style='{}'` 텍스트 = `"70 zero-waste stores in Seoul"` (정확 일치)
- C2: `data-top-label-text='주어'` 텍스트 = `"seller and buyer"` (정확 일치)

#### 메모리 함정 호환성 (feedback_pdf_annotation_visual.md)

PR #82 에서 고정된 5건 (highlight 다중 layer / 12색 정합 / 모서리 굴곡 / 라벨 검정 / paragraph 분리) — 본 spec 은 CSS/렌더링 영역을 건드리지 않으므로 충돌 없음.

---

## 2. F3-b: annotation_html.py 폐기 결정

### 현황

`packages/template_renderer/src/template_renderer/annotation_html.py`:
- Stage F2 (PR #90) 에서 deprecated 주석 추가.
- `LEGACY_ANNOTATION_RENDERER=true` 환경변수로만 활성화 (기본 비활성).
- 관련 테스트: `apps/api/tests/test_routers/test_worksheets_router.py` 에 53건 포함
  (Python 테스트 총 243건 중).

### 옵션 평가

| 옵션 | 장점 | 단점 |
|---|---|---|
| **(a) 즉시 폐기** | 코드 베이스 단순화, 53건 테스트 제거 | 와이프 검수(F4) 통과 전 fallback 소멸 — 예상 못한 Node.js 문제 시 복구 불가 |
| **(b) Phase 2.5 완전 종료 후 별 PR 폐기** | F4 검수 중 Node.js 장애 시 `LEGACY_ANNOTATION_RENDERER=true` 복구 가능 | 코드 deferred debt |

### 결정: **(b) 유지 (안전망)** — 권장

**사유**:
1. **Phase 2.5 완전 종료 전 폐기는 조기**: Stage F4 (와이프 검수)에서 실제 production 지문으로
   server-side Tiptap 경로를 검증하기 전까지는 legacy fallback 을 보존하는 것이 맞다.
2. **비용 낮음**: deprecated 주석이 이미 달려 있고, `LEGACY_ANNOTATION_RENDERER=false` 가
   기본값이므로 프로덕션 경로에서는 완전히 비활성화 상태.
3. **53건 테스트 유지 가치**: legacy 호환 검증 — F4 이후 별 PR 에서 일괄 제거가 깔끔.

**후속 action**:
- F4 와이프 검수 OK 후 **별 PR** 에서 폐기:
  - `annotation_html.py` 파일 삭제
  - `LEGACY_ANNOTATION_RENDERER` 관련 env var / config 제거
  - 53건 legacy 테스트 제거
  - `adapters.py` 의 `annotation_renderer` 파라미터 cleanup

---

## 3. F3-c: Dockerfile / 운영 환경

### 현황 확인

현재 `apps/api/Dockerfile`:
- Python 3.12-slim 기반, `uv` 의존성 설치.
- Node.js **없음** — Stage F2 이후 production 배포 시 Node.js + `apps/render` 가 필요.

현재 `docker-compose.yml`:
- `db` (PostgreSQL) + `api` (FastAPI) 두 서비스만.
- `apps/render` 별도 서비스 없음 (local dev 가정).

### Stage F2 이후 필요 변경 (Stage F2 보고서 §4 참조)

```dockerfile
# apps/api/Dockerfile 에 추가 필요 (Node.js + apps/render 의존성)
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# pnpm 설치 (Node.js 의존성 관리)
RUN npm install -g pnpm

# apps/render 의존성 파일 복사 + 설치
COPY pnpm-workspace.yaml .
COPY apps/render/package.json apps/render/
COPY packages/editor/package.json packages/editor/
RUN pnpm install --filter @english-worksheet-tool/render --frozen-lockfile

# packages/editor TypeScript source (jiti 가 런타임 resolve)
COPY packages/editor/ packages/editor/
```

### 결정: 별 PR 에서 Dockerfile 업데이트

**사유**:
1. Dockerfile 변경은 운영 영향이 크다 — 본 F3 cleanup PR 에 함께 넣으면 리뷰 범위 과다.
2. 현재 local dev 는 Node.js + `pnpm install` 이 완료된 환경에서 `subprocess` 가 동작.
3. production 배포 전(Phase 4)에 Dockerfile 을 정비할 시간이 있다.

**권장 action (별 PR)**:
- `apps/api/Dockerfile` — Node.js + pnpm + apps/render 설치 단계 추가.
- `docker-compose.yml` 환경변수 확인 (`NODE_BIN`, `JITI_BIN`, `SERVER_RENDERER_PATH`).
- CI 에서 Dockerfile build test 추가.

---

## 4. F3-d: CLAUDE.md §2.2 갱신

CLAUDE.md 변경이력 `v0.13` 추가 — Phase 2.5 F1/F2/F3 종료 표기 + F4 와이프 검수 진입 신호.

---

## 5. F4 (와이프 검수) 진입 준비

### F4 진입 조건

| 항목 | 상태 |
|---|---|
| F1: server-side Tiptap PoC | [x] 완료 (PR #89) |
| F2: 라우트 통합 (Python subprocess) | [x] 완료 (PR #90) |
| F3: 회귀 spec 강화 + cleanup | [x] 완료 (이 PR) |
| annotation_html.py fallback 보존 | [x] `LEGACY_ANNOTATION_RENDERER=false` 기본 |

### 검수 시나리오

**와이프 검수 대상**: 실제 사용 지문 (아잉카 or 수능 기출) 으로 `GET /worksheets/{id}/preview` 와 `POST /worksheets/{id}/export.pdf` 호출.

1. **에디터 annotation 작업** → 구문분석 에디터에서 top_label / bracket / highlight 마크 추가.
2. **Preview 확인** — 에디터 wrap 위치와 preview iframe wrap 위치가 시각적으로 일치하는지.
3. **PDF export** — Chromium PDF 출력 결과 및 annotation span 위치 검수.

### 핵심 검증 항목 (F4 검수표)

| # | 항목 | 기준 |
|---|---|---|
| 1 | 에디터 ↔ preview wrap 위치 | 같은 단어가 같은 줄에 있어야 (시각 확인) |
| 2 | top_label 라벨 텍스트 | 라벨 문자열이 올바른 span 위에 표시 |
| 3 | bracket `()` / `{}` / `[]` | 해당 span 에 정확히 감쌈 |
| 4 | highlight 색상 | 12색 정합 (PR #82 기준) |
| 5 | PDF 페이지 분할 | 박스 한계선 footer 위 11mm 분할 정상 |
| 6 | Node.js subprocess 오류 없음 | 서버 로그에 RuntimeError 없음 |

### 장애 시 fallback

```bash
# Node.js subprocess 장애 시 annotation_html.py 로 즉시 복구
LEGACY_ANNOTATION_RENDERER=true uvicorn worksheet_api.main:app ...
```

---

## 6. 테스트 결과 요약

### Playwright E2E (F3-a)

- `wrap_parity_stage_f3.spec.ts`: **신규** (F4 시 dev server 기동 후 실행 필요)
- `wrap_parity_stage_f1.spec.ts`: F1 진단 spec 유지
- `wrap_parity_stage_f2.spec.ts`: F2 mark DOM 정합 spec 유지
- `wrap_parity.spec.ts`: Coffee fixture 기반 (DB seed 필요)

### Python 테스트 (F2 기준 유지)

- `apps/api`: 243 passed
- `packages/template_renderer`: 53 passed (legacy annotation_html.py 테스트 유지)

### Node.js 테스트

- `apps/render`: 27 passed (F1 호환성 테스트)

---

## 7. Phase 2.5 Stage 진행 현황

| Stage | 내용 | 상태 |
|---|---|---|
| F1 | server-side Tiptap PoC (generateHTML + ProseMirror View) | [x] 완료 (PR #89) |
| F2 | Python subprocess → Node.js CLI 라우트 통합 | [x] 완료 (PR #90) |
| F3 | 회귀 spec 활성화 + cleanup | [x] 완료 (이 PR) |
| F4 | 와이프 검수 (실제 지문 + PDF 퀄리티) | [ ] 대기 |
