# ADR 0008 — Phase 1 출력 포맷 PDF 전환 결정 (HWPX 텍스트 재현 → PDF)

- **상태(Status)**: Accepted
- **작성일**: 2026-05-04
- **결정일**: 2026-05-04
- **작성자**: architect (초안)
- **결정자**: PM (Dennis)
- **채택안**: **A — HTML→PDF (브라우저 클라이언트-사이드 print 렌더링)** + 부수적
  PNG export
- **유형**: Phase 1 마감 차단 해제 ADR — P1-9 와이프 검수 결과 (HWPX 출력 D 등급 / 사용
  불가) 에 대한 출력 방향 재결정. Phase 2/3 출력 경로에도 영향.
- **관련 task**: `docs/phase-1-backlog.md` §2.4 P1-10d (본 ADR 의 출처) → P1-10e (구현)
- **관련 문서**:
  - `CLAUDE.md` v0.7 §1.3 ("HWPX 우선" 원칙) / §2.1 Phase 1 DoD #3 / §3.5 (HWPX
    렌더링 결정) / §3.6 (No Reinventing the Wheel)
  - `docs/phase-1-wife-feedback.md` (P1-9 검수 — fixture 3건 D 등급 / 와이프 대안 2가지)
  - `docs/adr/0007-bracket-hwpx-representation.md` (HWPX bracket 결정 — 본 ADR 채택 시
    의미 약화 / 보존 처리)
  - `docs/annotation-hwpx-mapping.md` (P1-7 매핑 카탈로그 — 본 ADR 채택 시 deprecate
    범위)
  - `docs/hwpx-align-poc.md` (P1-0b PoC — 한컴 floating textBox clamp 한계)
  - `packages/hwpx_renderer/` (deprecate 대상)

---

## Context (배경)

### 1. CLAUDE.md §1.3 의 출발점

`CLAUDE.md` §1.3 "HWPX 우선" — "한국 학원 시장의 표준 포맷을 1급으로 지원" 이 Phase
1 DoD #3 ("단일 지문에 대해 HWPX 출력이 와이프가 검수해서 OK 받을 수준") 의 근거였다.
이 원칙 위에서 Phase 1 의 출력 경로는 **HWPX 텍스트 재현** 으로 설계됐다.

### 2. HWPX 텍스트 재현 시도와 누적된 한계 (P1-7 ~ P1-9)

| Task | 시도 | 발견된 한계 |
|---|---|---|
| P1-0b | floating textBox 로 라벨 띄우기 | 한컴이 floating textBox 를 단락 라인 높이로 clamp — 본문 위/아래 정확 align 불가 |
| P1-7 | 7종 annotation × HWPX 매핑 카탈로그 | 라벨은 3단 단락 구조로 우회, bracket 은 Unicode, 화살표는 `hp:line` 도형 — 한컴 layout engine 의존 함정 누적 |
| P1-8a | 텍스트 런 highlight / underline / inline_note | charPr id 비연속 / `<hh:underline type>` SINGLE 무효 / `opf:item id` 확장자 등 한컴 스펙 함정 fix 라운드 3회 |
| P1-8b | 라벨 / 괄호 (3단 단락 + Unicode) | 라벨 수평 align 한계 (단락 indent 근사 — pixel-level 불가) |
| P1-9 | API + 와이프 검수 | **fixture 3건 모두 D 등급 — "냉정하게 사용 불가"** |

### 3. P1-9 와이프 검수 결과 (2026-05-04, PM 가 와이프 대신 검수)

`docs/phase-1-wife-feedback.md` §3.1~§5 발췌:

> **에디터 자체**: fixture 3건 모두 종합 등급 **A** — 작성/저장/칩 수정 흐름 사용 가능.
>
> **HWPX 출력**: **D 등급 (사용 불가)**. 한컴오피스에서 연 결과 에디터 화면 재현이
> 깨져 PM 판정 "냉정하게 사용 불가".
>
> 와이프 대안 제시:
> - HTML 렌더링 + PDF 출력
> - 에디터 패널을 이미지화 → HWPX 안에 삽입
>
> "두 대안 모두 Overflow 에 대한 로직은 필요해. (출력 페이지는 A4 용지 세로방향 기준
> 이고, 지문 박스를 넘어가는 경우)"

