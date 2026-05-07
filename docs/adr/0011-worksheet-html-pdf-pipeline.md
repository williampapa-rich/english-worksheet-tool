# ADR 0011 — Worksheet HTML 템플릿 + Jinja2 렌더 + Playwright PDF 파이프라인 (사후 정리)

- **상태(Status)**: Accepted (사후 정리)
- **작성일**: 2026-05-07
- **결정일**: 2026-05-06 (PM 결정 5건 — `docs/template-rendering-analysis.md` §5)
- **구현 머지일**: 2026-05-06 ~ 2026-05-07 (PR #40 / #41 / #42 / #44 / #45)
- **작성자**: architect (사후 정리)
- **결정자**: PM (Dennis)
- **유형**: 사후 정리 ADR — 결정 사항이 PR 본문 + `docs/template-rendering-analysis.md`
  §5 + `packages/template_renderer/README.md` + ADR-0010 에 분산되어 있어, 단일 결정
  문서로 통합. 코드 변경 0.
- **사후 정리 사유**: ADR-0008 (Phase 1 출력 포맷 PDF 전환) 채택 직후 외부 작업자
  템플릿 자산 도입 (Stage 0, PR #40) 이 빠르게 진행되며 결정 사항이 분석 문서 +
  README + PR 본문에 기록됨. ADR 승격은 "Stage 1 진입 시" 로 미뤄졌으나 Stage 1/2
  머지 후에도 작성되지 않은 상태로 남음 — Phase 2 본격 진입 전 dangling reference
  (`README.md`, `analysis.md`, `CLAUDE.md` §11) 닫기.
- **관련 문서**:
  - `CLAUDE.md` v0.8 §1.3 (HWPX 우선 → §1.4 비-목표 와 결합 — Phase 1 baseline 후
    PDF 1급 지원 합의), §2.1 Phase 2 (학생 배포용 자료), §3.6 (No Reinventing the
    Wheel)
  - `docs/template-rendering-analysis.md` §1 (자산), §2 (정합성), §3 (병렬 진행), §4
    (Stage 권고), §5 (PM 결정 5건), §6 (위험), §7 (결론)
  - `docs/adr/0008-phase-1-output-format.md` (HWPX → HTML/PDF 전환 — 본 ADR 의 출발점)
  - `docs/adr/0010-worksheet-output-parameters.md` (Worksheet 출력 파라미터 확장 —
    Stage 1 schema 갭 해소)
  - `packages/template_renderer/README.md` (템플릿 디렉토리 + 데이터 계약 + Stage 진행
    상태)
  - `packages/template_renderer/templates/{classic,modern,playful}.html` (자산 3종)
- **관련 PR**:
  - PR #40 (`a3f24f6`, 2026-05-06) — Stage 0 자산 도입 (3종 템플릿 + 분석 문서)
  - PR #41 (`a3f6646`, 2026-05-07) — Stage 1 schema (subtitle / orientation /
    instruction / `WorksheetItem.label` + ADR-0010)
  - PR #42 (`2533560`) — Stage 1 ORM / Alembic / Branding 어댑터
  - PR #44 (`bfa011a`) — Stage 2 PR #1 — Jinja2 HTML 렌더 +
    `GET /worksheets/{id}/preview`
  - PR #45 (`293a772`) — Stage 2 PR #2 — Playwright PDF +
    `POST /worksheets/{id}/export.pdf`

---

## Context (배경)

### 1. ADR-0008 의 출구 — Phase 1 출력 포맷 PDF 전환

P1-9 와이프 검수 (2026-05-04) 에서 HWPX 텍스트 재현 출력이 fixture 3건 모두 D 등급
("냉정하게 사용 불가") 을 받았다. ADR-0008 이 채택안 A — **HTML→PDF (브라우저
클라이언트-사이드 print 렌더링)** + 부수적 PNG export 로 결정.

ADR-0008 은 *방향* 결정만 하고 구체 구현 (라이브러리 / 템플릿 / 렌더 파이프라인) 은
열어둠. 본 ADR 은 그 빈자리를 닫는다.

### 2. 외부 자산 도입 — 결정 사항이 분석 문서로 흘러감

ADR-0008 채택 직후 (2026-05-06), 외부 작업자가 작성한 워크시트 템플릿 3종 (`classic`
/ `modern` / `playful`) 을 자산으로 받았다. CLAUDE.md §3.6 "No Reinventing the
Wheel" 에 따라 직접 작성 대신 외부 자산 채택 — 단 검증된 템플릿이 아니므로 분석
문서 (`docs/template-rendering-analysis.md`) 에서 정합성 / 갭 / 위험을 정리하고 PM
결정 5건을 닫았다.

### 3. ADR 승격 지연

`docs/template-rendering-analysis.md` §7 의 "다음 액션" #3:

> ⏳ ADR-0011 승격은 **Stage 1 진입 시점** 으로 미룸 — Stage 2 PoC 결과 (Playwright
> 실측, 폰트 동작, 에디터 산출 HTML 호환성) 를 ADR 에 반영하기 위해.

이후 Stage 1 (PR #41 / #42) 머지 시점에 ADR-0010 (Worksheet 출력 파라미터) 만 작성되고
본 ADR 은 누락. Stage 2 (PR #44 / #45) 머지 시점에도 ADR 추가 작성 없이 진행. 결과적으로
결정 사항은 PR 본문 + analysis.md + README + ADR-0010 에 분산된 상태로 남았다.

### 4. 본 ADR 의 역할

새 결정을 하지 않는다. **분산된 결정 사항을 단일 문서로 통합** + dangling reference
(`README.md` "향후 ADR-0011", `analysis.md` "Stage 1 진입 시 승격", `CLAUDE.md` §11
"ADR-0011 / ADR-0012 파일 부재") 를 닫는다.

---

## Decision (결정)

본 절의 결정은 모두 PR 본문 / analysis.md / README / ADR-0010 에서 인용·정리한 것이다
(새 결정 X).

### D1. 디렉토리 구조 — `packages/template_renderer/`

CLAUDE.md §5 의 `packages/` 컨벤션 (`hwpx_renderer` 와 대칭). ADR-0008 채택으로
`hwpx_renderer` 가 deprecate 되며 자연 대체.

```
packages/template_renderer/
├── README.md                  # 데이터 계약 + 사용 가이드
├── pyproject.toml
├── src/template_renderer/
│   ├── __init__.py
│   ├── render.py              # Jinja2 HTML 렌더
│   ├── pdf.py                 # Playwright PDF
│   └── adapters.py            # Worksheet/Branding → template context
└── templates/
    ├── classic.html           # Style 1 (보관, MVP 미노출)
    ├── modern.html            # Style 2 (보관, MVP 미노출)
    └── playful.html           # Style 3 (★ MVP 채택)
```

(출처: PM 결정 #1 — `analysis.md` §5)

### D2. PDF 변환 — Playwright (headless Chromium)

- **채택 이유**: playful.html 의 `color-mix(in srgb, ...)` 등 모던 CSS 완전 지원.
  WeasyPrint / LibreOffice 대안은 모던 CSS 호환성 한계 (PR #45 본문 §"라이브러리 검토"
  섹션 참조).
- **함정**: 매 호출 Chromium launch — Stage 2 PoC 단계의 *의도적 단순화*. 운영 단계
  process pool 은 Stage 3 트리거 (메모리 `template_renderer_stage_1.md`).
- **CSS / 파라미터 일관성**: `@page size` 와 Playwright `landscape` 파라미터가 둘
  다 `worksheet.orientation` 한 값에서 파생 — 라우터에서 일관 전달 (README §"PDF
  렌더").
- **`print_background=True`** 누락 시 playful 의 컬러 배너가 PDF 에서 사라짐
  (회귀 함정).

(출처: PM 결정 #2 — `analysis.md` §5 + PR #45 본문)

### D3. 외부 폰트 — CDN 유지 (Pretendard / Noto Serif KR / Fraunces / Tabler Icons)

- **현 사용 환경 (와이프 가정용 인터넷)** 에서 사내망 proxy 차단 우려 없음.
- **함정**: CDN 응답 지연 시 PDF 렌더 hang. → `wait_until="load"` 정책으로 완화 (PR
  #45 적용).
- **자가 호스팅 트리거**: 클라우드 배포 (Phase 4) 진입 시 또는 사내망 환경 추가 시 →
  `packages/template_renderer/static/fonts/` 두고 `@font-face` 로컬 경로 참조하도록
  템플릿 수정.

(출처: PM 결정 #3 — `analysis.md` §5)

### D4. MVP 노출 정책 — `playful` 1종

- 3종 자산 중 **`playful` 1종만** 라우트 (`?style=playful`) 노출. `classic` /
  `modern` 은 templates/ 디렉토리 보관, 라우트 미노출.
- **이유**: CLAUDE.md §2.1 Phase 2 점진 개선 영역 ("다중 템플릿") 과 일치. Phase 2
  종료 후 와이프 피드백에 따라 추가 노출 검토.
- **추가는 라우트 단 갱신만** — 새 템플릿 자산 작성 / 데이터 계약 변경 없음.

(출처: PM 결정 #4 — `analysis.md` §5 + PR #44 본문)

### D5. `student.*` schema 도입 안 함

- `Worksheet` / `WorksheetItem` 어디에도 `student_*` 필드 추가 X.
- 렌더 시점에 어댑터가 빈 dict (`{"name": "", "class_name": "", "date": ""}`) 만 주입.
- **이유**: 학생 이름 / 반 / 날짜는 인쇄 후 학생이 손기입. 콘텐츠 생성 ≠ 학생별
  발급. CLAUDE.md §1.4 비-목표 ("학생 성적 관리") 와 인접 영역 확장 회피.
- 학생별 발급 요구가 실제 생기면 Phase 4 에서 별 `WorksheetIssue` 엔티티 (현 schema
  에 끼워 넣지 않음).

(출처: PM 결정 #5 — `analysis.md` §5 / ADR-0010 §D4)

### D6. 데이터 계약 — Jinja2 컨텍스트 dict 구조 (사후 흡수)

세 템플릿 모두 동일한 컨텍스트를 받는다. 사용자는 스타일만 바꿔서 렌더링.

```python
{
    "academy": {
        "name": str,             # Branding.academy_name (ADR-0010 D3)
        "theme_color": str,      # Branding.primary_color (CSS hex)
        "logo_url": str | None,  # Branding.logo_url
    },
    "worksheet": {
        "title": str,            # Worksheet.title
        "subtitle": str | None,  # Worksheet.subtitle (ADR-0010 D1 #1)
        "page_number": int,      # 렌더 시점 1 (ADR-0010 D5)
        "total_pages": int,      # 렌더 시점 1 (ADR-0010 D5)
        "orientation": str,      # WorksheetOrientation (ADR-0010 D1 #2 / D2)
    },
    "student": {                 # schema 미도입 (D5)
        "name": "",
        "class_name": "",
        "date": "",
    },
    "instruction": str | None,   # Worksheet.instruction (ADR-0010 D1 #3)
    "questions": [
        {
            "number": int,
            "label": str | None,        # WorksheetItem.label (ADR-0010 D1 #4)
            "content_html": str,        # ⚠ 한계 — D8 참조
        },
    ],
}
```

(출처: README "데이터 계약" 섹션 + ADR-0010 D1~D5)

### D7. 어댑터 위치 — `packages/template_renderer/adapters.py`

- `worksheet_to_template_context(worksheet, passages) -> dict` — `Worksheet` +
  `Passage[]` → 위 D6 컨텍스트 dict 변환.
- `branding_to_academy_dict(branding) -> dict` — `Branding` → `academy` dict 변환.

이 두 함수가 **schema 와 템플릿 컨텍스트 사이의 단일 경계**. 다른 곳에서 직접 dict
구성 금지 (코드 리뷰 체크 항목).

(출처: PR #42 본문 + README §"제공 함수")

### D8. `content_html` 의 현재 한계 — `<p>{escape(body_text)}</p>` 단순 wrap

- 현재 (PR #44 / #45 머지 시점) `WorksheetItem.content_html` 는 `Passage.body_text` 를
  `markupsafe.escape()` 후 `<p>` 로 wrap 한 *단순 형태*. 에디터 산출 annotation
  (highlight / underline / inline_note / top_label / bottom_label / bracket) 의 정밀
  표현은 하지 못함.
- **이유**: annotation split-mark 정밀 렌더 ADR (CLAUDE.md §11 Open Questions —
  "annotation split-mark 정밀 렌더 ADR") 가 미작성 상태. 에디터 산출 HTML / DOM tree 를
  worksheet HTML 컨텍스트에 안전하게 주입하는 방법이 결정되지 않음.
- **현재 정책** (PR #44 docstring 명시): 단순 wrap + XSS escape — 정밀 annotation 은
  Phase 1 baseline 와이프 OK 후 별 ADR 신규 + B4 (Worksheet preview 컨텍스트 주입)
  와 묶어 진행.
- **위험**: 에디터에서 작업한 annotation 이 worksheet preview / PDF 에서 *보이지
  않는다*. Phase 2 본격 진입 전 ADR 작성 필수.

### D9. XSS / 보안 정책

- `Jinja2` autoescape 활성화 (HTML escape 자동) — 사용자 입력은 모두 escape.
- `q.content_html | safe` 만 escape 우회 — *신뢰 가능한 소스* (직접 렌더링한 결과)
  만 넣음. 사용자 직접 HTML 입력 경로가 생기면 `bleach` 등 sanitizer 필요 (Phase 2
  시작 시 명시적 정책 결정 — analysis.md §6 위험 항목).
- **W-2 가드** (PR #44): cross-tenant `WorksheetItemORM` 차단 — 다른 tenant 의
  WorksheetItem 이 응답에 섞이지 않도록 명시 필터.

### D10. CSS `color-mix` / Tabler Icons 의존성 — 템플릿 엔진 lock-in 함정

- **`color-mix(in srgb, ...)`**: playful.html 사용. **Chromium 111+ 에서만 동작**.
  WeasyPrint 등 다른 PDF 엔진 전환 시 fallback 필요. → Playwright 채택 근거
  중 하나 (D2).
- **Tabler Icons**: playful.html 의 배지 아이콘. 외부 jsDelivr CDN. 자가 호스팅
  트리거는 D3 와 동일 (클라우드 배포 또는 사내망).

### D11. Stage 진행 상태

- [x] **Stage 0** (PR #40, 2026-05-06) — 자산 도입 + 분석 문서.
- [x] **Stage 1** (PR #41 / #42) — schema 갭 해소 + 어댑터.
- [x] **Stage 2** (PR #44 / #45) — Jinja2 + Playwright + 라우트.
- [ ] **Stage 3** — Web preview UI / customizing / 운영 캐싱 / Chromium pool.
  트리거: (a) 와이프가 PDF 응답 시간 불만, 또는 (b) 클라우드 배포 (Phase 4) 진입.
  현재 PoC 수준 (매 호출 Chromium launch) 으로 충분.

(출처: README §"Stage 진행 상태" + 메모리 `template_renderer_stage_1.md`)

---

## Consequences (결과)

### 긍정적 결과

1. **dangling reference 닫힘** — `README.md`, `analysis.md`, `CLAUDE.md` §11 Open
   Questions 의 "ADR-0011 부재" 항목이 모두 본 ADR 로 닫힘.
2. **결정 사항 단일 진술** — Phase 2 본격 진입 / 신규 작업자 / B4 (Worksheet
   preview 컨텍스트 주입) 진행 시 분산된 5개 출처 추적 부담 제거.
3. **ADR-0010 와의 cross-ref 명료화** — ADR-0010 (Worksheet 출력 파라미터) 이 본
   ADR 의 schema 측 결정, 본 ADR 이 *렌더 파이프라인 측* 결정. 둘이 한 시스템의 양면.
4. **annotation split-mark 정밀 렌더 ADR 의 자리 명시** — D8 한계 명시로 다음 ADR
   trigger 가 분명.

### 부정적 결과 / 리스크

1. **사후 정리 ADR 의 한계** — 본 ADR 은 *새 결정* 을 하지 않으므로, 결정 사항이
   살짝 어긋나거나 PR 본문이 본 ADR 보다 더 정확한 경우가 있을 수 있다 (실제 코드
   = source of truth). 본 ADR 은 *지도* — 정확한 측량은 코드 / PR 본문.
2. **Stage 3 트리거 정의 불명확성** — "와이프가 불만" 이 trigger 라 측정 가능
   기준이 없음. 클라우드 배포 (Phase 4) 시점이 더 명확한 trigger — 그 시점에 동시성
   / 비용 검토 필수.
3. **D8 annotation split-mark ADR 미작성 부담** — Phase 2 본격 진입 차단 요소.
   B4 (Worksheet preview 컨텍스트 주입) 직전에 작성 필수 — 본 ADR 이 그 차단을 명시.

### 후속 작업

- **CLAUDE.md §11 갱신** — "ADR-0011 / ADR-0012 파일 부재" 항목 정정. ADR-0011 은
  본 ADR 로 닫힘. ADR-0012 는 (메모리 가정과 달리) 코드 어디에도 참조 없음 — B2 의
  ADR-0013 으로 다음 번호 자연 사용.
- **`packages/template_renderer/README.md` 갱신** — "향후 ADR-0011" 표기 → "ADR-0011"
  로 갱신 (본 PR 에 포함).
- **`docs/template-rendering-analysis.md` §7 갱신** — "Stage 1 진입 시 승격" 표기 →
  "사후 정리됨 (2026-05-07)" 으로 갱신 (본 PR 에 포함).
- **annotation split-mark 정밀 렌더 ADR (별 PR)** — Phase 2 본격 진입 전. D8 의
  `<p>{escape(body_text)}</p>` 한계 해소.
- **Stage 3 ADR (별 PR, 트리거 발생 시)** — 운영 캐싱 / Chromium pool /
  BackgroundTasks.

---

## 대안 검토 요약

본 ADR 은 사후 정리 — 새 대안 검토 없음. 원 결정의 대안은 다음 출처 참조.

| 항목 | 채택 | 탈락 후보 | 출처 |
|---|---|---|---|
| PDF 라이브러리 | Playwright (D2) | WeasyPrint / LibreOffice | PR #45 본문 |
| 폰트 정책 | CDN (D3) | 자가 호스팅 (Phase 4 트리거) | analysis.md §5 #3 |
| MVP 템플릿 | playful 1종 (D4) | 3종 모두 노출 / classic 단독 | analysis.md §5 #4 |
| `student.*` 도입 | 도입 안 함 (D5) | Worksheet schema 추가 / 별 발급 모델 즉시 도입 | analysis.md §5 #5 / ADR-0010 D4 |
| 어댑터 위치 | `template_renderer/adapters.py` (D7) | 라우트 핸들러 직접 / shared 위치 | PR #42 본문 |

---

## 결정 기록

| 날짜 | 상태 | 결정자 | 비고 |
|---|---|---|---|
| 2026-05-06 | 분산 결정 | PM | `analysis.md` §5 PM 결정 5건 + ADR-0008 채택. ADR 승격은 "Stage 1 진입 시" 로 미룸. |
| 2026-05-06 ~ 2026-05-07 | 구현 머지 | PM / backend-dev / frontend-dev | PR #40 / #41 / #42 / #44 / #45 — Stage 0~2 머지. ADR 추가 작성 없이 진행. |
| 2026-05-07 | Accepted (사후 정리) | architect (사후) | 분산된 결정 사항을 단일 ADR 로 통합. dangling reference 3개 닫음. 새 결정 X — `analysis.md` / `README` / PR 본문 / ADR-0010 인용. |
