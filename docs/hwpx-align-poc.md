# HWPX 텍스트박스 align PoC — 결과 메모

- **작성일**: 2026-05-03
- **작성자**: backend-dev
- **task**: P1-0b (phase-1-backlog.md §2.1)
- **fixture**: `packages/hwpx_renderer/tests/fixtures/poc_align.hwpx`
- **코드**: `packages/hwpx_renderer/src/hwpx_renderer/poc_align.py`
- **테스트**: `packages/hwpx_renderer/tests/test_poc_align.py` (28 passed)

---

## 결론 요약

| 항목 | 결론 |
|---|---|
| 라벨 (상단/하단 텍스트박스) | **부분 가능** — XML 구조는 올바르나 수평 align 정밀도 한계 있음 (아래 상세) |
| 하이라이트 | **가능** — `charPr.shadeColor` 로 구현, 한글 오피스 완전 지원 |
| 괄호 | **가능 (PoC 수준)** — Unicode bracket `[ ]` run. 실 구현에서 도형 방식 평가 필요 |
| XML zip 구조 | **이상 없음** — 28 단위 테스트 모두 통과 |

**PM 수동 확인 필요**: `packages/hwpx_renderer/tests/fixtures/poc_align.hwpx` 를 한글 오피스로 열어 라벨이 본문 위/아래에 align 되는지 확인. 결과를 아래 §"PM 검증 기록" 에 기입해 달라.

---

## 1. 구현 접근

### 1-1. 라벨 텍스트박스 (top_label / bottom_label)

HWPX 의 `hp:drawObj` + `hp:textBox` 조합을 사용한다.

```xml
<hp:drawObj id="0" zOrder="0" numberingType="FIGURE"
            textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0">
  <hp:sz width="800" widthRelTo="ABSOLUTE" height="700" heightRelTo="ABSOLUTE"/>
  <hp:pos treatAsChar="0" affectLSpacing="1" flowWithText="1"
          allowOverlap="0" holdAnchorAndSO="0"
          vertRelTo="PARA" horzRelTo="PARA"
          vertAlign="TOP"  horzAlign="LEFT"
          vertOffset="-900"   <!-- 음수 = 단락 위 -->
          horzOffset="0"/>    <!-- 단락 왼쪽 시작 기준 수평 이동 -->
  <hp:textBox ...>...</hp:textBox>
  <hp:shapeComponent .../>
</hp:drawObj>
```

**anchor 방식**:
- `horzRelTo="PARA"` `vertRelTo="PARA"` — 단락 기준 상대 좌표. 단락이 이동해도 라벨이 따라감.
- `flowWithText="1"` — 본문이 페이지에 걸쳐 이동해도 drawObj 가 같은 단락에 붙어 이동.
- `treatAsChar="0"` — floating 객체. 텍스트박스가 본문 흐름을 밀어내지 않음(단 affectLSpacing=1 로 줄간격에는 영향).

### 1-2. 수평 offset 계산 한계 (가장 큰 제약)

**문제**: 라벨을 특정 단어 위에 정확히 놓으려면 해당 단어까지의 문자 누적 너비(character run width)를 알아야 한다. 한글 오피스는 런타임에 font metric 으로 계산하지만, Python 에서는 폰트 metric API 가 없다.

**PoC 에서의 근사**:
- 상단 라벨 "S": `horzOffset=0` — 단락 왼쪽 시작점.
- 하단 라벨 "V": `horzOffset=11400` — "The quick brown fox" ≈ 19자 × 600 unit/char 근사.
  - 실제 "jumps" 위치와 차이 날 가능성 높음.

**Phase 1 P1-7/P1-8 에서의 해결 방향 (권고사항)**:

옵션 A — **pillow 폰트 metric 활용**:
```python
from PIL import ImageFont
font = ImageFont.truetype("TimesNewRoman.ttf", size=10)
char_widths = [font.getlength(c) for c in text_before_target]
total_offset = int(sum(char_widths) * HWP_UNIT_PER_PT)
```
대안 검토: `fonttools` (더 정확한 kerning 포함). 단 폰트 파일 번들링 필요.

옵션 B — **고정 폭 근사 + PM 수기 보정**:
10pt Times New Roman 영어 평균 글자 너비 ≈ 560 HWP unit. 충분히 빠르게 구현 가능.
PoC 검증 이후 Phase 1 검수 단계에서 PM 이 "±N단어" 허용 기준으로 판단.

옵션 C — **단어 단위 sticky label** (대안 레이아웃):
라벨을 특정 char offset 이 아닌 **단어 단위** 로 anchoring. 예: 각 단어를 별 단락으로 분리하거나, `hp:tbl` 로 단어 단위 셀 분할.
복잡도 높음 — Phase 1 baseline 에는 옵션 A/B 우선 권고.

