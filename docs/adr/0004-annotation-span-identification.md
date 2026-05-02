# ADR 0004 — Annotation span 식별 방식 (Phase 1 진입 차단 해제)

- **상태(Status)**: Accepted
- **작성일**: 2026-05-02
- **작성자**: architect agent
- **유형**: Phase 1 진입 전 차단 ADR — `shared/schemas/annotation.py` 의 `AnnotationSpan` placeholder 확정
- **관련 문서**:
  - `CLAUDE.md` v0.4 §3.5 (Tiptap 기반), §11 Open Question (Annotation span 식별 방식)
  - `docs/schema-coverage-audit.md` §4-4
  - `docs/audit-review-domain.md` §3.4, §5.2 (domain-expert 이견)
  - `docs/reference-program-analysis.md` §3.1, §4.1 (영상 레퍼런스 — 단어 단위 선택)
  - `docs/adr/0001-canonical-schema-philosophy.md` (5경계 척추 원칙)
  - `docs/adr/0002-content-model-v0_1.md` D3.5 (placeholder 정의 + 본 ADR 위임)
  - `apps/web/src/pages/EditorPoc.tsx` (Sprint 0 #7 Tiptap PoC — 직렬화 형태 관찰)
- **함께 결정된 ADR**: `docs/adr/0006-marker-processing-policy.md` (마커 처리 정책) —
  본 PR 에 묶여 정합성 확보. §"두 ADR 의 함께 작동" 섹션 참고.

---

## Context (배경)

ADR-0002 D3.5 는 `shared/schemas/annotation.py` 의 `AnnotationSpan` 을
**placeholder** (`span_format: Literal["character_offset_v1"]` + `data: dict[str, Any]`)
로 두고, 식별 방식 확정을 본 ADR 로 위임했다.

3자 입력이 누적됐다.

| 출처 | 권고 |
|---|---|
| audit §4-4 (architect 1차) | character offset on `Passage.body_text`. 단순함 우선. |
| audit-review-domain §3.4 (domain-expert) | token id 1순위 검토. 강사 멘탈 모델은 단어/절 단위. 약~중 강도 이견. |
| reference-program-analysis §3.1, §4.1 | 영상 레퍼런스 = 단어 단위 선택 + Shift/Alt 비연속 다중 선택. |
| EditorPoc.tsx 직렬화 관찰 (frontend-dev 메모) | ProseMirror JSON 은 mark range 를 `text` 노드 분리 + `marks[]` 로 표현. 절대 character offset 은 트리 누적 순회로 복원 필요. |

본 ADR 은 위 4개 입력을 종합해 v0.1 식별 방식을 확정하고, ADR-0001 의 5경계 척추 원칙
(LLM / API / DB / 에디터 / 렌더러) 모두에 무손실 통과 가능한 표현을 선택한다.

### 평가 기준

1. **5경계 통과 가능성** — 한 표현이 LLM structured output / DB row / Tiptap 상태 /
   HWPX 출력 / API 응답 모두에 의미 보존되며 흘러야 함 (ADR-0001).
2. **Phase 1 작업 차단 해제 비용** — frontend-dev 가 Phase 1 에디터 첫 PR 에 곧바로
   진입할 수 있는가? 새 라이브러리 / 토크나이저 도입이 필요하면 비용 증가.
3. **텍스트 변경 robust 성** — 사용자가 본문을 수정할 때 annotation 이 깨지는 정도.
4. **변형문제 (Phase 3) 호환** — 같은 본문에서 다른 위치 마커, 또는 어휘 변형으로 본문이
   미세하게 바뀐 derived passage 와의 annotation 호환.
5. **CLAUDE.md §3.6 — No Reinventing the Wheel** — 새 토크나이저 / 형태소 분석기 도입
   비용.

---

## 후보 평가

### A. Character offset (`{start: int, end: int}` on `Passage.body_text`)

**모델 표현**:
```python
class AnnotationSpan(BaseModel):
    span_format: Literal["character_offset_v1"]
    start: int  # body_text 위 [start, end) 반열린 구간
    end: int
```

| 기준 | 평가 |
|---|---|
| 5경계 통과 | LLM/API/DB 단순. 에디터에서는 Tiptap pos ↔ char offset 누적 변환 필요 (PoC 메모). HWPX 는 char offset → 텍스트 런 분할 매핑. |
| Phase 1 진입 비용 | 낮음. 추가 의존성 없음. |
| 텍스트 변경 robust | **취약**. 1글자 추가/삭제로도 모든 후속 offset shift. |
| Phase 3 호환 | 변형 본문은 별 Passage 로 분리되므로 본 자체 영향 없음. 단 같은 Passage 에 마커 위치만 바뀌는 시나리오 (ADR-0006) 에서는 마커 변경이 annotation offset 을 깰 수 있음 — **ADR-0006 결정과 강하게 결합**. |
| 라이브러리 비용 | 없음. |

### B. ProseMirror position (`{from: number, to: number}` — Tiptap doc 위치)

**모델 표현**:
```python
class AnnotationSpan(BaseModel):
    span_format: Literal["prosemirror_pos_v1"]
    from_pos: int
    to_pos: int
    # 영속화 시 schema 의존 — schema_version 동반 필요
    schema_version: str
```

| 기준 | 평가 |
|---|---|
| 5경계 통과 | Tiptap-native. 단 LLM/HWPX/API 외부에서는 ProseMirror schema 의 paragraph/heading 노드가 1 char 차지하는 규칙을 알아야 해석 가능 — 외부 경계에서 의미 불명확. |
| Phase 1 진입 비용 | 매우 낮음. Tiptap 의 native 표현. |
| 텍스트 변경 robust | Tiptap 내부에서는 transform 으로 position mapping 가능 (ProseMirror 의 mark step). 직렬화 후 외부에서 위치 mapping 은 schema 동봉 필수. |
| Phase 3 호환 | derived passage 마다 ProseMirror schema 다시 적용하면 동작. 단 schema 변경 마이그레이션 부담. |
| 라이브러리 비용 | 없음 (Tiptap 이미 채택). |

### C. Token id (`{token_ids: list[str]}` — 사전 토큰화 후 stable ID)

**모델 표현**:
```python
class AnnotationSpan(BaseModel):
    span_format: Literal["token_id_v1"]
    token_ids: list[str]  # Passage.tokens[] 의 id 시퀀스
```

`Passage.tokens: list[Token]` 새 필드 필요 (`Token = {id, text, char_start, char_end}`).

| 기준 | 평가 |
|---|---|
| 5경계 통과 | 영어 단어 단위는 자연스럽게 매핑되나 — 한국어 / 영어 혼합 (예: 어휘 박스의 한국어 의미) 케이스에서 토큰화 정책 결정 필요. |
| Phase 1 진입 비용 | **높음**. (1) 토크나이저 결정 (whitespace? sentencepiece? spaCy? KoNLPy?) (2) `Passage.tokens` 필드 추가 + 마이그레이션 (3) frontend-dev 의 Tiptap mark schema 가 token id 를 anchor 로 잡는 ProseMirror plugin 직접 작성 (4) LLM 출력 → token id 매핑 어댑터. |
| 텍스트 변경 robust | **강함**. 토큰 추가/삭제만 영향. id 가 stable 하면 문장 중간 단어 수정해도 다른 token id 는 보존. |
| Phase 3 호환 | derived passage 의 token id 가 원본과 매핑 가능하면 변형 어휘 swap 같은 시나리오에서 강력. 그러나 매핑 자체가 별 추론 단계. |
| 라이브러리 비용 | **무거움**. KoNLPy 같은 형태소 분석기 도입은 CLAUDE.md §3.6 의 "작은 유틸 1~2개 쓰자고 무거운 라이브러리 통째 도입은 지양" 에 충돌. 영어 전용 whitespace 토크나이저는 자체 구현 가능하나 한국어 혼합 (어휘 박스 등) 케이스에서 깨짐. |

### D. 하이브리드 — 메모리는 B, 영속화는 A

에디터 내부 (Tiptap) 는 ProseMirror position 로 동작, 직렬화 / DB 저장 / API 응답은
character offset 으로 정규화.

| 기준 | 평가 |
|---|---|
| 5경계 통과 | A 와 동일 — DB/LLM/API/HWPX 는 char offset 만 본다. Tiptap 내부는 PoC 가 이미 보여주듯 자동 변환. |
| Phase 1 진입 비용 | A + 변환 어댑터 1개. 변환 어댑터는 PoC 메모에 이미 구현 단서가 있음 (트리 순회 + 텍스트 노드 길이 누적). |
| 텍스트 변경 robust | A 와 동일하게 취약. 단 에디터 세션 동안에는 Tiptap 의 mark transform 으로 자동 보정. |
| Phase 3 호환 | A 와 동일. |
| 라이브러리 비용 | 없음. |

---

## Decision (결정)

### 채택안: **D 하이브리드 변형 — 메모리 ProseMirror position + 영속화 character offset**

`AnnotationSpan` 의 정식 형태는 v0.1 placeholder 의 `character_offset_v1` 을
**확정 default 로 승격**한다. 단 본 ADR 은 변환 책임 분리를 명시한다.

```python
class SpanFormat(StrEnum):
    CHARACTER_OFFSET_V1 = "character_offset_v1"

class AnnotationSpan(BaseModel):
    span_format: Literal["character_offset_v1"]
    start: int = Field(..., ge=0)
    end: int = Field(..., gt=0)  # exclusive, [start, end)
    # ADR-0002 v0.1 의 data: dict[str, Any] placeholder 는 본 ADR 로 정식 필드 승격.
```

**핵심 규칙**:

1. **DB / API / LLM structured output / HWPX 렌더러**: `AnnotationSpan` =
   `(start, end)` character offset on `Passage.body_text`. 5경계 통과 단순.
2. **Tiptap 에디터 내부**: ProseMirror position `(from, to)` 로 작업. 사용자 편집 중
   ProseMirror 의 mark transform 이 자동 보정.
3. **변환 책임**: `packages/editor/` 에 양방향 변환 어댑터 `pmPosToCharOffset` /
   `charOffsetToPmPos` 를 둔다 — frontend-dev 의 Phase 1 첫 작업.
   - Tiptap doc 트리를 순회하며 텍스트 노드 길이를 누적하는 EditorPoc.tsx 메모의
     로직을 정식 구현.
4. **`Passage.body_text` 는 안정 source**: ADR-0006 의 마커 정책 결정에 따라
   `body_text` 가 마커 inline 보존 텍스트인지 정제 텍스트인지 결정되며, 본 ADR 의
   offset 은 **그 결정된 text 를 기준**으로 계산.

### 사유 (한 줄)

ADR-0001 의 5경계 척추 원칙을 가장 단순하게 만족하면서, Tiptap PoC 가 이미 변환
보일러플레이트 단서를 제시했고, token id (C) 는 한국어 혼합 케이스에서 무거운 형태소
분석기 도입을 강제하므로 CLAUDE.md §3.6 위반 위험이 크다.

### 단순함 vs 정확성 trade-off (명시)

- **단순함 채택**: `(start, end)` 만으로 영속화. 추가 의존성 0.
- **포기한 정확성**:
  - 텍스트 변경 robust 성 — 사용자가 본문 수정 시 annotation offset shift 위험 존재.
    완화: 에디터 세션 내에서는 ProseMirror mark transform 이 자동 보정. 세션 외
    body_text 수정 (예: API 직접 PATCH) 은 v0.1 에서 막거나 annotation 일괄 무효화
    정책으로 대응 (Phase 1 PR 결정).
  - 단어 단위 강사 멘탈 모델 — 저장은 char offset 이지만 **에디터 입력은 단어 스냅
    (snap)** 으로 강제 (영상 레퍼런스 §3.1 의 "클릭+드래그 단어 선택"). frontend-dev
    의 Tiptap plugin 작업 영역 — 입력 단계에서 단어 경계로 snap 후 char offset 으로
    저장.
- **PoC 메모와 정합**: EditorPoc 의 직렬화 관찰 ("ProseMirror JSON 은 mark range 를
  text 노드 분리로 표현, 절대 char offset 은 트리 누적 순회 필요") 가 본 결정의 변환
  어댑터 위치를 정확히 시사함.

---

## 후보별 5경계 영향 상세

| 후보 | shared/schemas/annotation.py | Tiptap mark serialize/deserialize | HWPX 출력 (Phase 1 DoD) | 변형문제 (Phase 3) derived passage 호환 |
|---|---|---|---|---|
| A | `start: int, end: int` 단순 추가 | `pmPosToCharOffset` / 역방향 어댑터 1쌍 | char offset → 텍스트 런 분할 인덱스 1:1 | derived passage 는 별 ID. annotation 은 원본 Passage 종속이라 직접 호환 영역 아님. ADR-0006 정책에 따라 마커 변경 시 annotation 영향 가능. |
| B | `from_pos, to_pos, schema_version` | native (변환 0) | ProseMirror schema 해석 필요 — HWPX 빌더가 Tiptap schema 를 알아야 함. 결합도 ↑ | derived passage 마다 schema 다시 박아야. schema 마이그레이션 부담. |
| C | `token_ids: list[str]` + `Passage.tokens` 새 필드 | Tiptap plugin 으로 token id anchor mark 직접 구현 — 검증된 라이브러리 없음 | token id → char range 매핑 후 텍스트 런 분할 | token id 가 derived passage 와 매핑 가능하면 강력. 매핑 추론은 별 단계 (LLM 또는 alignment). |
| D (채택) | A 와 동일 | A + Tiptap 변환 어댑터 (PoC 메모의 트리 누적 로직) | A 와 동일 | A 와 동일. |

---

## 두 ADR 의 함께 작동 — ADR-0006 (마커 처리 정책) 과의 정합

본 ADR 은 ADR-0006 과 강하게 결합된다. 둘이 함께 작동하는 시나리오를 한 곳에 명시한다.

### 결정 정합 매트릭스

| 본 ADR | ADR-0006 | 정합성 |
|---|---|---|
| A char offset | A 마커 inline 보존 | **취약 조합** — 마커 변경 시 모든 offset shift. |
| A char offset (채택) | C 하이브리드 — 출제용 마커 분리 / 구문분석 마커 inline 보존 (채택) | **선택 조합** — `body_text` 는 출제용 마커 (`①②③④⑤`, `______`, `_..._`) 분리된 정제 본문. annotation offset 은 정제 본문 위에서 stable. |
| C token id | B 마커 분리 | 가장 robust 하지만 토크나이저 도입 비용 |

### 함께 작동하는 한 줄 시나리오

`Passage.body_text` = **출제용 마커가 제거된 정제 영어 본문** (ADR-0006 C 채택).
`AnnotationSpan` = **정제 본문 위 character offset** (본 ADR 채택). 출제용 마커는
`Question.markers[]` 또는 ADR-0006 정책에 따른 별 메타로 분리되어, 본문 변경 없이
어휘 변형 / 어법 변형 / 빈칸 변형으로 재가공해도 annotation offset 은 영향받지 않는다.

이 정합이 ADR-0001 의 "콘텐츠 자산화" 가치 명제 (한 Passage 가 여러 출력에 재사용) 를
구현한다.

---

## Consequences (결과)

### 긍정적 결과

- **Phase 1 진입 차단 해제**: frontend-dev 가 Tiptap mark schema + 변환 어댑터로 곧바로
  진입 가능. 새 라이브러리 도입 0.
- **5경계 무손실**: char offset 은 LLM/API/DB/HWPX 모두 단순 정수쌍으로 통과.
- **EditorPoc 메모 활용**: 트리 누적 순회 변환 로직이 PoC 에서 이미 식별됨 — 정식
  구현은 boilerplate 1쌍.
- **ADR-0006 과 정합**: 출제용 마커 분리 정책이 채택되면 char offset 의 텍스트 변경
  취약성이 대부분 무력화 (마커 변경이 body_text 를 안 건드림).
- **`shared/schemas/annotation.py` v0.1 placeholder 의 `data: dict[str, Any]` 가
  정식 `start/end` 로 승격**되어 mypy strict 환경에서 cast 부담 해소.

### 부정적 결과 / 비용

- **세션 외 body_text 수정 시 annotation 무효화 위험**: API 직접 PATCH 등으로
  body_text 가 변경되면 char offset shift. 완화책:
  1. body_text 수정은 Tiptap 에디터 세션 내에서만 허용 (Phase 1 PR 정책 결정).
  2. 또는 body_text PATCH 시 모든 annotation 일괄 무효화 + 재작성 강제.
- **단어 단위 멘탈 모델 ↔ char offset 저장 mismatch**: 입력 단계의 단어 스냅 plugin
  필요 — frontend-dev 영역. 검증된 Tiptap plugin 이 있는지 PoC 단계에서 확인 필요
  (CLAUDE.md §3.6).
- **token id 옵션 영구 폐기 아님**: `SpanFormat` enum 디스크리미네이터 구조 유지로
  ADR-0005 (Vocabulary 글로벌 마스터) 또는 후속 ADR 에서 token id 가 정당화되면
  추가 가능. v0.1 데이터는 `span_format` 디스크리미네이터로 식별되어 마이그레이션
  가능.

### 후속 결정 트리거

| 항목 | 시점 | 담당 |
|---|---|---|
| 같은 span 에 라벨 2개 이상 충돌 시 시각적 처리 (CLAUDE.md §11) | Phase 1 PR | frontend-dev + domain-expert |
| body_text 수정 후 annotation 무효화 정책 | Phase 1 PR | frontend-dev + architect |
| 단어 스냅 Tiptap plugin — 자체 구현 vs 검증된 라이브러리 | Phase 1 PR | frontend-dev (CLAUDE.md §3.6 절차) |

---

## 후속 작업 (다음 작업자에게)

### frontend-dev — Phase 1 에디터 첫 PR 진입 전 follow-up 검증 항목

본 ADR 의 결정이 Tiptap 에디터 구현에 정합한지 검증할 항목:

1. **Tiptap mark schema 정합성 PoC**:
   - `SyntaxAnnotation.kind` 7종 (top_label / bottom_label / highlight / bracket /
     arrow / inline_note / underline) 각각이 ProseMirror mark / decoration / nodeView
     중 어느 표현으로 가장 자연스러운가?
   - `bracket` (괄호 묶기) 은 mark 가 아니라 decoration 또는 nodeView 후보 — 영상
     레퍼런스 §1 의 시각이 mark 만으로는 어려움.
2. **직렬화 → DB → 역직렬화 round-trip 검증**:
   - Tiptap doc 에 mark 3개 그리고 → `pmPosToCharOffset` 으로 정규화 → DB 저장 형태
     mock → `charOffsetToPmPos` 로 복원 → 원래 Tiptap doc 와 일치 검증.
   - `EditorPoc.tsx` 의 트리 누적 순회 로직을 `packages/editor/` 의 정식 함수로 승격.
3. **Mark 충돌 / 겹침 / 분할 / 결합 처리 검증**:
   - 같은 span 에 highlight + top_label 이 동시에 걸린 케이스, 분할된 mark 가 결합되는
     케이스 등 — ProseMirror 의 mark step 이 자동 처리하는지, 별도 어댑터 로직이
     필요한지.
4. **단어 스냅 입력 plugin** — 영상 레퍼런스 §3.1 의 "클릭+드래그 단어 선택" 구현
   방법 조사 (CLAUDE.md §3.6 절차 — 검증된 라이브러리 우선).

위 4개 항목은 Phase 1 에디터 PR 의 설계 단계 산출물로 요청. PoC 결과로 본 ADR 의
가정이 깨지면 (예: round-trip 이 lossy) follow-up ADR 로 재검토.

### architect — schema 변경 (`shared/schemas/annotation.py`)

본 ADR 의 결정에 따라 `AnnotationSpan` 을 다음과 같이 정정:

```python
# 변경 전 (ADR-0002 D3.5 placeholder)
class AnnotationSpan(BaseModel):
    span_format: Literal["character_offset_v1"]
    data: dict[str, Any]   # {"start": int, "end": int}

# 변경 후 (본 ADR 확정)
class AnnotationSpan(BaseModel):
    span_format: Literal["character_offset_v1"]
    start: int = Field(..., ge=0)
    end: int = Field(..., gt=0)  # exclusive, [start, end)
```

**본 PR 에는 schema 변경 미포함** — 본 PR 은 순수 ADR 문서. schema 변경은 후속 PR
(`architect/annotation-span-schema-update`) 로 분리. 사유: ADR PR 의 리뷰 범위를
문서로 한정해 결정 검토를 빠르게 마무리하고, schema PR 에서 round-trip 테스트 + ORM
동기화 (backend-dev 협업) 를 별 PR 로 다룬다.

### backend-dev — DB 마이그레이션 (필요 시)

`SyntaxAnnotation.span` 의 컬럼 형태가 JSONB 라면 본 ADR 결정으로 schema 가
`{span_format, start, end}` 로 narrow 됨 — 기존 JSONB 컬럼은 그대로 사용 가능.
별도 마이그레이션 불필요. ORM 매핑 시 Pydantic 모델을 그대로 흡수.

### domain-expert — 인터뷰 체크리스트 보강

audit-review-domain §5.2 의 미해결 질문 ("token 채택 시 토큰화 정책") 은 본 ADR 로
해소 (token id 미채택). 단 §5.4 의 "와이프의 실제 표기 규약 sample 자료 요청" 은
유효 — Phase 1 진입 전 와이프 인터뷰 시 본 ADR 의 char offset 결정으로 실사용에
영향이 없는지 확인 항목 추가.

---

## Alternatives Considered (검토한 대안)

### A. 순수 character offset (D 채택안의 영속화 부분만)

- 장점: 가장 단순.
- 단점: Tiptap 내부에서도 char offset 으로 동작하면 ProseMirror 의 mark transform
  이점을 못 살림 — 사용자 편집 중 offset shift 처리 부담.
- 기각 사유: 메모리 표현은 ProseMirror position 으로 두는 D 가 같은 외부 비용으로
  내부 robust 성을 얻음.

### B. 순수 ProseMirror position 영속화

- 장점: 변환 0.
- 단점: HWPX 빌더 / API 응답 / LLM structured output 모두 ProseMirror schema 를
  알아야 — 5경계 척추 원칙 위반.
- 기각 사유: ADR-0001.

### C. Token id

- 장점: 도메인 직관 (단어/절 단위) 와 가장 일치. 영어 텍스트 robust.
- 단점:
  1. 한국어 혼합 케이스 (어휘 박스 한국어 의미, 본문 내 한국어 주석 등) 에서 형태소
     분석기 도입 필요 — KoNLPy 등은 CLAUDE.md §3.6 위반 위험.
  2. `Passage.tokens[]` 새 필드 + 마이그레이션.
  3. Tiptap plugin 자작 — 검증된 token-anchor mark 라이브러리 없음.
  4. LLM 출력 → token id 매핑 어댑터.
- 기각 사유: Phase 1 진입 비용이 너무 큼. 단 본 ADR 의 `SpanFormat` 디스크리미네이터
  구조로 미래 ADR 에서 추가 가능 — 영구 폐기 아님.

### E. 하이브리드 (D) 의 inverse — 메모리는 char offset, 영속화는 token id

- 장점: 영속화 robust + 메모리 단순.
- 단점: token id 의 사전 토큰화 비용은 그대로. 메모리 char offset 은 Tiptap mark
  transform 이점 못 살림.
- 기각 사유: token id 비용 + char offset 단점 = 두 단점 동시.

---

## References

- `CLAUDE.md` v0.4 §3.5, §3.6, §11
- `docs/schema-coverage-audit.md` §4-4
- `docs/audit-review-domain.md` §3.4, §5.2
- `docs/reference-program-analysis.md` §3.1, §4.1, §4.4
- `docs/adr/0001-canonical-schema-philosophy.md` (5경계 척추)
- `docs/adr/0002-content-model-v0_1.md` D3.5 (placeholder 정의 + 본 ADR 위임)
- `apps/web/src/pages/EditorPoc.tsx` (PoC 직렬화 메모)
- `shared/schemas/annotation.py` (v0.1 placeholder — 본 ADR 후속 PR 에서 정정)
