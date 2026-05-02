# ADR 0006 — 마커 처리 정책 (Phase 1 진입 차단 해제)

- **상태(Status)**: Accepted
- **작성일**: 2026-05-02
- **작성자**: architect agent
- **유형**: Phase 1 진입 전 차단 ADR — `Passage.body_text` / `Question.choices` /
  추출 파이프라인의 마커 처리 정책 확정
- **관련 문서**:
  - `CLAUDE.md` v0.4 §11 Open Question (마커 분리 vs inline 유지)
  - `docs/schema-coverage-audit.md` §3 Gap K, §4-6
  - `docs/audit-review-domain.md` §3.5 (출제 도메인 멘탈 모델 = 분리)
  - `docs/reference-program-analysis.md` §4.2 (영상에서 출제용 마커 미관찰 — 구문분석
    단계는 정제 본문)
  - `docs/adr/0001-canonical-schema-philosophy.md`
  - `docs/adr/0002-content-model-v0_1.md` D1.1 (Passage `body_text` 마커 정책 중립
    명시 — 본 ADR 위임)
  - `docs/adr/0004-annotation-span-identification.md` (본 ADR 과 강하게 결합 — 함께
    결정 필요)
- **함께 결정된 ADR**: `docs/adr/0004-annotation-span-identification.md` — 본 PR 에 묶여
  정합성 확보. §"두 ADR 의 함께 작동" 섹션 참고.

---

## Context (배경)

ADR-0002 D1.1 은 `Passage.body_text` / `Passage.paragraphs` 가 출제용 마커
(`①②③④⑤`, `_..._`, `______`, `(A)/(B)/(C)`, `(a)~(e)` 등) inline 보존 여부에 대해
**중립**이라 명시하고, 최종 정책 확정을 본 ADR 로 위임했다.

### 마커 종류 인벤토리 (audit §2.2 + 영상 레퍼런스 종합)

| 마커 | 의미 | 표면 형태 예시 | 등장 유형 (exam-generator) |
|---|---|---|---|
| 원숫자 (`①②③④⑤`) | 어법/어휘 선지 또는 위치 마커 | `is ①_word_ ... ⑤_word_` / `①다음문장` | 어법(29), 어휘(30), 무관문장(35), 문장삽입(38, 39) |
| 인라인 밑줄 (`_..._`) | 텍스트 런 underline (출제용) | `①_endeavor_` | 밑줄함의(21), 어법(29), 어휘(30), 장문(41-42, 43-45) |
| 빈칸 (`______`) | 6 underscore 빈칸 | `... by ______ ...` | 빈칸-구(31), 빈칸-절(32~34), 요약문(40) |
| 본문 내장 박스 (`(A)/(B)/(C)`) | 어휘/어법 선택 박스 (Gap A) | `(A) [long-term / short-term]` | exam-generator 미흡수, 내신/사설 흔함 (audit-review-domain §3.1) |
| 단락 라벨 (`(A) (B) (C) (D)`) | 순서배열 / 장문 단락 라벨 | `(A) ...` 시작 단락 | 순서(36, 37), 장문독해(43-45) |
| 지칭 라벨 (`(a)~(e)`) | 지칭/어휘 라벨 (소문자) | `(a) word` | 장문(41-42), 장문독해(43-45) |

### 영상 레퍼런스의 시사점 (reference-program-analysis §4.2)

영상의 "구문 분석 편집" 도구에서는 위 출제용 마커가 **전혀 보이지 않는다**. 즉
구문분석은 정제된 영어 본문 위에서 이뤄지는 별 단계의 작업이다. 같은 지문이 출제용
(마커 박힘) ↔ 분석용 (마커 정제) 두 표현 사이를 오간다.

### 결정 영역 (3단계 모두 영향)

1. **추출 (Phase 0)**: LLM 이 PDF/이미지/텍스트 입력에서 본문을 받을 때 마커 inline
   보존 vs 분리 후처리.