### 4. PM 의 사용 시나리오 인사이트 (2026-05-04 인터뷰)

> 강사들이 한글문서 편집을 많이 해. 근데 본인들이 사용하는 템플릿을 많이 쓰거든,
> 거기에 Editor 결과물만 껴넣도록 하는 방향이면 이미지나 pdf 형태로 출력해주면
> 복붙해서 써도 될 거 같거든.

→ 1차 사용자 (와이프) 의 실제 워크플로우는 **"에디터 결과물을 강사 본인 한컴 템플릿에
붙여넣기"**. 따라서 **재현 정확도가 최우선** 이고, 한컴 안에서 텍스트 단위 편집 가능
여부는 **부차적 요건**. 이 인사이트가 결정의 핵심 지렛대.

---

## 옵션 비교

### A. HTML→PDF (브라우저 클라이언트-사이드 print)

- **구현**: 에디터 본문 + annotation 을 print stylesheet (`@page size: A4 portrait` +
  `page-break-inside`) 로 렌더 → `window.print()` 또는 동등 클라이언트 라이브러리
  (jsPDF, html2pdf, react-to-print 등 — P1-10e 에서 No Reinventing the Wheel 평가).
- **장점**:
  - 에디터 화면 그대로 재현 — Tiptap DOM 을 그대로 인쇄 → 시각 충실도 100%.
  - 클라이언트 부담만, 추가 인프라 0 (서버사이드 headless 브라우저 불필요).
  - PDF 는 한컴 / Word / Mac Preview / 모바일 모두 표준 지원.
  - Phase 2 학생 배포용 자료 / Phase 3 변형문제집 모두 PDF 가 표준 출력 — 한 경로로
    Phase 전체 커버.
- **단점**:
  - 한컴에서 텍스트 단위 편집 불가 (PDF). 단 PM 의 사용 시나리오상 부차적.
  - 브라우저별 print 동작 차이 (Chrome/Safari) — Phase 1 baseline 은 단일 사용자 (와이프)
    환경에 맞춤, 다중 브라우저 호환은 Phase 4 진입 시 보강.
  - A4 overflow 의 자동 페이지 분할 로직 별도 구현 필요 (모든 안 공통).

### B. HTML→PDF (서버사이드 Playwright headless)

- **구현**: 백엔드에서 Playwright/Puppeteer headless Chrome 으로 에디터 페이지 렌더 →
  PDF 추출 → API 응답.
- **장점**:
  - 클라이언트 / 브라우저 차이 없음 (서버에서 단일 Chrome 버전 고정).
  - 서버에서 인증·권한 / 워터마크 등 후가공 가능.
- **단점**:
  - 서버 인프라 부담 — Playwright 컨테이너 (Chrome 포함) 가 기존 FastAPI 컨테이너에
    추가. 메모리·디스크·콜드 스타트 비용.
  - 단일 사용자 (Phase 1 ~ Phase 3) 환경에 과한 인프라.
  - 클라이언트의 실시간 에디터 상태 (저장 안 한 변경) 는 서버에서 못 봄 — "에디터
    그대로" 재현이 미세하게 어긋날 수 있음.
- **결론**: Phase 4 클라우드 배포 시 재검토 가치 있음. Phase 1 baseline 으론 과함.

### C. 에디터 패널을 PNG 캡처 → HWPX 삽입

- **구현**: 클라이언트에서 에디터 본문 영역을 html2canvas / dom-to-image 로 PNG 캡처
  → 백엔드의 HWPX 렌더러가 본문을 비우고 PNG 이미지를 본문에 삽입.
- **장점**:
  - 한컴에서 파일 자체는 HWPX (확장자) — §1.3 의 표면적 충실.
  - PNG 가 에디터 화면 그대로 재현.
- **단점**:
  - 한컴 안에서 본문 텍스트 편집 불가 (PNG 이미지 덩어리).
  - PNG 단독은 Phase 2 학생 배포에 약함 — 확대 시 깨짐, 텍스트 검색·복사 불가, 고해상도
    인쇄 시 anti-aliasing 흔적.
  - HWPX 안의 PNG 는 한컴 layout 에서 페이지 분할이 자유롭지 않음 (이미지가 한 단락에
    묶여 페이지 경계 처리 어색).
