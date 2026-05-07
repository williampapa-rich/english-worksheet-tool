# ADR 0014 — SyntaxAnnotation → HTML 렌더러 (양방향 출력 정합)

- **상태(Status)**: Proposed
- **작성일**: 2026-05-07
- **결정일**: TBD (PM 검토 대기)
- **작성자**: architect
- **결정자**: PM (Dennis)
- **유형**: ADR-0011 D8 (`content_html` 단순 wrap 한계) 해소. B4 (Worksheet preview
  컨텍스트 주입) 직전 차단 해제.
- **범위**: backend 단독 SyntaxAnnotation → HTML 변환기 + worksheet content_html
  주입 정책. `packages/hwpx_renderer/render.py` 와 *대칭* 구조.
- **관련 문서**:
  - `CLAUDE.md` v0.8.1 §1.2 (1차 사용자), §2.1 (Phase 2 학생용 자료, Phase 3 변형
    문제), §3.5 (구문분석 에디터)
  - `docs/adr/0008-phase-1-output-format.md` (HWPX → HTML/PDF 채택안 A)
  - `docs/adr/0011-worksheet-html-pdf-pipeline.md` D8 (현재 단순 wrap 한계 명시)
  - `docs/adr/0004-annotation-span-identification.md` (character offset 채택)
  - `docs/adr/0007-bracket-hwpx-representation.md` (bracket Unicode 채택)
  - `docs/annotation-hwpx-mapping.md` (P1-7 매핑 카탈로그)
  - `shared/schemas/annotation.py` (SyntaxAnnotation 도메인 모델)
  - `packages/hwpx_renderer/src/hwpx_renderer/render.py` (HWPX 렌더 — 본 ADR 의
    *대칭* 구현 참조)
  - `packages/editor/src/serialization/annotationSerializer.ts` (에디터 측 직렬화)

---

## Context (배경)

### 1. ADR-0011 D8 의 차단 — 단순 wrap 의 한계

ADR-0011 D8 명시:

> 현재 `WorksheetItem.content_html` 는 `Passage.body_text` 를 `markupsafe.escape()`
> 후 `<p>` 로 wrap 한 *단순 형태*. 에디터 산출 annotation (highlight / underline /
> inline_note / top_label / bottom_label / bracket) 의 정밀 표현은 하지 못함.
>
> **위험**: 에디터에서 작업한 annotation 이 worksheet preview / PDF 에서 *보이지
> 않는다*. Phase 2 본격 진입 전 ADR 작성 필수.

### 2. 출력 채널 매트릭스 — PM 답변 반영

본 프로젝트의 출력 채널은 두 축으로 분기한다:

| 콘텐츠 | HTML / PDF | HWPX |
|---|---|---|
| 구문분석 에디터 (Phase 1) | ✅ 채택안 (ADR-0008) | ❌ 미사용 (P1-9 검수 D 등급) |
| 학생용 worksheet (Phase 2) | ✅ MVP (ADR-0011) | ✅ 가능 (Phase 2/4 트리거) |
| 변형문제 (Phase 3) | ✅ | ✅ 동시 제공 (한국 학원 표준) |
| 교사용 자료 | ✅ | ✅ |

**PM 답변 (2026-05-07)**: 구문분석 에디터는 HTML→PDF 단방향, 변형문제 등은 HTML +
HWPX 양방향. 이 분기를 schema 가 알 필요 없음 — **렌더러 2개가 동일 SyntaxAnnotation
을 입력으로 받아 각자 출력**.

### 3. 에디터 직접 HTML vs 서버 렌더 — 정합성 결정

같은 `SyntaxAnnotation[]` 에서 출발해도 렌더 결과가 일치하지 않으면 silent drift.
세 가지 가능한 source 가 있다:

| 후보 | source | 단점 |
|---|---|---|
| A. 에디터 `getHTML()` | Tiptap | 변형문제 등 에디터 미경유 흐름은 source 가 없음. 클라이언트 의존. |
| B. 에디터 → 서버 sanitize | Tiptap + bleach | A 의 한계 동일 + sanitize 정책 결정 부담. |
| C. 서버 단독 SyntaxAnnotation → HTML | `packages/template_renderer/annotation_html.py` (신규) | 에디터와 매핑 규칙 동기화 필요 (변경 시 양쪽 동시 수정). |

**채택**: **C — 서버 단독 렌더**. 이유:

1. **변형문제 / 교사용 / API 직접 호출** 등 *에디터 미경유 흐름* 도 출력 가능해야.
2. **HWPX 와 대칭** — `hwpx_renderer/render.py` 가 이미 SyntaxAnnotation → HWPX
   서버 렌더. HTML 도 같은 패턴이면 코드 구조 일관.
