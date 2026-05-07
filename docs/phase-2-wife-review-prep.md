# Phase 2 와이프 검수 준비 — 학생 배포용 자료 v0.1

- **작성일**: 2026-05-07
- **작성자**: PM (Dennis) + architect / backend-dev
- **검수자**: 와이프 (영어 강사)
- **관련 PR**: B1 (#51) / B2 (#52) / ADR-0011 (#53) / B3 (#54) / ADR-0014 (#55) / B4 (#56)
- **상태**: 검수 시작 대기 — 본 문서는 검수 시작 전 _준비_ 산출물

---

## 0. 본 문서의 목적

Phase 2 진입 베이스 (B1~B4 + ADR-0011 + ADR-0014) 가 머지된 시점에서, **와이프
검수를 시작하기 직전** 의 정리.

- 검수 시나리오 (어떤 흐름으로 무엇을 확인할지) 를 미리 정리.
- 와이프가 답해야 할 미정 항목 (ADR-0013 / 0014 의 학원 스타일 의존 항목 6+3건)
  을 한 곳에 모음.
- 검수 결과에 따른 v0.2 미세 조정 PR 의 변경 비용을 항목별로 미리 평가.

이 문서 자체는 코드 / 스키마 변경 0. 검수 시작 신호가 오면 §3 검수 기록을
이어서 채움.

---

## 1. 검수 대상

### 1.1 학생 배포용 자료 1건 (`playful` 템플릿, MVP 채택)

검수자 (와이프) 가 다음 흐름으로 1건 생성 후 결과 검토:

```
1. POST /passages/extract
   { kind: "text", payload: "<영어 지문 1개>" }
   → passage_id 1+ 확보

2. POST /passages/{passage_id}/translation
   → 한글 해석 LLM 보강 (B3, mode=skip_if_user_edited default)

3. POST /passages/{passage_id}/vocabulary?count=10
   → 어휘 박스 LLM 보강 (B3, count=10 default)

4. POST /passages/{passage_id}/annotations
   { annotations: [<top_label / highlight / underline / bracket 등>] }
   (구문분석 에디터에서 작업한 결과)

5. POST /worksheets
   {
     title: "<예: '고2 영어 어휘 핸드아웃'>",
     kind: "student",
     template_id: "playful",
     items: [{
       passage_id: <위 passage_id>,
       order: 0,
       include_translation: true,
       include_vocabulary: true,
     }]
   }
   → worksheet_id 확보

6. GET /worksheets/{worksheet_id}/preview?style=playful
   → 브라우저로 HTML 미리보기

7. POST /worksheets/{worksheet_id}/export.pdf
   → PDF 다운로드
```

검수는 **PDF 결과** 기준 (HTML preview 는 보조). 학생용 자료는 인쇄/배포가 본질.

### 1.2 비교 baseline

Phase 1 (HWPX 출력 D 등급, 사용 불가) → ADR-0008 채택안 A (HTML→PDF) → 본 검수가
_첫 PDF baseline_. Phase 1 baseline (구문분석 단독 PDF) 가 OK 받은 상태에서 진행.

---

## 2. 평가 기준 (와이프 작성)

Phase 1 검수 (`docs/phase-1-wife-feedback.md`) 와 같은 등급 체계 사용. 와이프가
검수 시작 전에 아래 표를 채움.

### 2.1 합격 등급 정의

| 등급  | 의미 (제안)                                             | 와이프 정의 |
| ----- | ------------------------------------------------------- | ----------- |
| **A** | 수업에서 그대로 인쇄해서 학생에게 배포 가능             |             |
| **B** | 약간 수기 보완하면 사용 가능 (예: 학생 이름란 손기입)   |             |
| **C** | 컴퓨터로 재편집 후 사용 가능 (예: 어휘 1~2개 직접 수정) |             |
| **D** | 사용 불가. 처음부터 재설계 또는 다른 접근 필요          |             |

**Phase 2 baseline 합격선**:

- [ ] A 만 합격
- [ ] B 까지 합격
- [ V ] C 까지 합격

(와이프가 체크. C 까지 합격이면 v0.2 미세 조정 PR 로 충분, B 이상만 합격이면 큰
변경 필요 가능성.)

---

## 3. 와이프에게 묻는 결정 항목 (11건)

ADR-0013 / 0014 작성 시 도메인 단독 결정 보류한 항목들. 각 항목은 와이프 답변에
따라 v0.2 미세 조정 PR 의 변경 범위가 달라짐.

### 3.A. 한글 해석 톤 (`docs/prompts/augment-translation-v0.md`) — 6건

#### A1. paragraph 보존 강도

영어 원문 paragraph 가 너무 길 때 한국어 줄바꿈 추가 OK?

- (b) 한국어로 옮길 때 더 짧게 쪼개도 OK.

**변경 비용**: 프롬프트 가이드 1줄 수정 — 매우 작음.

#### A2. 영어 병기 임계

"잘 알려진 고유명사" 의 기준?

- 현재 정책: 인명/지명은 한국어 + 첫 등장 1회 영어 병기. 기관명/브랜드는 영어 그대로.
- 와이프가 평소 어디까지 한국어로 옮기는지?
  - 예: `Apple` → "Apple"
  - 예: `Microsoft` → "Microsoft"
  - 예: 인용 출처 (`Nature`, `Time`) → 영어 그대로

**변경 비용**: 프롬프트 가이드 예시 갱신 — 작음.

#### A3. idiom / phrasal verb 표기

- (a) 의역만 — `It's not rocket science` → "그렇게 어려운 일은 아니다" (현재).

**변경 비용**: 프롬프트 가이드 정반대 정책 — 작음 (LLM 출력 검증은 도메인 expert
검토 필요).

#### A4. 해석 문체

- (a) 평어 — "~한다", "~이다" (현재 example 톤).

**변경 비용**: 프롬프트 가이드 + example 갱신 — 작음.

#### A5. 부정 / 시제 / 가정법 / 대명사 referent 정책

ADR-0013 의 high #2 반영 (한국 해설지 핵심 가이드 추가) 가 와이프 톤과 맞는지.
실제 검수 PDF 의 해석을 보고 OK/NG 판단. --> 오케이

**변경 비용**: 프롬프트 가이드 미세 조정 — 검수 결과 보고 결정.

#### A6. 학년별 어휘 / 톤 조정

`target_grade` (중1~수능) 별로 LLM 이 적절히 톤 조정하는지.

- 중학생용: 더 쉬운 한국어, 짧은 문장.
- 수능용: 시험 해설지 톤, 정확성 우선.

-> 오케이

**변경 비용**: 프롬프트 가이드 학년별 분기 — 중간 (학년 매트릭스 확장 필요할 수도).

### 3.B. 어휘 박스 정책 (`docs/prompts/augment-vocabulary-v0.md`) — 2건

#### B1. count default

- (a) 현재: 라우트 default 10, 1~30 허용.
- (b) 학년별 — 고1: 5~8, 고3: 12~15, 수능: 12~20.

**변경 비용**: 라우트 default 학년 분기 — 작음 (단, UI 가 학년 알아야).

#### B2. `level_label` 추가 라벨

ADR-0013 v0.1 권고: `수능 필수` / `고N 교과서` / `중N 교과서` / `어법 / 구문` /
`심화` / `숙어`.

**변경 비용**: 프롬프트 권고 값 추가 — 작음. 자유 문자열이라 LLM 이 학습.

### 3.C. annotation HTML 시각 표현 (ADR-0014) — 3건

#### C1. `<ruby>` (top_label) 의 PDF 렌더 호환성

Chromium 의 `<ruby>` + `ruby-position: over` 가 Pretendard / Noto Serif KR 폰트와
잘 맞는지. PDF 에서:

- 라벨 글자 크기 (현재 0.55em) 가 적절한가?
- 본문 위 위치가 너무 가까운가 / 멀리 있는가?
- 색상 (현재 `--theme`) 이 가독성 OK?

**변경 비용**: CSS 미세 조정 — 매우 작음.

#### C2. bottom_label CSS `::after` 위치

본문 _아래_ 라벨이 다음 줄과 겹치지 않는지. 현재 `line-height: 2.2` 로 보정.

- 너무 띄움 → 종이 낭비.
- 너무 가까움 → 라벨 충돌.

-> 웹앱 상에서는 괜찮아 보이는데, 출력물은 안봐서 모르겠음

**변경 비용**: CSS 미세 조정.

#### C3. 12색 highlight 의 인쇄 충실도

12색 `--annot-highlight-{1..12}` 가 Chromium PDF 에서 화면 색상 그대로 인쇄되는지.

- `print-color-adjust: exact` 적용됨 (playful.html 의 `print_background=True`).
- 와이프 프린터 (잉크젯 / 레이저) 에서 색상 차이 큰지?

-> 웹앱 상에서는 괜찮아 보이는데, 출력물은 안봐서 모르겠음

**변경 비용**: 색상 dict 재선정 — 작음 (와이프 프린터 색상 가이드 따라).

---

## 4. 변경 비용 매트릭스 (검수 결과 기반 v0.2 PR 추정)

| 검수 결과                                    | 변경 범위                                 | 추정 PR 수 |
| -------------------------------------------- | ----------------------------------------- | ---------- |
| 모든 항목 A 등급, 11건 모두 OK               | v0.2 PR 없음, B5 → Phase 2 baseline 종료  | 0          |
| A~C 등급, 일부 항목 (예: A1, A4, B1) 만 변경 | 프롬프트 v0.2 PR 1건 + 라우트 default 1건 | 2          |
| C/D 등급 우려, 다수 항목 변경                | 프롬프트 + 라우트 + 템플릿 CSS + 어댑터   | 3~4        |
| D 등급 (사용 불가)                           | 처음부터 재설계 — 별 ADR 신규             | 별 phase   |

D 등급 트리거 — Phase 1 처럼 fixture 모두 D 면 ADR-0008 의 채택안 A (HTML→PDF) 가
**다음 단계** 에서 한계 가 드러난 것. 본 검수가 그 첫 신호.

---

## 5. 검수 시작 시 PM 가이드

검수 시작 신호 (와이프 OK) 가 오면 PM 이 다음 순서로 진행:

1. 와이프와 함께 §1.1 의 1~7 단계 한 번 따라가서 PDF 1건 확보.
2. 와이프가 §2 등급 정의 채움 + §2.1 합격선 체크.
3. 와이프가 §3 의 11 항목에 OK / NG / 의견 기록.
4. 결과를 본 문서 §6 (검수 기록) 에 추가.
5. v0.2 PR 들어갈 변경 사항 정리 → §4 매트릭스로 추정.

본 문서는 §3 의 답변이 들어오기 전까지 채워지지 않은 _가이드_ 단계.

---

## 6. 검수 기록 (진행 중 — 2026-05-07 1차 라운드)

### 6.1 검수 fixture

- 영어 지문: zero-waste stores (와이프 학원 자료가 아닌 PM 임의 sample, 6 paragraph,
  276 단어).
- worksheet 메타: 제목 "고2 영어 — Zero-Waste Stores" / subtitle "Week 01" / kind=
  student / template_id=playful / branding "테스트 학원" / theme `#1F4E79` / instruction
  "다음 글을 읽고 한글 해석과 어휘를 학습하세요."
- include_translation=true / include_vocabulary=true.
- annotation 0건 (학생 자료라 본 라운드는 annotation 검수 외).

### 6.2 LLM provider — Gemini 임시 전환 (2026-05-07)

Anthropic API 결제 이슈로 검수 단계만 Gemini 2.5 Flash Lite 로 임시 전환:
- `packages/llm/src/llm/gemini_client.py` 신규 — `StructuredLLMClient` Protocol 구현.
- `apps/api/.../config.py` 에 `llm_provider` / `google_api_key` 필드 추가.
- `apps/api/.../llm_setup.py` 가 `LLM_PROVIDER` 환경변수로 분기.
- `.env` 에 `LLM_PROVIDER=gemini` + `GOOGLE_API_KEY=...` 추가 (기기마다 직접 추가).
- `packages/llm/src/llm/augment.py` 의 LLM output schema 에서 `extra="forbid"` 제거
  (Gemini API 가 schema 의 `additionalProperties: false` 거절).
- 단위 테스트 6건 추가 (`packages/llm/tests/test_gemini_client.py`).

운영 단계 (Phase 3+ 또는 Anthropic 결제 후) 에는 `.env` 의 `LLM_PROVIDER=anthropic`
으로 되돌림. 두 client 코드 / 테스트는 그대로 유지 (멀티 provider 지원).

### 6.3 검수 산출물 (1차 라운드)

- `var/b5_review_preview.html` — HTML preview (커밋됨).
- `var/b5_review_worksheet.pdf` — Playwright PDF, overflow 정책 3차 패치 적용 후
  (커밋됨).

### 6.4 와이프 응답 (1차 라운드)

**§2.1 합격선**: `C 까지 합격` (사용자 체크).

**§3 답변**:
- A1 paragraph 보존: (b) 한국어로 짧게 쪼개도 OK.
- A2 영어 병기: 모두 영어 그대로 (Apple / Microsoft / Nature / Time).
- A3 idiom: (a) 의역만 (현재 정책 유지).
- A4 문체: (a) 평어 (현재 정책 유지).
- A5/A6: HTML preview 등급 자체가 A 라 자동 OK 가정 (NG 명시 없음).
- B1 count default: Q1 의 *어휘 박스 schema 확장* (유의어/반의어/예문 표 형태) 으로
  흡수됨 — count default 자체의 의미 약화. 별 항목으로 갈음.
- B2 level_label: 동일하게 schema 확장에 흡수 — 평소 라벨은 와이프와 별 라운드
  (v0.2-γ 작업 시) 에서.
- C1/C2/C3: annotation fixture 별도 필요 → Phase 1 baseline 검수와 함께. 본 라운드
  검수 외.

**HTML 자체 등급**: `A` (사용자 평가).

**PDF 등급 — 진행 중 (5차 결과 대기 — 2026-05-07)**:
- 1차 (overflow 정책 미적용): 두 페이지로 찢어지면서 한글 해석 + 어휘 박스 *사라짐*.
  본문도 두 번째 페이지로 밀림. → D 등급에 가까움.
- 2차 (CSS 1차 패치 — `break-inside: avoid` 적용): 빈 페이지 1개 추가됨 + footer
  가 페이지 중앙에 떠 다님.
- 3차 (CSS 2차 패치 — 박스 분할 허용 + footer position fixed + 어휘 *항목 단위*
  묶음): page1 거의 빈 표지화 (q-passage 가 통째 page2 로 밀림). page1 = 103자, page2 = 2598자.
- 4차 (override fix — `.q { page-break-inside: auto !important }` 로 screen
  cascade 덮어쓰기 + 본문 12pt + line-height 2.78 + 어휘 박스 q 밖으로 분리 + 5컬럼 표):
  page1 표지화 해소 (2 페이지로 정착, page1 본문/해석/어휘 시작 + page2 어휘 표 일부).
  q 박스가 footer 영역 침범 시각 잔존.
- **5차 (D안 — Playwright Chromium native `display_header_footer` + `margin`
  채택, ADR-0015 작업 진행 중)**:
  - fixed footer / `.body padding-bottom` / `@page margin` 모두 제거.
  - `pdf.py` 의 `page.pdf()` 에 `margin={"top": "12mm", "bottom": "33mm"}` +
    `footer_template=footer_html` 전달.
  - footer 부분 템플릿 신규 (`templates/_pdf_footer.html`) — Chromium native
    `<span class="pageNumber">` / `<span class="totalPages">` 자동 갱신.
  - `.banner { margin-top: -12mm }` — page1 banner 종이 위 붙음 보정 (음수 마진).
  - 어휘 표 `<tr>` 단위 `break-inside: avoid` + table 자체 `break-inside: auto`.
  - **검증**: 박스 y_max=750.0 ≈ 한계선 748.0 (오차 0.7mm), page1 first_y=52.4
    (banner 종이 위), page2 first_y=54.6 (12mm 상단 여백 적용), footer 모든 페이지 표시,
    page3 에 thead + biodegradable 1행 (시각상 어색 가능 — 와이프 평가 대상).
  - 회귀 검증: `packages/template_renderer/tests` 48 green +
    `apps/api/tests/test_routers/test_worksheets_router.py` 65 green
    (`level_label` → 표 헤더 `단어 (품사) / 한글 뜻` 검증으로 갱신, v0.2-α 의도
    반영).
  - **상태**: 사용자가 PDF 확인 후 등급 부여 대기 — 본 5차 결과로 §6.4 채움.

**§6.4 최종 (5차 결과, 2026-05-07)**:
- **PDF 퀄리티 등급**: `A` (사용자 평가 — "기능 자체는 A. 디자인/컨텐츠는 변경
  영역이지 기능 결함 아님").
- **§2.1 합격선** (사용자 사전 체크): C 까지 합격 → A 등급은 합격선 *훌쩍 초과*.
- **결론**: B5 검수 OK → Phase 2 baseline 종료 → v0.2-α 머지 → Phase 2-edit
  sprint (ADR-0015) 시작 신호.
- **§4 매트릭스 정합 노트**: 매트릭스 첫 행 ("11건 모두 OK → 0 PR") 는 검수
  *시작 전* 가정. 실제로는 검수 진행 중 5차에 걸쳐 v0.2-α 작업이 누적되어
  PR 머지 필요. v0.2-β 는 5차 채택안 (Chromium native pageNumber/totalPages)
  으로 자동 해소되어 별 PR 불필요. v0.2-γ (Vocabulary schema 확장) 는 본 sprint
  외 영역 — 별 ADR.
- **디자인/컨텐츠 후속 영역 (별 sprint 또는 점진 개선)**:
  - CLAUDE.md §2.1 Phase 2 점진 개선 영역 — 타이포그래피 / 여백·간격·정렬 /
    어휘 박스 강조 / 다중 템플릿 / 로고·컬러 외 프리셋.
  - ADR-0015 Phase 2-edit sprint — 사용자 편집 UI (translation 인라인 편집 /
    vocabulary 행 편집 / passage paragraph 분할).

### 6.5 v0.2 PR 분리 (예정)

검수 결과에 따라 다음 PR 들로 분리:

- **v0.2-α (overflow 정책 + Chromium native footer + 박스 한계선 + 어휘 표 분리)**:
  현재 `docs/b5-wife-review-prep` 브랜치에 작업 누적. 5차 결과 OK 면 별 PR 로 분리 머지.
  - **5차 채택안 (D안 — Chromium native)**:
    - `packages/template_renderer/src/template_renderer/pdf.py` —
      `render_worksheet_pdf()` 에 `footer_html` 인자 추가, `page.pdf()` 에
      `display_header_footer=True` + `margin={"top":"12mm","bottom":"33mm"}` +
      `footer_template` 전달. 기존 시그니처 backward compat (footer_html 빈
      문자열 시 fallback 경로).
    - `packages/template_renderer/src/template_renderer/render.py` —
      `render_pdf_footer_html()` 신규 (footer 부분 템플릿 별도 렌더).
    - `packages/template_renderer/templates/_pdf_footer.html` 신규 — 인라인
      스타일 + Chromium native `pageNumber` / `totalPages` variable 사용.
    - `packages/template_renderer/templates/playful.html` —
      `<footer class="footer">` HTML 블록 / `.footer { position: fixed }` /
      `.body { padding-bottom }` / `@page margin` 모두 제거.
      `.banner { margin-top: -12mm }` 추가 (page1 banner 종이 위 붙음 보정).
      `.q-vocabulary__table tr { break-inside: avoid }` + table 자체
      `break-inside: auto` (어휘 행 단위 분할).
    - `apps/api/src/worksheet_api/routers/worksheets.py` —
      `_build_worksheet_html()` 시그니처 `(Worksheet, str)` →
      `(Worksheet, str, dict)` 로 context 반환 추가. PDF export 라우트가
      `render_pdf_footer_html(context)` 호출 후 `render_worksheet_pdf` 에
      전달.
  - **CSS 변경 (1~4차 누적, 5차에서 일부 제거됨 정합)**: `.page`
    overflow/min-height 풀기 + `.q*` break-inside auto !important + 어휘 항목
    단위 묶음 + 헤딩 break-after avoid.
  - **본문/표 변경 (검수 답변 흡수)**: 본문 12pt + line-height 2.78 (150% ↑) +
    어휘 박스 큰 q 박스 *밖* 으로 분리 + 5컬럼 표 (단어(품사)/한글뜻/유의어/
    반의어/예문) — 유의어/반의어/예문 컬럼은 v0.2-γ 까지 빈 칸.
  - 회귀 테스트: `packages/template_renderer/tests` 48 green + 라우터
    테스트 65 green (`level_label` → 표 헤더 검증으로 갱신).
- **v0.2-β (page counter fix)**: **5차 채택안 D 에서 자동 해소** —
  Chromium native `<span class="pageNumber"></span>` / `<span class="totalPages"></span>`
  가 매 페이지 자동 갱신. 별 PR 불필요.
- **v0.2-γ (Vocabulary schema 확장)**: 큰 변경. 본 sprint 종료 후 별 ADR 로
  진행 — Phase 2-edit (ADR-0015) sprint 와 별개 영역.
  - `shared/schemas/vocabulary.py` 에 `synonyms` / `antonyms` / `example_sentences`
    필드 추가 (Pydantic + Alembic 마이그레이션).
  - `docs/prompts/augment-vocabulary-v0.md` 갱신 (출력 schema 확장).
  - `playful.html` 의 어휘 표는 v0.2-α 에서 이미 5컬럼 형태로 준비됨 — 컬럼만
    채워지면 됨.
  - 별 ADR 신규 — Vocabulary v0.2 schema. (PM 결정 영역 — 표 컬럼 / 페이지 분할 정책.)

### 6.6 인계 노트 (기기 간 컨텍스트 복원용)

다른 기기에서 작업 이어가는 경우 (예: 맥북 → 아이맥):
1. `git pull origin docs/b5-wife-review-prep` 후 본 문서 (`docs/phase-2-wife-review-prep.md`)
   읽기 — §6.1~6.5 가 현재 상태.
2. **`.env` 에 `LLM_PROVIDER=gemini` + `GOOGLE_API_KEY=...` 추가** (gitignore 됨,
   기기마다 직접 입력 필요. 키는 Google AI Studio 에서 새로 발급 권장).
3. `uv sync --all-packages` 로 venv 복구 (Gemini SDK / Playwright 등 deps).
4. `playwright install chromium` (이미 있으면 skip — `~/Library/Caches/ms-playwright`
   확인).
5. Docker DB 가동: `docker compose up -d db`.
6. Alembic head 적용: `cd apps/api && uv run alembic upgrade head` (이미 head 면 skip).
7. API 서버 (워크스페이스 루트에서):
   ```bash
   uv run python -c "
   from dotenv import load_dotenv
   load_dotenv('.env')
   from worksheet_api.main import app
   import uvicorn
   uvicorn.run(app, host='127.0.0.1', port=8000, log_level='info')
   "
   ```
8. PDF 재검수 — 두 가지 옵션:
   - **(a) 같은 worksheet 재사용**: 맥북에서 만든 worksheet_id 가 *같은 DB* (Docker
     volume) 에 있으면 그대로:
     ```bash
     curl -sX POST http://localhost:8000/worksheets/247d1ebd-d5e7-4c3d-a7d6-8bc011409cf9/export.pdf \
       > var/b5_review_worksheet.pdf
     ```
   - **(b) 새 worksheet 생성**: DB 가 다르면 §1.1 의 1~5 단계 재실행. 자동 스크립트
     `/tmp/b5_review_run.py` (PDF 만 깨졌으니 그 파일 위에 zero-waste 지문 / fixture
     메타 그대로) — 단 `/tmp` 는 기기 종속. PDF 만 재생성하려면 직접 curl 패턴.
9. PDF 열어 `var/b5_review_worksheet.pdf` 결과 와이프와 함께 §2.1 등급 + §6.4 PDF
   3차 결과 평가.
10. 결과 본 문서 §6.4 의 "PDF 등급 — 진행 중" 부분 채움 → v0.2-α 머지 또는 추가
    패치 진행.

**Claude 가 컨텍스트 복원할 때** — 본 문서 §6 + `git log --oneline -10` + 마지막
PR (#57) 머지 시점만 보면 지금까지 한 작업 거의 다 파악 가능. 메모리 (기기 단위
로컬) 와 별개로 본 문서가 인계 source-of-truth.

집에서 Claude 에게 던질 첫 메시지 예시:
> "퇴근 후 이어서 작업한다. `docs/phase-2-wife-review-prep.md` §6 읽고 어디까지
> 진행됐는지 파악한 다음, PDF 3차 결과 와이프와 검수 시작하려고 해. 셋업 가이드
> §6.6 따라가서 API 서버 띄워주고, PDF 다시 생성해줘."

### 6.7 Phase 2-edit Sprint 정의 (후속)

B5 검수 결과 = A/B/C 등급 시 본 sprint 종료 → **Phase 2-edit sprint 시작
신호**. `docs/adr/0015-phase-2-edit-sprint.md` 가 sprint 범위 / Stage E1 (백엔드
PATCH 라우트) / Stage E2 (학생 자료 편집 UI) / Stage E3 (Passage 편집 UI) +
PM 결정 항목 (D3-D6) 정의. 와이프가 학생 자료 1건을 *UI 만으로* 완성 가능하게
하는 것이 종료 조건.

D 등급 시 본 sprint 보류 → ADR-0008 채택안 한계 → 별 phase 신규.
