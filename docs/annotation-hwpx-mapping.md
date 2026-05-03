# Annotation → HWPX 매핑 카탈로그 (P1-7)

- **작성일**: 2026-05-03
- **작성자**: architect agent
- **task**: Phase 1 백로그 P1-7 (`docs/phase-1-backlog.md` §2.4)
- **직접 입력**:
  - `docs/hwpx-align-poc.md` §5 권고사항 (P1-0b 머지 결과)
  - `packages/hwpx_renderer/src/hwpx_renderer/poc_align.py` (실제 PoC 구현 패턴)
  - `shared/schemas/annotation.py` v0.2 (P1-3 머지 — 7종 `AnnotationKind` + `AnnotationSpan` discriminated union + arrow 비대칭 표현)
- **CLAUDE.md 참조**: §3.5 (하이라이트·밑줄 = 텍스트 런 / 라벨 = 텍스트박스 / 화살표 = 도형 우선)
- **본 PR 범위**: `docs/annotation-hwpx-mapping.md` 1개 파일 신설. 코드/스키마 변경 없음.
- **다음 task**: P1-8 (HWPX 렌더러 구현). 본 문서가 PR 분할 (a/b/c) 의 분할 기준.

---

## 0. 요약

| # | 결론 |
|---|---|
| 1 | CLAUDE.md §3.5 의 "라벨 = 텍스트박스" 결정은 P1-0b PoC 결과 **번복**. 채택안은 **3단 단락 구조** (라벨 단락 / 본문 단락 / 라벨 단락). 사유 = 한컴이 `vertRelTo="PARA"` + `vertOffset` 음수/양수 조합의 floating textBox 를 단락 라인 높이 안에 clamp 하여 본문 위/아래로 올라가지 않음. → **CLAUDE.md §3.5 갱신 필요** (본 문서는 메모만, 갱신은 PM 이 별 PR 로). |
| 2 | 7종 annotation 중 **검증 완료** = `top_label`, `bottom_label`, `highlight`, `bracket`(Unicode). **PoC 미검증** = `underline`, `inline_note`, `arrow`. P1-8 에서 a/b/c 분할 시 검증 깊이 + 기술 리스크 기준으로 묶음. |
| 3 | 수평 align 정밀도는 모든 라벨 계열 (top_label / bottom_label) 의 공통 미해결 영역. P1-8 에서 pillow `ImageFont.getlength()` 또는 tabstop 으로 보정 권고. **픽셀 단위 정확도는 Phase 1 baseline 필요 조건 아님** (백로그 §4 리스크 #2). |
| 4 | `arrow` 는 양 끝점 좌표가 필요해 가장 복잡. char offset → HWP unit 변환 + `hp:line` drawObj 양 끝점 좌표 산출 둘 다 PoC 필요. **P1-8c 에서 별도 PoC 권고**. |
| 5 | `bracket` 의 시각 표현은 Unicode `[ ]` (단순) vs `hp:rect` drawObj (정교) vs `hp:tbl` borderFill (exam-generator 패턴 재활용) 3안. **domain-expert + 와이프 1차 피드백 후 결정** — P1-8b 진입 전 PM 결정 필요. |

---

## 1. 매트릭스 (7종 annotation × HWPX 표현)

| kind | HWPX 표현 (채택안) | 한컴 호환성 | 수평 align 정밀도 | 우선순위 (P1-8) | 미해결 / 추가 PoC | 참고 |
|---|---|---|---|---|---|---|
| `highlight` | `hh:charPr.shadeColor="#FFFF00"` 새 charPr 추가 → 본문 run 의 `charPrIDRef` 교체 | ✅ 표준 (P1-0b 검증) | N/A (run 내부 표시) | **P1-8a** (가장 단순) | 색상 12종 팔레트 (`color_index` 1~12) → charPr 12개 사전 정의 vs 동적 생성 결정 | poc_align `CHARPR_HIGHLIGHT=1` |
| `underline` | `hh:charPr.underline type="SINGLE" shape="SOLID" color="#000000"` charPr 추가 → run `charPrIDRef` 교체 | ✅ 표준 (PoC 미검증, exam-generator 에서 사용 패턴 확인 가능) | N/A | **P1-8a** | 색상 / 굵기 변형 정책 (밑줄 색이 `color_index` 와 연동되는가?) | poc_align `_HEADER_XML` 의 `hh:underline type="NONE"` 자리 — `SINGLE` 로 교체 |
| `inline_note` | 본문 run 사이에 작은 폰트 (height=600~700) charPr 의 별 run 삽입. (라벨이 아니라 본문 inline) | ✅ 표준 (PoC 미검증) | N/A (inline) | **P1-8a** | 영상 레퍼런스 §2 의 "본문 위 작은 글씨 어휘 동의어" 라는 표현은 inline 이 아니라 위 단락 라벨일 가능성. domain-expert 확인 필요. inline 채택 시 화면 레이아웃 깨질 위험 | `shared/schemas/annotation.py` AnnotationKind 주석 |
| `top_label` | **3단 단락 구조** — 본문 단락 직전에 별 단락 (`paraPrIDRef=1`, lineSpacing=100%, prev/next margin 0, charPrIDRef=2 7pt bold) 삽입 | ✅ PoC 검증 (P1-0b fix 3차) | ⚠ 근사 (단락 indent / leading space 로 보정) | **P1-8b** | (1) 폰트 metric 기반 indent 계산 (pillow `ImageFont.getlength`) (2) 같은 줄 라벨 다중 시 충돌 (P1-4 와 협의) (3) 라벨 텍스트 길이가 본문 단어 폭보다 클 때 처리 | poc_align `_label_para_xml` |
| `bottom_label` | 동일 (본문 단락 직후에 별 단락 삽입) | ✅ PoC 검증 | ⚠ 근사 | **P1-8b** | top_label 과 동일 + 본문 단락이 줄바꿈된 경우 어느 줄 아래에 붙을지 (현재 PoC 는 단일 줄 가정) | poc_align `_label_para_xml` |
| `bracket` | **PoC 채택**: Unicode `[ ]` `( )` `{ }` 를 일반 charPr=0 run 으로 본문에 inline 삽입. **대안**: `hp:rect` drawObj (외곽선 사각형) 또는 `hp:tbl` 단일 셀 borderFill (exam-generator 박스 패턴 재활용) | ✅ Unicode 안 검증 (P1-0b). drawObj/tbl 안 PoC 필요 | N/A (inline) | **P1-8b** | **방식 결정 필요** — domain-expert + 와이프 시각 피드백 (단순 `[ ]` vs 실선 박스). `bracket_style` 필드 (`()/{}/[]`) 가 있으나 PoC 는 `[]` 만. | poc_align `_bracket_run_xml`, hwpx-align-poc.md §1-4 |
| `arrow` | **채택안 미정** — 1순위: `hp:line` drawObj (양 끝점 절대 좌표) / 2순위: `hp:polyLine` 곡선 / 3순위: SVG → PNG 이미지 fallback | ❓ PoC 없음. drawObj 가 본문 흐름과 align 되는지 미검증 | ⚠⚠ 양 끝점 모두 char offset → HWP unit 변환 필요 | **P1-8c (별 PoC 선행)** | (1) `hp:line` drawObj 의 startX/Y, endX/Y 가 본문 단락 기준 좌표계인지 절대 좌표인지 PoC (2) 단어 중앙을 가리키는 화살표 — span(start, end) 의 중점 채택 정책 명문화 (3) 화살표가 여러 줄을 건널 때 (multi-line arrow) — Phase 1 baseline 에서는 단일 줄로 제약 권고 | `shared/schemas/annotation.py` `arrow_target_span`, hwpx-align-poc.md §5 |

표 범례:
- ✅ = PoC 검증 완료
- ❓ = PoC 없음 (P1-8 에서 추가 PoC 필요)
- ⚠ / ⚠⚠ = 알려진 정밀도 한계 (강도)

---

## 2. kind 별 상세 — 검증된 것 / 검증 안 된 것 / P1-8 에서 추가 작업

### 2-1. `highlight`

**P1-0b 가 검증한 것**:
- `hh:charPr id="1"` 에 `shadeColor="#FFFF00"` 지정 → 본문 run 의 `charPrIDRef="1"` 로 노란색 형광펜 효과. 한글 오피스에서 정상 렌더 (PM fix 3차 검증 §7).
- borderFillIDRef="0" (테두리 없음) 로 충분.
- P1-0b follow-up (test_poc_align.py 한컴 스펙 검증 케이스 + indent 파라미터 정리) 은 PR #10 에서 머지 완료. P1-8a 코드 패턴 신뢰 가능.

**검증 안 된 것**:
- 12색 팔레트 (`color_index` 1~12) 와 charPr 매핑 — 매번 새 charPr 동적 생성 vs 12개 사전 정의 후 재사용.
- 같은 run 에 underline + highlight 둘 다 적용된 경우 (charPr 1개에 두 속성 동시 명시 가능).

**P1-8a 작업**:
1. 12색 팔레트 → charPr id 매핑 테이블 정의 (예: `id=10~21`).
2. 다중 속성 charPr 동적 생성 함수 작성 (highlight + underline 조합 등).

### 2-2. `underline`

**P1-0b 가 검증한 것**:
- 없음. PoC `_HEADER_XML` 에 `<hh:underline type="NONE" shape="SOLID"/>` 자리만 존재.

**검증 안 된 것**:
- `type="SINGLE"` `type="DOUBLE"` `type="DOTTED"` 등 한컴 지원 변형 + 색상 적용.

**P1-8a 작업**:
1. exam-generator 코드베이스에서 `CHAR_UNDERLINE` 사용 패턴 확인 (참조: hwpx-align-poc.md §5 의 "exam-generator CHAR_UNDERLINE=53 패턴 그대로").
2. underline charPr 생성 + 단위 테스트 1건.

### 2-3. `inline_note`

**검증 안 된 것**: 전부.

**리스크**:
- `shared/schemas/annotation.py` 주석: "본문 위 작은 글씨 어휘 동의어 (예: `=foster, promote`)". 이 표현이 **inline run** 인지 **별 단락 라벨** 인지 모호. domain-expert 확인 필요.
- inline 채택 시 본문 가독성 + line wrap 영향. 별 단락 라벨 채택 시 `top_label` 과 표현이 유사해짐.

**P1-8a 작업**:
1. domain-expert 에 표현 의도 재확인 (영상 레퍼런스 §2 재독).
2. inline 안: 작은 폰트 charPr 추가 + 본문 run 사이 삽입.
3. 별 단락 안 채택 시 → P1-8a 가 아니라 P1-8b 로 재분류 (top_label 과 동일 메커니즘).

### 2-4. `top_label` / `bottom_label`

**P1-0b 가 검증한 것**:
- 3단 단락 구조 (라벨 단락 / 본문 단락 / 라벨 단락) 가 한컴에서 안정적 렌더 (PM fix 3차 §7).
- 라벨 단락은 `paraPrIDRef=1` (lineSpacing=100%, prev/next margin=0) + `charPrIDRef=2` (height=700, bold).
- `<hh:strikeout shape="NONE" color="#000000"/>` 명시 필요 (생략하면 `shape="SOLID"` 가 취소선 활성화).

**검증 안 된 것** (= P1-8b 작업):
1. **수평 align 정밀도** — PoC 는 라벨이 단락 좌측에 정렬됨 ("S" 가 "The" 위, "V" 도 "The" 위). 단어 중앙을 가리키려면 `paraPr.margin.indent` 또는 `tabDef` + `tabStop` + leading whitespace 필요.
2. **폰트 metric** — pillow `ImageFont.getlength()` 로 char offset → HWP unit 변환 함수 구현. 폰트 파일 번들링 (Times New Roman / 함초롬돋움) 필요 여부 결정.
3. **다중 라벨 / 줄바꿈 본문** — 본문이 여러 줄로 wrap 된 경우 라벨 단락이 어느 줄 위/아래에 붙는지 (현 3단 구조는 단일 줄 가정). 다중 줄 본문은 P1-8b 후속 PR 또는 P1-10 으로.
4. **다중 라벨 충돌** — 같은 span 에 top_label 2개 (예: "S" + "동명사주어") — P1-4 정책 결정 후 반영.

**P1-8b 작업 분할 권고**:
- b-1: 단일 줄 본문 + 단일 라벨 (PoC 직접 흡수).
- b-2: 폰트 metric 기반 수평 align 보정.
- b-3: bracket (Unicode 안 우선, drawObj 안은 별도).
- b-4 (선택): 다중 줄 본문, 다중 라벨 충돌 — P1-10 으로 연기 가능.

### 2-5. `bracket`

**P1-0b 가 검증한 것**:
- Unicode `[ ]` 를 일반 run 으로 본문에 inline 삽입 (poc_align `_bracket_run_xml`).
- 한글 오피스에서 정상 표시 (PM fix 3차 §7).

**검증 안 된 것**:
- `hp:rect` drawObj 안 — 본문 위에 투명 배경 외곽선 사각형 floating. floating 의 align 한계는 `top_label` 과 동일 (단락 라인 안 clamp 가능성 — PoC 필요).
- `hp:tbl` borderFill 안 — exam-generator 가 박스 표현에 사용 중인 패턴. inline table 셀로 "괄호 대상 단어" 포함. 본문 흐름 영향 큼.

**Phase 1 결정 포인트** (P1-8b 진입 전 PM 결정):
- domain-expert + 와이프 시각 피드백: 단순 `[over]` 로 충분한가? 아니면 실선 박스 외곽선이 필요한가?
- `bracket_style` 필드 (`()/{}/[]`) 와 무관하게 채택 표현은 1개로 통일.

**P1-8b 작업** (Unicode 안 채택 가정):
1. `bracket_style` enum 별 Unicode 매핑 (`()` → `( )`, `{}` → `{ }`, `[]` → `[ ]`).
2. 여닫이 Unicode 를 본문 span 양 끝에 inline run 으로 삽입.
3. drawObj/tbl 안 채택 시 → P1-8b 분리 + 별 PoC.

### 2-6. `arrow`

**P1-0b 가 검증한 것**: 없음. hwpx-align-poc.md §5 가 "Phase 1 P1-8c (화살표) task 에서 별도 PoC 권고" 라고 명시.

**검증 안 된 것**: 전부.

**기술 리스크 (가장 큼)**:
1. `hp:line` drawObj 의 좌표계 — 단락 기준 vs 절대. 단락 기준이라면 `hp:offset` `hp:size` 와 함께 본문 단락 안에 삽입. 절대라면 페이지 단위 좌표 계산 필요.
2. char offset → HWP unit 변환 — `top_label` 과 동일한 폰트 metric 의존.
3. 단어 중앙 좌표 산출 — `span` 과 `arrow_target_span` 각각의 (start+end)/2 를 anchor 로 정책화.
4. multi-line arrow — Phase 1 에서는 단일 줄로 제약 권고 (`docs/phase-1-backlog.md` §4 리스크 #4).
5. 화살표 머리 (arrow head) 표현 — `hp:line` 의 `headStyle="ARROW"` 같은 속성 PoC 필요.

**P1-8c 작업 분할 권고**:
- c-1: `hp:line` drawObj 좌표계 PoC (단일 줄, 두 단어 잇는 직선 1개) — `packages/hwpx_renderer/tests/fixtures/poc_arrow.hwpx` 신설. **별 PoC 필요 — P1-8c 가 사실상 P1-0b 의 화살표판**.
- c-2: 폰트 metric 기반 단어 중앙 좌표 산출 (`top_label` b-2 와 코드 공유 가능 → 의존성 명시).
- c-3: 화살표 머리 + 곡선 (`hp:polyLine`) 필요 시.
- c-4 (fallback): SVG → PNG 변환 후 `hp:pic` 으로 임베드. drawObj 안 모두 실패 시 마지막 수단.

---

## 3. P1-8 PR 분할 권고 (백로그 §2.4 a/b/c 의 구체화)

**기준**: (1) PoC 검증 깊이, (2) 기술 리스크, (3) 코드 의존성.

### P1-8a — 텍스트 런 계열 (highlight, underline, inline_note*)

- **포함 kind**: `highlight`, `underline`, `inline_note` (inline 안 채택 시. 별 단락 안이면 P1-8b 로).
- **공통 메커니즘**: `hh:charPr` 추가 + 본문 run `charPrIDRef` 교체.
- **위험도**: 낮음. PoC 가 highlight 는 검증 완료. underline / inline_note 는 표준 charPr 속성으로 추정 가능.
- **선결 작업**: 12색 팔레트 → charPr id 매핑 테이블 정의 (`color_index` 1~12).
- **DoD**: 3종 모두 fixture passage 1건 + 단위 테스트 (각 kind 1건 + multi-attr charPr 1건).

### P1-8b — 라벨 / 괄호 계열 (top_label, bottom_label, bracket)

- **포함 kind**: `top_label`, `bottom_label`, `bracket`.
- **공통 메커니즘**: 단락 구조 변형 (3단 구조) 또는 inline Unicode/외곽선 도형.
- **위험도**: 중간. 3단 단락 구조는 PoC 검증되었으나 수평 align 정밀도가 미해결. bracket 은 표현 방식 결정 필요.
- **선결 작업**:
  1. PM 결정: bracket 표현 (Unicode vs drawObj vs tbl).
  2. domain-expert 확인: `inline_note` 가 별 단락 안인지 (별 단락이면 본 묶음으로 이동).
  3. P1-4 (충돌 정책) 의 결정사항 반영 (다중 라벨).
- **세부 분할** (선택):
  - b-1: 단일 줄 본문 + 단일 라벨 (PoC 흡수).
  - b-2: 폰트 metric 기반 수평 align 보정.
  - b-3: bracket (Unicode 안 우선).
- **DoD**: 3종 모두 fixture passage 1건 + 한글 오피스 수동 검증 (와이프 검수 1라운드는 P1-9).

### P1-8c — 화살표 (arrow) — 별 PoC 선행 필요

- **포함 kind**: `arrow`.
- **공통 메커니즘**: `hp:line` drawObj (or `hp:polyLine` / SVG fallback).
- **위험도**: 높음. PoC 전무. 본 task 의 처음 절반은 PoC 와 동일.
- **선결 작업**:
  1. `packages/hwpx_renderer/tests/fixtures/poc_arrow.hwpx` PoC 1건 — 단일 줄 본문 위에 두 단어를 잇는 직선 1개.
  2. PM 한글 오피스 수동 검증 (P1-0b 와 동일 사이클).
  3. P1-8b 의 폰트 metric 함수 재활용.
- **세부 분할**:
  - c-1: `hp:line` 좌표계 PoC.
  - c-2: 폰트 metric 기반 anchor 산출.
  - c-3: 화살표 머리 / 곡선.
  - c-4 (fallback): SVG → PNG.
- **DoD**: arrow 1건 fixture passage + 한글 오피스 수동 검증 + (선택) multi-line arrow 는 Phase 1 baseline 제외.

### 작업 순서 권고

```
P1-8a (텍스트 런 계열)        ← 의존 없음. 가장 단순. 먼저 착수 권장.
   │
   ├─ P1-8b-1 (라벨 단일 줄)   ← P1-0b 직접 흡수
   │      │
   │      ├─ P1-8b-2 (폰트 metric)  ── 코드 공유 ──┐
   │      └─ P1-8b-3 (bracket)                     │
   │                                               │
   └─ P1-8c-1 (arrow PoC)                          │
            │                                      │
            ├─ P1-8c-2 (폰트 metric anchor) ←──────┘
            ├─ P1-8c-3 (head / curve)
            └─ P1-8c-4 (SVG fallback, 선택)
```

**critical path**: P1-8a → P1-8b-1 → P1-8b-2 → P1-8c-1 → P1-8c-2 → P1-9.

---

## 4. CLAUDE.md §3.5 갱신 권고 (본 PR 범위 외)

CLAUDE.md §3.5 현재 내용:

> - 하이라이트 / 밑줄: HWPX 텍스트 런 속성 (이미지 아님)
> - 라벨: HWPX 텍스트박스 도형
> - 화살표 / 곡선: HWPX 도형 우선, 복잡할 때만 SVG → 이미지 fallback

**갱신 필요 항목**:
1. **"라벨 = 텍스트박스 도형"** → **"라벨 = 3단 단락 구조 (라벨 단락 / 본문 단락 / 라벨 단락)"** 로 정정. 사유 = P1-0b 결과 (한컴이 floating textBox 를 단락 라인 높이 안에 clamp).
2. **bracket 표현 방식**이 §3.5 에 누락. P1-8b 결정 후 추가.
3. **수평 align 한계** — "라벨의 수평 정밀도는 폰트 metric 근사" 라는 단서 명시 권고.

본 갱신은 PM 이 별 PR 로 처리 (본 PR 범위 밖). 본 문서에서는 메모만.

---

## 5. ADR 필요 여부

본 문서 작성 중 ADR 신설이 필요할 만큼 큰 결정은 발견되지 않음. 단:

- **ADR 후보 1**: `bracket` 표현 방식 결정 (Unicode vs drawObj vs tbl) — domain-expert + 와이프 피드백 후 결정. ADR 까지 갈지 P1-8b PR 안에서 결정 기록만 남길지 PM 판단.
- **ADR 후보 2**: `arrow` anchor 정책 (단어 중앙 vs 단어 시작) — P1-8c-1 PoC 후 결정. PoC 결과가 명확하면 ADR 불필요.
- **ADR 후보 3**: 폰트 번들링 정책 (pillow `ImageFont.truetype` 의 폰트 파일을 repo 에 포함할지) — 라이센스 영향. P1-8b-2 진입 전 PM 확인.

본 PR 에서는 ADR 신설 안 함. 위 3개는 P1-8 진행 중 발생 시 신규 ADR 또는 PR 결정 기록.

---

## 6. 미해결 사항 요약

> **표 읽는 법 — 결정 주체 구분**:
> - "PM 결정" = 비즈니스·우선순위 판단이 필요한 항목. PM 이 결정 전까지 착수 불가.
> - "구현 레벨" = 팀 내 기술 협의로 결정 가능 (architect / backend-dev / domain-expert). PM 개입 불필요.

| # | 항목 | 결정 주체 | 구분 | 시점 |
|---|---|---|---|---|
| 1 | bracket 표현 (Unicode / drawObj / tbl) | domain-expert + 와이프 + PM | PM 결정 | P1-8b 착수 전 |
| 2 | inline_note 가 inline 인지 별 단락 라벨인지 | domain-expert | 구현 레벨 | P1-8a 착수 전. **P1-8a PR 에서 후보 A (inline run, 작은 폰트 charPr) 채택.** 사유: `inline_note` 의 의도가 본문 흐름 안에서 짧은 부연이라면 inline 이 자연스러우며, 별 단락은 `top_label`/`bottom_label` 의 역할과 겹친다. domain-expert 검토 follow-up. |
| 3 | 12색 팔레트 → charPr id 매핑 정책 (사전 정의 / 동적 생성) | architect + backend-dev | 구현 레벨 | P1-8a 착수 전 |
| 4 | underline 색상이 `color_index` 와 연동되는가 | domain-expert | 구현 레벨 | P1-8a 착수 전 |
| 5 | 폰트 번들링 (Times New Roman / 함초롬돋움) | PM (라이센스 확인) | PM 결정 | P1-8b-2 착수 전 |
| 6 | multi-line arrow Phase 1 제외 여부 | PM | PM 결정 | P1-8c 착수 전. c-1 PoC 결과에 따라 단일 줄 arrow 도 Phase 1 제외 가능 — PoC 후 PM 최종 결정. |
| 7 | 다중 라벨 충돌 시각 처리 (P1-4) | frontend-dev + domain-expert | 구현 레벨 | P1-8b-1 착수 전 |
| 8 | CLAUDE.md §3.5 갱신 | PM | PM 결정 | 본 PR 머지 후 별 PR |