3. **에디터 ↔ 서버 매핑 규칙 동기화 비용** 은 양쪽 모두 docs/annotation-hwpx-mapping.md
   인 single-source-of-truth 와 매핑 테이블 1개로 통제 가능. 변경은 PR 1건.
4. **클라이언트 의존성 제거** — 백엔드 단독 PDF 생성 가능 (B5 와이프 검수 시
   에디터 안 거치고도 학생용 자료 출력 가능 — UX 단축).

A / B 는 **에디터가 *추가* source 로 쓰일 수 있음** — Phase 2 후반 이후 검토 가능
(예: 에디터에서 직접 미리보기). 본 ADR 은 *한 source* 만 결정하고, 추가 source 는
별 ADR.

### 4. CSS class 매핑 — 디자인 토큰 호환성

ADR-0011 D10 의 `--theme` / `--ink` / `--muted` 등 CSS 변수 + playful 템플릿의
`color-mix(in srgb, ...)` 그대로 호환. annotation HTML 도 *템플릿이 정의한 CSS 변수
를 참조* 하는 BEM / utility class 만 사용.

---

## Decision (결정)

### D1. 위치 — `packages/template_renderer/annotation_html.py` (신규)

`packages/hwpx_renderer/render.py` 와 *대칭*. `packages/template_renderer/` 에
배치하는 이유:
- HTML 렌더는 worksheet 출력 채널의 일부 (ADR-0011 의 `template_renderer` 영역).
- `hwpx_renderer` 와 별 패키지로 분리해 deprecate 시 영향 격리 (ADR-0008 추후
  HWPX 사용처 줄어들면 hwpx_renderer 통째 제거 가능 — 본 모듈은 영향 X).

```python
# packages/template_renderer/src/template_renderer/annotation_html.py
from shared.schemas.passage import Passage
from shared.schemas.annotation import SyntaxAnnotation

def render_annotations_to_html(
    passage: Passage,
    annotations: list[SyntaxAnnotation],
) -> str:
    """SyntaxAnnotation 을 적용한 HTML <p> 문자열 반환.

    출력 = 단일 paragraph 가정 (Passage.body_text).
    Phase 2 후반에 paragraph 분할이 필요하면 별 함수.
    """
```

### D2. CSS class 명명 규칙 — BEM-lite

`hwpx_renderer/render.py` 의 charPr id 매핑과 *동일 의미적 분류*:

| AnnotationKind | HTML 표현 | 비고 |
|---|---|---|
| `highlight` | `<mark class="annot-highlight annot-highlight--{idx}">` | `idx` = 1~12 (color_index). |
| `underline` | `<span class="annot-underline">` | 단일 색상 (`#000000`, `text-decoration: underline`). |
| `inline_note` | `<span class="annot-inline-note">{본문}<sup class="annot-inline-note__text">{text}</sup></span>` | 작은 폰트 메모. |
| `top_label` | `<ruby class="annot-top-label">{본문}<rt>{text}</rt></ruby>` | HTML `<ruby>` 가 본문 *위* 라벨에 자연스럽게 매핑. CSS 로 색상 / 폰트 보강. |
| `bottom_label` | `<span class="annot-bottom-label" data-label="{text}">{본문}</span>` | CSS `::after` 로 본문 *아래* 라벨. `<rtc>` (ruby text container) 도 가능하지만 브라우저 호환성 약해 `data-` + CSS 채택. |
| `bracket` | `[본문]` 등 Unicode 직접 inline (ADR-0007) | HWPX 와 동일 — `<span class="annot-bracket">` 으로 wrap 해 CSS 폰트 weight 만 조정 가능. |
| `arrow` | (Phase 1 baseline 후) | P1-8c 별 PoC. 본 ADR 범위 밖. |

**BEM 권고 변형 (`annot-X__Y` / `annot-X--Y`)**:
- `annot-highlight--{idx}`: 12색 변형. CSS 는 `:root { --annot-highlight-1: ...; }`
  dict 정의.
- `annot-inline-note__text`: 메모 텍스트 부분.

CSS 정의 위치 — `packages/template_renderer/templates/_annotation.css` (별 파일,
3 템플릿이 `<style>` 또는 `<link>` 로 import).

### D3. 매핑 single-source-of-truth — `docs/annotation-hwpx-mapping.md` 갱신

P1-7 매핑 카탈로그가 HWPX 측만 다룸. 본 ADR 머지와 함께 **HTML 측 매핑 표** 를 같은
문서에 추가. 양 렌더러는 이 문서를 single-source-of-truth 로 가짐.

향후 매핑 변경 PR:
1. `docs/annotation-hwpx-mapping.md` 업데이트.
2. `packages/hwpx_renderer/render.py` 갱신.
3. `packages/template_renderer/annotation_html.py` 갱신.
4. (필요 시) `packages/editor/src/serialization/annotationSerializer.ts` 갱신.

