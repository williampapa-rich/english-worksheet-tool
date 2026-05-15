# Phase 2.5 Stage F1 — Server-side Tiptap PoC 사전 가이드

- **작성일**: 2026-05-15
- **상태**: Prep (PoC 시작 전 사전 조사 + 환경 셋업 가이드)
- **관련 ADR**: `docs/adr/0018-unified-rendering-editor-pdf.md` §Stage F1 (Accepted, 2026-05-15)
- **목표**: PoC 시작 시 환경 셋업 / 의존성 / 검증 시나리오를 단번에 따라갈 수 있게 정리. **코드 변경 0** — 본 문서는 가이드.

---

## 0. 본 문서의 위치

ADR-0018 §Stage F1 (1주) 의 *실행 가이드*. F1-a ~ F1-d 각 작업 별 사전 조사 결과 + 권장 선택 + 알려진 함정. PoC 시작 시 본 문서 + ADR-0018 본문 + 메모리 `feedback_pdf_annotation_visual.md` / `feedback_playwright_measure_first.md` 를 함께 읽고 진행.

---

## 1. 의존성 후보 비교

### 1.1 DOM polyfill 라이브러리 (Node.js 환경)

Tiptap (ProseMirror) 은 `document` / `Range` / `Selection` 등 브라우저 DOM API 에 의존. Node.js 에는 없으므로 polyfill 필요.

| 옵션 | 장점 | 단점 | Tiptap 호환성 |
|---|---|---|---|
| **jsdom** | 가장 완성도 높음 + npm 표준 + 다양한 Tiptap PoC 사례 | 느림 (실제 브라우저 대비 10~50배), 메모리 큼 | ProseMirror 공식 테스트가 jsdom 사용 → 호환 OK |
| **linkedom** | 빠름 (jsdom 대비 10배) + lightweight | 일부 API 미구현 가능성 (Range / MutationObserver 등) | ProseMirror 사용 사례 적음 — F1-d 에서 검증 |
| **happy-dom** | 빠름 + Vitest 표준 | jsdom 대비 호환성 낮음 | ProseMirror 호환 미검증 |

**권장 (F1-a)**: **jsdom** 먼저 시도. 호환성 우선 — 동작 확인 후 F1-d 에서 linkedom 대안 평가.

### 1.2 Tiptap server-side rendering 패턴

Tiptap 공식 가이드 — `@tiptap/html` (server-side static rendering 패키지):

- `generateHTML(content, extensions)` — JSON content + extension list → HTML 문자열.
- `generateJSON(html, extensions)` — 반대 방향.
- DOM 환경 필요 (`@tiptap/core` 의 Schema 구성). jsdom + `global.document` 주입 패턴.

**다만 Decoration.widget 은 generateHTML 에 미포함** — ProseMirror View 의 dynamic decoration 영역이라 정적 HTML 출력에 빠짐. PoC 의 핵심 결정 항목.

**대안 1**: `@tiptap/html` 폐기 + 직접 ProseMirror View 를 Node.js 에서 띄워서 DOM 채택 (브라우저와 동일 코드 경로).
- 장점: 100% 정합 (브라우저와 같은 View).
- 단점: jsdom 위에서 ProseMirror View 가 안정 동작하는지 검증 필요. View 는 마우스 / 키보드 이벤트 / focus 등도 처리 — 그 부분 unused 라도 boot 시 호환성 영향 가능.

**대안 2**: Decoration.widget 을 static HTML 로 *직접* emit — `@tiptap/html` 결과에 widget DOM 을 manual injection.
- 장점: 가볍게 시작 가능.
- 단점: widget 위치 계산 (mark range → char offset) 을 server 에서 다시 구현 — 결국 `annotation_html.py` 와 같은 길.

**권장 (F1-a/b)**: **대안 1** (ProseMirror View 띄우기). ADR-0018 옵션 (a) 의 정합 100% 약속을 지키려면 동일 View 가 답. jsdom 호환성은 F1-d 에서 측정.

### 1.3 Node.js 통합 위치

server-side Tiptap 을 어디서 호출?