- **결론**: PDF 출력의 부수 옵션으로 PNG export 만 따로 제공하는 게 더 적합 (강사가
  본인 한컴 템플릿에 1-step 으로 이미지 삽입). HWPX 안에 PNG 삽입까지 자동화할
  필요는 없음.

### D. 현재 HWPX 텍스트 재현 미세 개선 (라벨 위치 / 폰트 metric / pixel-level align)

- **구현**: P1-8b 의 3단 단락 + bracket Unicode + 텍스트 런 위에서 폰트 metric 보정
  강화 / 라벨 indent 보정 알고리즘 정밀화.
- **장점**:
  - 기존 코드 자산 (`packages/hwpx_renderer/`) 보존.
  - 한컴에서 텍스트 단위 편집 가능 — §1.3 의 본질에 가장 충실 (표면적).
- **단점**:
  - **와이프 검수 D 등급 — 미세 개선으로 도달 불가능 판정**. 한컴 layout engine 함정
    이 P1-8a/b 에서 누적적으로 노출됨 (charPr id 비연속, `hh:underline type` 무효, 라벨
    floating textBox clamp 등).
  - pixel-level align 은 한컴 layout engine 비공개 동작에 의존 — 폰트 metric / 줄간격
    / 단락 indent 셋의 상호작용을 외부에서 정확히 재현 불가.
  - 매몰비용 (P1-8a/b 의 누적 코드) 회복하려는 sunk cost fallacy 위험.
  - Phase 2/3 출력 경로 결정 차단 — 각 Phase 마다 같은 한계 재발.

### 평가 매트릭스

| 기준 | A: HTML→PDF (클라이언트) | B: HTML→PDF (서버) | C: PNG→HWPX 삽입 | D: HWPX 텍스트 재현 미세 개선 |
|---|---|---|---|---|
| CLAUDE.md §1.3 본질 (한국 학원 워크플로우) | ✅ 강사 한컴 템플릿에 PDF/PNG 붙여넣기 가능 | ✅ 동일 | ✅ HWPX 확장자 유지 | ✅ HWPX 직접 출력 |
| CLAUDE.md §1.3 표면 ("HWPX 우선") | ⚠️ 표면적 위반 — 본 ADR §6 에서 원칙 갱신 권고 | ⚠️ 동일 | ✅ | ✅ |
| 한컴 텍스트 편집 가능 여부 | ❌ PDF | ❌ PDF | ❌ PNG 이미지 | ✅ HWPX |
| 시각 재현 정확도 (와이프 검수 통과 가능성) | ✅ 에디터 DOM 그대로 | ✅ 동일 | ✅ PNG 캡처 그대로 | ❌ D 등급 / 미세 개선 도달 불가 판정 |
| Phase 2/3 일관성 | ✅ 학생 배포 / 변형문제집 모두 PDF 표준 | ✅ 동일 | ⚠️ PNG 단독 학생 배포 부적절 | ⚠️ Phase 마다 한컴 함정 재발 |
| A4 overflow 자동 페이지 분할 | ⚠️ `@page` + `page-break-inside` 구현 필요 (CSS 표준) | ⚠️ 동일 | ❌ HWPX 안 PNG 페이지 분할 어색 | ⚠️ HWPX 단락 자체 분할은 자연스러움 |
| 구현 복잡도 | ✅ 클라이언트 print stylesheet — Phase 1 적정 | ❌ Playwright 컨테이너 추가 | ⚠️ 클라이언트 캡처 + 서버 HWPX 재구성 | ❌ 한컴 layout engine 함정 누적 |
| 인프라 / 운영 부담 | ✅ 추가 인프라 0 | ❌ headless Chrome 서버 추가 | ⚠️ 캡처 라이브러리만 | ✅ 기존 그대로 |
| 와이프 평가 A/B 등급 도달 가능성 | ✅ 시각 재현 충실로 高 | ✅ 동일 | ✅ PNG 캡처 충실로 高 | ❌ 검수에서 D 판정 — 미세 개선 도달 불가 |
| sunk cost (`packages/hwpx_renderer/`) | ⚠️ deprecate (코드 보존, 신규 사용 금지) | ⚠️ 동일 | ⚠️ 부분 재활용 | ✅ 보존 |