본 PR 머지 후 매핑 변경은 *반드시 4 곳 모두* 갱신 필수 — code-reviewer 체크 항목.

### D4. SVG 화살표 — Phase 1 baseline 이후

`AnnotationKind.ARROW` 는 `arrow_target_span` (출발/도착 두 span) 가 필요해 단순
inline 매핑 불가. ADR-0011 D8 처럼 한계 *명시* + 향후 별 PoC:
- HTML: SVG `<line>` / `<path>` overlay 후보. body_text 위에 절대 위치.
- HWPX: `hp:line` / `hp:polyLine` (P1-8c 미진행).

본 ADR 은 화살표를 *명시적으로 skip* — `render_annotations_to_html` 이 arrow kind
를 받으면 **로깅 후 무시** (HWPX 와 동일 동작).

### D5. 중첩 / 충돌 처리

`hwpx_renderer/render.py` 의 `_slice_text_with_annotations` 와 동일 정책:
- **텍스트 런 계열 (highlight / underline / inline_note)**: char-by-char `charPr id`
  맵으로 마지막 적용 우선. multi-attr (highlight + underline 동시) 은 v0.1 범위 밖.
- **라벨 (top_label / bottom_label)**: 별 단락 인근 inline span. 같은 span 에 라벨
  2개는 v0.1 미지원 (CLAUDE.md §11 Open Questions).
- **bracket**: 본문 양 끝 inline 글자. char position 기준 open / close 매핑.

HTML 측은 char 단위 분할 자료 구조 (segments) 를 hwpx 와 *공유* 가능 — 헬퍼 함수
(`_slice_text_with_annotations`) 를 `shared/` 또는 `packages/template_renderer/`
공통 모듈로 추출할지 검토. 본 ADR 은 **분리 유지** (코드 중복 vs 의존 방향 정리
부담 trade-off — 머지 후 후속 PR 에서 추출).

### D6. XSS / 보안

- `Passage.body_text` 와 `SyntaxAnnotation.text` 모두 **HTML escape** 필수
  (`markupsafe.escape`). text 가 사용자 입력이므로 trust 안 함.
- 본 함수는 **escape 된 HTML 만 반환** — 호출자 (`worksheet_to_template_context`)
  가 Jinja2 `| safe` 로 우회 escape 시 안전.
- 추가 sanitizer (`bleach`) 는 본 ADR 범위 외 — 본 함수가 *한정된 tag set 만* 생성
  (mark / span / ruby / sup / rt) 하므로 추가 sanitize 불필요. 사용자 직접 HTML 입력
  경로가 생기면 그때 ADR 신설 (ADR-0011 D9 의 정책).

### D7. content_html 주입 위치

`worksheet_to_template_context()` 어댑터 (`packages/template_renderer/adapters.py`)
가 본 함수를 호출:

```python
# B4 PR 변경 (본 ADR 머지 후)
def worksheet_to_template_context(
    worksheet: Worksheet,
    passages: dict[UUID, Passage],
    annotations_by_passage: dict[UUID, list[SyntaxAnnotation]],
    translations_by_passage: dict[UUID, Translation | None],
    vocabulary_by_passage: dict[UUID, list[Vocabulary]],
) -> dict:
    questions = []
    for item in worksheet.items:
        passage = passages[item.passage_id]
        annotations = annotations_by_passage.get(passage.id, [])
        questions.append({
            "number": item.order + 1,
            "label": item.label,
            "content_html": render_annotations_to_html(passage, annotations),
        })
    # academy / worksheet / student / instruction / questions / 추가: translation /
    # vocabulary block per item (B4 결정)
    ...
```

라우트 (`apps/api/.../routers/worksheets.py`) 가 라이트한 fan-out — passage_id 마다
annotations / translation / vocabulary 를 batch 로 조회 (N+1 회피). 본 ADR 은
어댑터 시그니처만 결정 — 라우트 변경은 B4 PR.

### D8. 테스트 정책

- 단위 테스트 — 마크 종류별 (6종 × 빈 본문 / 단순 / 중첩 / 충돌) 출력 HTML 검증.
- snapshot 테스트 — 복합 fixture (highlight + underline + label) 의 출력 HTML 을
  fixture 파일과 대조 (회귀 차단).
- HWPX 와 *시각적 동일성* 은 본 ADR 검증 X — 양 렌더러가 같은 매핑 표 (`docs/...`)
  를 따른다는 신뢰. 와이프 검수 (B5) 가 1차 시각 확인.

### D9. 변형문제 (Phase 3) 와의 정합성

