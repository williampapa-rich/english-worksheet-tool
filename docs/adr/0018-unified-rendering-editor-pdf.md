# ADR 0018 — 에디터 ↔ PDF 본문 렌더링 통합 sprint 정의

- **상태(Status)**: Accepted
- **작성일**: 2026-05-15
- **결정일**: 2026-05-15 (PM Dennis — 옵션 (a) server-side Tiptap 채택. ADR-0014 → Superseded. Phase 2.5 자리 신설. Stage F1~F4 즉시 시작.)
- **작성자**: architect
- **결정자**: PM (Dennis)
- **유형**: Phase 2-edit baseline 마무리 중 발견된 *근본 결함* (에디터 ↔ PDF wrap
  어긋남) 해소 sprint 정의. 본 ADR 은 코드 변경 0 — 후속 sprint PR 들의 가이드.
- **범위**: 와이프 v0.2 통합 검수 중 발견된 *두 렌더 엔진의 DOM/wrap 처리 차이* 를
  해결하기 위한 옵션 4종 비교 + 권장안 + Stage 분해 + 비용 추정. 사용자 (PM Dennis)
  의 결정 "임시방편으로 이슈건들을 하드코딩하는건 안좋아. 근본적으로 에디터와 pdf
  프리뷰 페이지가 동일한 방식으로 렌더링되게해야 모든 케이스에 이슈가 없게 작동
  하지." (2026-05-15) 에 응한 sprint.
- **관련 문서**:
  - `CLAUDE.md` v0.10.1 §1.3 핵심 가치 명제 #3 — *"편집 가능한 출력: AI 가 만든
    결과는 항상 사용자가 검수/수정한 후 내보낸다 (자동 = 신뢰 부족 ≠ 완성)"*
  - `CLAUDE.md` v0.10.1 §3.5 (구문분석 에디터 — Tiptap), §3.6 (No Reinventing
    the Wheel)
  - `docs/adr/0008-phase-1-output-format.md` (HWPX → HTML/PDF 전환 — 본 sprint
    의 출발점. 두 렌더 엔진 분기의 근본 원인)
  - `docs/adr/0011-worksheet-html-pdf-pipeline.md` D2 (Playwright / Chromium),
    D6 (`content_html`), D8 (annotation 단순 wrap 한계 — 본 ADR 의 *전 단계*)
  - `docs/adr/0014-annotation-html-renderer.md` D1 (서버 단독 렌더 채택 C),
    D3 (매핑 single-source-of-truth — 본 ADR 이 *이 가정을 시험*),
    "Consequences §부정적 결과 #1" — *"에디터 ↔ 서버 매핑 규칙 동기화 부담"*
    이 본 ADR 의 직접 trigger
  - `docs/adr/0015-phase-2-edit-sprint.md` D5 (Tiptap 재사용 + prop 분기 — 본
    sprint 의 옵션 (b) 와 인접 영역)
  - `docs/annotation-hwpx-mapping.md` (P1-7 매핑 카탈로그 — HTML 측 매핑 표
    포함, 본 sprint 종료 시 *단일 렌더 라이브러리* 로 봉합 가능)
  - `packages/editor/src/extensions/{topLabel,bottomLabel,bracket}.ts` (Tiptap
    Decoration.widget 측 구현)
  - `packages/template_renderer/src/template_renderer/annotation_html.py`
    (서버 측 char-position 기반 inline span emit)
  - `packages/template_renderer/templates/_annotation.css` (3 템플릿 공유 CSS)
  - `apps/web/src/pages/EditorPoc.css` (에디터 측 CSS — 본문 폭/line-height/
    annotation 시각 설정)
  - `apps/web/tests/e2e/wrap_parity_*` (검수 중 작성된 측정 spec — 본 ADR 의
    근거 자료)
  - 메모리 `feedback_pdf_annotation_visual.md` (2026-05-08 확정 픽셀 값 — 본
    sprint 진행 시 보존 필수), `feedback_playwright_measure_first.md` (시각
    정합 작업 = 측정 우선 원칙)
