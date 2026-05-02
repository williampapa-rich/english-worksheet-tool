# exam-generator 스키마 Audit & Coverage Gap 분석

- **작성자**: architect agent
- **작성일**: 2026-05-02
- **분석 대상**: `~/workspace/exam-generator` (별도 repo, 읽기 전용)
- **목적**: 새 repo `english-worksheet-tool`의 `shared/schemas/` v0.1 설계 기반 마련
- **다음 단계**: domain-expert가 §3 / §4 / §7에 도메인 검토 코멘트 → architect가 §5
  권고를 바탕으로 Pydantic 모델 PR (Sprint 0 작업 #5)
- **관련 문서**: `docs/adr/0001-canonical-schema-philosophy.md`, `CLAUDE.md` §6

---

## 1. exam-generator 스키마 인벤토리

### 1.1 핵심 발견 — 단일 파일 SSOT 구조

exam-generator는 **`shared/schemas/question.py` 단 하나의 파일**이 LLM / parser /
renderer / FastAPI 4개 경계의 SSOT로 동작한다. 별도 ORM 모델이나 DB 영속성 계층은 없다
(생성 후 즉시 HWPX 다운로드로 끝나는 stateless 흐름). 이는 본 프로젝트가 흡수해야 할
**구조적 차이**의 핵심이다 — 우리는 "콘텐츠 자산화"를 위해 영속성을 추가해야 한다.

### 1.2 발견된 모델 목록

| 모델 | 위치 | 역할 |
|---|---|---|
| `SubQuestion` | `shared/schemas/question.py:128-132` | 장문 세트(41-42, 43-45) 안의 개별 부속 문항 |
| `QuestionPlan` | `shared/schemas/question.py:135-172` | LLM이 passage 작성 전에 강제 채우는 메타 계획 (topic_scope, thesis, structure_plan, target_word_count) |
| `Question` | `shared/schemas/question.py:185-269` | 단일 문제의 SSOT — passage + question_text + choices + answer + 메타 필드 다수 |
| `QuestionConfig` | `shared/schemas/question.py:272-276` | 클라이언트 → /api/generate 요청의 각 문항 설정 (number, type, points) |
| `ExamMeta` | `shared/schemas/question.py:279-288` | 시험지 메타 (title, subject, school, grade, date, time_limit, layout) |
| `GenerateRequest` | `shared/schemas/question.py:294-300` | API 요청 페이로드 (meta + questions[] + reference_text + provider/model) |

### 1.3 `Question` 필드 구조 상세

```python
class Question(BaseModel):
    # 식별
    number: Optional[int] = Field(default=None, ge=1, le=45)  # parser는 None 허용, LLM/renderer는 채워짐
    type:   Optional[str] = None                               # ACTIVE_TYPES 중 하나 (예: "빈칸-구(31)")
    points: Optional[float] = None

    # LLM 1단계 (자가 계획)
    plan: Optional[QuestionPlan] = None    # passage 작성 전 강제 채움. parser/renderer는 무시

    # 본문 + 문항 + 보기 + 정답 + 해설
    passage:       list[str]               # 단락 시퀀스
    question_text: str
    choices:       list[str]               # 기본 ["①","②","③","④","⑤"]
    answer:        int = Field(ge=1, le=5)
    explanation:   str

    # 유형별 선택 필드 (discriminated union을 평탄화한 형태)
    given_sentence: Optional[str]               # 문장삽입(38, 39)
    sub_passages:   Optional[list[list[str]]]   # 순서배열(36, 37) (A)/(B)/(C) 단락 / 장문독해(43-45) (B)/(C)/(D)
    summary:        Optional[str]               # 요약문(40)
    sub_questions:  Optional[list[SubQuestion]] # 장문 세트 안의 부속 문항

    # LLM 3단계 (자가검증)
    naturalness_check: Optional[Literal[       # validators가 'OK' 외 reject → 재시도
        "OK", "REWRITE_SCOPE_TOO_BROAD", "REWRITE_ABRUPT_ENDING",
        "REWRITE_REPETITIVE", "REWRITE_FORCED_BREVITY"]]

    # 장문독해(43-45) 전용 — 4:1 분포의 단일 진실 원천
    referent_assignments: Optional[list[str]]  # (a)~(e) 5개 라벨이 가리키는 인물명

    # 그룹 라벨 (시스템이 후처리로 부착)
    group_label: Optional[str]

    # parser 메타 (LLM/renderer는 무시 가능)
    has_passage_box:    bool
    has_inline_markers: bool
    has_blanks:         bool
    raw_paragraphs:     list[str]
    paragraph_indices:  list[int]
```

### 1.4 부속 상수 / 매핑 테이블 (스키마와 함께 다니는 도메인 지식)

| 상수 | 위치 | 역할 |
|---|---|---|
| `CIRCLED` | `:14` | `("①","②","③","④","⑤")` 원문자 5개 |
| `UNDERLINE_MARK = "_"` | `:20` | LLM 출력의 인라인 밑줄 마커 |
| `BLANK_PLACEHOLDER = "______"` | `:21` | 정확히 6개 underscore (빈칸) |
| `LAYOUT_PATTERN` | `:38-63` | 24개 유형별 본문 레이아웃 분류 (reasoning / letter_box / blank_inline / marker_inline / passage_segments / long_set 6종) |
| `ACTIVE_TYPES` | `:69-80` | 활성 유형 24개 |
| `DISABLED_TYPES` | `:81` | 비활성 유형 (도표(25)만 — 이미지 생성 미지원) |
| `TYPE_SLOT_COUNT` | `:84-87` | 장문 세트의 슬롯 수 (41-42=2, 43-45=3) |
| `TYPES_WITH_*_BOX` | `:102-114` | 박스 단락 필요 유형 분류 (passage_box / given_box / summary_box / longset_box) |
| `GROUP_LABEL_TEMPLATES` | `:120-125` | 동일 대분류 연속 출제 시 자동 부착되는 그룹 라벨 |
| `NATURALNESS_OK` / `NATURALNESS_REWRITE_VALUES` | `:176-182` | 자가검증 결과의 enum 값들 |

### 1.5 외부 산출물

| 파일 | 위치 | 역할 |
|---|---|---|
| `templates/schema.json` | `templates/schema.json` | `Question.model_json_schema()` 자동 추출 — parser CLI가 갱신 |
| `templates/type_profiles.json` | `templates/type_profiles.json` | 평가원 5년치 본문 길이/박스/마커 통계 (24개 유형) |
| `templates/template.hwpx` | (바이너리) | HWPX 빌더의 base ZIP — parser SSOT |

### 1.6 LLM 어댑터 / 도메인 분류 코드 위치

| 항목 | 위치 |
|---|---|
| Anthropic 어댑터 (tool_use 강제 + Pydantic input_schema) | `app/llm/anthropic.py:31-64` |
| LLM Protocol 정의 | `app/llm/base.py:30-41` |
| 유형별 프롬프트 카탈로그 (`TYPE_HINTS`) | `app/llm/prompts.py:99-319` |
| 시스템 프롬프트 + 마커 규약 | `app/llm/prompts.py:24-95` |
| 길이 가이드 / 회피 디렉티브 / 정답 다양성 | `app/llm/prompts.py:339-486` |
| 마커/길이 검증 (`validate_question`) | `app/llm/validators.py` 전체 |
| HWPX 빌더 진입점 (`build_hwpx`) | `app/renderer/builder.py:27-53` |
| Section0 / 마스터페이지 인젝션 | `app/renderer/template_injector.py` |
| Parser 진입점 (CLI) | `tools/parser/cli.py` |
| Question 감지 (정규식 기반) | `tools/parser/questions.py` |
| 유형 분류 (번호 + 키워드) | `tools/parser/classify.py` |
| PDF Vision 추출 | `app/llm/pdf.py` (Gemini Vision 한정 — Claude Vision 미사용) |

---

## 2. 변형 유형 카탈로그 (현황)

exam-generator는 "변형문제 생성기"가 아니라 **수능형 시험지 생성기**다. 즉 한 시험지 안에서
24개 유형(18~45번)을 **새로 작성**하는 방식이며, 본 프로젝트가 추구하는 "한 지문 →
여러 변형문제" 워크플로우는 직접 제공하지 않는다.

### 2.1 24개 활성 유형 (입출력 형태)

| 유형 코드 | 입력 (LLM에 전달) | 출력 형태 (Question 필드) | 본문 마커 |
|---|---|---|---|
| 목적(18) | 유형 가이드 + 학년/배점 | passage(편지 형식) + choices(한국어) | 없음 |
| 심경(19) | 동일 | passage(1인칭 서사) + choices(영어 형용사 쌍) | 없음 |
| 주장(20) | 동일 | passage(논설문) + choices(한국어 단문) | 없음 |
| 밑줄함의(21) | 동일 | passage + choices | `_..._` 정확히 1개, question_text와 글자 일치 필수 |
| 요지(22) / 주제(23) / 제목(24) | 동일 | passage + choices(한국어/영어) | 없음 |
| 인물일치(26) | 동일 | passage(약력 5~7문장) + choices(한국어 사실 진술) | 없음 (모든 마커 금지) |
| 안내문(27) / 안내문(28) | 동일 | passage(박스 안 큰 제목 + 헤딩 + 항목) + choices | 없음 |
| 어법(29) | 동일 | passage + choices=["①","②","③","④","⑤"] | `①_word_ ... ⑤_word_` 정확히 5개 |
| 어휘(30) | 동일 | 동일 | 동일 |
| 빈칸-구(31) | 동일 | passage(`______` 1곳) + choices(영어 명사구) | `______` 정확히 1개 |
| 빈칸-절(32~34) | 동일 | passage(`______` 1곳) + choices(영어 절) | 동일 |
| 무관문장(35) | 동일 | passage=[도입, ①문장, ②문장, ③무관, ④문장, ⑤문장] + choices=원문자 | `①~⑤` 5개 |
| 순서배열(36, 37) | 동일 | passage(주어진 글) + sub_passages([(A),(B),(C)]) + choices=`(X)-(Y)-(Z)` | 시스템이 (A)/(B)/(C) 라벨 후처리 부착 |
| 문장삽입(38, 39) | 동일 | passage(`①~⑤` 위치 마커) + given_sentence + choices=원문자 | `①~⑤` 5개 |
| 요약문(40) | 동일 | passage(긴 본문) + summary("... (A) ______ ... (B) ______ ...") + choices=`(A) word1 …… (B) word2` | summary에 `______` 정확히 2개 |
| 장문(41-42) | 동일 | passage(제목 + 본문, `(a)~(e)` 평문 라벨 5개) + sub_questions=[42번 어휘] | 시스템이 `(a) word` → `(a) _word_` 후처리 |
| 장문독해(43-45) | 동일 | passage((A)단락) + sub_passages=[(B),(C),(D)] + sub_questions=[44번 지칭, 45번 일치] + referent_assignments | 동일 (a)~(e) 라벨, 4:1 분포 강제, 시스템이 셔플 |

### 2.2 마커 시스템 (4종, 시스템 후처리 vs LLM 직접 출력)

| 마커 | 의미 | 허용 유형 | LLM이 직접? 시스템이 후처리? |
|---|---|---|---|
| `_..._` | 텍스트 런 underline | 21, 29, 30, 41-42, 43-45 | LLM 직접 (단, 41-42 / 43-45는 시스템이 `(a) word`에서 자동 부착) |
| `______` (6개) | 빈칸 | 31~34, 40 | LLM 직접 |
| `①②③④⑤` | 인라인 번호 마커 | 29, 30, 35, 38, 39 | LLM 직접 |
| `(a)~(e)` | 지칭/어휘 라벨 | 41-42, 43-45 | LLM 직접 (라벨만, underline은 시스템 후처리) |

### 2.3 도메인 후처리 로직 (스키마와 분리할 수 없는 비즈니스 로직)

- **`_apply_alpha_markers`** (`app/llm/generator.py:221-238`): `(a) word` →
  `(a) _word_` 자동 변환. 정규식 3종 우선순위 (직함/the명사구/단어1개).
- **`_shuffle_long_set_passages`** (`app/llm/generator.py:90-206`): 장문독해(43-45)
  sub_passages 무작위 셔플 + 라벨/assignments/answer 자동 재계산. LLM 정답 ① 편향
  대응.
- **`_attach_group_labels`** (`app/llm/generator.py:474-512`): 동일 대분류 연속 출제 시
  `[N~M]` 그룹 라벨 자동 부착.
- **`_expand_sub_questions`** (`app/llm/generator.py:431-471`): 장문 세트의
  sub_questions를 N개 Question으로 평탄화 (number 자동 부여).

이 로직들은 스키마 자체보다 **렌더링 어댑터**의 책임에 가깝다. 본 프로젝트도 분리할 것
(권고: `packages/llm/` 또는 `packages/normalizer/`).

### 2.4 LLM 호출 시 길이 제어 / 다양성 제어 (Phase 1 학습 가치)

- `QuestionPlan` 강제 채움 → `target_word_count` self-report → validators가 평균의
  70~125% 비대칭 hard limit으로 검증 → 실패 시 재시도 (temperature 0.9 → 0.5 → 0.3).
- `_recent_scopes_directive` / `_recent_answers_directive`: `usage_log.jsonl`에서 최근
  성공 호출의 scope / answer 분포를 읽어 다음 호출에 회피 가이드로 첨부.
- Hotfix 17-2의 약한 신호 / Hotfix 7-3의 강한 명령 실패 사례 — 본 프로젝트도 비슷한
  경험을 할 가능성. 학습 가치 있음.

---

## 3. Coverage Gap 분석

CLAUDE.md §6.2의 케이스 + audit 중 발견된 추가 케이스를 평가.

### 3.1 CLAUDE.md §6.2 명시 케이스

#### Gap A — "본문 내장형 어휘 선택 (예: `(A) [long-term / short-term]`이 본문 중간에 박힌 형태)"

- **현재 표현 가능 여부**: **표현 불가**.
- **근거**: exam-generator의 24개 유형 어디에도 `(A) [opt1 / opt2]` 형태의 본문 내장
  선택지 케이스가 없다. `tools/parser/questions.py:51`의 `abc_choice_inline` 정규식
  (`r"\((?P<letter>[A-D])\)\s*\[(?P<opt1>[^/\]]+)/(?P<opt2>[^/\]]+)\]"`)이
  정확히 이 패턴을 노린 것으로 보이지만, **현재 코드에서 사용처가 없는 dead detection**.
  `Question` 모델에도 이 패턴을 저장할 필드가 없다.
- **참고**: 평가원 24개 유형에는 없으나, **사설/내신 변형문제의 흔한 형식** (예: 어휘
  선택지 본문 박힘 — A/B/C 3쌍, 학생이 각 쌍에서 적절한 단어 고르기). domain-expert
  검증 필요.
- **보강 방향**:
  1. `Question`에 새 sub-type `inline_word_choice` 도입 (또는 변형문제 전용 모델로
     분리).
  2. `passage` 안에서 선택지 위치를 식별하기 위해 `InlineChoice` 별도 엔티티 (label,
     options, answer_index, position_marker) — character offset 또는 ProseMirror
     position 중 결정 필요.
  3. choices 필드의 의미가 "5개 원문자"에서 "n개 매트릭스 행"으로 일반화되어야 함.
- **결정 필요 사항**: domain-expert가 영어 교육에서 이 형식의 실제 빈도와 우선순위를
  검증해야 함 (Phase 1/2/3 어디서 필요한가?).

#### Gap B — "다중 선택지 매트릭스 (A/B/C 컬럼)"

- **현재 표현 가능 여부**: **표현 불가**.
- **근거**: exam-generator의 `choices: list[str]`은 평탄한 5개 원소 리스트. A/B/C
  컬럼 매트릭스(예: 어휘 변형 — `(A) embrace / (B) embraced / (C) to embrace` 같은
  3컬럼 5행 매트릭스에서 행 단위로 정답 조합을 고르는 형식)는 표현 안 됨. 단,
  요약문(40)의 `(A) word1 …… (B) word2` 형태는 단일 문자열로 평탄화되어 들어가 있어,
  엄밀히 보면 2컬럼 매트릭스의 lossy 표현.
- **보강 방향**:
  1. `ChoiceMatrix` 모델 — `columns: list[str]` (예: ["A", "B", "C"]) +
     `rows: list[list[str]]` (각 행이 컬럼 길이만큼의 원소).
  2. 또는 평탄화한 `choices`에 `choice_format: Literal["flat", "matrix_AB", "matrix_ABC"]`
     필드를 추가하여 렌더러가 분기.
- **결정 필요 사항**: 평탄화 vs 구조화 — domain-expert + frontend-dev 협의.
  매트릭스 렌더링이 HWPX에서 어떻게 표현되는지(표 도형 vs 텍스트박스)에 따라 달라짐.

### 3.2 Audit 중 발견한 추가 Gap

#### Gap C — Passage가 1급 entity가 아니다 (현재는 Question에 종속)

- **현재**: `Question.passage`는 그 문제에 종속된 `list[str]`. 같은 지문에 여러 변형문제를
  붙이려면 passage가 독립 엔티티여야 한다.
- **CLAUDE.md §1.3 가치 명제 "콘텐츠 자산화"의 핵심**: Passage는 한 번 만들고 여러
  Question이 참조해야 한다.
- **보강 방향**: `Passage`를 1급 엔티티로 추출. `Question.passage_id`로 참조. raw
  paragraphs는 Passage 쪽으로 이동.

#### Gap D — Translation (한글 해석) 표현 없음

- **현재**: 없음. exam-generator는 학생 배포용 자료를 만들지 않음.
- **CLAUDE.md Phase 2 DoD**: "지문 + 한글 해석 + 어휘 박스" 학생용 템플릿 필수.
- **보강 방향**: `Translation` 엔티티 — `passage_id` + `text` + 부분 해석 표현(문장
  단위? 단락 단위?) 결정 필요.
- **결정 필요 사항** (Open Question §4-2):
  - 1:1 vs 1:N (한 passage에 여러 번역?) — domain-expert 의견 필요.
  - 부분 해석 (`SentenceTranslation[]`)을 처음부터 박을지, Phase 2에서 추가할지.

#### Gap E — Vocabulary (어휘) 표현 없음

- **현재**: 없음.
- **CLAUDE.md Phase 2 DoD**: 어휘 박스 필수.
- **보강 방향**: `Vocabulary` 엔티티 — `word`, `pos`(품사), `meaning`, `cefr_level`(?),
  `passage_id`(종속) + 글로벌 어휘 자산 분리 여부.
- **결정 필요 사항** (Open Question §4-3):
  - Passage 종속 vs 글로벌 어휘 마스터 — Phase 2/3에서 어휘 자산 재사용을 어떻게 할 것인가?
    domain-expert 의견 필요.
  - 어휘 등급(CEFR / 수능 빈도 등급)을 처음부터 필드로 박을지.

#### Gap F — SyntaxAnnotation (구문분석 마크) 표현 없음

- **현재**: 없음 (Phase 1의 핵심 산출물).
- **CLAUDE.md Phase 1 DoD**: Tiptap 에디터에서 상단/하단 라벨, 괄호, 하이라이트, 밑줄,
  화살표 작업 → `SyntaxAnnotation[]` 직렬화.
- **보강 방향**: `SyntaxAnnotation` 엔티티 — `passage_id` + `kind`(top_label /
  bottom_label / bracket / highlight / underline / arrow) + `span`(시작/끝) +
  `payload`(라벨 텍스트 / 색상 / 스타일).
- **결정 필요 사항** (Open Question §4-4): **span 식별 방식이 핵심 미결**.
  - character offset (단순. 텍스트 변경에 취약).
  - token id (안정적이지만 토큰화 정책 결정 필요).
  - ProseMirror position (Tiptap-native이지만 비-에디터 경계에서 해석 부담).
  - 화살표는 (start_span, end_span) 두 개 + 곡선 메타. 별도 모델 필요할 수 있음.
  - 같은 span에 라벨 2개 이상 충돌 시 시각적 처리 (CLAUDE.md §11 Open Question와 연결).

#### Gap G — Worksheet (출력물 단위) 표현 없음

- **현재**: `ExamMeta`가 시험지 메타를 담지만, "여러 Passage + Question 조합으로
  학생용 / 변형문제집 / 구문분석 자료" 같은 다중 템플릿 단위가 없음.
- **CLAUDE.md §6.1**: Worksheet는 `template + branding(로고, 컬러) + items[] →
  Passage 참조` 구조.
- **보강 방향**: `Worksheet` 엔티티 — `template_id`, `branding`, `items: list[WorksheetItem]`.
  `WorksheetItem`은 Passage 참조 + 그 passage에 적용할 옵션 (해석 포함 여부, 어휘 위치,
  변형문제 포함 여부 등).

#### Gap H — Source / Origin 메타 없음 (저작권/출처 추적)

- **현재**: 없음.
- **CLAUDE.md §10.2 저작권 정책**: Phase 4에서 출처 표기 필수. 처음부터 메타 박지 않으면
  나중에 retrofit 비용 큼.
- **보강 방향**: Passage에 `source` 메타 — `provider`(아잉카/평가원/EBSi/내신/사용자
  직접 입력), `original_year`, `original_grade`, `original_question_number`,
  `license_note`.

#### Gap I — Difficulty / Topic / Word Count 등 검색·필터 메타 없음

- **현재**: `QuestionPlan.target_word_count`만 LLM 자기보고용.
- **콘텐츠 자산화 관점**: Passage 검색·필터 메타가 자산 활용도를 결정.
- **보강 방향**: Passage에 `topic_tags: list[str]`, `cefr_level: Optional[str]`,
  `word_count: int`(actual), `subject_domain: Optional[str]`(과학/사회/문학/...).
- **결정 필요 사항** (Open Question §4-1):
  - 어떤 메타가 v0.1 필수이고 어떤 게 Phase 2+ 추가인지 — domain-expert 의견.

#### Gap J — VariantQuestion (Phase 3) 표현 없음

- **현재**: exam-generator는 "기출 패턴은 따르되 내용은 완전히 새롭게" 작성하는 방식.
  "원본 문제 → 변형 문제" 관계 자체가 없음.
- **CLAUDE.md Phase 3 DoD**: "변형 결과가 다시 정규화된 Question으로 들어가서 Phase 1, 2
  파이프라인과 호환".
- **보강 방향**: `VariantQuestion`은 `Question`을 상속 또는 디스크리미네이터 union의
  한 분기. `original_question_id` + `variant_kind` 필드 추가.
- **결정 필요 사항** (Open Question §4-5):
  - 같은 테이블 + discriminator vs 별도 테이블 — domain-expert가 변형 유형 카탈로그
    확정 후 결정.

#### Gap K — Question의 `passage`가 본문/박스/마커 혼합 (정규화 부족)

- **현재**: `Question.passage: list[str]`이 단순 단락 시퀀스. 박스 여부는
  `has_passage_box: bool`로만 표시. 마커는 본문 텍스트에 직접 박힘 (`_..._`,
  `①②③④⑤`, `______`, `(a)~(e)`).
- **문제**: 마커가 텍스트와 entangled되어 있어 같은 passage를 다른 유형의 변형문제로
  재사용할 때 마커를 제거/재부착해야 함. 콘텐츠 자산화 관점에서 lossy.
- **보강 방향**:
  1. **원본 Passage**는 "마커 없는 정제된 영어 텍스트"로 보관.
  2. 마커는 **별도 annotation**으로 모델링 (Gap F의 `SyntaxAnnotation`과 통합 가능?).
  3. 변형 유형별로 적절한 annotation을 후처리 부착해서 렌더.
- **결정 필요 사항** (Open Question §4-6, **중요**):
  - 마커를 텍스트에 inline으로 두는 exam-generator 방식의 단순함 vs 마커를 분리한
    정규화 방식의 자산화 가치 — 분리하면 LLM 출력/검증/렌더링 모든 경계에 영향.
  - 본 audit의 권고는 **분리** (자산화 가치 우선). 단 Phase 1 진입 전 ADR로 확정.

#### Gap L — 표/도표/이미지 (도표(25)) 표현 없음

- **현재**: exam-generator는 도표(25)를 `DISABLED_TYPES`로 비활성화 — "이미지 생성
  후속 작업 필요".
- **본 프로젝트**: 입력 측에 PDF/이미지 스캔본이 들어오므로 표/도표/이미지를 **저장**해야
  함 (재배포 시 동일 이미지 재사용). 단 LLM 자동 생성은 Phase 4 이후.
- **보강 방향**: `Passage.attachments: list[Attachment]` — kind(image/table) +
  binary_storage_ref + caption + alt_text.
- **결정 필요 사항**: Phase 0 입력 파이프라인에서 이미지 추출 필요한가? PM 결정.

#### Gap M — 인증 / 사용자 / 멀티테넌트 표현 없음

- **현재**: exam-generator는 단일 사용자 stateless 도구.
- **CLAUDE.md §3.3**: 모든 도메인 테이블에 `tenant_id` 처음부터 박음.
- **보강 방향**: `Tenant`, `Workspace` 엔티티 + 모든 도메인 엔티티에 `tenant_id` 또는
  `workspace_id`. 자세한 §5에.

#### Gap N — `naturalness_check` / `referent_assignments` 등 LLM 자가검증 필드 처리

- **현재**: Question 모델에 박혀 있되 parser/renderer가 무시.
- **본 프로젝트 권고**: LLM 호출 결과를 그대로 영속화하면 자가검증 필드까지 DB에 저장됨.
  검증 후에는 불필요하나 사후 분석에 가치. 보존하되 **렌더러는 무시** (현재와 동일).

### 3.3 Gap 요약 표

| ID | 항목 | 표현 가능성 | 우선순위 (추정) |
|---|---|---|---|
| A | 본문 내장형 어휘 선택 `(A) [opt1 / opt2]` | 불가 | Phase 3 (변형문제) — domain-expert 검증 |
| B | 다중 선택지 매트릭스 (A/B/C 컬럼) | 불가 | Phase 3 — domain-expert 검증 |
| C | Passage 1급 entity 분리 | 부분 가능 | Phase 0 필수 |
| D | Translation | 불가 | Phase 2 필수 (단, 모델은 Phase 0에 박을 것) |
| E | Vocabulary | 불가 | Phase 2 필수 (단, 모델은 Phase 0에 박을 것) |
| F | SyntaxAnnotation | 불가 | Phase 1 필수 |
| G | Worksheet | 불가 | Phase 1/2 필수 |
| H | Source / Origin 메타 | 불가 | Phase 0 권장 (retrofit 비용 회피) |
| I | Difficulty / Topic / WordCount 메타 | 부분 (target_word_count만) | Phase 0 일부, Phase 2+ 확장 |
| J | VariantQuestion | 불가 | Phase 3 (단, discriminator 형태로 Phase 0에 자리만 둘 것) |
| K | 마커/텍스트 분리 정규화 | 가능하나 미적용 | **ADR 결정 필요** (Phase 1 진입 전) |
| L | 표/도표/이미지 attachment | 불가 | Phase 0 입력 의존 (PM 결정) |
| M | Tenant / Workspace / 멀티테넌트 | 불가 | Phase 0 필수 |
| N | LLM 자가검증 필드 영속화 | 가능 | Phase 0, 그대로 흡수 |

---

## 4. 신규 스키마 설계 권고 (엔티티 경계 + 핵심 필드 후보)

> ⚠️ 필드 수준 확정은 Sprint 0 작업 #5에서. 본 섹션은 **엔티티 경계와 관계, 미결
> 사항(Open Question)** 만 명시.

### 4.1 엔티티 관계 다이어그램 (권고안)

```
Tenant (1) ─── (N) Workspace
                     │
                     ├── (N) Passage ─────────── (1) Translation? (또는 1:N)
                     │      │ ├── (N) SentenceTranslation (선택, Phase 2)
                     │      │ ├── (N) Vocabulary (passage 종속분)
                     │      │ ├── (N) SyntaxAnnotation
                     │      │ ├── (N) Question (원본 + Variant 디스크리미네이터)
                     │      │ │     └── (N) SubQuestion (장문 세트)
                     │      │ └── (N) Attachment (이미지/표, Phase 0 후순위)
                     │      └── meta: source/topic/level/word_count/...
                     │
                     ├── (N) VocabularyMaster (글로벌 어휘 자산, Phase 2+ 결정)
                     └── (N) Worksheet
                            ├── template_id
                            ├── branding (로고, 컬러)
                            └── (N) WorksheetItem ─── passage_id (참조)
```

### 4.2 엔티티별 권고

#### Tenant
- 핵심 필드 후보: `id`, `name`, `created_at`, `auth_provider_id` (Phase 4용
  optional).
- Phase 0: 환경변수 stub으로 단일 tenant 자동 생성.

#### Workspace
- 핵심 필드: `id`, `tenant_id` (FK), `name`, `created_at`.
- 기본 1 tenant = 1 workspace로 stub 운영. 추후 강사 1인이 복수 workspace 보유 가능.
- **Open Question §4-7**: Phase 0에서 Workspace 계층을 실제로 박을지, Tenant만으로
  충분한지 — backend-dev와 협의. 권고: 박는다 (retrofit 비용 회피, exam-generator의
  ExamMeta 같은 시험지 단위 메타가 Workspace에 자리잡을 수 있음).

#### Passage
- 핵심 필드 후보:
  ```
  id, tenant_id, workspace_id,
  body_text: str       # 마커 제거된 정제 영어 본문 (Gap K 권고)
  paragraphs: list[str]  # 단락 분할 (직렬 보존용 — 또는 body_text + paragraph_breaks)
  source: SourceMeta (Gap H)
  topic_tags: list[str]
  cefr_level: Optional[str]
  word_count: int (actual, 시스템 계산)
  subject_domain: Optional[str]
  created_at, updated_at
  ```
- **Open Question §4-1**: 메타 어디까지 v0.1 필수인가? domain-expert 검토 필요.
- **Open Question §4-6**: `body_text`(마커 분리) vs `body_text_with_markers`(현재
  exam-generator 방식). **별도 ADR 필수**.

#### Translation
- 핵심 필드: `id`, `passage_id` (FK), `language: Literal["ko"]`, `text`,
  `created_by: Literal["llm", "user"]`, `created_at`.
- **Open Question §4-2**:
  - 1 passage : 1 translation (간단) vs 1:N (사용자가 여러 버전 보관) — domain-expert
    의견.
  - 부분 해석(`SentenceTranslation`) 처음부터 박을지, Phase 2에서 추가할지.
  - 권고: v0.1은 1:N + 부분 해석은 Phase 2에서 추가 (모델은 자리만).

#### Vocabulary
- 핵심 필드: `id`, `passage_id` (Optional FK — 글로벌일 수도), `tenant_id`, `word`,
  `pos: Optional[str]`, `meaning_ko: str`, `cefr_level: Optional[str]`,
  `frequency_rank: Optional[int]`, `created_by`.
- **Open Question §4-3**:
  - Passage 종속 vs 글로벌 마스터 분리 — Phase 2/3에서 어휘 자산 재사용을 어떻게 할
    것인가?
  - 권고: `passage_id`를 nullable로 두고, 같은 word는 글로벌 마스터에 dedup. v0.1은
    passage 종속 only로 출시, Phase 2+에서 dedup 도입.

#### SyntaxAnnotation
- 핵심 필드 후보:
  ```
  id, passage_id, tenant_id,
  kind: Literal["top_label", "bottom_label", "bracket", "highlight",
                "underline", "arrow", ...]
  span: AnnotationSpan      # 시작/끝 위치 (식별 방식 결정 필요)
  payload: dict (kind별 형태)
    - top_label/bottom_label: { text, color }
    - bracket: { style: "()", "{}" }
    - highlight/underline: { color }
    - arrow: { from_span, to_span, curve_meta }
  created_at, updated_at
  ```
- **Open Question §4-4 (중요)**: span 식별 방식.
  - (a) character offset: `{ start: int, end: int }`. 단순. 텍스트 변경에 매우 취약.
  - (b) ProseMirror position: Tiptap-native. 에디터 경계 밖에서는 해석 부담.
  - (c) token id: 토큰화 정책 결정 필요 (whitespace? sentencepiece?).
  - 권고 (architect 1차): **(a) character offset on `Passage.body_text` (마커
    분리된 정제 본문)**. 텍스트 변경 시 마이그레이션은 별도 어댑터로 흡수. 이유:
    DB/LLM/렌더러 경계 모두 단순. ProseMirror position은 에디터 내부에서만 유지하고
    저장 시 character offset으로 변환.
  - **단 Phase 1 진입 전 frontend-dev + domain-expert와 별도 ADR로 확정 필수**.
- **Open Question (CLAUDE.md §11과 연결)**: 같은 span에 라벨 2개 이상 충돌 시
  시각적/모델 처리 — 모델은 단순 list 허용 (1:N), 시각적 처리는 frontend-dev 책임.

#### Question (+ VariantQuestion)
- 핵심 필드 후보 (exam-generator의 Question을 흡수 + 일반화):
  ```
  id, passage_id (FK), tenant_id, workspace_id,
  number: Optional[int]   # 시험지 안에서의 번호
  type: str                # exam-generator의 24개 유형 + 변형 유형 추가
  variant_kind: Literal["original", "vocabulary_swap", "grammar_swap",
                        "blank_fill", "order_shuffle", "topic_shift", ...]
                          # original = 입력에서 추출된 원본 문제
  origin_question_id: Optional[FK]   # variant_kind != original이면 필수
  question_text: str
  choices: ChoicesField    # 평탄 list[str] vs ChoiceMatrix 결정 (Gap B)
  answer: int | list[int]  # 다중 정답 케이스 처리 (요약문(40)의 (A)/(B) 조합 등)
  explanation: str
  # exam-generator의 sub-type 필드들
  given_sentence: Optional[str]
  sub_passages: Optional[list[list[str]]]
  summary: Optional[str]
  sub_questions: Optional[list[SubQuestion]]
  # LLM 메타 (영속화하되 렌더러는 무시)
  plan: Optional[QuestionPlan]
  naturalness_check: Optional[Literal[...]]
  referent_assignments: Optional[list[str]]
  group_label: Optional[str]
  # parser 메타
  has_passage_box, has_inline_markers, has_blanks: bool
  # 본문 내장형 선택 (Gap A) — 추가 권고
  inline_choices: Optional[list[InlineChoice]]
  ```
- **Open Question §4-5**: Original / Variant 분리 모델링.
  - (a) 단일 테이블 + `variant_kind` discriminator. 단순.
  - (b) 별도 테이블 (Question vs VariantQuestion 상속). 정확.
  - 권고: (a) 단일 테이블 — Pydantic v2의 discriminated union으로 깔끔히 표현 가능.
    단 domain-expert가 변형 유형 카탈로그 확정 후 재검토.
- **Open Question §4-8**: choices 평탄 vs 매트릭스 (Gap B 연결) — domain-expert
  확인 필수.
- **Open Question §4-9**: `inline_choices` (Gap A) — Phase 3 진입 전 별도 ADR.

#### Worksheet
- 핵심 필드:
  ```
  id, workspace_id, tenant_id,
  title, kind: Literal["student", "teacher", "syntax_analysis", "variant_set"]
  template_id: str    # 학생용 v0.1 / 변형문제집 v0.1 등 템플릿 식별자
  branding: { logo_url, primary_color, secondary_color }
  meta: { school?, grade?, date, time_limit?, layout? }   # exam-generator의 ExamMeta 흡수
  items: list[WorksheetItem]
  created_at, updated_at
  ```
- `WorksheetItem`: `passage_id` + `options` (어휘 박스 표시 여부, 해석 포함 여부, 변형
  문제 N개 포함 등 kind별 옵션).

### 4.3 도메인 후처리 로직 위치

exam-generator의 `_apply_alpha_markers` / `_shuffle_long_set_passages` /
`_attach_group_labels` / `_expand_sub_questions` 같은 후처리는 **스키마가 아니라
어댑터** 책임. 본 프로젝트에서는 `packages/llm/normalizer.py` 또는 `packages/extractor/`
에 위치. 스키마는 결과 구조만 정의.

---

## 5. 멀티테넌트 적용 권고

### 5.1 `tenant_id` 박는 위치

**모든 도메인 엔티티**에 `tenant_id` 직접 컬럼으로 박는다.

| 엔티티 | tenant_id | workspace_id |
|---|---|---|
| Tenant | (자기 자신) | — |
| Workspace | FK | (자기 자신) |
| Passage | FK | FK |
| Translation | FK (passage 통해 transitive지만 컬럼으로도 박음 — 조회 단순화) | FK |
| Vocabulary | FK | FK |
| SyntaxAnnotation | FK | FK |
| Question | FK | FK |
| VariantQuestion (또는 Question 분기) | FK | FK |
| Worksheet | FK | FK |
| WorksheetItem | FK (transitive) | FK (transitive) |
| Attachment | FK | FK |

**근거**: transitive FK만 두면 모든 쿼리에 join이 필요. RLS 도입 시에도 직접 컬럼이
편함. 정규화 위반 비용 < 실수 방지 + 성능 이득.

### 5.2 Repository 패턴 (필터 강제)

- 모든 DB 접근은 `packages/db/` 내 repository 클래스를 거침.
- repository는 생성 시 `tenant_id`를 받아 모든 쿼리에 자동 필터.
- 직접 SQLAlchemy session 노출 금지 (code-reviewer 체크리스트에 포함됨).

```python
# 권고 패턴 (구체 구현은 backend-dev가)
class PassageRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID, workspace_id: UUID):
        self._session = session
        self._tenant_id = tenant_id
        self._workspace_id = workspace_id

    async def get(self, passage_id: UUID) -> Passage:
        # 자동으로 tenant_id + workspace_id 필터
        ...
```

### 5.3 Pydantic 스키마 측 강제

- 도메인 모델의 `tenant_id`는 `Optional`이 아닌 **필수 필드**.
- 단 외부 LLM이 채우지 않으므로 LLM 호출 직후 후처리에서 강제 주입.
- API 경계의 request DTO는 별도로 두지 말고, 도메인 모델 그대로 사용 + path/header에서
  tenant_id 주입.

### 5.4 RLS 도입 시점

- Phase 0~3: 애플리케이션 레벨 필터 (repository 패턴) 만으로 충분.
- Phase 4 (클라우드 배포) 진입 전 PostgreSQL RLS로 강화 — 별도 ADR.
- 본 결정은 RLS와 호환되는 스키마 설계 (tenant_id 컬럼이 모든 도메인 테이블에 존재)로 충분.

---

## 6. 마이그레이션 / 호환성 메모

### 6.1 exam-generator → 새 스키마 변환 가능성

| exam-generator 산출물 | 새 스키마 매핑 | Lossy 여부 |
|---|---|---|
| `Question` 객체 (24개 유형) | `Passage` + `Question(variant_kind="original")` | **부분 lossy** — Gap K (마커/텍스트 분리)를 적용하면 텍스트는 보존되되 마커는 SyntaxAnnotation 또는 마커 인덱스로 재구성 필요 |
| `Question.passage: list[str]` | `Passage.paragraphs` + `Passage.body_text` | 문단 분할 정보는 보존 |
| `Question.choices` | `Question.choices` | 5개 원소 case는 1:1, 매트릭스는 Gap B |
| `Question.given_sentence/sub_passages/summary/sub_questions` | 동일 이름 필드 | 1:1 |
| `Question.plan/naturalness_check/referent_assignments` | 동일 이름 | 1:1 (LLM 메타 영속화) |
| `Question.has_passage_box/has_inline_markers/has_blanks` | Passage 또는 Question 메타 | 1:1 |
| `Question.raw_paragraphs/paragraph_indices` | Passage 메타 | 1:1 |
| `ExamMeta` (title, school, grade, date, ...) | `Worksheet.meta` | 1:1 |
| `GenerateRequest` | API DTO (별도 매핑) | API 경계용이라 도메인 영속화 안 함 |
| `templates/type_profiles.json` | 도메인 지식 — Phase 1+ LLM 호출에 그대로 활용 | 1:1 (영속화 대상 아님) |
| `templates/template.hwpx` | `packages/hwpx_renderer/` 자산 | 1:1 |

### 6.2 Lossy 영역 상세

- **Gap K 적용 시 (마커 분리)**:
  - 입력: `Question.passage = ["... is ①_word1_ ... ⑤_word5_ ..."]`
  - 출력: `Passage.body_text = "... is word1 ... word5 ..."` +
         `Question.markers = [{ kind: "circled", index: 1, span: ... }, ...]`
  - LLM 출력에서 분리 변환은 정규식 1회로 가능 (lossless).
  - 단 마커 위치를 `body_text` 위 character offset으로 재계산 필요. 이 변환은
    `packages/llm/normalizer.py`에 두는 게 자연스러움.

- **Gap K 미적용 시 (그대로 흡수)**:
  - 1:1 lossless. 단 변형문제 생성 시 마커 제거/재부착 부담이 도메인 코드 전반에 분산됨.
  - **architect 1차 권고**: Gap K 적용 (분리). Phase 1 진입 전 ADR 필요.

### 6.3 마이그레이션 전략 권고

- exam-generator는 별도 repo로 유지 (legacy로 보존).
- 새 repo는 처음부터 새 스키마로 작성. 기존 운영 데이터 마이그레이션은 없음 (운영 중인
  서비스가 아니므로).
- 단 **테스트용 fixture**로 exam-generator의 24개 유형 sample을 새 스키마로 변환한
  파일 1개 만들면 valuable: `tests/fixtures/exam_generator_compat/*.json`.
  Sprint 0 작업 #5 또는 그 직후 작업으로.

---

## 7. domain-expert 검토 요청 항목

다음 항목들에 대해 domain-expert agent의 영어 교육 도메인 관점 검토를 요청한다.
PR 코멘트로 양쪽 입장을 제시 → PM(Dennis) 결정 흐름.

### 7.1 변형 유형 카탈로그 우선순위

- **Gap A (본문 내장형 어휘 선택)**: 사설/내신 변형문제에서 실제로 얼마나 자주
  쓰이는가? Phase 3 변형 유형 5개 안에 포함되어야 하는가?
- **Gap B (다중 선택지 매트릭스)**: 위와 동일 질문. (A)-(B)-(C) 3컬럼 매트릭스의
  실제 출제 빈도?
- exam-generator의 24개 유형 중 본 프로젝트의 1차 사용자(와이프)가 **실제로 다루는
  유형**은 무엇인가? 우선순위 순서로 정렬해줄 수 있는가? (Phase 0~3 작업 순서 결정에
  영향).

### 7.2 Passage 메타 — Phase 0 v0.1 필수 vs 후순위

- `topic_tags`, `cefr_level`, `subject_domain`, `word_count` 중 Phase 0 v0.1
  스키마에 박아야 하는 필드는?
- 추가로 박아야 할 도메인 메타가 있는가? (예: 출제 학교/학년 분류, 단원 분류, 주제
  카테고리 표준 등)

### 7.3 Translation의 1:1 vs 1:N

- 한 영어 지문에 한국어 해석이 여러 버전 필요한 실사용 케이스가 있는가? (예: 직역 +
  의역, 또는 학년별 다른 난이도의 해석)
- 부분 해석(문장 단위)은 처음부터 필요한가, Phase 2에서 추가해도 되는가?

### 7.4 Vocabulary의 글로벌 자산화

- 동일 단어가 여러 지문에 등장할 때, 매번 새 Vocabulary 엔트리를 만드는 게 자연스러운가,
  글로벌 마스터에서 재사용하는 게 자연스러운가? (예: "endeavor"는 한 강사가 평생
  100번 가르치는 단어 — 매번 의미를 다시 입력하는 건 비효율)
- 어휘 등급 표기 표준은 무엇인가? (CEFR / 수능 빈도 / 자체 분류)

### 7.5 SyntaxAnnotation 종류

- exam-generator는 구문분석 자료를 다루지 않으므로, **SyntaxAnnotation의 kind 목록을
  domain-expert가 정의해야 함**. CLAUDE.md Phase 1 DoD 명시: 상단 라벨, 하단 라벨,
  괄호, 하이라이트, 밑줄, 화살표.
- 와이프가 실제 작업할 때 사용하는 표기 규약을 sample 자료(이미지/HWPX)와 함께 받을 수
  있는가?
- 같은 span에 라벨 2개 이상 겹치는 케이스의 빈도와 표기 규약?

### 7.6 마커/텍스트 분리 (Gap K) — 도메인 관점 의견

- exam-generator는 마커를 본문 텍스트에 inline으로 박는 단순 방식.
- 본 프로젝트에서 분리(정규화)하는 권고는 자산화 가치 우선이지만, **출제 도메인 관점**
  에서 마커가 본문과 entangled 되는 게 실제 작업 흐름과 맞는가, 분리되는 게 맞는가?

### 7.7 변형 유형 카탈로그 (별도 산출물)

- domain-expert 자체 산출물인 `docs/variant-type-catalog.md` 작성 시, 본 audit의 §3
  Gap A/B/J를 참고하여 변형 유형별 입출력 형태를 정의해야 함.
- 그 결과가 `Question.variant_kind` enum 값들의 source가 됨.

---

## 8. 핸드오프 메모

### 8.1 → domain-expert (Sprint 0 작업 #4-1)

본 audit PR에 대한 도메인 검토 요청. 우선순위 검토 영역:

1. **§3 Gap A / Gap B**: 본문 내장형 어휘 선택, 다중 선택지 매트릭스의 실제 출제 빈도와
   본 프로젝트 1차 사용자 (와이프) 의 사용 빈도.
2. **§3 Gap D / E / F / I**: Translation, Vocabulary, SyntaxAnnotation 모델링에
   필요한 도메인 메타 (등급, 부분 해석, annotation 종류 등).
3. **§7 전체**: 7개 항목 모두 domain-expert 의견 필요.
4. **자체 산출물**: `docs/variant-type-catalog.md` 초안 — 본 audit의 §2.1 (24개 유형)
   에 변형 유형 5개 이상 추가하여 Phase 3 입력 데이터 마련.

domain-expert는 본 audit 파일에 직접 수정 가하지 말고 **PR 코멘트** 또는 별도 PR
(`docs/schema-coverage-audit-domain-review.md`) 로 의견 제출. architect와 의견
충돌 시 PR에 양쪽 입장 명시 → PM 결정.

### 8.2 → architect 자신 (Sprint 0 작업 #5 — 본 audit 다음 단계)

`shared/schemas/` v0.1 PR 작성 시 우선순위.

#### Phase 0 v0.1 필수 (작업 #5에서 작성)

1. **`shared/schemas/tenant.py`** — Tenant, Workspace.
2. **`shared/schemas/passage.py`** — Passage (필드는 §4.2 권고 + domain-expert 피드백
   반영).
3. **`shared/schemas/question.py`** — Question + SubQuestion + QuestionPlan + 부속
   상수 (exam-generator의 LAYOUT_PATTERN, ACTIVE_TYPES 등). VariantQuestion은
   `variant_kind` discriminator로 자리만 두고 Phase 3 확장 여지 명시.
4. **`shared/schemas/translation.py`** — Translation (1:N 권고, SentenceTranslation은
   주석으로만 placeholder).
5. **`shared/schemas/vocabulary.py`** — Vocabulary (passage 종속 only, 글로벌 마스터는
   주석 placeholder).
6. **`shared/schemas/annotation.py`** — SyntaxAnnotation (span 식별 방식은 별도 ADR
   결정 후 확정. v0.1은 **architect 권고안 (character offset on body_text)** 으로
   placeholder 작성하되 ADR 미확정 상태 명시).
7. **`shared/schemas/worksheet.py`** — Worksheet, WorksheetItem.

#### 미해결 결정사항 (작업 #5 진행 중 ADR로 처리)

| Open Question | 해결 시점 | 담당 |
|---|---|---|
| §4-1 Passage 메타 v0.1 필수 필드 | 작업 #5 진행 중 | domain-expert + architect |
| §4-2 Translation 1:1 vs 1:N | 작업 #5 진행 중 | domain-expert + architect |
| §4-3 Vocabulary 글로벌화 시점 | Phase 2 진입 전 (별도 ADR) | architect |
| §4-4 Annotation span 식별 방식 | Phase 1 진입 전 (별도 ADR) | architect + frontend-dev |
| §4-5 Question/VariantQuestion 분리 | Phase 3 진입 전 (별도 ADR) | architect + domain-expert |
| §4-6 마커/텍스트 분리 (Gap K) | Phase 1 진입 전 (별도 ADR) | architect + domain-expert |
| §4-7 Workspace v0.1 필요성 | 작업 #5 진행 중 | architect + backend-dev |
| §4-8 choices 평탄 vs 매트릭스 | Phase 3 진입 전 | architect + domain-expert |
| §4-9 inline_choices 도입 시점 | Phase 3 진입 전 | architect + domain-expert |

#### 위임 / 협업 필요 항목

- **backend-dev**: Sprint 0 작업 #3 (DB 셋업)에서 Tenant + Workspace 테이블 작성 시
  본 audit §5 권고 반영. SQLAlchemy 매핑 도구(SQLModel / pydantic-sqlalchemy /
  imperative) 선정은 backend-dev 결정. ADR 0001 §Consequences "후속 결정 트리거"의
  Open Question.
- **frontend-dev**: Sprint 0 작업 #7 (Tiptap PoC)에서 직렬화 결과 형식이 Annotation
  span 식별 방식 결정에 영향. PoC 결과를 architect와 공유 후 Phase 1 진입 전 ADR
  공동 작성.
- **PM (Dennis)**: §7.1 변형 유형 우선순위 / §7.2 Passage 메타 필수 범위 / §7.5
  SyntaxAnnotation 종류는 도메인 영역. domain-expert와의 충돌 시 PM 결정.

---

## 9. 요약 — Sprint 0 종료 시점에 확보된 것 / 안 된 것

### 확보된 것 (본 audit 산출 결과)

- exam-generator의 단일 SSOT 구조 + 24개 유형 + 4종 마커 시스템 + 도메인 후처리 로직
  전수 파악.
- 새 스키마의 엔티티 경계 (Tenant / Workspace / Passage / Translation / Vocabulary /
  SyntaxAnnotation / Question / VariantQuestion / Worksheet) 권고.
- Coverage Gap 14개 (A~N) 식별 + 각각 보강 방향.
- 멀티테넌트 적용 권고 (모든 도메인 테이블에 직접 tenant_id, repository 패턴).
- 마이그레이션/호환성 분석 (exam-generator → 새 스키마 거의 lossless, Gap K만 변환
  필요).
- ADR 0001 — Canonical Schema 중심 설계 (시스템의 척추) 기록.

### 확보 안 된 것 (다음 단계 의존)

- `shared/schemas/` 실제 Pydantic 모델 (작업 #5).
- 변형 유형 카탈로그 (domain-expert 작업 #4-1 + 자체 산출물).
- DB 매핑 / 마이그레이션 (backend-dev 작업 #3).
- Tiptap 직렬화 결과 형식 (frontend-dev 작업 #7).
- 9개 Open Question의 결정 (작업 #5 진행 중 + Phase 1/3 진입 전 ADR).
