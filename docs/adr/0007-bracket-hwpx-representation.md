# ADR 0007 — bracket annotation HWPX 표현 (P1-8b 진입 차단 해제)

- **상태(Status)**: Accepted
- **작성일**: 2026-05-03
- **결정일**: 2026-05-03
- **작성자**: architect (초안)
- **결정자**: PM (Dennis)
- **채택안**: **A — Unicode `[ ]` `( )` `{ }`**
- **유형**: Phase 1 진입 전 차단 ADR — P1-8b (라벨 / 괄호 계열 HWPX 렌더러) 착수 전
  필수.
- **관련 문서**:
  - `docs/annotation-hwpx-mapping.md` §1, §2-5, §6 #1 (3안 비교 + 미해결 항목)
  - `docs/hwpx-align-poc.md` §1, §5 (Unicode `[ ]` PoC 검증 결과)
  - `CLAUDE.md` v0.7 §3.5 (bracket 표현 결정 미정 명시)
  - `shared/schemas/annotation.py` `bracket_style` 필드 (`()` / `{}` / `[]` 3종)
  - `docs/phase-1-backlog.md` §2.4 P1-8b
  - `docs/reference-program-analysis.md` §1, §3.2 (영상 레퍼런스의 bracket 사용 패턴)

---

## Context

`SyntaxAnnotation.kind = "bracket"` 은 영상 레퍼런스에서 빈번하게 등장한다 — 본문의
구/절 범위를 시각적으로 표시하는 핵심 annotation. `bracket_style` 필드는 `()` /
`{}` / `[]` 3종을 받는다.

HWPX 출력에서 이를 어떻게 표현할지 3가지 옵션이 있고, P1-7 매핑 카탈로그 §6 #1 에서
"P1-8b 착수 전 PM + domain-expert + 와이프 시각 피드백으로 결정" 으로 미뤄둔 상태.
P1-8b (라벨 / 괄호 계열 HWPX 렌더러) 가 본 결정을 기다리고 있어 Phase 1 critical
path 에서 차단 항목.

### 영상 레퍼런스의 bracket 표현 (§1, §3.2)

영상 mock-up 에서 관찰되는 bracket 사용 패턴:

```
부사구       관계절                현재재구문                전치사구
{each} and {every} word — (something {people don't often do}
(when {reading} quickly, or {reading} (in silence])])).
```

→ `(...)`, `{...}`, `[...]` 가 본문 inline 으로 들어가 구/절 범위를 표시. **외곽선
박스 (테두리) 가 아니라 단순 글자**. 색상은 라벨과 매칭되는 듯 (영상 해상도로는
정확한 색 매칭 미확인).

---

## 옵션 비교

### A. Unicode `[ ]` `( )` `{ }` (PoC 검증 완료)

- **표현**: `bracket_style` 에 따라 본문 run 의 양 끝에 해당 글자 inline 삽입
  (charPr=0 일반 본문 run 으로).
- **검증 상태**: ✅ P1-0b PoC fix 3차에서 한글 오피스 정상 렌더 확인
  (`packages/hwpx_renderer/tests/fixtures/poc_align.hwpx`).
- **장점**:
  - 가장 단순. 추가 도형 / 표 / drawObj 없음.
  - 한컴 호환성 100%. 다른 HWPX 뷰어에서도 깨지지 않음.
  - 본문 텍스트 흐름과 자연스럽게 align.
  - 영상 레퍼런스 패턴과 가장 일치 — bracket 이 글자로 보임.
  - color_index 는 별 charPr 로 색 입힘 가능 (P1-8a HIGHLIGHT_PALETTE 패턴 재활용).
- **단점**:
  - 외곽선 사각형 박스 표현 불가 — 단순 글자.
  - 다중 줄 bracket (구가 줄바꿈을 건넘) 시각적으로 약함.

### B. `hp:rect` drawObj (실선 외곽선)

- **표현**: 본문 단락에 floating drawObj `hp:rect` 를 anchor — bracket 시작/끝 좌표
  산출 후 사각형 외곽선 그림.
- **검증 상태**: ❌ PoC 없음. P1-0b PoC 결과 한컴이 floating textBox 를 단락 라인
  높이로 clamp 한다는 사실이 확인되어 (라벨 = 텍스트박스 결정 번복 사유), drawObj
  도 동일 문제 가능성.
- **장점**:
  - 실선 외곽선 박스 — 시각적으로 명확.
  - 색상 / 선 스타일 자유.