- **선행 결정**:
  - ADR-0014 D1 "**서버 단독 렌더 채택 C**" 의 *"에디터와 매핑 규칙 동기화
    필요 (변경 시 양쪽 동시 수정)"* 라는 risk 가 v0.2 통합 검수에서 *현실화*. 본
    ADR 은 그 risk 를 sprint 로 해소.
  - ADR-0011 D8 의 *"annotation split-mark 정밀 렌더 ADR — Phase 2 본격 진입
    전 작성 필수"* 가 ADR-0014 로 닫혔지만, **두 렌더의 wrap 정합** 은 ADR-0014
    범위 밖이었음 (D8 은 *"보이지 않는다"* 가 risk, 본 ADR 은 *"보이지만 위치가
    다르다"* 가 risk).

---

## Context (배경)

### 1. 와이프 v0.2 통합 검수에서 발견된 wrap 어긋남 (2026-05-15)

ADR-0015 (Phase 2-edit sprint) 의 Stage E1/E2/E3 코드 완료 (PR #70~#74 open)
이후 와이프 v0.2 통합 검수 진행 중. 학생 자료 1건 (zero-waste fixture) 의
*에디터 화면* 과 *PDF 미리보기* 를 나란히 두고 비교한 결과, 동일 본문 + 동일
annotation 임에도 wrap 위치 / 라벨 box 폭이 어긋나는 케이스 다수 발견:

#### 케이스 (a) — bracket + 긴 라벨 (374px 라벨)

본문: `... eliminating plastic together (to minimize the negative impact on the environment).`

라벨: `(to minimize ... environment.)` 가 한 줄 폭 (626px) 보다 길어 wrap 필요.

| 엔진 | wrap 동작 |
|---|---|
| Tiptap 에디터 | 라벨 본문이 **글자 단위 wrap** — `together (to minimize the negative impact on the` (개행) `environment.)` |
| Chromium PDF | 라벨 inline-block 통째 wrap — `together` (개행) `(to minimize ... environment.)` 또는 통째 한 줄 |

#### 케이스 (b) — 일반 본문 wrap 위치 1~2 글자 차이

`eliminating plastic` 같은 일상 어휘에서도 같은 폭 (626px) 같은 폰트 (Pretendard
+ Noto Serif KR) 인데 line-break 위치가 1~2 글자 다름. PDF 가 한 줄에 한 단어 더
들어가거나 덜 들어가는 식.

**원인 식별** (`apps/web/tests/e2e/wrap_parity_diagnose*.spec.ts` 측정 결과):

1. **에디터 측 Decoration.widget**: 라벨 / bracket 을 ProseMirror Plugin 의
   `Decoration.widget(side=-1)` 으로 *inline DOM 노드* 삽입. 이 노드가 본문
   word 사이에 zero-width inline anchor 역할 — Chromium 의 word-break 알고리즘
   이 widget 위치를 *break opportunity* 로 인식. 같은 폭에서도 widget 이 박힌
   곳마다 line-break 가 추가 가능.
2. **PDF 측 inline span**: `annotation_html.py` 가 char-by-char `<span>` 으로
   emit. 라벨 wrap 은 `display: inline-block` 으로 *통째 한 단위* — break-
   opportunity 가 widget 보다 더 *낮음* (inline-block 내부는 wrap 안 됨).
3. **결과**: 같은 폭이라도 break opportunity 집합이 다름 → wrap 위치 다름.

### 2. 시도된 임시방편 (모두 원복됨)

검수 중 사용자 요청으로 짧은 fix 라운드 진행. 모든 케이스 정합 못 함 → 원복:

| 시도 | 결과 |
|---|---|
| PDF 본문 폭 626 → 622 → 612 px 좁힘 | 일부 case 정합되나 다른 case 의 wrap 깨짐. 폭 의존 fix 는 본질적 해결 X. |
| label `<span>` 안에 zero-width inline-block anchor 추가 (`&#8203;` 등) | 일부 case 만 break-opportunity 추가. 라벨 box 시각 박스 표시 깨짐. |
| bracket open 글자를 라벨 span 의 *안* 으로 이동 | borderline 시각 (라벨 box 폭 확장) vs wrap 정합 trade-off — 둘 다 만족 불가. |
| 라벨 `display: inline-block` → `display: inline` | borderline 의 `::before` 가 inline 박스의 line-box 안에서 잘림. 시각 깨짐. |

사용자 결론 (2026-05-15):

> 임시방편으로 이슈건들을 하드코딩하는건 안좋아. 근본적으로 에디터와 pdf
> 프리뷰 페이지가 동일한 방식으로 렌더링되게해야 모든 케이스에 이슈가 없게
> 작동하지.

### 3. 본질적 원인 — 두 렌더 엔진의 *DOM 생성 경로* 가 다름

ADR-0014 D1 의 *channel matrix* 를 다시 보면:

```
SyntaxAnnotation[]  ─┬─→  Tiptap (Decoration.widget) → 에디터 DOM   (브라우저 측)
                     └─→  annotation_html.py (inline span) → PDF DOM (서버 측)
```

두 경로는 *같은 입력* 에서 출발하지만 *다른 DOM tree* 를 생성. CSS
(`_annotation.css` / `EditorPoc.css`) 는 같은 클래스 / 변수 / borderline 픽셀
값을 공유하지만, **DOM 구조 자체가 다른 이상 CSS 만으로는 wrap 정합 불가능**.

ADR-0014 채택 시점 (2026-05-07) 의 *risk 인식*:

> **에디터 ↔ 서버 매핑 규칙 동기화 부담** — 변경 시 4곳 (`docs/...md` /
> hwpx_renderer / template_renderer / editor) 동시 수정 필수. **완화**:
> docs/...md 를 single-source-of-truth + code-reviewer 체크 항목.

이 *risk* 가 단순한 *규칙 동기화* 가 아니라 **DOM 구조 자체의 동기화** 임이
v0.2 검수에서 명확해짐. 4곳 docs 동기화 + 코드 동기화는 *시각 결과* 의 정합을
보장하지 않음 — break-opportunity 와 같이 *DOM 구조* 에서 파생되는 속성은
시각 결과를 결정하지만 매핑 표에는 잡히지 않음.

### 4. CLAUDE.md §1.3 핵심 가치 명제 #3 정합성

> **편집 가능한 출력**: AI 가 만든 결과는 항상 사용자가 검수/수정한 후
> 내보낸다 (자동 = 신뢰 부족 ≠ 완성)

이 명제는 *논리적 정합* (사용자 수정 → DB → PDF 그대로) 뿐 아니라 *시각적
정합* (사용자가 에디터에서 본 것 = PDF 결과) 도 포함. 와이프 검수 결과 후자
미충족 — **사용자는 에디터에서 봤던 wrap 위치를 PDF 에서 다시 보지 못함**.
편집 결과를 신뢰할 수 없으면 *편집 가능한 출력* 의 가치 명제가 무너짐.

### 5. Phase 정합 — 본 sprint 의 위치

| Phase | 출력 채널 | 본 sprint 의 영향 |
|---|---|---|
| Phase 1 baseline | 구문분석 단독 HWPX → 폐기 (ADR-0008) → Phase 2 PDF 로 흡수 | 영향 없음 (HWPX 폐기 영역) |
| Phase 2 baseline (B5 OK) | 학생 자료 PDF | **직접 영향 — wrap 정합 깨진 영역** |
| Phase 2-edit (현재) | 학생 자료 편집 UI + PATCH 라우트 + PDF | **직접 영향 — 편집 후 wrap 결과 정합 깨짐** |
| Phase 3 (변형문제) | 변형문제 PDF + HWPX | **간접 영향 — 같은 렌더 엔진 분기 위에 추가 콘텐츠** |
| Phase 4 (클라우드 배포) | 추가 사용자 | **간접 영향 — 사용자 수 증가 시 검수 비용 증가** |

본 sprint 가 **늦어질수록 비용 ↑** — Phase 3 진입 시 변형문제 PDF 가 같은
이슈 위에서 발생, Phase 4 진입 시 사용자 수 증가로 회귀 검출 비용 ↑.

---

## Decision (결정)

### D1. 옵션 비교

본 sprint 가 해결해야 할 문제는 *"두 렌더 엔진의 DOM 생성 경로 통합"*. 후보 4개:

#### 옵션 (a) — **PDF 도 Tiptap 으로 정적 렌더링** (server-side Tiptap)

`apps/api` 또는 `apps/web/server` 에서 Node.js 프로세스로 headless Tiptap 인스턴스를
띄워 동일 DOM 생성 후 그 HTML 을 Playwright 가 PDF 로 변환.

```
SyntaxAnnotation[]  ──→ Tiptap (DOM polyfill) → 동일 DOM tree
                              ↓
                  ┌───────────┴───────────┐
                  ↓                       ↓
            에디터 (브라우저)        PDF 렌더 (Chromium)
```

| 항목 | 평가 |
|---|---|
| 정합성 | **★★★★★** 100% — 같은 Tiptap 인스턴스가 같은 DOM 생성 |
| NRTW 정합 | **★★★★☆** Tiptap 은 검증된 라이브러리, jsdom / LinkedDOM 도 검증된 polyfill |
| 인프라 부담 | **★★☆☆☆** Node.js / DOM polyfill / Tiptap 라이프사이클 추가 |
| 변경 영역 | apps/api 또는 신규 micro-service. `annotation_html.py` 폐기 |
| 비용 (대략) | 3~4주 (PoC 1주 + 라우트 통합 1주 + 회귀 1~2주) |
| 리스크 | DOM polyfill 미지원 API (Range, Selection, IntersectionObserver) — Tiptap 동작 단계에 따라 호환성 검증 필수 |

**기술 검토 — DOM polyfill 후보**:
- **jsdom** (npmjs.com/jsdom, 100M+ DL/주, MIT, 활발) — 가장 표준. Tiptap
  /ProseMirror 가 jsdom 위에서 동작 검증된 사례 다수 (vitest + jsdom).
- **LinkedDOM** (linkedom, 빠름, jsdom 의 경량 대체) — 일부 ProseMirror Plugin
  미지원 가능성. PoC 필요.
- **happy-dom** (vitest 등에서 활용) — 비슷한 영역.

ADR-0015 D5 *"Tiptap 재사용 + prop 분기"* 채택과 *방향성 일치* — 본 sprint 는
*에디터* 와 *PDF 렌더* 모두 단일 Tiptap base 사용. ADR-0014 의 D1 "서버 단독
렌더" 결정은 *Python 렌더기 채택* 이었으나 *결과적 위치 (서버)* 는 유지 — 단,
*구현 언어 / 엔진* 만 Node.js + Tiptap 으로 전환.

#### 옵션 (b) — **에디터 widget 을 PDF DOM 패턴으로 재설계** (Mark + CSS pseudo)

Tiptap 측에서 `Decoration.widget` 을 폐기, 라벨 / bracket 을 ProseMirror Mark
로 통일 + CSS `::before` / `::after` 로 라벨 텍스트 표현. PDF 측은 현행 유지
(`annotation_html.py` 의 inline span).

| 항목 | 평가 |
|---|---|
| 정합성 | **★★★☆☆** DOM 구조 유사. 하지만 Mark 가 텍스트 노드 경계마다 분할되며 라벨 / bracket 위치 추적 어려움 (이전 PR #67/#70 회귀 원인 — `topLabel.ts` 주석 §렌더링 방식 참조). |
| NRTW 정합 | **★★★★☆** Tiptap 의 native pattern 활용 |
| 인프라 부담 | **★★★★★** 변경 영역 = `packages/editor/` 만. Node.js / polyfill 불필요. |
| 변경 영역 | `packages/editor/src/extensions/{topLabel,bottomLabel,bracket}.ts` 재설계 |
| 비용 (대략) | 2~3주 (재설계 1.5주 + 회귀 1~1.5주) |
| 리스크 | **이전 ::before/::after 방식이 실패한 이유 재현** — `topLabel.ts` 주석: *"기존 CSS ::before pseudo-element 방식은 highlight/underline 과 같은 span 에 겹칠 때 ProseMirror 가 topLabel span 을 텍스트 노드 경계마다 분할하면서 모든 조각에 ::before 가 붙어 라벨 텍스트가 중복 렌더되는 버그가 있었다."* 같은 함정 재발. |

#### 옵션 (c) — **별 공통 렌더 라이브러리 추출** (cross-language)

JavaScript / Python 양쪽에서 사용 가능한 *annotation → HTML* 라이브러리 신규.
SyntaxAnnotation → 동일 HTML string. 에디터는 그 HTML 을 ProseMirror 의
initial doc 로 parse, PDF 는 그대로 Jinja 컨텍스트 주입.

| 항목 | 평가 |
|---|---|
| 정합성 | **★★★★☆** 같은 함수 → 같은 HTML. 단, 에디터 측은 ProseMirror parse 단계에서 DOM tree 가 변형될 수 있음. |
| NRTW 정합 | **★★☆☆☆** *새 abstract layer* 신규 — 매우 큰 단점. |
| 인프라 부담 | **★★☆☆☆** 두 언어 지원 — WASM / FFI / micro-service 중 택1. 운영 복잡도 ↑ |
| 변경 영역 | 신규 `packages/annotation_renderer/`. 에디터 / 서버 양쪽 통합 |
| 비용 (대략) | 5~7주 (라이브러리 설계 2주 + 두 언어 통합 3~5주) |
| 리스크 | 직접 구현 라이브러리 — CLAUDE.md §3.6 "No Reinventing the Wheel" 위반 가능성 높음. *왜 라이브러리를 쓰지 않았는가* 근거 필요. |

#### 옵션 (d) — **시각 정합 포기 / 명시적 인정**

Sprint 없음. 사용자 문서 / UI 안내에 *"에디터와 PDF 의 wrap 위치는 미세하게
다를 수 있습니다. PDF 미리보기를 최종 확인용으로 사용해주세요."* 명시.

| 항목 | 평가 |
|---|---|
| 정합성 | **★☆☆☆☆** 0% |
| NRTW 정합 | n/a |
| 인프라 부담 | **★★★★★** 변경 0 |
| 변경 영역 | docs / UI 카피만 |
| 비용 (대략) | 0.5일 |
| 리스크 | **CLAUDE.md §1.3 핵심 가치 명제 #3 위반** — *편집 가능한 출력* 의 *편집 = PDF 결과* 신뢰 부서짐. 사용자 합의 거부 (§Context #2 인용). |

### D2. 권장안 — 옵션 **(a)** server-side Tiptap

**근거**:

1. **정합성 = 100% 만 받아들일 수 있는 영역**. 옵션 (b) 와 (c) 는 정합성이
   *높지만 100% 가 아님* — 회귀 검출 / 사용자 신뢰 회복 비용을 다음 단계에서
   다시 지불. 한 번 박힌 *"에디터와 PDF 가 다를 수 있음"* 인상은 사용자가
   *모든 차이* 를 의심하게 만들어 검수 흐름 자체를 무너뜨림.
2. **CLAUDE.md §3.6 정합** — Tiptap 은 검증된 라이브러리, jsdom 은 검증된
   polyfill. 둘 다 *기존 사용* 영역의 확장 (에디터 측 Tiptap 이 이미 있음).
   직접 구현 라이브러리 (옵션 c) 보다 NRTW 정합 ↑.
3. **ADR-0015 D5 의 자연 연장** — *"Tiptap 재사용 + prop 분기"* 결정의 다음
   단계. 에디터 측 Tiptap base 가 *읽기 전용* 모드로 server-side 에서도
   동작.
4. **비용 vs 이익** — 3~4주는 짧지 않으나, Phase 3 진입 전 봉합 시 변형문제
   영역까지 영향 차단. 옵션 (b) 의 2~3주는 *회귀 위험* 까지 포함하면 실질
   비용 (a) 와 비슷.

**탈락 사유 — 옵션 (b)**: `Decoration.widget` 채택 자체가 *이전 ::before 방식
실패* 의 결과 (코드 주석 명시). 옵션 (b) 는 *과거 실패한 경로로 되돌아감* —
같은 함정 재발 가능성 높음.

**탈락 사유 — 옵션 (c)**: 새 abstract layer 도입은 §3.6 위반. WASM / FFI /
micro-service 운영 복잡도 ↑. 두 언어 지원 부담이 단일 언어 (Node.js) 단일
도구 (Tiptap) 보다 명확히 큼.

**탈락 사유 — 옵션 (d)**: §Context #2 사용자 결론에 반함. 핵심 가치 명제 #3
위반.

### D3. Stage 분해 (옵션 a 채택 가정)

#### Stage F1 — Server-side Tiptap PoC (1주)

**목표**: jsdom (또는 linkedom) 위에서 Tiptap 인스턴스 띄워 annotation → HTML
변환 동등성 검증.

| # | 작업 |
|---|---|
| F1-a | Node.js + jsdom 환경에서 Tiptap minimum boot (`@tiptap/core` + ProseMirror dependencies). PoC 스크립트. |
| F1-b | 기존 `packages/editor/src/extensions/*` 가 server-side 에서 동작하는지 검증 (Decoration.widget 측 DOM 조작 호환성). |
| F1-c | annotation → 동일 HTML 출력 확인 (브라우저 측 출력과 byte-by-byte 비교는 *어렵지만*, 핵심 DOM 구조 + 클래스 / 속성 정합 검증). |
| F1-d | jsdom 미지원 API (Range, Selection 등) 호환 layer 평가. linkedom / happy-dom 대안 비교. |

**DoD**:
- 단일 fixture (zero-waste passage + 6종 annotation) 가 server-side Tiptap →
  HTML → Playwright PDF 경로로 출력됨.
- 와이프 검수 케이스 (§Context #1) 의 wrap 위치가 *에디터와 동일* 함을
  Playwright spec 으로 측정 검증.
- PoC 결과 보고서 `docs/stage-f1-server-tiptap-poc.md`.

#### Stage F2 — `annotation_html.py` 폐기 + Node 서비스 통합 (1주)

**목표**: 백엔드 PDF 라우트가 Node.js Tiptap 렌더기를 호출.

| # | 작업 |
|---|---|
| F2-a | `apps/api/.../routers/worksheets.py` 의 PDF export 라우트가 Node Tiptap 호출. 두 후보: (1) `subprocess.run(["node", "render.js", json])` 단순, (2) FastAPI ↔ Node 사이드카 (FastAPI 가 Node 프로세스 라이프사이클 관리). |
| F2-b | `packages/template_renderer/src/template_renderer/annotation_html.py` deprecate marking — 본 PR 머지 시 import 경로 차단, F4 정리 PR 에서 제거. |
| F2-c | Worksheet preview / PDF 라우트 회귀 — translation / vocabulary block 은 Jinja2 측 그대로 유지 (annotation 영역만 Node 위임). |
| F2-d | 운영 측면 — Node 프로세스 콜드 스타트 / 메모리 / 보안 (입력 sanitization) 검토. ADR-0011 D2 의 *Chromium pool* 검토와 묶어 Stage 3 자리 표시. |

**DoD**:
- PDF 응답 시간 < 3s (현행 + 1s 이내) — 검수 시 와이프 불만 없을 수준.
- 모든 fixture (PoC + B5 검수 + Phase 2-edit 검수) PDF 가 정합.

#### Stage F3 — Worksheet preview / export 라우트 갱신 (0.5주)

**목표**: `GET /worksheets/{id}/preview` + `POST /worksheets/{id}/export.pdf`
가 새 렌더 경로 사용. 라우트 시그니처 / 응답 형식 변경 X — 내부 구현 교체.

| # | 작업 |
|---|---|
| F3-a | `worksheet_to_template_context()` (`adapters.py`) — `content_html` 생성 함수 교체 (`render_annotations_to_html` → Node 호출). |
| F3-b | 단위 테스트 — 같은 annotation 입력 → 같은 (또는 *동등한 시각* 인) HTML 출력. snapshot 테스트는 Tiptap 출력에 맞춰 갱신. |
| F3-c | Phase 2-edit 의 신규 라우트 (Stage E1 PATCH) 와 정합 — translation / vocabulary 편집 후 즉시 새 PDF 가 wrap 정합. |

**DoD**:
- B5 와이프 검수 fixture (zero-waste passage) 의 PDF 가 *에디터 화면 그대로*
  wrap 정합.
- 와이프 v0.2 검수 케이스 (§Context #1 의 a / b) 모두 정합.

#### Stage F4 — 회귀 / 검수 / 정리 (1주)

**목표**: 와이프 v0.2 통합 검수 OK + 코드 정리.

| # | 작업 |
|---|---|
| F4-a | `apps/web/tests/e2e/wrap_parity_*` spec 통합 — 와이프 검수 fixture 의 wrap 정합 회귀 spec. |
| F4-b | `annotation_html.py` + `_annotation.css` 의 PDF 측 분기 제거 (CSS 는 에디터와 공유 유지). |
| F4-c | `docs/annotation-hwpx-mapping.md` 갱신 — HTML 매핑 표를 Tiptap base 로 단일화. HWPX 측 매핑은 별 영역 (Phase 2/3 트리거 시 별 ADR). |
| F4-d | ADR-0014 Status 변경 (Accepted → Superseded by ADR-0018), ADR-0011 D8 갱신, CLAUDE.md §3.5 갱신. |
| F4-e | 와이프 v0.2 통합 검수 — `docs/phase-2-edit-wife-review.md` (또는 v0.2 검수 문서) 에 결과 기록. |

**DoD**:
- 와이프 검수 OK (등급 A/B/C — A 기대).
- ADR / docs / CLAUDE.md 정합.
- 회귀 spec green.

### D4. No Reinventing the Wheel 원칙 정합 (§3.6)

본 sprint 가 §3.6 의 4가지 평가 기준에 부합하는지 점검:

| 기준 | 평가 |
|---|---|
| 1. 이미 검증된 라이브러리/프레임워크가 있는가? | ✅ **Tiptap** (검증, 기존 사용) + **jsdom** (검증, 표준 polyfill) |
| 2. 부분 충족만 하는가 → 어댑터/래퍼? | n/a — Tiptap 은 정의상 100% 충족 (같은 라이브러리). jsdom 호환성은 F1 PoC 에서 측정. |
| 3. 도메인 특수성이 너무 큰가 → 직접 구현? | ❌ — annotation 렌더는 Tiptap base 위에서 표현 가능. 직접 구현 필요 X. |
| 4. 작은 유틸 1~2개 쓰자고 무거운 라이브러리? | ❌ — 큰 영역 통합 (전체 annotation 렌더). |

PR 본문에 "왜 jsdom 을 골랐는가 + 대안 검토 (linkedom / happy-dom)" 기록 필수
— §8.4 신규 라이브러리 도입 규칙.

### D5. Phase 정합 — 본 sprint 의 위치 (CLAUDE.md 갱신 제안)

**제안**: 본 sprint = *Phase 2-edit 종료 직후, Phase 3 진입 직전* 의 **Phase
2.5 (unified-rendering)** 자리.

| 시점 | 상태 |
|---|---|
| Phase 2-edit Stage E1/E2/E3 완료 (PR #70~#74 머지) | 본 sprint 시작 trigger |
| 본 sprint F1~F4 진행 | Phase 2.5 |
| 와이프 v0.2 통합 검수 OK | Phase 2.5 종료 |
| Phase 3 진입 (변형문제 ADR 작성 + VocabularyMaster ADR) | 본 sprint 종료 후 |

**근거**: Phase 3 진입 후 변형문제 PDF 가 같은 wrap 이슈 위에 추가 콘텐츠를
얹으면 *회귀 검출 비용* 이 2배 ↑. 본 sprint 가 Phase 3 전 차단 = 사용자 신뢰
회복 + 향후 영역 확장 기반 안정화.

CLAUDE.md §2.2 "현재 위치" 갱신 제안 (본 ADR Accepted 시):

> Phase 2-edit Stage E1/E2/E3 코드 완료 (PR #70~#74) + 와이프 v0.2 통합 검수
> 중 발견된 *에디터 ↔ PDF wrap 어긋남* (ADR-0018) → **Phase 2.5 (unified-
> rendering) 진입 신호**. ADR-0018 Stage F1 (server-side Tiptap PoC) 시작
> 가능.

### D6. 비용 추정 — 권장안 (a) 의 작업 분량

| Stage | 기간 | PR 수 (대략) |
|---|---|---|
| F1 (PoC) | 1주 | 1 (PoC + 보고서) |
| F2 (Node 통합) | 1주 | 2~3 (subprocess / 사이드카 / deprecate) |
| F3 (라우트 갱신) | 0.5주 | 1~2 |
| F4 (회귀 + 정리) | 1주 | 2~3 (spec / docs / cleanup) |
| **합계** | **3.5주** | **6~9 PR** |

검수 OK 후 즉시 진행 vs 후순위 결정은 PM 영역. **권장: 즉시 진행** — Phase 3
진입 전 봉합이 비용 최소. (와이프 v0.2 통합 검수 OK 등급에 따라 trigger
조정 — D 등급 시 별 phase, A/B/C 등급 시 본 sprint.)

### D7. ADR-0014 와의 관계 — Superseded?

본 ADR Accepted 시 ADR-0014 의 상태는:

| 후보 | 의미 |
|---|---|
| (a) Superseded by ADR-0018 | ADR-0014 의 핵심 결정 (D1 서버 단독 렌더 채택 C) 이 본 ADR 로 *교체*. 단, ADR-0014 의 D2 (CSS class 매핑) / D3 (single-source-of-truth) / D6 (XSS) 는 그대로 살아남음. |
| (b) Amended | ADR-0014 가 본 ADR 의 *전구체* 임을 명시하고 둘 다 살림. |

**권장**: (a) Superseded. ADR-0014 의 *Python 단독 렌더* 결정이 *언어 변경
(Node.js)* + *엔진 변경 (Tiptap)* 둘 다 뒤집힘 — 부분 amend 가 아니라 전면
교체.

ADR-0014 의 부속 영역 (CSS class / 매핑 표 / XSS) 은 *본 ADR 의 부속 영역
으로 흡수* — Stage F4-c (`docs/annotation-hwpx-mapping.md` 갱신) 에서 일괄.

### D8. HWPX 측 영향

ADR-0008 (HWPX → HTML/PDF 전환) 으로 Phase 1 HWPX 영역은 폐기. 그러나
CLAUDE.md §2.1 "Phase 3 — 변형문제" + ADR-0014 D9 의 *channel matrix* 는
변형문제 / 교사용 자료의 *HWPX + HTML 양방향* 제공을 명시. Phase 3 진입 전
**HWPX 측 렌더기는 별 ADR 영역** — 본 sprint 는 *HTML / PDF 측 통합* 만
다룸.

본 ADR 이 HWPX 렌더기 (`packages/hwpx_renderer/`) 에 미치는 영향:
- 직접 영향 없음 (현행 유지)
- 간접 영향: ADR-0014 의 *single-source-of-truth* 매핑 표는 본 ADR 종료 후
  *Tiptap 측 매핑* 으로 단일화. HWPX 렌더기가 다시 활용될 때 (Phase 3 변형
  문제 진입) 그 매핑 표가 1차 입력.

---

## Consequences (결과)

### 긍정적 결과

1. **CLAUDE.md §1.3 핵심 가치 명제 #3 정합 복구** — *편집 가능한 출력* 의
   *시각적 정합* 회복. 사용자 신뢰 회복.
2. **단일 렌더 source** — 두 렌더기 동기화 부담 (ADR-0014 risk #1) 영구 해소.
   매핑 변경 PR 1건이 한 곳만 갱신.
3. **Phase 3 진입 안정화** — 변형문제 PDF 가 같은 wrap 이슈 위에 얹히지 않음.
4. **NRTW 정합** — 검증된 Tiptap + jsdom 활용. 직접 abstract layer 도입 회피.

### 부정적 결과 / 리스크

1. **Node.js 인프라 추가** — 백엔드가 Python 단독에서 Python + Node 혼합으로
   확장. 운영 / 배포 복잡도 ↑. **완화**: subprocess 단순 모델 채택 → 라이프
   사이클 단순. 사이드카 / micro-service 는 Phase 4 클라우드 배포 트리거.
2. **PoC 단계 호환성 불확실성** — Tiptap 의 일부 ProseMirror Plugin 이 jsdom
   미지원 API 사용 가능성. **완화**: F1 PoC 가 명시적 차단 게이트. PoC 실패
   시 옵션 (b) 재검토.
3. **PDF 응답 시간 잠재 증가** — subprocess 콜드 스타트 (~500ms). **완화**:
   process pool / persistent Node 사이드카 (Stage F2-d). Chromium pool 결정
   (ADR-0011 Stage 3) 과 묶어 검토 가능.
4. **ADR-0014 superseded 의 정리 부담** — F4-d 에서 ADR / CLAUDE.md / docs
   여러 곳 갱신 필수.
5. **PoC 실패 시 fallback** — 옵션 (b) 로 후퇴. 단, 이 시점에 비용 증가
   (PoC 1주 + 옵션 b 2~3주 = 3~4주, 본 sprint 와 동일 비용이나 정합성 ↓).

### 후속 작업

- **본 ADR Accepted 후**: Stage F1 PR (PoC) 즉시 시작.
- **CLAUDE.md §2.2 갱신** — *Phase 2.5 (unified-rendering)* 진입 신호 표기 (D5
  제안).
- **CLAUDE.md §11 Open Questions** — 본 ADR 항목 추가 (Proposed 상태).
- **ADR-0014 상태 변경** — F4-d 에서 Superseded by ADR-0018.
- **메모리 (`feedback_pdf_annotation_visual.md`) 갱신** — 본 sprint 진행 시
  픽셀 값 보존 가이드 추가. Tiptap base 단일화 후에도 사용자 확정 픽셀 값
  유지 필수.

---

## Open Questions

PM 결정 필요 항목 (별 PR 코멘트 또는 본 ADR 의 결정 기록 단에서):

- [ ] **OQ1**: 권장안 (a) server-side Tiptap 채택 vs 옵션 (b) Mark + CSS
  재설계. 권장 = (a). 단, F1 PoC 실패 시 (b) 자동 fallback.
- [ ] **OQ2**: 본 sprint 의 trigger — Phase 2-edit Stage E1/E2/E3 모두 머지
  + 와이프 v0.2 통합 검수 *시작 전* vs *검수 결과 확정 후*. 권장 = *검수
  결과 확정 후* (검수 등급에 따라 trigger 조정).
- [ ] **OQ3**: Node 통합 모델 — (1) subprocess 단순 vs (2) FastAPI 사이드카
  vs (3) micro-service. 권장 = (1) MVP, Phase 4 트리거 시 (2). F2-d 결과로
  최종 결정.
- [ ] **OQ4**: DOM polyfill — jsdom vs linkedom vs happy-dom. F1 PoC 결과
  기반 결정. 본 ADR 채택 시점에는 미결.
- [ ] **OQ5**: ADR-0014 상태 — Superseded vs Amended. 권장 = Superseded
  (D7).
- [ ] **OQ6**: 본 sprint 의 Phase 분류 — *Phase 2.5* 신규 vs *Phase 2-edit
  연장* vs *Phase 3 진입 전 단일 sprint*. 권장 = *Phase 2.5* (D5).
- [ ] **OQ7**: HWPX 렌더기 영향 — 본 sprint 에서 *HTML/PDF 측만* vs HWPX
  렌더기도 단일화 (Tiptap → HWPX 변환). 권장 = HTML/PDF 측만 (HWPX 는 Phase
  3 변형문제 ADR 영역).

---

## 후속

본 ADR 결정 후:

1. PM 검토 — OQ1~OQ7 결정.
2. architect — 본 ADR 갱신 (Proposed → Accepted, OQ 결정 반영). ADR-0014 상태
   변경 PR (F4-d 의 일부).
3. backend-dev — Stage F1 PoC PR (Node + jsdom + Tiptap minimum boot).
4. frontend-dev — Stage F2 후속 (에디터 측 변경 X, server-side Tiptap 의 PDF
   결과 정합 측정 spec 추가).
5. code-reviewer — 각 PR 의 wrap parity 회귀 spec 정합 / NRTW 검토 (Node 인프라
   추가 근거).
6. domain-expert — Phase 2.5 검수 시 와이프 검수 시나리오 작성 (`docs/phase-2_5-
   unified-rendering-wife-review-prep.md` 또는 v0.2 검수 문서에 합치).
7. CLAUDE.md v0.11 갱신 — §2.2 Phase 2.5 진입 + §3.5 Tiptap 측 결정 확장 + §11
   본 ADR 항목 + §12 변경 이력.

---

## 대안 검토 요약

| 항목 | 권장 | 탈락 후보 | 출처 |
|---|---|---|---|
| 렌더 통합 방식 | (a) server-side Tiptap | (b) Mark + CSS / (c) cross-lang lib / (d) 시각 정합 포기 | D1 / D2 |
| Node ↔ Python | subprocess MVP | 사이드카 / micro-service | D3 F2-d |
| DOM polyfill | jsdom (PoC 기준) | linkedom / happy-dom | D3 F1-d |
| Phase 위치 | Phase 2.5 | Phase 2-edit 연장 / Phase 3 진입 전 단일 | D5 |
| ADR-0014 처리 | Superseded | Amended | D7 |
| HWPX 영향 | HTML/PDF 측만 | HWPX 동시 단일화 | D8 |

---

## 결정 기록

| 날짜 | 상태 | 결정자 | 비고 |
|---|---|---|---|
| 2026-05-15 | Proposed | architect | 와이프 v0.2 통합 검수 중 wrap 어긋남 발견 → 사용자 결론 "근본적 통합 필요" → 옵션 4종 비교 + 권장안 (a) server-side Tiptap. PM 검토 대기 — OQ1~OQ7. |
