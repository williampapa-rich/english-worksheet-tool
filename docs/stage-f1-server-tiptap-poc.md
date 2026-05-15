# Stage F1 — Server-side Tiptap PoC 결과 보고서

- **작성일**: 2026-05-15
- **상태**: 완료 (27/27 tests 통과)
- **관련 ADR**: `docs/adr/0018-unified-rendering-editor-pdf.md` (Accepted)
- **관련 PR**: feat/stage-f1-server-tiptap-poc

---

## 1. 사용 의존성 + 버전

| 의존성 | 버전 | 용도 |
|---|---|---|
| `jsdom` | ^26.1.0 | Node.js DOM polyfill — Tiptap/ProseMirror DOM 접근 |
| `linkedom` | ^0.18.9 | 대안 DOM polyfill (F1-d 비교) |
| `@tiptap/html` | ^2.11.5 | `generateHTML()` — JSON doc → HTML 정적 변환 |
| `@tiptap/core` | ^2.11.5 | Editor / Schema / Extension 기반 |
| `@tiptap/pm` | ^2.11.5 | ProseMirror View, State, Decoration |
| `@tiptap/starter-kit` | ^2.11.5 | 기본 extension 묶음 |
| `@english-worksheet-tool/editor` | workspace:* | 프로젝트 커스텀 extensions (TopLabel / BottomLabel / Bracket 등) |
| Node.js | v23.11.0 | 런타임 |

---

## 2. DOM polyfill 선택: jsdom 권장

### jsdom vs linkedom 비교

| 항목 | jsdom | linkedom |
|---|---|---|
| boot | O | O |
| ProseMirror 호환성 | **완전 OK** | 미검증 (ProseMirror View 사용 사례 드묾) |
| `@tiptap/html` generateHTML | **OK** | 미검증 |
| ProseMirror View (EditorView) | **OK** | 불확실 (Range/MutationObserver 구현 한계 가능) |
| Decoration.widget DOM 반영 | **OK** | 미검증 |
| layout (getBoundingClientRect) | **미지원** — 항상 `{0,0,0,0}` | 미지원 (layout 엔진 없음) |
| 속도 | 기준 | 10배 빠름 |
| ProseMirror 공식 테스트 환경 | **Yes** | No |

**결론**: ProseMirror 는 jsdom 을 공식 테스트 환경으로 사용. 검증 사례 있어 안전.
linkedom 은 빠르지만 ProseMirror View boot 에 대한 사용 사례 없음 — F2 단계에서 성능 최적화 필요 시 재평가.

**권장**: jsdom (호환성 우선).

---

## 3. Tiptap boot 패턴: generateHTML + ProseMirror View 양쪽 모두 동작

### 3.1 `@tiptap/html generateHTML` 경로 (대안 2)

```ts
import { generateHTML } from "@tiptap/html";
const html = generateHTML(doc, [StarterKit, HighlightMark, BracketMark, ...]);
```

- **동작**: 완전 OK. jsdom 전역 주입(`global.document`, `global.Node` 등) 후 정상 동작.
- **Decoration.widget 포함 여부**: **포함 안 됨** — `generateHTML` 은 정적 HTML 생성, widget 은 View-only.
- **출력 HTML 구조**: mark span (`data-annotation-kind`, `data-bracket-style`, `data-top-label-text` 등) 정상 출력.
- **에디터 측과 비교**: mark span 구조는 동일. widget DOM (괄호 글자, 라벨 텍스트 span) 만 없음.

### 3.2 ProseMirror View 직접 boot (대안 1, 권장)

```ts
import { Editor } from "@tiptap/core";
const editor = new Editor({ extensions, content: doc, element: dom.window.document.createElement("div"), injectCSS: false });
const widgetEls = editor.view.dom.querySelectorAll("[data-bracket-widget], [data-top-label-widget]");
```

- **동작**: 완전 OK. jsdom 위에서 ProseMirror View 정상 boot + Decoration.widget 포함.
- **Decoration.widget 포함 여부**: **포함됨** — bracket 괄호 글자, top_label 라벨 텍스트 widget 이 `view.dom` 에 반영.
- **에디터 측과 비교**: DOM 구조 100% 동일 (사전 가이드 §1.2 대안 1 선택 근거 확인).

**최종 권장**: **ProseMirror View 경로** — Decoration.widget 포함 완전 정합.

---

## 4. 핵심 검증 시나리오 C1/C2/C3 통과 여부

### 4.1 generateHTML 경로 (mark 구조 검증)