| 옵션 | 장점 | 단점 |
|---|---|---|
| **별 Node 서비스** (`apps/render`?) | Python (`apps/api`) 와 분리 → 안정 / 배포 격리 | 인프라 추가 (Docker 컨테이너 1개 더) + 라우트 간 HTTP RTT |
| **`apps/web` 서버 (Vite SSR / Express)** | 이미 Node.js — 인프라 0 추가 | Vite SSR 은 dev / prod 다름. preview 라우트 = 서버 측 렌더 호출 vs PDF export = `apps/api` 가 호출 — 양쪽 패턴 다름 |
| **`apps/api` Python 에서 Node subprocess** | API 가 진입점 1곳 | subprocess 오버헤드 (boot 시간) + 에러 처리 복잡 |

**권장 (F1-a 진입 시 PM 결정)**: **별 Node 서비스 (`apps/render` 신규)** — Phase 4 (클라우드 배포) 정합. 단 PoC 단계에서는 *직접 호출* (Python 안 subprocess) 로 시작 → F2 에서 서비스화 결정.

---

## 2. 핵심 검증 시나리오

### 2.1 와이프 v0.2 검수에서 발견된 wrap 어긋남 케이스

PoC 가 *반드시* 통과해야 하는 시나리오 — 모두 와이프 v0.2 검수 (2026-05-10 ~ 2026-05-15) 에서 측정 확정.

| 케이스 | 본문 | 현 PDF 결과 | 목표 |
|---|---|---|---|
| C1 | `These supermarkets and grocery stores attempt to prevent waste by eliminating plastic packages altogether.` | `eliminating plastic` 같은 줄 | `eliminating` 다음 줄바꿈 (에디터와 동일) |
| C2 | `both seller and buyer work together (to minimize the negative impact on the environment.)` (라벨 + bracket) | `together (` 같은 줄 또는 통째 한 줄 | `together` / `(to minimize ... on the` / `environment.)` 3 줄 (에디터와 동일) |
| C3 | `Currently, there are more than {70 zero-waste stores in Seoul}.` | 동일 | 동일 (이미 OK) |

### 2.2 회귀 검증 spec

PoC 결과를 Playwright 측정 spec 으로 확정. 위치 — `apps/web/tests/e2e/wrap_parity_zero_waste.spec.ts` 같은 fixture 기반 + assertion 추가 (검수 중 임시 spec 은 dump 만 했으나 본 PoC 종료 시 byte-level 비교):

```ts
test("C1 — eliminating plastic 같은 줄 위치 정합", async ({ page }) => {
  // 에디터 'plastic' rect.y 와 PDF 'plastic' rect.y 가 *같은 줄* 차이 (line-height 이내)
  expect(editorY).toBeCloseTo(pdfY, lineHeightTolerance);
});
```

### 2.3 fixture worksheet (살아있음)

- worksheet `74c1a9e0-f973-495c-b1d6-09c33ba194a1` ("Zero waste")
- passage `104309e6-b77c-4945-a7a6-95d0ca8f9e50` (7 paragraphs, annotation 11)
- DB 가 사라지면 재셋업 — `docs/phase-2-edit-wife-review-prep.md` §3.1 가이드 따라.

---

## 3. 함정 / 알려진 제약

### 3.1 jsdom 의 layout 미지원

jsdom 은 **layout 엔진 없음** — `getBoundingClientRect()` 가 항상 `{x:0, y:0, width:0, height:0}` 반환. wrap 위치 계산은 *브라우저에서만* 가능. PoC 검증 시:

- server-side 출력 = **HTML 문자열** 만 비교 (브라우저 측 출력 HTML 과 byte-by-byte). DOM 트리 정합.
- wrap 위치 측정 = **여전히 Playwright** (실제 Chromium). server-side HTML 을 Playwright 가 받아서 render 후 측정.

즉 PoC 의 출력은 "server 가 만든 HTML 이 *브라우저 측 Tiptap 이 만들 HTML* 과 동일한가" 의 검증. wrap 자체는 Playwright Chromium 이 두 HTML 받아서 동일 결과 그려야.