- **단점**:
  - PoC 미검증 — 본문 텍스트 위에 정확히 align 되는지 불확실.
  - 좌표 계산 (char offset → HWP unit) 필요. 폰트 metric 의존.
  - 다중 줄 bracket 시 drawObj 분할 필요 (복잡).
  - 본문 편집 시 drawObj anchor 가 어긋날 위험.

### C. `hp:tbl` 단일 셀 borderFill (exam-generator 패턴 재활용)

- **표현**: bracket 으로 감쌀 텍스트를 1×1 표 안에 넣고 borderFill 로 외곽선 표시.
  exam-generator 의 박스형 문제 (예: `(A) [long-term / short-term]`) 가 이 패턴 사용.
- **검증 상태**: ❌ 본 프로젝트 PoC 없음. 단 exam-generator 에서 검증된 패턴 재활용.
- **장점**:
  - 검증된 패턴 (exam-generator).
  - 외곽선 표현 가능.
  - 표 셀이라 한컴 layout engine 이 자연스럽게 처리.
- **단점**:
  - 본문 inline 흐름이 깨짐 — 표 셀이 새 단락처럼 동작.
  - 다중 줄 bracket 표현 불가 (단일 셀 단위).
  - 영상 레퍼런스 패턴과 가장 멀음.

---

## 결정 (PM 채택안)

> **상태**: Accepted (2026-05-03). PM 이 architect 추천 그대로 수용.

### 채택: **A (Unicode 글자)**

**근거**:
1. **영상 레퍼런스와 가장 일치** — 와이프가 보던 도구의 bracket 도 글자였을 가능성 높음.
2. **PoC 검증 완료** — 즉시 구현 가능, 추가 PoC 없음.
3. **No Reinventing the Wheel (CLAUDE.md §3.6)** — 가장 단순한 안.
4. **Phase 1 baseline** 의 정의 = "와이프가 검수해서 OK 받을 수준" → 외곽선 박스가
   필수가 아니라면 글자로 시작 후 와이프 피드백 받아서 (B)/(C) 로 업그레이드 여부
   결정하는 게 비용 효율.

**리스크**:
- 와이프가 외곽선 박스를 강하게 선호하면 (B) 또는 (C) 로 재작업 필요. 매몰비용은
  P1-8b 의 bracket 부분만 (~1~2일).

### 단계적 진행 권고

1. **Phase 1 P1-8b**: A 채택 → 와이프 검수 (P1-9).
2. **검수 결과**:
   - OK → A 그대로 유지, ADR 상태 Accepted 로 갱신.
   - NG (외곽선 박스 강하게 선호) → P1-10 에서 B 또는 C 로 재작업, ADR 상태 Superseded
     로 갱신 + 후속 ADR 생성.

---

## 함께 결정 / 영향

### `shared/schemas/annotation.py` `bracket_style` 필드

3안 모두 `bracket_style` (`()` / `{}` / `[]`) 를 보존:
- A: 글자 그대로 사용
- B: drawObj 형태 차이로 변환 (사각형 / 둥근사각형 / 미정)
- C: 표 셀 borderFill 스타일 차이로 변환

`bracket_style` 필드는 어느 안 채택해도 호환. 스키마 변경 불필요.

### color_index 와의 연동

3안 모두 color_index (1~12) 를 색에 매핑 — 채택안에 영향 없음.

### multi-line bracket

3안 중:
- A: 한 줄 끝 글자 + 다음 줄 시작 글자 자연스럽게 분리 (단점: 시각적 약함)
- B: drawObj 분할 필요 (복잡)
- C: 표현 불가

→ A 가 multi-line 처리에서도 가장 자연스러움.

---

## 결정 후 P1-8b 작업 진입 절차

1. 본 ADR 상태 Accepted (PM 결정 후) → 머지.
2. `docs/annotation-hwpx-mapping.md` §6 #1 [done] 표기.
3. `docs/phase-1-backlog.md` P1-8b 진입 차단 해제 표기.
4. backend-dev 가 P1-8b PR 착수 — 본 ADR 의 채택안에 따라 구현.
5. P1-9 (HWPX 출력 + 와이프 검수) 에서 시각 피드백 수집.

---

## 결정 기록

| 날짜 | 상태 | 결정자 | 비고 |
|---|---|---|---|
| 2026-05-03 | Proposed | architect (초안) | PM 결정 대기 |
| 2026-05-03 | Accepted | PM (Dennis) | architect 추천 (A) 그대로 수용. P1-8b 진입 차단 해제. |
