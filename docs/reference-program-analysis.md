# 레퍼런스 프로그램 분석 — 구문 분석 편집 도구

- **분석자**: Dennis (PM, 직접 멀티모달 분석)
- **분석일**: 2026-05-02
- **소스**: `/Users/william/Downloads/ScreenRecording_04-24-2026 15-11-52_1.MP4`
- **소스 메타**: 22초, 60fps, 1206×2622 (모바일 인스타그램 캡처). 인스타 계정
  `highendedu` × `gin__edu` 콜라보 게시물. 대치동 27년 노하우의 "3모 분석지 편집
  단축키 공개" 영상.
- **분석 입력**: ffmpeg 장면 변화 9프레임 + 1초 간격 22프레임 = 31프레임 (`admin/reference-analysis/frames/`, gitignored)
- **목적**: 본 프로젝트의 **Phase 1 구문분석 에디터** UI/기능 설계 입력. 우리가
  만들 도구의 거의 직접적인 기능 명세 후보.
- **관련**: `CLAUDE.md` §11 Open Question, `docs/schema-coverage-audit.md` §4-4
  (Annotation span), `docs/audit-review-domain.md`

---

## 0. 핵심 발견 — 한 줄 요약

영상의 레퍼런스 프로그램은 **"구문 분석 편집"** 모달이고, 영어 본문 위에 **다층
annotation**(라벨, 색깔 마크, 괄호, 동의어 주석)을 그리면 **하단 분석표**가 카테고리별
(주석/주성분/구/절/기타)로 자동 누적된다. 본 프로젝트 Phase 1의 정확한 reference
implementation이다.

---

## 1. 화면 레이아웃 (모달 구조)

영상 scene_006이 가장 깨끗한 풀샷이다. 모달 제목: **"구문 분석 편집"**.

```
┌─────────────────────────────────────────────────────────────────────┐
│ 구문 분석 편집                                                    [×] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [영문 본문 + annotation 영역]                                       │
│  =동명사주어        단수동사       =to부정사(형)            부사절     │
│  Reading aloud is also a good way (to develop ...)  because it ...  │
│      S          V         SC                          S   V  O  OC  │
│                                                                     │
│  부사구       관계절                현재재구문                전치사구  │
│  {each} and {every} word — (something {people don't often do}       │
│  (when {reading} quickly, or {reading} (in silence])])).            │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [하단 분석표 — 카테고리별 누적 칩]                                    │
│  주석   | 형광펜 Reading | 텍스트 Reading | 형광펜 is | 텍스트 is |    │
│         | 형광펜 develop | 텍스트 =foste→nase, develop |              │
│         | 형광펜 because | 형광펜 forces | 형광펜 to read |            │
│         | 말줄 people don't often do | 형광펜 when reading |          │
│         | 형광펜 reading |                                            │
│                                                                     │
│  주성분 | 주어 Reading aloud | 동사 is | 주격보어 a good way |         │
│         | 주어 it | 동사 forces | 목적어 you |                       │
│         | 목적격보어 to read each and every word | 주어 people |      │
│         | 동사 don't often do |                                      │
│                                                                     │
│  구(Phrase) | (to부정사형) to develop yo...eaking skills |             │
│             | (부사구) something peo...ng in silence |                │
│             | (현재분사구문) when reading...ng in silence |            │
│             | (전치사구) in silence |                                 │
│                                                                     │
│  절(Clause) | (부사절) because it to...ng in silence |                 │
│             | (관계절) people don't...ng in silence |                 │
│                                                                     │
│  기타       | (단위) each→every | (단위) reading→reading |             │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  색상  ●●●●●●●●●●●●  (1~12 번호된 색상 팔레트)                         │
│        1 2 3 4 5 6 7 8 9 10 11 12                                   │
│  [텍스트 입력]  =foster, promote, increase                          │
│        develop                                                      │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  Esc 편집 취소/2회 닫기 │ Del 선택 집 삭제 │ 집 클릭 → 드래그로 단어 선택 │
│  Shift +드래그 추가     │ Alt +드래그 제거                              │
└─────────────────────────────────────────────────────────────────────┘
```

(scene_002, scene_003, scene_006 합성 기반)

---

## 2. Annotation 종류 (영상에서 식별된 6종)

| 종류 | 시각적 표현 | 데이터 의미 | 예시 |
|---|---|---|---|
| **상단 라벨** | 본문 위에 작은 글씨 + 색상 박스 (괄호 포함) | 구/절 카테고리 | `=동명사주어`, `단수동사`, `=to부정사(형)`, `부사절`, `관계절`, `현재재구문`, `전치사구`, `부사구` |
| **하단 라벨** | 본문 아래 한 글자 약어 | 주성분(S/V/O/OC/SC) | `S`, `V`, `O`, `OC`, `SC` |
| **하이라이트 (형광펜)** | 단어/구의 배경색 (12색 팔레트 중) | 색깔로 카테고리 구분 (분홍/파랑/노랑/초록 등) | `Reading`(분홍), `is`(파랑), `develop`(파랑) 등 |
| **괄호** | `()`, `{}`, `[]` 다양한 괄호 | 구/절 범위 표시 | `(to develop your public speaking skills)`, `{people don't often do}`, `[reading]` |
| **화살표 / 연결** | 가는 줄로 두 토큰 연결 (영상에서 일부 보임) | 단어 간 의미 관계 | `each → every`, `reading → reading` (=의미 동일 표시) |
| **인라인 주석** | 본문 위에 작게 떠 있는 텍스트 (라벨 형식 아님) | 어휘 동의어/풀이 | `=foster, promote, increase, enhance`가 `develop` 위에 |