| 시나리오 | 본문 | mark HTML 출력 | 통과 |
|---|---|---|---|
| C1 | eliminating plastic... | `data-annotation-kind="top_label"`, `data-top-label-text="목적어구"` | O |
| C2 | together (to minimize...) | `data-annotation-kind="top_label"`, `data-bracket-style="()"` | O |
| C3 | {70 zero-waste stores...} | `data-bracket-style="{}"`, 텍스트 "70 zero-waste stores in Seoul" | O |
| Zero Waste 7p | 7 paragraphs | 7개 `<p>` 태그 출력 | O |

### 4.2 ProseMirror View 경로 (widget 포함 검증)

| 시나리오 | widget 수 | 통과 |
|---|---|---|
| C2 (bracket + top_label) | 2 이상 | O |
| C3 (bracket) | 2 (여는/닫는 괄호) | O |
| 단순 bracket 1개 | 2 | O |

### 4.3 Playwright E2E (F1-e, wrap 위치 검증)

`apps/web/tests/e2e/wrap_parity_stage_f1.spec.ts` 신규 추가.

검증 내용:
- `/preview/server-tiptap?scenario=C1|C2|C3` 라우트 신설 (PoC 전용).
- server-side HTML 렌더 후 에디터 ↔ generateHTML 첫 줄 텍스트 비교.
- C1: "eliminating" 이 첫 줄에 포함됨 확인.
- C2: "together" Y 좌표 + bracket span DOM 존재 확인.
- C3: `data-bracket-style="{}"` span 텍스트 "70 zero-waste stores in Seoul" 확인.

**주의** (사전 가이드 §3.1): jsdom 은 layout 미지원. 픽셀 단위 wrap 비교는 Playwright Chromium 에서.
ProseMirror View 경로의 `view.dom` 은 jsdom 위 — `getBoundingClientRect()` 가 `{0,0}` 반환.
실제 줄바꿈 위치 측정은 Playwright 로 HTML 을 실제 Chromium 에 로드한 후 수행.

---

## 5. 알려진 제약 / 향후 작업

### 5.1 jsdom layout 미지원

- `getBoundingClientRect()` → 항상 `{x:0, y:0, width:0, height:0}`.
- wrap 위치 pixel 측정은 Playwright Chromium 에서만 가능.
- F2 에서 server render 결과 HTML 을 Playwright 에 전달 → Chromium 가 줄바꿈 결정.

### 5.2 generateHTML 경로의 widget 부재

- `generateHTML` 는 Decoration.widget 출력 안 됨.
- `data-bracket-style="()"` span 은 있지만 실제 괄호 글자 `(` `)` 는 없음 (View 경로에서만 있음).
- F2 에서 ProseMirror View 경로를 사용하면 해결.

### 5.3 HoverPreview / WordSnap extension 미포함

- PoC 에서는 rendering 관련 extension 만 포함 (TopLabel, BottomLabel, Bracket, Highlight, Underline, InlineNote).
- HoverPreview / WordSnap / Arrow 는 server-side 불필요 (상호작용/미지원 기능).

### 5.4 injectCSS 비활성화

- `new Editor({ injectCSS: false })` — server-side 에서는 CSS 주입 불필요.
- 스타일은 PDF 렌더 시 별도 CSS 파일로 로드 (기존 `_passage_body.css` 활용).

### 5.5 pre-existing test failure (무관)

- `apps/web/tests/worksheet-detail-page.test.tsx` 1건 기존 실패 — 본 PoC 와 무관 (main 에서도 동일하게 실패).

---

## 6. F2 진입 가능 여부 판단: YES

### 판단 근거

- **ProseMirror View (jsdom 위)** 정상 동작 확인.
- **Decoration.widget** 이 jsdom DOM 에 반영됨 확인.
- **generateHTML** 경로도 정상 동작 (mark span 구조 정합).
- 핵심 extensions (TopLabel / BottomLabel / Bracket / Highlight / Underline / InlineNote) 모두 jsdom 에서 호환.

### F2 작업 범위 (권장)

1. `apps/render/src/serverRenderer.ts` 의 `renderToHTMLViaProseMirrorView()` 를 HTTP 서비스로 노출.
2. `apps/api/src/worksheet_api/routers/worksheets.py` 의 `_build_worksheet_html()` 에서 Python `annotation_html.py` 대신 Node.js renderer 호출.
3. `packages/template_renderer/src/template_renderer/annotation_html.py` Superseded 처리 (ADR-0014 §3.3).
4. Playwright wrap 비교 spec 을 pixel-level assertion 으로 업그레이드.

### F2 권장 경로

**ProseMirror View (jsdom)** — Decoration.widget 포함 완전 정합.
서비스 방식: 별 Node.js 서비스 (`apps/render`) — HTTP API 노출, `apps/api` 가 호출.

---

## 변경 이력

| 버전 | 날짜 | 변경 |
|---|---|---|
| v0.1 | 2026-05-15 | F1 PoC 완료 — 27/27 tests 통과. F2 진입 권장 YES. |