### 3.2 메모리 함정 (feedback_pdf_annotation_visual.md)

PoC 진행 중 절대 변경 금지 영역:
- `.annot-top-label / .annot-bottom-label` `display: inline-block`
- borderline `::before { top: 15px }` / `bottom: 15px`
- 라벨 텍스트 `::after` `bottom: calc(100% - 15px + 2px)`
- 12색 팔레트 (`feedback_pdf_annotation_visual.md` 4번 정책)
- `line-height: 3.4` (PDF) / `2.78` (에디터)
- 라벨 글씨 `color: #000`

PoC 결과 HTML 이 위 CSS 와 *호환* 되도록 출력. annotation 영역 fix (PR #82) 의 5건 모두 보존.

### 3.3 ADR-0014 Superseded 처리

PoC 성공 시 (F2 에서) `packages/template_renderer/src/template_renderer/annotation_html.py` 폐기. 단 PoC 단계에서는 *병행* — 기존 annotation_html.py 동작 그대로 유지하고 server-side Tiptap 출력을 *별 경로* 로 띄움.

### 3.4 hwpx_renderer 와의 정합

ADR-0014 의 단일 source-of-truth 정책 — `annotation_html.py` 와 `hwpx_renderer` 가 대칭 구조였음. server-side Tiptap 도입 시 `hwpx_renderer` 는 어떻게 되나?

- HWPX 출력은 ADR-0008 에서 폐기 (Phase 1 baseline 결정). 코드는 남아있지만 *비활성*.
- Phase 2.5 sprint 에서 hwpx_renderer 추가 작업 X — 별 Phase / 정리 작업.

---

## 4. PoC 산출물 체크리스트

Stage F1 종료 시 다음이 모두 있어야:

- [ ] `apps/render/` (또는 inline) — Node.js + jsdom + Tiptap PoC 스크립트
- [ ] PoC 입력 — `Passage + SyntaxAnnotation[]` JSON fixture
- [ ] PoC 출력 — HTML 문자열 (annotation 적용)
- [ ] Playwright 검증 — server-side HTML 을 받아서 render → 에디터 측 출력과 wrap 정합 (C1 / C2 / C3 모두 통과)
- [ ] `docs/stage-f1-server-tiptap-poc.md` 결과 보고서:
  - 사용 의존성 + 버전
  - DOM polyfill 선택 (jsdom vs linkedom 측정 비교)
  - Tiptap boot 패턴 (`@tiptap/html` vs ProseMirror View)
  - 알려진 제약 / 향후 작업
  - F2 (실제 라우트 통합) 진입 가능 여부 판단

---

## 5. F2 진입 트리거

Stage F1 종료 후 본 단계 자동 진입:

- F2 = `annotation_html.py` 폐기 → 새 라이브러리로 worksheet preview / PDF export 라우트 교체
- 영향 범위 — `apps/api/src/worksheet_api/routers/worksheets.py` 의 `_build_worksheet_html()` + `packages/template_renderer/` 의 사용처
- 회귀 — `packages/template_renderer/tests/test_annotation_html.py` 53건 → 새 라이브러리의 회귀 spec 으로 이관

---

## 6. 후속 / 의존성

- **schema v0.2 PR (backend-dev 진행 중)** — ADR-0016 / ADR-0017 schema 변경. 본 sprint 와 *영역 분리* — schema 는 데이터 모델, 본 sprint 는 렌더. 병렬 가능.
- **CLAUDE.md §2.2** — Phase 2.5 진입 신호 (이미 v0.12 반영). PoC 시작 시 Stage F1 in-progress 추가 갱신.
- **메모리** — `project_current_session.md` 갱신 시점 = PoC 시작.

## 변경 이력

| 버전 | 날짜 | 변경 |
| --- | --- | --- |
| v0.1 | 2026-05-15 | 초안 — ADR-0018 Accepted 후 Stage F1 진입 가이드 사전 작성. PoC 시작 시 본 문서 따라가서 PR 단위로 진행. |