2. **저장 (DB)**: `Passage.body_text` 가 inline 보존 vs 정제 본문 + 별 마커 메타.
3. **출력**:
   - **학생용 (Phase 2)**: 빈 칸 형태 (학생 푸는 용) ↔ 정답 마커 (교사용 / 정답지) 동적
     생성.
   - **변형문제 (Phase 3)**: 같은 본문에서 다른 위치의 마커 재부착.
   - **구문분석 (Phase 1)**: 정제 본문 위에서 작업.

---

## 후보 평가

### A. inline 보존 (`body_text` 안에 마커 그대로)

`Passage.body_text` 에 출제용 마커가 그대로 박힌다. exam-generator 와 동일.

| 기준 | 평가 |
|---|---|
| 추출 단계 | LLM 출력 그대로 저장 — 단순. |
| Phase 1 (구문분석) | `body_text` 가 마커 박힌 상태로 들어옴. 에디터에서 마커 제거 필요 — 에디터 책임 비대. ADR-0004 의 char offset 이 마커 변경 시 invalidate. |
| Phase 2 (학생용) | 학생용은 마커 박힌 그대로 출력 (요약문 빈칸 등). 정제 텍스트 필요 시 후처리 (마커 제거 정규식). |
| Phase 3 (변형문제) | **취약**. 같은 본문으로 어법 → 빈칸 → 어휘 변형을 만들 때 마커 위치가 매번 다름 → 본문을 매번 새로 저장하거나 마커 제거/재부착 후처리 분산. |
| ADR-0004 정합 | **취약**. char offset 이 마커 inline 텍스트 위에서 계산되면, 학생용 출력 시 마커 제거 후 offset shift → annotation 깨짐. |

### B. 완전 분리 (`body_text` 는 정제, 별 `markers: list[Marker]` 메타)

`Passage.body_text` 는 마커 0인 정제 영어 본문. 모든 마커는 별 엔티티 또는 메타로 분리.

```python
class Passage(BaseModel):
    body_text: str  # 마커 0
    # markers 는 Question 종속? Passage 종속? — 결정 필요

class Marker(BaseModel):
    kind: Literal["circled", "blank", "inline_underline", "inline_choice_box",
                  "section_label", "referent_label"]
    span: AnnotationSpan  # body_text 위 char offset (ADR-0004)
    payload: dict
```

| 기준 | 평가 |
|---|---|
| 추출 단계 | LLM 출력에서 마커 분리 후처리 필요 — 정규식 1회 (대부분 lossless, audit §6.2). |
| Phase 1 | `body_text` 가 정제 본문이라 에디터 입력이 자연스러움. ADR-0004 char offset 이 stable. |
| Phase 2 | 학생용 출력 시 마커 동적 삽입 — markers[] 를 char offset 순으로 본문에 inject. 변형 유형별로 다른 markers[] 만 갈아끼우면 됨. |
| Phase 3 | **강력**. 같은 body_text 에 다른 markers[] 를 부착해 어법/빈칸/어휘 변형 모두 표현. 본문 중복 저장 0. |
| ADR-0004 정합 | **강력**. char offset 이 정제 본문 위에서 stable — 마커 변경이 본문을 안 건드림. |
| 비용 | 모든 추출/렌더 코드가 marker injection 어댑터를 알아야 함. schema 복잡도 ↑. exam-generator 와의 호환성 변환 layer 필요. |

### C. 하이브리드 — 마커 종류별 다른 정책

| 마커 종류 | 정책 | 사유 |
|---|---|---|
| 원숫자 (`①②③④⑤`) — 출제용 위치 마커 | **분리** | 변형 시 위치 재계산. |
| 인라인 밑줄 (`_..._`) — 출제용 underline | **분리** | 변형 시 다른 단어에 underline. |
| 빈칸 (`______`) — 출제용 | **분리** | 변형 시 다른 위치에 빈칸. |
| 본문 내장 박스 `(A)/(B)/(C)` — 출제용 | **분리** | Question.inline_choices (ADR-0002 D2.3) 와 통합. |
| 단락 라벨 `(A) (B) (C) (D)` — 구조 마커 | **inline 보존** | 단락 자체의 본문 일부 — 의미상 본문에 속함. |
| 지칭 라벨 `(a)~(e)` — 본문 일부 | **inline 보존** | 지문 내 인물/사물 지칭으로 본문에 박혀 있어야 의미 있음. |