PM 답변 — 변형문제 등은 HTML + HWPX 양방향. 본 ADR 의 HTML 렌더러는 *Phase 3 진입
시 그대로 재사용*:
- 변형문제도 `Passage.body_text` + `SyntaxAnnotation[]` 구조 그대로.
- 변형 자체는 `VariantQuestion` (Phase 3 ADR) 의 영역이라 *annotation* 변환 영향 X.
- 즉 본 ADR 은 Phase 1 baseline 부터 Phase 3 까지 *변경 없이* 통과.

---

## Consequences (결과)

### 긍정적 결과

1. **에디터 의존성 제거** — backend 단독 PDF 생성. 변형문제 등 에디터 미경유 흐름
   대응.
2. **HWPX 와 대칭 구조** — 두 렌더러 모두 `SyntaxAnnotation[]` → 출력. 매핑 변경
   PR 1건이 양쪽 동시 갱신.
3. **Phase 3 까지 변경 없음** — 변형문제 / 교사용 자료 모두 본 렌더러 재사용.
4. **테스트 가능 단위** — backend 단독 함수라 mock 없는 단위 테스트 가능.
5. **B4 차단 해제** — `content_html` 단순 wrap 의 한계 (ADR-0011 D8) 해소.

### 부정적 결과 / 리스크

1. **에디터 ↔ 서버 매핑 규칙 동기화 부담** — 변경 시 4곳 (`docs/...md` /
   hwpx_renderer / template_renderer / editor) 동시 수정 필수. **완화**: docs/...md
   를 single-source-of-truth + code-reviewer 체크 항목.
2. **CSS 변수 / 디자인 토큰 호환성** — 3 템플릿 (`classic` / `modern` / `playful`)
   이 모두 `_annotation.css` 의 클래스를 인식해야. **완화**: D2 의 BEM-lite 명명 +
   템플릿마다 import 의무. 신규 템플릿 추가 시 동일 import.
3. **arrow / 복합 마크 미지원** — v0.1 은 6종 (highlight / underline / inline_note /
   top_label / bottom_label / bracket) 만. arrow 는 명시적 skip + 로깅. **트리거**:
   와이프가 학생용 자료에서 화살표 요청.
4. **char 분할 헬퍼 코드 중복** — hwpx 의 `_slice_text_with_annotations` 와 동일
   로직 별 함수. **트리거**: 본 PR 머지 후 후속 chore PR 로 공통 모듈 추출.
5. **`<ruby>` 의 PDF 렌더 호환성** — Chromium 은 `<ruby>` 지원 OK 이지만 폰트 미세
   조정 필요할 수 있음 (Pretendard / Noto Serif KR ruby glyph). B4 + B5 검수 시
   확인. **fallback**: `<span class="annot-top-label" data-label="...">` 로 CSS
   `::before` 사용 (bottom_label 과 대칭).

### 후속 작업 (별 PR)

- **본 PR 의 일부**: `packages/template_renderer/annotation_html.py` 신규 +
  `_annotation.css` + 단위 테스트 + `docs/annotation-hwpx-mapping.md` HTML 측 매핑
  표 추가.
- **B4 PR (next)**: `worksheet_to_template_context()` 가 `render_annotations_to_html`
  호출 + translation / vocabulary 컨텍스트 주입. `routers/worksheets.py` 의 batch
  조회.
- **chore PR (후속)**: hwpx 의 `_slice_text_with_annotations` 와 본 모듈의 char 분할
  로직 공통 추출 (`packages/template_renderer/_segments.py` 또는 `shared/`).
- **arrow 별 ADR**: 와이프 화살표 요청 트리거 시.

---

## 대안 검토 요약

| 항목 | 채택 | 탈락 후보 |
|---|---|---|
| Source | C 서버 단독 (D1) | A 에디터 `getHTML()` / B 에디터 → bleach |
| 위치 | `template_renderer/annotation_html.py` | `hwpx_renderer/` (잘못된 패키지) / `apps/api/` (배포 경계 위반) |
| top_label HTML | `<ruby>` (D2) | `<sup>` (의미 다름) / pure CSS (의미 표현 약함) |
| bottom_label HTML | `<span data-label>` + CSS `::after` | `<rtc>` (브라우저 호환성 약함) |
| arrow | 명시적 skip + 로깅 (D4) | SVG overlay 즉시 도입 (PoC 부담) |
| Char 분할 헬퍼 | 별 구현 + chore PR 로 추출 (D5) | 즉시 공통화 (분리 유지 후 추출이 더 안전) |

---

## 결정 기록

| 날짜 | 상태 | 결정자 | 비고 |
|---|---|---|---|
| 2026-05-07 | Proposed | architect | ADR-0011 D8 차단 해소. PM 답변 반영 (구문분석 = HTML→PDF, 변형문제 = HTML+HWPX 양방향). 서버 단독 렌더 채택 (C). HTML 매핑 표 6종 결정 + arrow 명시 skip. B4 직전 차단 해제. |