이 6종이 본 프로젝트 `SyntaxAnnotation.kind` enum의 **1차 후보 source**가 된다.
CLAUDE.md §2.1 Phase 1 DoD ("상단 라벨 / 하단 라벨 / 괄호 / 하이라이트 / 밑줄 /
화살표")와 거의 일치한다 — 추가로 발견된 것은 **인라인 주석(어휘 동의어)**.

`밑줄`은 영상에 보이지 않았다. 레퍼런스에서 미사용일 가능성도 있고, 영상에 단순히
나타나지 않은 케이스일 가능성도 있다. **PM 결정 필요**.

---

## 3. 인터랙션 패턴 (영상에서 추론)

### 3.1 단어 선택

하단 단축키 안내에서 직접 명시:
- **클릭 + 드래그**: 단어 선택
- **Shift + 드래그**: 선택에 추가
- **Alt + 드래그**: 선택에서 제거
- **Esc**: 편집 취소 / (2회) 모달 닫기
- **Del**: 선택된 칩 삭제

→ **선택 단위는 단어**(token), 글자 단위가 아님. 이는 audit §4-4 (Annotation span
식별 방식) 결정에 직접 영향. domain-expert 권고("강사 멘탈 모델은 단어/절 단위")와
일치.

### 3.2 라벨 입력

scene_002 하단의 **색상 팔레트(1~12)** + **텍스트 입력박스**가 다음을 시사:
- 단어/구를 선택한 뒤 색상을 고르고 라벨 텍스트를 입력하면 **상단 라벨이 입력 텍스트로,
  하이라이트가 선택한 색깔로** 적용된다.
- 라벨 종류(`=동명사주어`, `S`, `(부사구)` 등)는 **자유 문자열**로 보인다 — preset이
  아니라 사용자가 직접 입력. 단, 카테고리 분류(`주석`/`주성분`/`구`/`절`/`기타`)는
  시스템이 자동 분류하거나 사용자가 행을 선택하는 방식일 수 있다 (영상에서 분명치
  않음).

### 3.3 카테고리별 누적 표

본문에 마크를 추가하면 **하단 분석표**의 해당 행에 칩이 추가된다. scene_007(거의
빈 상태) → scene_006(여러 마크 추가됨)의 변화에서 명확히 보인다.

표의 5개 행:
- **주석**: 어휘/형광펜 단위 메모. `형광펜 Reading`, `텍스트 =foste→nase, develop`
- **주성분**: 문장 5형식 요소. `주어 Reading aloud`, `동사 is`, `목적격보어 to read each and every word`
- **구 (Phrase)**: 구 단위. `(to부정사형) to develop yo...`, `(부사구) something peo...`
- **절 (Clause)**: 절 단위. `(부사절) because...`, `(관계절) people don't...`
- **기타**: 그 외. `(단위) each→every`

→ 본 프로젝트의 `SyntaxAnnotation`은 `category` 필드(`note`/`sentence_role`/`phrase`/
`clause`/`other`)를 갖는 게 자연스러움.

---

## 4. 본 프로젝트와의 매핑 / 영향

### 4.1 audit §4-4 (Annotation span 식별 방식)에 결정적 입력

레퍼런스가 **단어 단위 선택**이라는 점, **Shift/Alt 드래그로 비연속 다중 선택**이
가능하다는 점은 character offset 기반 모델보다 **token 기반 모델이 더 자연스럽다는
domain-expert 권고에 강한 근거**를 추가한다. 단, ProseMirror 자체가 단어 경계
인식을 어느 정도 지원하므로, 저장은 character offset이고 입력만 단어 스냅(snap)
패턴이 가능. **Phase 1 진입 전 ADR에서 다시 검토**.

### 4.2 audit §4-6 (마커 분리)에 영향

레퍼런스 본문에는 우리 `①②③④⑤`/`_..._`/`______` 같은 **출제용 마커는 보이지
않는다**. 이 영상은 "구문 분석" 도구라 출제 자체와 분리된 단계의 도구다. 즉:
- **출제 본문(Passage)** = 마커 박힌 raw text
- **구문 분석용 정제 본문(`Passage.body_text`)** = 마커 제거된 분석 대상

이 두 단계 분리가 자연스럽다는 의미이며, audit §4-6의 **마커 분리 권고를 강화**한다.

### 4.3 SyntaxAnnotation 모델 v0.1 권고 보강

audit §4 권고를 다음과 같이 보강한다 (architect 작업 #5에 반영 권고):

```python
class SyntaxAnnotation(BaseModel):
    id: UUID
    passage_id: UUID
    tenant_id: UUID
    workspace_id: UUID

    kind: Literal[
        "top_label",      # 상단 라벨 (자유 문자열 + 색상)
        "bottom_label",   # 하단 라벨 (S/V/O 등)
        "highlight",      # 형광펜 (배경색)
        "bracket",        # 괄호 () {} []
        "arrow",          # 단어 간 연결
        "inline_note",    # 인라인 주석 (=foster, promote 같은 동의어)
        # underline은 레퍼런스 미관찰. CLAUDE.md §2.1 명세이므로 일단 자리만.
        "underline",
    ]

    category: Optional[Literal[
        "note",           # 주석
        "sentence_role",  # 주성분
        "phrase",         # 구
        "clause",         # 절
        "other",          # 기타
    ]]   # 하단 분석표 행 결정

    span: AnnotationSpan      # §4-4 ADR로 확정될 식별 방식
    payload: dict             # kind별 구조

    color_index: Optional[int]  # 1~12 색상 팔레트 인덱스
    text: Optional[str]         # top_label / inline_note / bottom_label 의 표시 텍스트

    bracket_style: Optional[Literal["()", "{}", "[]"]]
    arrow_target_span: Optional[AnnotationSpan]

    created_at: datetime
    updated_at: datetime
```

### 4.4 Phase 1 단축키 명세 (frontend-dev 입력)

- 클릭 + 드래그: 단어 선택
- Shift + 드래그: 선택에 추가
- Alt + 드래그: 선택에서 제거
- Esc: 편집 취소 (2회 누르면 모달 닫기)
- Del: 선택된 annotation 삭제

→ Tiptap의 기본 텍스트 선택 동작을 단어 단위 스냅 + 비연속 다중 선택으로 확장
필요. ProseMirror plugin 작업 영역.

---

## 5. 미해결 / 추가 조사 필요

### 5.1 색상 팔레트 12색의 의미

색상이 단순 시각 구분인지, **카테고리별 컨벤션**(예: 1번 = 주어, 2번 = 동사 등)이
있는지 영상으로는 불명확. 와이프 또는 강사 인터뷰로 확인 필요.

### 5.2 라벨 텍스트 preset 여부

`=동명사주어`, `=to부정사(형)`, `(부사구)` 등이 자유 입력인지, **자주 쓰는 라벨
preset 메뉴**가 있는지 영상으로는 불명확. 강사 사용 효율을 위해 preset이 있을
가능성이 큼.

### 5.3 출력 형식

이 도구가 "분석지"를 어떤 포맷으로 출력하는지 영상에 안 나옴. 우리는 HWPX가 1급
포맷 (CLAUDE.md §1.3)이지만, 레퍼런스의 출력이 HWPX인지 PDF인지 모름. 와이프
인터뷰로 확인 필요 — Phase 1 출력 호환성에 영향.

### 5.4 영상 출처 (도구 정체)

영상은 `gin__edu` × `highendedu` (대치동 학원) 콜라보 게시물. 도구의 정체는 명시
안 됨. 와이프에게 도구 이름을 확인하면 직접 사용·평가가 가능. 우리 프로젝트의
"Reinventing the Wheel" 검토에도 영향 (CLAUDE.md §3.6) — 만약 이 도구가 일반
판매 중인 솔루션이라면 통합/구매 옵션을 고려할 수도 있음.

---

## 6. 작업 #5 / Phase 1 인계 메모

### architect (작업 #5)
- §4.3의 SyntaxAnnotation 권고 모델을 작업 #5 PR에 반영. 단 `span` 식별 방식은
  §4-4 ADR로 미룸 (자리만 박음).
- `category` 필드를 v0.1 도입 — 하단 분석표가 카테고리별 누적이라 도메인이 매우
  강하게 구조화되어 있음.

### domain-expert
- 영상 분석을 입력으로 `docs/variant-type-catalog.md` 재작성 시 **annotation kind**도
  카탈로그 항목으로 추가 검토. 6종 (top_label / bottom_label / highlight / bracket /
  arrow / inline_note) 각각의 출제 의도와 사용 패턴.
- 5.1, 5.2, 5.4는 와이프 직접 인터뷰 필요 항목 — domain-expert가 정리한 인터뷰
  체크리스트에 추가.

### frontend-dev (Phase 1)
- §4.4 단축키 명세를 Tiptap PoC 다음 마일스톤에 반영.
- 비연속 다중 선택은 Tiptap 기본에 없음 — ProseMirror plugin 자작 또는 검증된
  multi-selection 라이브러리 조사 필요 (CLAUDE.md §3.6 절차).

### PM (Dennis)
- 5.4 도구 정체 확인 후 Reinventing the Wheel 재평가.
- 5.1~5.3 와이프 인터뷰 일정.
- `밑줄` annotation의 실제 사용 여부 — CLAUDE.md §2.1에 박혔지만 레퍼런스 미관찰.