| 기준 | 평가 |
|---|---|
| 추출 단계 | LLM 에게 마커 종류별 정책 안내 — 프롬프트 명세 1회 갱신. 후처리 정규식은 분리 마커만 적용. |
| Phase 1 | `body_text` 에는 단락 라벨 / 지칭 라벨만 inline 보존 — 구문분석에 영향 미미 (영상 레퍼런스도 `(a)~(e)` 같은 라벨이 본문에 박힌 상태로 작업). |
| Phase 2 | 출제용 마커 (원숫자/밑줄/빈칸/박스) 는 동적 삽입. 단락/지칭 라벨은 본문 그대로. |
| Phase 3 | 출제용 마커 분리로 변형 자유도 강력. 단락/지칭 라벨은 본문 일부라 변경 안 됨. |
| ADR-0004 정합 | **강력**. char offset 이 출제용 마커 0인 본문 위에서 stable. 단락/지칭 라벨은 본문 일부라 텍스트 변경 없음. |
| 비용 | "어떤 마커가 분리인가" 분류 명세 + 마커별 처리 어댑터. B 보다는 단순하나 A 보다는 복잡. |

### D. inline + marker_index 메타 (A 변형)

`body_text` 에 마커 inline + 별 `marker_index: list[int]` 로 위치 인덱스 보존.

| 기준 | 평가 |
|---|---|
| Phase 3 | 본문 자체가 변형마다 다름 — 본문 중복 저장. 자산화 가치 훼손. |
| ADR-0004 정합 | char offset 이 마커 포함 본문 위에서 계산 — 마커 변경 시 offset shift. A 와 동일 약점. |
| 비용 | A + 인덱스 메타 — 추가 가치 적음. |

기각.

---

## Decision (결정)

### 채택안: **C 하이브리드 — 마커 종류별 분리 정책**

마커는 **출제용 (variability 있음)** vs **본문 구조 일부 (variability 없음)** 로 나뉘며,
정책이 다르다.

#### 분리 마커 (출제용)

다음 4종은 **`Passage.body_text` 에서 제거** 되고 별 메타로 분리된다:

1. 원숫자 (`①②③④⑤`)
2. 인라인 밑줄 (`_..._`)
3. 빈칸 (`______`)
4. 본문 내장 박스 (`(A) [opt1 / opt2]`) — ADR-0002 D2.3 의 `Question.inline_choices` 로
   이미 분리 중이므로 본 ADR 은 그 결정 재확인.

#### inline 보존 마커 (본문 구조 일부)

다음 2종은 **`Passage.body_text` 에 그대로 박힌다**:

1. 단락 라벨 (`(A) (B) (C) (D)` — 순서배열 / 장문독해 단락 시작 라벨)
2. 지칭 라벨 (`(a)~(e)` — 장문 세트의 인물/사물 지칭)

이들은 본문의 의미적 구조 일부이며, 다른 마커처럼 변형마다 위치가 바뀌지 않는다.
영상 레퍼런스에서도 본문에 박힌 상태로 구문분석이 진행되는 것이 자연스럽다.

#### 분리 마커의 메타 위치

본 ADR 은 분리 마커 메타의 영속 위치를 다음과 같이 정한다:

- **출제용 마커 (원숫자 / 빈칸 / 인라인 밑줄)** 는 `Question` 종속.
  구체 schema 는 후속 PR (architect, ADR-0002 후속) — 본 ADR 은 정책 결정만:
  - 같은 Passage 에 여러 Question 이 매달릴 수 있고, 각 Question 이 자신의 마커를
    소유.
  - `Question.markers: list[QuestionMarker]` 형태 가설. `QuestionMarker` =
    `{kind, span(AnnotationSpan), payload}`.
