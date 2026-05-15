# Stage F2 — Route Integration 진행 보고서

**날짜**: 2026-05-15
**브랜치**: `feat/stage-f2-route-integration`
**ADR**: ADR-0018 Stage F2

---

## 1. 채택 통합 방식: subprocess (jiti)

### 결정

Python (`apps/api`) → Node.js (`apps/render/src/bin.ts`) 호출 방식으로 **subprocess** 채택.

### 대안 검토

| 방식 | 장점 | 단점 |
|---|---|---|
| **subprocess (채택)** | 배포 복잡도 최소, 별 서비스 불필요, Dockerfile 단순 | 매 호출 Node.js 콜드 스타트 ~200ms |
| HTTP 마이크로서비스 | RTT 10~50ms, 프로세스 재사용 | 별 서비스 관리, health check, restart policy 필요 |
| Python ↔ Node IPC | 가장 빠름 | 구현 복잡, 비표준, 유지보수 부담 |

**subprocess 채택 이유**:
- Phase 2.5 트래픽 규모에서 ~200ms overhead 는 허용 범위 (preview 총 응답 ~500ms).
- PDF export 는 이미 Playwright launch가 수 초 → subprocess overhead 비중 미미.
- HTTP 서비스 전환 시 Python wrapper (`server_renderer.py`) 만 교체하면 됨 (인터페이스 고정).

### jiti 선택 이유

`@english-worksheet-tool/editor` 패키지가 TypeScript source를 `exports` (`"./src/index.ts"`)하므로 `node dist/bin.js` 실행 시 resolve 실패. 두 가지 해결책 평가:

- **jiti** (채택): workspace TypeScript source 런타임 트랜스파일. 별도 빌드 단계 불필요. `apps/render/node_modules/.bin/jiti` 에 존재 (vitest devDependency 연쇄).
- **vite build --ssr** (미채택): `@english-worksheet-tool/editor` 를 포함한 번들 생성 가능하나, vite 가 devDependency 라 `.vite-temp` 에서 resolve 실패 문제 발생. 추가 설정 필요.

---

## 2. 변경 파일 목록

### 신규

| 파일 | 설명 |
|---|---|
| `apps/render/src/bin.ts` | CLI 진입점 — stdin JSON → ProseMirror View HTML → stdout |
| `apps/render/tsconfig.build.json` | emit 가능 tsconfig (noEmit false) |
| `apps/api/src/worksheet_api/integrations/__init__.py` | 패키지 초기화 |
| `apps/api/src/worksheet_api/integrations/server_renderer.py` | Python subprocess wrapper |
| `apps/web/tests/e2e/wrap_parity_stage_f2.spec.ts` | F2-e 회귀 spec |
| `docs/stage-f2-route-integration.md` | 이 보고서 |

### 수정

| 파일 | 변경 내용 |
|---|---|
| `apps/render/package.json` | `build:cli` 스크립트 추가 |
| `apps/api/src/worksheet_api/config.py` | `node_bin`, `jiti_bin`, `server_renderer_path`, `legacy_annotation_renderer`, `server_renderer_timeout` 필드 추가 |
| `packages/template_renderer/src/template_renderer/adapters.py` | `annotation_renderer` 콜백 파라미터 추가 |
| `apps/api/src/worksheet_api/routers/worksheets.py` | `render_annotations_html_via_node` import + `_build_worksheet_html` 에 `annotation_renderer` 주입 |
| `packages/template_renderer/src/template_renderer/annotation_html.py` | deprecated 주석 추가 |
| `apps/web/src/pages/ServerTiptapPreview.tsx` | `zero-waste` scenario + `Scenario` 타입 확장 |
| `apps/api/tests/test_routers/test_worksheets_router.py` | `test_preview_worksheet_xss_escape` — `paragraphs` 도 malicious 로 업데이트 (pre-existing 버그 fix) |

---

## 3. Python subprocess 흐름

```
GET /worksheets/{id}/preview
  → _build_worksheet_html()
    → worksheet_to_template_context(
        ...,
        annotation_renderer=render_annotations_html_via_node
      )
      → _ann_renderer(passage, anns)
        → render_annotations_html_via_node(passage, annotations)
          → subprocess.run([jiti, src/bin.ts], input=JSON)
            → bin.ts: renderToHTMLViaProseMirrorView()
              → ProseMirror View boot (jsdom)
              → view.dom.innerHTML 출력
          ← HTML string
      ← content_html
    ← template context
  → render_worksheet_html(context, style="playful")
  ← HTML response
```