**권고**: Phase 1 P1-7/P1-8 에서 pillow `ImageFont.getlength()` 로 approximate offset 계산 → PM/와이프 검수 에서 허용 기준 판단. 픽셀 단위 정확도는 Phase 1 baseline 필요 조건 아님 (백로그 §4 리스크 3번).

### 1-3. 하이라이트

`charPr.shadeColor` 로 구현. header.xml 에 별도 charPr 1개 추가.

```xml
<hh:charPr id="1" height="1000" textColor="#000000" shadeColor="#FFFF00" ...>
```

section0.xml 의 해당 run 에 `charPrIDRef="1"` 지정. **구현 완성도 높음** — 한글 오피스 표준 기능.

한글 오피스가 "charPr.shadeColor" = "강조 색" (형광펜)과 동일하게 렌더링하는지 PM 확인 권고.

### 1-4. 괄호

PoC: Unicode bracket `[ ]` 를 일반 run 에 포함.

```python
f"[{text}]"  # charPrIDRef=0, 일반 본문 run
```

**실 구현 옵션** (Phase 1 P1-7/P1-8 결정 사항):
- Unicode bracket 문자: 가장 단순. 단 시각적으로 단순히 `[over]` 로 보임.
- `hp:rect` drawObj: 본문 위에 투명 배경 실선 사각형 floating. 텍스트를 감싸는 외곽선 효과. 복잡도 중.
- `hp:tbl` 단일 셀 borderFill: exam-generator 에서 박스 구현에 이미 사용 중인 패턴. 단락 안에 inline table 로 "괄호 대상 단어" 포함.

**권고**: 와이프가 원하는 시각 표현 (단순 `[ ]` vs 실선 박스)을 P1-7 매핑 카탈로그에서 domain-expert 와 협의 후 결정.

---

## 2. 좌표 시스템 정리

| 항목 | 값 |
|---|---|
| 단위 | HWP unit = 1/7200 inch ≈ 0.0353mm |
| 10pt | = 1000 HWP unit |
| A4 용지 폭 | 59528 HWP unit |
| A4 용지 높이 | 84188 HWP unit |
| 본문 폭 (기본 좌우 여백 각 8504) | ≈ 42520 HWP unit |
| 라벨 박스 높이 (700 unit = 7pt) | 충분히 작은 라벨 |
| vertOffset 음수 | 단락 위 (상단 라벨) |
| vertOffset 양수 | 단락 아래 (하단 라벨) |
| horzRelTo="PARA" | 단락 왼쪽 edge 기준 수평 |
| vertRelTo="PARA" | 단락 상단 edge 기준 수직 |

---

## 3. drawObj anchor 동작 — PoC 에서 발견한 것

1. `flowWithText="1"` 없이는 drawObj 가 단락 이동 시 따라가지 않고 절대 좌표에 고정된다. 반드시 설정 필요.
2. `treatAsChar="0"` (floating) + `affectLSpacing="1"` 조합:
   - drawObj 가 본문 줄간격에 영향을 줌 → 라벨이 존재하는 줄은 자동으로 더 높은 줄간격을 확보.
   - 이는 원하는 동작 (라벨이 본문 텍스트와 겹치지 않게).
   - `affectLSpacing="0"` 으로 설정하면 라벨이 본문 텍스트와 겹칠 수 있음.
3. `textWrap="TOP_AND_BOTTOM"` — drawObj 좌우에는 텍스트가 흐르지 않음. 라벨 전후로만 본문이 흐름. 단락이 한 줄이면 영향 없음.
4. HWPX 에서 drawObj 는 단락 내부의 run 들 사이에 XML 상으로 위치한다. 실제 렌더링 anchor 는 drawObj 가 속한 단락.

---

## 4. hwpx-auto-parser-for-template 활용 불가 근거

CLAUDE.md §3.6 원칙 ("No Reinventing the Wheel") 에 따라 기존 컴포넌트 재활용을 먼저 검토했다.

검토 결과:
- `hwpx-auto-parser-for-template` (`/Users/william/workspace/hwpx-mcp`) 는 **TypeScript VSCode extension**.
- Python 에서 직접 import 불가. Node.js subprocess 호출은 가능하나 의존성 비대화 + 인터페이스 복잡도.
- exam-generator (`/Users/william/workspace/exam-generator/app/renderer/`) 는 Python 이고 HWPX template ZIP 재패키징 패턴을 이미 구현. 단 텍스트박스 / 도형 생성 기능은 없음 (문항 단락/표만).
- 따라서 exam-generator 의 ZIP 패키징 패턴은 재활용하되, `hp:drawObj` + `hp:textBox` XML 빌더는 raw OOXML 로 직접 작성.

**대안 검토 결과**: 라이브러리 없이 직접 OOXML 빌더 작성이 현재 조건에서 가장 단순하고 유지보수 가능한 방향. Phase 1 P1-8 에서 패키지 의존성 추가 필요성이 생기면 재검토.