---

## 결정 (PM 채택안)

> **상태**: Accepted (2026-05-04). PM 이 P1-9 검수 결과 직후 PM 인터뷰 + 와이프 대안
> 평가 + Phase 2/3 일관성 고려해 결정.

### 채택: **A — HTML→PDF (브라우저 클라이언트-사이드 print)** + 부수적 PNG export

**근거 (3개)**:

1. **B 대비 인프라 비용**. Phase 1 ~ Phase 3 은 단일 사용자 (와이프) 환경. 서버사이드
   headless Chrome 컨테이너 추가는 과함. Phase 4 클라우드 배포 시 재검토 가치 있음.

2. **C / D 대비 Phase 2/3 일관성**. PNG 단독 (C) 은 학생 배포 (Phase 2) 에 부적절
   (확대 깨짐, 검색·복사 불가). HWPX 텍스트 재현 (D) 은 Phase 마다 한컴 layout 함정
   재발. PDF (A) 는 Phase 2 학생 배포 / Phase 3 변형문제집 모두 표준 — 한 경로로 Phase
   전체 커버.

3. **D 대비 실제 검수 결과**. P1-9 에서 와이프가 D 등급 판정 + "냉정하게 사용 불가" /
   "재설계하거나 대안 모색 필요" 명시. 미세 개선으론 도달 불가. 매몰비용 회복하려는
   sunk cost fallacy 위험.

**부수 PNG export 의 근거**: PM 인터뷰의 "강사 본인 한컴 템플릿에 복붙" 시나리오 →
PDF 는 페이지 단위 / PNG 은 영역 단위. 강사가 한컴에서 그림 삽입으로 1-step 끝낼 수
있게 PNG 도 부수 제공.

### 리스크 / 잔존 트레이드오프

- **한컴에서 PDF 텍스트 편집 불가** — 와이프가 PDF 안의 텍스트를 직접 수정하길 원하면
  대안 재검토. 단 PM 인터뷰 인사이트로 이 시나리오는 우선순위 낮음.
- **브라우저별 print 동작 차이** — Phase 1 은 단일 사용자 환경 (와이프 Mac + Chrome /
  Safari 예상) 에서 OK 면 Phase 1 DoD #3 충족. 다중 브라우저 호환은 Phase 4 진입 시
  보강.
- **클라이언트 라이브러리 도입** — `window.print()` 만으로 부족하면 jsPDF / html2pdf /
  html2canvas 등 도입 검토. 본 ADR 은 후보만 제시, 실제 도입은 P1-10e 에서 CLAUDE.md
  §3.6 (No Reinventing the Wheel) 원칙으로 평가 기록.

---

## 함께 결정 / 영향

### `packages/hwpx_renderer/` 처리

- **deprecate** — 신규 사용 금지. 즉시 삭제는 X. 코드는 보존 (Phase 2/3 의 "강사 한컴
  템플릿 + 이미지/PDF 삽입" 워크플로우 후 검토 시 참고 가능, ADR-0007 결정 등 함께
  보존).
- 에디터 페이지의 "HWPX 다운로드" 버튼은 P1-10e 에서 deprecate 표기 / 숨김 — UX
  결정은 frontend-dev 가 P1-10e 에서.

### ADR-0007 (bracket Unicode 표현) 의 의미 변화

- 본 ADR 채택 시 bracket Unicode 의 HWPX 출력 의미는 약화 (HWPX 출력 자체가
  deprecate). 하지만 Tiptap 에디터 본문에서 bracket 을 Unicode 글자로 inline 표시하는
  결정은 그대로 유효 (PDF 출력은 에디터 DOM 을 그대로 인쇄 → 동일 글자 그대로 보임).
- ADR-0007 상태 갱신 불요 — bracket 표현의 데이터 결정은 보존.

### `docs/annotation-hwpx-mapping.md` 처리

- **deprecate 표기 권고** (별 PR). HWPX 텍스트 재현 매핑은 신규 작업 입력으로 사용 금지.
  단 자료 보존 (Phase 2/3 의 "강사 한컴 템플릿 + 이미지 삽입" 검토 시 참고 가능).

### Phase 2 (학생 배포용 자료) 영향