- **본문 내장 박스 `(A)/(B)/(C)`**: `Question.inline_choices` (ADR-0002 D2.3 채택)
  그대로 사용.

#### `body_text` 의 정의 갱신

`Passage.body_text` 의 docstring 갱신 (후속 schema PR):

> 본문 영어 텍스트. 출제용 마커 (`①②③④⑤`, `______`, `_..._`, `(A) [opt/opt]`) 는
> 제거된 정제 본문. 단락 라벨 (`(A) (B) (C) (D)`) 과 지칭 라벨 (`(a)~(e)`) 은 본문
> 구조 일부로 inline 보존된다.

### 사유 (한 줄)

audit Gap K + audit-review-domain §3.5 의 출제 도메인 멘탈 모델 ("본문은 한 번 저장,
마커는 매번 다시") + 영상 레퍼런스 §4.2 (구문분석은 정제 본문 위) + ADR-0004 char
offset 의 stable 성 확보 — 4가지가 모두 분리 방향을 가리키되, 본문 구조 일부인 단락/
지칭 라벨까지 무리하게 분리하면 schema 비대화 + 의미 손실 (지칭 라벨이 없는
"비-본문" 표현은 부자연) 이라 하이브리드가 자연스럽다.

### 단순함 vs 정확성 trade-off (명시)

- **B (완전 분리) 대비 단순함 양보**: 단락 / 지칭 라벨을 분리 안 하므로 schema 가
  덜 복잡. 단 분리 정책 분류 ("어떤 마커가 분리인가") 가 도메인 지식으로 코드/문서에
  분산.
- **A (inline 보존) 대비 정확성 확보**: 출제용 마커 분리로 Phase 3 자산화 + ADR-0004
  char offset stable 확보.
- **결정 비용**: 추출 파이프라인 (`packages/extractor/src/extractor/normalizer.py`)
  + LLM 프롬프트 (`docs/prompts/extract-*-v0.md`) 가 분리 마커 4종을 알아야 함.
  exam-generator 와의 호환 변환 layer 1회 필요 (audit §6.2 — 정규식 lossless).

---

## 영향 받는 schema / 코드

본 ADR 은 정책 결정만 — 실제 schema 변경은 후속 PR 로 분리.

### Schema (architect 후속 PR)

| 파일 | 변경 |
|---|---|
| `shared/schemas/passage.py` | `body_text` docstring 갱신 — 분리 마커 4종 제거된 정제 본문 명시. `paragraphs` 도 동일. v0.1 의 "마커 정책 중립" 명시는 본 ADR 결정 인용으로 갱신. |
| `shared/schemas/question.py` | `Question.markers: list[QuestionMarker]` 신규 필드 (또는 `circled_markers / blank_markers / underline_markers` 분리 — 후속 PR 결정). `inline_choices` (ADR-0002 D2.3) 는 그대로 유지. |
| `shared/schemas/annotation.py` | 변경 없음. `SyntaxAnnotation` 은 구문분석 전용. **출제용 마커 ≠ 구문분석 마커** — audit-review-domain §3.5 의 "데이터 모델 통합 가능 / 개념적으로 별 카테고리" 권고에 따라 본 ADR 은 **별 카테고리 유지** 결정. |

### 코드 (backend-dev 후속 PR)

| 파일 | 변경 |
|---|---|
| `packages/extractor/src/extractor/normalizer.py` | LLM 출력 본문에서 분리 마커 4종 추출 + `body_text` 정제 + `Question.markers` 채움. exam-generator `app/llm/generator.py:221-238` (`_apply_alpha_markers`) 의 역방향. |
| `docs/prompts/extract-text-v0.md` | LLM 에게 마커 정책 안내 — "본문은 정제, 마커는 별 필드로". |
| `docs/prompts/extract-image-v0.md` | 동일. Vision LLM 입력에도 동일 정책. |
| `packages/llm/` 의 structured output | LLM 이 `Passage` + `Question.markers` 분리된 형태로 출력하도록 prompt + Pydantic model 정합. |

### Repository / Renderer

- `packages/hwpx_renderer/`: 렌더 시 `body_text` + `Question.markers` 를 다시 합성해
  HWPX 출력. 학생용 vs 교사용 분기에서 마커 표시 여부만 toggle.
- `packages/editor/`: 구문분석 에디터는 `body_text` (정제) 그대로 입력 — 변경 없음.

---

## 두 ADR 의 함께 작동 — ADR-0004 (Annotation span 식별 방식) 과의 정합

본 ADR 은 ADR-0004 와 강하게 결합된다. 함께 작동하는 시나리오:

### 결정 정합 매트릭스

| ADR-0004 | 본 ADR | 정합성 |
|---|---|---|
| A char offset | A 마커 inline 보존 | **취약 조합** — 마커 변경 시 모든 offset shift. |
| A char offset (채택) | C 하이브리드 — 출제용 분리 / 단락·지칭 inline 보존 (채택) | **선택 조합** — `body_text` 는 출제용 마커 제거된 정제 본문. annotation offset 은 정제 본문 위에서 stable. 단락/지칭 라벨은 본문 일부라 텍스트 변경 없음 → offset shift 없음. |
| C token id | B 마커 분리 | 가장 robust 하지만 토크나이저 도입 비용 (ADR-0004 가 기각) |

### 함께 작동하는 한 줄 시나리오

`Passage.body_text` = 출제용 마커 (원숫자/밑줄/빈칸/박스) 가 제거된 정제 영어 본문
+ 단락 라벨 / 지칭 라벨만 inline 보존 (본 ADR). `AnnotationSpan` = 그 정제 본문 위
character offset (ADR-0004). 같은 Passage 에 어휘 변형 / 어법 변형 / 빈칸 변형 N개의
Question 이 매달려도 `body_text` 는 1번 저장, `Question.markers[]` 만 다르고, 구문분석
annotation 은 영향받지 않는다.

### 정합 패키지의 5경계 통과 (ADR-0001 검증)

| 경계 | 통과 형태 |
|---|---|
| LLM structured output | `Passage(body_text 정제)` + `Question(markers, inline_choices)` 분리 형태로 LLM 이 출력. |
| FastAPI request/response | 동일 Pydantic 모델 그대로. |
| DB ORM | `body_text` = TEXT 컬럼, `markers` = JSONB 또는 별 테이블 (backend-dev 결정). |
| 에디터 (Tiptap) | `body_text` 정제 본문 + `SyntaxAnnotation[]` 만 받음 — 출제용 마커는 에디터 무관 (영상 레퍼런스 §4.2 정합). |
| HWPX 렌더러 | 학생용 출력 시 `body_text` + `Question.markers` 합성. 교사용도 동일 + 정답 마커 표시. 렌더러가 분기 책임. |

---

## Consequences (결과)

### 긍정적 결과

- **Phase 1 진입 차단 해제**: `Passage.body_text` 정의 확정으로 구문분석 에디터의
  입력 형태가 명확. ADR-0004 char offset 의 stable 영역 확보.
- **콘텐츠 자산화 가치 명제 (CLAUDE.md §1.3) 구현**: 한 Passage 가 여러 Question
  변형의 base 가 됨. 본문 중복 저장 0.
- **Phase 3 변형 자유도**: 같은 body_text 에 markers[] 만 갈아끼우면 어휘/어법/빈칸
  변형 모두 표현.
- **출제 도메인 멘탈 모델 정합** (audit-review-domain §3.5): 강사가 작업하는 단위와
  schema 단위가 일치.
- **영상 레퍼런스 정합** (reference-program-analysis §4.2): 구문분석 단계가 정제 본문
  위에서 진행됨이 자연.
- **exam-generator 호환성**: audit §6.2 의 "정규식 1회 lossless" 변환으로 기존
  exam-generator fixture 24개 유형 흡수 가능.

### 부정적 결과 / 비용

- **추출 파이프라인 복잡도 증가**: LLM 프롬프트 / normalizer 가 분리 마커 4종을
  알아야 함. exam-generator 의 inline 방식 대비 후처리 1단계 추가.
- **분리/inline 보존 분류 도메인 지식 분산**: "어떤 마커가 분리, 어떤 게 보존" 이
  코드/프롬프트/ADR 에 흩어짐. 완화: 본 ADR 의 §"분리 마커" / §"inline 보존 마커"
  목록이 SSOT. 변경 시 본 ADR 갱신 PR 필수.
- **출제용 마커 schema 미확정**: 본 ADR 은 `Question.markers` 의 정확한 schema 를
  결정하지 않음 — 후속 PR (architect) 책임. v0.1 schema 가 일시적으로 마커 미흡수
  상태로 머무를 수 있음. 완화: ADR-0002 D2.3 의 `inline_choices` 가 이미 한 sub-form
  분리 — 후속 PR 에서 다른 마커도 같은 패턴 적용.
- **단락/지칭 라벨 inline 보존의 도메인 한계**: 매우 드물게 단락 셔플 변형
  (exam-generator `_shuffle_long_set_passages`) 같은 케이스에서 단락 라벨 위치가
  바뀜. 이 경우 본문 자체가 변형되므로 별 Passage 로 저장하는 것이 자연 (콘텐츠
  자산화 관점에서 다른 본문). 완화: shuffle 결과는 별 Passage entity.
- **migration 비용 (Phase 0 fixture)**: exam-generator 24개 유형 sample 을 분리 형태로
  변환하는 fixture 1개 작성 필요 (audit §6.3 권고).

### 후속 결정 트리거

| 항목 | 시점 | 담당 |
|---|---|---|
| `Question.markers` 의 정확한 schema | 후속 architect PR | architect |
| 추출 normalizer 의 마커 분리 정규식 | Phase 0 입력 파이프라인 작업 | backend-dev |
| LLM 프롬프트 마커 정책 안내 | 동일 | domain-expert + backend-dev |
| 단락 셔플 결과를 별 Passage 로 저장하는 정책 | Phase 3 진입 전 | architect + domain-expert |
| 변형문제 생성 시 markers[] 자동 생성 vs 사용자 입력 | Phase 3 | qa-validator + domain-expert |

---

## 후속 작업 (다음 작업자에게)

### architect — schema 변경 (후속 PR)

본 ADR 결정에 따른 schema 변경:

1. `shared/schemas/passage.py` — `body_text` / `paragraphs` docstring 갱신 (정제 본문
   + 단락/지칭 라벨 inline 보존 명시).
2. `shared/schemas/question.py` — `Question.markers: list[QuestionMarker]` 추가
   (구체 구조는 후속 PR 결정 — 원숫자/빈칸/인라인 밑줄 통합 vs 분리 결정).
3. `shared/schemas/annotation.py` — 변경 없음 (별 카테고리 유지 결정).

**본 PR 에는 schema 변경 미포함** — 본 PR 은 순수 ADR 문서.

### backend-dev — 추출 파이프라인 갱신

1. `packages/extractor/src/extractor/normalizer.py`:
   - LLM 출력에서 분리 마커 4종 추출 정규식 (audit §2.2 + exam-generator 의
     `_apply_alpha_markers` 역방향 패턴 참고).
   - `body_text` 정제 + `Question.markers` 채움.
   - 단락/지칭 라벨은 inline 보존 — 정규식 매칭에서 제외.
2. exam-generator fixture (24개 유형) 변환 함수 — `tests/fixtures/exam_generator_compat/`
   (audit §6.3 권고).

### domain-expert — LLM 프롬프트 갱신

1. `docs/prompts/extract-text-v0.md` — LLM 에게 마커 정책 안내. 본 ADR §"분리 마커" /
   §"inline 보존 마커" 목록 인용.
2. `docs/prompts/extract-image-v0.md` — Vision LLM 입력 동일 정책.
3. `docs/variant-type-catalog.md` (재작성 시) — 변형 유형별 markers[] 형태 정의 시
   본 ADR 결정 반영.

### frontend-dev — 영향 없음 (확인 항목만)

본 ADR 은 구문분석 에디터 입력 형태에 영향 없음 (`body_text` 정제 본문이 그대로 들어옴).
단 Phase 2 학생용 / 교사용 미리보기 구현 시 markers[] 합성 렌더링 책임이 frontend
에도 있을 수 있음 — Phase 2 진입 시 확인.

---

## Alternatives Considered (검토한 대안)

### A. inline 보존 (exam-generator 동일)

- 장점: 추출 단순. exam-generator 1:1 호환.
- 단점: Phase 3 변형 시 본문 중복 저장 또는 마커 제거/재부착 후처리 분산. ADR-0004
  char offset 이 마커 변경 시 invalidate.
- 기각 사유: 콘텐츠 자산화 가치 명제 위배. ADR-0004 와 결합 시 취약.

### B. 완전 분리 (단락/지칭 라벨까지 분리)

- 장점: 가장 정규화. schema 일관.
- 단점:
  1. 단락 라벨 `(A) (B) (C) (D)` 가 본문 의미 일부 — 분리하면 본문 표현이 부자연
     ("Look at the (A): ..." 같은 자연어가 안 됨).
  2. 지칭 라벨 `(a)~(e)` 동일 — 본문에서 `(a) word` 형태로 등장하는 게 출제 관행.
  3. 영상 레퍼런스에서도 단락/지칭 라벨이 본문에 박힌 상태로 구문분석.
- 기각 사유: schema 정규화의 과도한 추구가 도메인 자연스러움과 충돌.

### D. inline + marker_index 메타

- 장점: 일부 후처리 회피.
- 단점: 본문 자체 중복 저장. ADR-0004 char offset 이 마커 변경 시 여전히 invalidate.
- 기각 사유: A 의 단점 + 추가 비용 = 가치 없음.

### E. 마커를 SyntaxAnnotation 에 통합

audit-review-domain §3.5 가 시사한 "데이터 모델 통합 가능" 옵션 — 출제용 마커도
`SyntaxAnnotation.kind` 의 한 종류로 흡수.

- 장점: 단일 entity 로 모든 마커 표현. schema 단순.
- 단점:
  1. 개념적으로 별 카테고리 — `SyntaxAnnotation` 은 강사가 구문분석 작업으로 그리는
     마크 (영상 레퍼런스 §2 의 7종), 출제용 마커는 출제 단계 산출물. 시각 표현 / 데이터
     라이프사이클 / 사용자 권한 모두 다름.
  2. `kind` enum 비대화 (현재 7종 → 13종).
  3. 같은 span 에 두 종류가 동시에 걸리는 케이스 (어법 ① 마크 단어를 구문분석에서도
     형용사로 라벨링) 의 시각적 구분이 enum value 만으로는 어려움.
- 기각 사유: audit-review-domain §3.5 의 "개념적으로 별 카테고리" 권고가 강함.
  데이터 통합 가치 < 개념 분리 가치.

---

## References

- `CLAUDE.md` v0.4 §1.3 (콘텐츠 자산화), §11
- `docs/schema-coverage-audit.md` §2.2 (4종 마커 시스템), §3 Gap K, §4-6, §6.2 (호환
  변환)
- `docs/audit-review-domain.md` §3.5
- `docs/reference-program-analysis.md` §4.2
- `docs/adr/0001-canonical-schema-philosophy.md`
- `docs/adr/0002-content-model-v0_1.md` D1.1, D2.3
- `docs/adr/0004-annotation-span-identification.md` (본 ADR 과 함께 결정)
- exam-generator `app/llm/generator.py:221-238` (`_apply_alpha_markers` — 역방향
  변환 참고)