### Feature flag

`LEGACY_ANNOTATION_RENDERER=true` 환경변수로 `annotation_html.py` fallback 활성화. 기본값 `false`.

---

## 4. production 환경 셋업 가이드

### Node.js 의존성

`apps/render` 의 `node_modules` 가 설치돼 있어야 합니다:

```bash
pnpm install --filter @english-worksheet-tool/render
```

Python API 컨테이너에서 Node.js 와 `apps/render/node_modules` 에 접근 가능해야 합니다.

### Dockerfile 영향

현재 `apps/api` 만 배포하는 경우, Dockerfile 에 다음 추가 필요:

```dockerfile
# Node.js 설치
RUN apt-get install -y nodejs

# apps/render 의존성 설치
COPY apps/render/package.json apps/render/
COPY pnpm-workspace.yaml .
RUN pnpm install --filter @english-worksheet-tool/render --frozen-lockfile

# packages/editor TypeScript source (jiti가 런타임에 resolve)
COPY packages/editor/ packages/editor/
```

### 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `NODE_BIN` | `node` | node 바이너리 경로 |
| `JITI_BIN` | `apps/render/node_modules/.bin/jiti` | jiti 실행기 경로 |
| `SERVER_RENDERER_PATH` | `apps/render/src/bin.ts` | bin.ts 경로 |
| `LEGACY_ANNOTATION_RENDERER` | `false` | `true` 이면 annotation_html.py fallback |
| `SERVER_RENDERER_TIMEOUT` | `30` | subprocess 타임아웃 (초) |

---

## 5. 응답 시간 변화

| 경로 | 이전 (annotation_html.py) | F2 후 (jiti subprocess) | 비고 |
|---|---|---|---|
| `GET /preview` | ~50ms | ~250ms | Node.js + jsdom + Tiptap 콜드 스타트 |
| `POST /export.pdf` | Playwright 지배적 (~3s) | ~+200ms | overhead 비율 < 7% |

preview 라우트 응답 시간 증가 (~200ms)는 MVP 단계에서 허용 범위. 트래픽 증가 시 HTTP 마이크로서비스 전환 권장.

---

## 6. 알려진 제약 / fallback 정책

1. **jiti 미설치 시**: `server_renderer.py` 가 `node` 직접 호출로 fallback. `dist/bin.js` (tsc build) 가 없으면 `RuntimeError`.
2. **Node.js 미설치 시**: `FileNotFoundError` → `RuntimeError`. `LEGACY_ANNOTATION_RENDERER=true` 로 annotation_html.py 경로 유지 가능.
3. **subprocess 타임아웃**: 기본 30초. 비정상 종료 시 `RuntimeError` → HTTP 500.
4. **annotation 없는 passage**: `if anns:` 분기 — Node.js 미호출, escape() 경로 유지.
5. **deprecation 미제거**: `annotation_html.py` 본체 유지 (legacy fallback + 53개 테스트).

---

## 7. 회귀 spec 결과 (C1/C2/C3)

### Python 테스트

- `apps/api`: 243 passed
- `packages/template_renderer`: 53 passed (legacy annotation_html.py 테스트 유지)

### Node.js 테스트

- `apps/render`: 27 passed (F1 호환성 테스트)

### F2-e spec

`apps/web/tests/e2e/wrap_parity_stage_f2.spec.ts` 추가 — C1/C2/C3 annotation mark 구조 + Zero Waste 7 단락 분리 검증 (Playwright E2E, frontend dev server 필요).

---

## 8. F3 (실제 검수) 진입 권장

**권장**: F3 진입 가능.

조건 충족:
- [x] Python subprocess → Node.js CLI 동작 확인 (smoke test)
- [x] ProseMirror View 경로 출력 (`<mark>`, `[data-annotation-kind]`, `[data-bracket-style]`)
- [x] 기존 Python 테스트 전부 통과 (243 + 53건)
- [x] LEGACY_ANNOTATION_RENDERER feature flag 준비
- [x] annotation_html.py legacy fallback 보존

진입 전 체크:
- [ ] 실제 와이프 fixture (`74c1a9e0-...`) preview 시각 검증 (F3 단계)
- [ ] production Dockerfile 업데이트 (Node.js + apps/render deps)