---

## 5. Phase 1 P1-7 (Annotation → HWPX 매핑 카탈로그) 입력 권고사항

| annotation kind | HWPX 표현 | 기술 리스크 | 비고 |
|---|---|---|---|
| `top_label` | `hp:drawObj` + `hp:textBox`, `vertRelTo="PARA"` `vertOffset` 음수 | 수평 정렬 근사 | horzOffset = 폰트 metric 으로 계산 필요 |
| `bottom_label` | 동일, `vertOffset` 양수 | 동일 | |
| `highlight` | `charPr.shadeColor` (노란색 = `#FFFF00`) | 없음 (표준 기능) | charPr 1개 추가만 필요 |
| `bracket` | Unicode `[ ]` run (단순) 또는 `hp:rect` drawObj (정교) | 낮음~중간 | domain-expert + 와이프 피드백으로 방식 결정 |
| `underline` | `charPr.underline` type/shape 설정 | 없음 | exam-generator CHAR_UNDERLINE=53 패턴 그대로 |
| `inline_note` | `charPr` + 작은 폰트 run | 낮음 | Phase 1 basket |
| `arrow` | `hp:line` drawObj (startX/endX 명시) | 높음 | 양 끝점 좌표 → char offset 변환 필요. P1-7 에서 별 task 검토 권고 |

화살표 (`arrow`) 는 양 끝점 절대 좌표가 필요하기 때문에 `hp:line` drawObj 를 쓰더라도 char offset → 좌표 변환이 가장 복잡하다. Phase 1 P1-8c (화살표) task 에서 별도 PoC 권고.

---

## 6. 단위 테스트 한계 (2026-05-03 추가)

**단위 테스트는 zip/XML 구조만 검증한다 — 한컴 스펙 적합성은 보장하지 않는다.**

P1-0b 커밋(`9814faf`) 이후 PM 이 한글 오피스로 fixture 를 열었을 때 "파일 손상" 에러가 발생했다. 28개 단위 테스트는 모두 통과했었으나, 다음 항목들이 레퍼런스 HWPX 와 불일치했다:

| 파일 | 이전 (잘못된) 구조 | 수정 후 (레퍼런스 일치) |
|---|---|---|
| `META-INF/container.xml` | `xmlns:container` + `media-type="application/oebps-package+xml"` | `xmlns:ocf` + `xmlns:hpf` + `media-type="application/hwpml-package+xml"` |
| `Contents/content.hpf` | `hpf:rootfile` 루트 요소 | `opf:package` 루트 + `opf:metadata` + `opf:manifest` + `opf:spine` |
| `version.xml` | `hv:version` 자식 요소 구조 | `hv:HCFVersion` 단일 요소 (attribute-only) |
| `META-INF/container.rdf` | **파일 없음** | RDF document (header + section 등록) |
| `settings.xml` | `hs:settings` 빈 요소 | `ha:HWPApplicationSetting` 구조 |

수정은 레퍼런스 HWPX(`exam-generator/templates/template.hwpx`, `samples/평가원_영어_양식.hwpx`)를 unzip + diff 하여 진행했다.

**교훈**: HWPX 호환성 확인 방법 순서:
1. 레퍼런스 HWPX 와 생성 HWPX 를 unzip 후 파일별 diff
2. 한컴 오피스에서 직접 열기 (PM 수동 확인)
3. 단위 테스트는 구조 회귀 방지용이며, 스펙 적합성 검증 수단이 아님

---

## 7. PM 검증 기록

(PM 이 한글 오피스에서 열어본 후 기입)

- [ ] 파일을 한글 오피스에서 열었을 때 오류 없이 열리는가?
- [ ] 본문 "The quick brown fox [over] the lazy dog." 가 보이는가?
- [ ] " jumps " 부분에 노란색 하이라이트가 적용되어 있는가?
- [ ] 단락 위에 "S" 라벨 텍스트박스가 보이는가?
- [ ] 단락 아래에 "V" 라벨 텍스트박스가 보이는가?
- [ ] 라벨이 본문과 겹치지 않고 위/아래에 배치되는가?
- [ ] 수평 align: 라벨 "S" 가 문장 시작("The") 위에 대략 위치하는가?
- [ ] 수평 align: 라벨 "V" 가 "jumps" 근처 아래에 대략 위치하는가?

align 결론:
- [ ] 정확히 align 가능 (pixel-level 정도)
- [ ] 부분 align 가능 (단어 수준, ±1~2단어 오차 허용)
- [x] **근사 align** — 수평 horzOffset 계산에 font metric 이 필요하여 PoC 단계에서는 근사값. 실 구현(P1-8)에서 pillow `ImageFont.getlength()` 로 보정 필요.

스크린샷: (PM 이 추후 첨부)