- **CLAUDE.md §2.1 Phase 2 DoD**: 학생용 템플릿 (지문 + 한글 해석 + 어휘 박스) 가
  HWPX/PDF 양쪽 출력. 본 ADR 채택 시 **PDF 가 1차 출력**, HWPX 는 deprecate (강사
  한컴 템플릿 워크플로우는 PDF/PNG 로 대체). Phase 2 진입 시 Phase 2 DoD 의 "HWPX,
  PDF 양쪽 출력" 문구는 PM 결정으로 갱신 필요 — 본 ADR 의 자연 정합 결과.

### Phase 3 (변형문제) 영향

- 변형문제집 출력도 PDF 표준 — 본 ADR 의 출력 경로 재사용. 학생 배포는 PDF 가
  자연스럽고 검색·복사 가능. PNG 은 강사 한컴 워크플로우용으로만 부수 제공.

### Phase 4 (클라우드 배포) 재검토 항목

- 다중 사용자 환경에서 옵션 B (서버사이드 Playwright) 재검토 가치 — 클라이언트
  브라우저 차이 통제 / 서버에서 워터마크·권한 후가공 가능. Phase 4 ADR 후보로 표시.

---

## CLAUDE.md §1.3 "HWPX 우선" 원칙 정합성

본 결정은 **표면상 §1.3 위반** 처럼 보임 (HWPX → PDF 전환). 하지만 §1.3 의 본질은
"한국 학원 시장 표준 포맷 지원" — 강사가 한컴에서 본인 템플릿에 자료를 끼워넣는
워크플로우 (PM 인터뷰 §"PM 의 사용 시나리오 인사이트" 인용) 가 그 본질이다. PDF + PNG
는 이 워크플로우를 더 잘 지원한다.

따라서 §1.3 갱신 권고:

```
(현재) "HWPX 우선": 한국 학원 시장의 표준 포맷을 1급으로 지원
       ↓
(권고) "한국 학원 시장 워크플로우 우선": 강사 한컴 템플릿 호환 (PDF 출력 + PNG export)
       을 1급으로 지원. HWPX 직접 출력은 Phase 4 이후 재검토.
```

**CLAUDE.md 갱신은 본 ADR 머지 후 별 PR 로 진행 (본 ADR 의 범위 밖)**.

---

## 결정 후 P1-10e 작업 진입 절차

1. 본 ADR 머지.
2. `docs/phase-1-backlog.md` P1-10d 항목에 본 ADR PR 링크 추가 (별 PR 불요 — backlog
   메모만).
3. P1-10e 착수 — 다음 DoD:
   - 에디터 페이지에 **"PDF 다운로드" 버튼** 추가 (기존 "HWPX 다운로드" 버튼 옆 또는
     대체 — UX 결정).
   - 에디터 본문 + annotation 을 print stylesheet (`@page size: A4 portrait`,
     `page-break-inside: avoid` 등) 로 렌더 → `window.print()` 또는 동등 클라이언트
     라이브러리로 PDF 저장.
   - 부수적 **"PNG 다운로드" 버튼** — 본문 영역만 html2canvas / dom-to-image 등으로
     캡처. (라이브러리 후보는 P1-10e 에서 §3.6 원칙으로 평가 기록.)
   - **A4 세로 overflow**: 본문이 길면 자동 페이지 분할.
   - 기존 "HWPX 다운로드" 버튼은 deprecate 표기 (문구 변경 또는 숨김 — UX 결정).
   - fixture 3건 재출력 → PM (또는 와이프) 재검수 → A 또는 B 등급 도달 시 Phase 1 DoD
     #3 충족 선언.
4. CLAUDE.md §1.3 / §3.5 / §2.1 Phase 2 DoD 갱신 별 PR (본 ADR 머지 후).

---

## 결정 기록

| 날짜 | 상태 | 결정자 | 비고 |
|---|---|---|---|
| 2026-05-04 | Proposed | architect (초안) | P1-9 검수 결과 직후 — PM 결정 대기 |
| 2026-05-04 | Accepted | PM (Dennis) | P1-9 와이프 검수 D 등급 + PM 사용 시나리오 인터뷰 + Phase 2/3 일관성 고려해 A 채택. P1-10e 진입. |
