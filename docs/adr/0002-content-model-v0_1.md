# ADR 0002 — 콘텐츠 모델 v0.1 (Pydantic 스키마 1차 정의)

- **상태(Status)**: Accepted
- **작성일**: 2026-05-02
- **작성자**: architect agent
- **유형**: Sprint 0 작업 #5 산출물 — `shared/schemas/` v0.1 PR 의 결정 기록
- **관련 문서**:
  - `CLAUDE.md` v0.3 §3.1, §6.2
  - `docs/adr/0001-canonical-schema-philosophy.md` (선행 결정 — 시스템의 척추)
  - `docs/schema-coverage-audit.md` (1주 audit 결과)
  - `docs/audit-review-domain.md` (domain-expert 검토)
  - `docs/reference-program-analysis.md` (영상 레퍼런스)
  - `docs/adr/_pm-decisions-sprint-0.md` (PM 결정 D-1/D-2/D-3 — 본 ADR 에 흡수)

---

## Context (배경)

Sprint 0 한 주 동안 다음 입력이 누적됐다.

1. **schema-coverage-audit** (architect, 2026-05-02): `~/workspace/exam-generator` 의
   기존 Pydantic 스키마를 전수 분석. 14개 Coverage Gap (A~N) 식별. 9개 Open Question
   제기.
2. **audit-review-domain** (domain-expert, 2026-05-02): 영어 교육 도메인 관점 검토.
   특히 Gap A/B 의 학원 시장 빈도, Vocabulary 글로벌화 패턴, SyntaxAnnotation span
   식별 방식, 변형 유형 우선순위에 대한 의견 제시.
3. **reference-program-analysis** (PM, 2026-05-02): `gin__edu × highendedu` 의
   "구문 분석 편집" 영상 31프레임 분석. **Phase 1 의 거의 직접적인 reference
   implementation**. SyntaxAnnotation 모델 v0.1 의 결정적 입력.
4. **PM 결정 D-1 / D-2 / D-3** (`_pm-decisions-sprint-0.md`, 2026-05-02): audit 의
   3개 차단 Open Question 에 대한 PM 답.
5. **CLAUDE.md v0.3 §6.2 정정**: 변형 유형은 별 카테고리가 아니라 기존 24개 유형의
   sub-form / 파생.

본 ADR 은 위 입력을 기반으로 `shared/schemas/` v0.1 의 모든 핵심 결정을 한 곳에
기록한다. 흩어진 결정 (PM 메모, audit 권고, domain review, 영상 분석) 의 정식 통합
문서다.

---

## Decision (결정)

### D1. PM 결정 D-1 / D-2 / D-3 채택 (별도 PM 결정 기록 흡수)

`_pm-decisions-sprint-0.md` 의 D-1 / D-2 / D-3 을 본 ADR 의 정식 결정으로 흡수한다.
PM 결정 기록 파일은 **삭제하지 않고** 그대로 둔다 (1차 기록). 본 ADR 이 정식 문서.

#### D1.1 Passage 메타 (PM 결정 D-1)

`Passage` 의 v0.1 메타:

| 필드 | 타입 | 비고 |
|---|---|---|
| `body_text` | `str` | 마커 분리 정책은 ADR-0004 에서 결정 (v0.1 은 중립) |
| `paragraphs` | `list[str]` | 단락 분할 |
| `word_count` | `int` | 시스템 자동 계산 |
| `source` | `SourceMeta` | 필수. Pydantic validator 로 `school_internal` 일 때 `school_name` 강제 |
| `topic_tags` | `list[str]` | 빈 list 허용. enum 정규화는 v0.2 검토 |
| `target_grade` | `TargetGrade` enum | `middle_1` ~ `suneung` + `other` |

**제외**:
- `cefr_level` — PM 명시 결정 ("공식적으로 나눠진 난이도 등급은 없다").
- `subject_domain` — v0.2 검토.
- 수능 빈도 등급 — v0.2 검토 (domain-expert 권고였으나 PM 보류).

`SourceProvider` enum: `aingka` / `evaluator` / `ebsi` / `school_internal` /
`user_input` / `other`.

#### D1.2 Translation 카디널리티 (PM 결정 D-2)

1 Passage : 1 Translation 강제.

- `Translation.passage_id` 에 DB 레벨 UNIQUE 제약 — **backend-dev 의 SQLAlchemy 마이그레이션에서
  박는다**. 본 Pydantic 모델은 타입만 명시.
- `language: Literal["ko"]` 고정. 다중 언어는 v0.2+ ADR.
- 부분 해석 (`SentenceTranslation`) 은 v0.1 제외. Phase 2 별 모델로 추가.
- 사용자 수정 시 in-place 업데이트, **이전 버전 보존 없음** (PM 명시).

domain-expert 권고 (1:N + UI 1개만 보여주기, retrofit 비용 회피) 와의 충돌:
PM 결정 우선. 1:N 도입 후 unused 복잡도 누적 비용 > 향후 1:1→1:N 마이그레이션 비용
판단.

#### D1.3 Workspace 계층 (PM 결정 D-3)

Tenant → (1:N) Workspace 박는다. 모든 도메인 엔티티는 `workspace_id` FK NOT NULL.

- `Workspace` v0.1: `id, tenant_id, name, created_at, updated_at` (단순).
- v0.1 운영 stub: Tenant 생성 시 default workspace 1개 자동 생성 (application 로직 —
  Pydantic 모델은 강제하지 않음).
- 후속 (v0.2+): `school_name` / `grade` / `season` 등 구조화 필드 추가 검토 — PM 코멘트
  ("와이프가 맡게될 학교/학년도 다양할거라 나누는게 좋아").

### D2. Question 모델 — 24개 유형 enum + variant_kind discriminator

#### D2.1 24개 활성 유형을 `QuestionType` enum 으로 흡수

CLAUDE.md v0.3 §6.2 정정: **변형 유형은 별 카테고리가 아니라 기존 24개의 sub-form /
파생**.

exam-generator `ACTIVE_TYPES` (24개) + `DISABLED_TYPES` (1개) 모두 `QuestionType`
enum 의 멤버로 흡수. enum value 는 **영문 snake_case + 평가원 문항 번호** 명명 규칙.

전체 25개 멤버:

```
purpose_18, mood_19, assertion_20, underline_implication_21,
gist_22, theme_23, title_24,
chart_25  (DISABLED — 이미지 생성 미지원),
figure_match_26, notice_27, notice_28,
grammar_29, vocabulary_30,
blank_phrase_31, blank_clause_32, blank_clause_33, blank_clause_34,
irrelevant_sentence_35,
order_36, order_37,
insertion_38, insertion_39,
summary_40,
long_set_41_42, long_set_43_45
```

한국어 라벨 매핑 (예: `'빈칸-구(31)' ↔ blank_phrase_31`) 은 후처리 어댑터 (renderer /
parser) 의 책임 — 도메인 모델은 영문 snake_case 만 사용 (mypy strict + JSON 직렬화
호환).

#### D2.2 변형 표현 — 단일 테이블 + discriminator

- `Question.variant_kind: VariantKind = ORIGINAL` (default).
- `Question.derived_from_question_id: Optional[UUID]`.
- model_validator 로 정합성 강제: `ORIGINAL` ↔ `derived_from_question_id is None`.

`VariantKind` v0.1 멤버:
- `original`
- `vocabulary_swap` (1순위 — audit-review-domain §3.6)
- `grammar_swap`
- `blank_inference`
- `theme_reword`
- `order_shuffle`

**의존성**: domain-expert 의 `docs/variant-type-catalog.md` 재작성 결과로 `VariantKind`
enum value 가 정정/보강될 수 있음. 본 PR 은 audit + exam-generator + audit-review-domain
§3.6 1순위 5개를 1차 안으로 박고, 후속 PR 에서 정정 가능 (CLAUDE.md "breaking
change 최소화" — 새 멤버 추가는 non-breaking).

audit §4-5 / audit-review-domain §2 의 단일 테이블 + discriminator 권고를 그대로
채택. 별도 테이블은 Phase 3 진입 전 변형 유형 카탈로그 확정 후 재검토 (Open
Question 으로 유지).

#### D2.3 Sub-form 표현 (Gap A / Gap B)

audit + audit-review-domain 권고를 그대로 채택:

- **Gap A (본문 내장형 어휘 선택)**: `Question.inline_choices: Optional[list[InlineChoice]]`.
  - `InlineChoice` 필드: `label, options, answer_index, position_marker, kind`.
  - `InlineChoiceKind`: `vocabulary` / `grammar` / `mixed` (audit-review-domain §3.1
    권고 — 같은 표면 형태라도 출제 의도가 다르다).
- **Gap B (다중 선택지 매트릭스)**: 평탄화-우선 + 매트릭스-옵트인 (audit-review-domain
  §3.2 권고).
  - `Question.choice_format: ChoiceFormat = FLAT` (default).
  - `Question.choice_matrix: Optional[ChoiceMatrix]` — `MATRIX_AB` / `MATRIX_ABC`
    일 때 NOT NULL (model_validator 강제).
  - 평탄 `choices: list[str]` 는 그대로 유지 — 평가원 요약문(40) 의 lossy 평탄화
    하위 호환.

**자율 판단 근거**: domain-expert 가 §5.5 에서 architect 동의를 물었음. architect
판단 = audit-review-domain §3.2 의 평탄화-우선 + 매트릭스-옵트인 권고 채택. 이유는
exam-generator 의 lossy 평탄화 데이터가 v0.1 마이그레이션 대상이며, `choices`
필드를 죽이지 않는 게 가장 적은 변경.

#### D2.4 LLM 자가검증 / 자가계획 메타 영속화 (Gap N)

`QuestionPlan` / `naturalness_check` / `referent_assignments` 모두 exam-generator
1:1 흡수. 영속화하되 렌더러는 무시 (audit Gap N + domain review §2 동의).

#### D2.5 qa-validator 메타 자리 (audit-review-domain §4.1)

`Question.uniqueness_validated: bool = False` + `Question.uniqueness_validator_note:
Optional[str]`. Phase 3 의 qa-validator agent 가 별도 LLM call 로 채움. v0.1 은
자리만.

### D3. SyntaxAnnotation 모델 — 영상 레퍼런스 v0.1 흡수

`docs/reference-program-analysis.md` §4.3 의 권고 모델을 그대로 채택.

#### D3.1 7종 `AnnotationKind`

`top_label, bottom_label, highlight, bracket, arrow, inline_note, underline`

영상에서 6종 식별 + CLAUDE.md §2.1 명세의 `underline` 추가 (영상 미관찰이지만 DoD
명시이므로 자리 마련).

#### D3.2 5종 `AnnotationCategory`

`note, sentence_role, phrase, clause, other`

영상의 하단 분석표 5개 행 (주석/주성분/구/절/기타) 1:1 매핑. Optional — 분류 미정
허용.

#### D3.3 12색 `color_index`

영상의 12색 팔레트. `Optional[int]` ge=1 le=12. **색상 컨벤션 의미** (1=주어, 2=동사
등) 는 미해결 — `reference-program-analysis.md` §5.1, 와이프 인터뷰 필요.

#### D3.4 `bracket_style` / `arrow_target_span` / `text`

`bracket` 일 때 `bracket_style: Literal["()", "{}", "[]"]`.
`arrow` 일 때 `arrow_target_span` (출발점은 `span`).
`top_label / bottom_label / inline_note` 일 때 `text`.

#### D3.5 `AnnotationSpan` placeholder + `SpanFormat` 디스크리미네이터

**핵심 결정**: span 식별 방식은 **ADR-0003 에서 확정** — 본 v0.1 은 placeholder.

근거:
- audit §4-4: architect 1차 권고 = character offset.
- audit-review-domain §3.4: domain-expert 권고 = token id (강사 멘탈 모델은 단어/절
  단위).
- reference-program-analysis §4.1: 영상 레퍼런스 = 단어 단위 선택.

3자 의견이 갈리고, frontend-dev 의 Tiptap PoC 결과를 입력으로 받아야 함. Phase 1 진입
전 ADR-0003 에서 확정.

v0.1 placeholder 구조:
```python
class SpanFormat(str, Enum):
    CHARACTER_OFFSET_V1 = "character_offset_v1"

class AnnotationSpan(BaseModel):
    span_format: Literal["character_offset_v1"]
    data: dict[str, Any]   # character_offset_v1 일 때 {"start": int, "end": int}
```

ADR-0003 결정 시 `AnnotationSpan` 을 discriminated union 으로 교체하고 `data` 의 키
마이그레이션. **현재 v0.1 데이터는 `span_format` 디스크리미네이터로 식별 가능**해서
하위 호환 보장.

### D4. Pydantic v2 source of truth, ORM 은 별 PR

본 PR 의 산출물은 `shared/schemas/` 의 **순수 Pydantic v2 모델** 만이다. SQLAlchemy
ORM 동기화는 backend-dev 의 후속 PR.

근거 (CLAUDE.md §7.2 권한 분리):
- architect 는 `shared/schemas/` + `docs/adr/` 만 작성.
- ORM 매핑 도구 (SQLModel / pydantic-sqlalchemy / imperative) 선정은 backend-dev 의
  결정.

### D5. timezone-aware datetime, `datetime.utcnow` 금지

모든 `datetime` 필드는 `default_factory=utc_now` (UTC, timezone-aware).
`datetime.utcnow()` 는 Python 3.12+ deprecated 이므로 사용 금지 (code-reviewer M-3
지적).

`shared/schemas/common.py` 의 `utc_now()` 함수가 단일 source.

### D6. 멀티테넌트 강제 — `WorkspaceScopedEntity` mixin

audit §5 권고 채택:
- 모든 도메인 엔티티 (Tenant/Workspace 자체 제외) 에 `tenant_id` + `workspace_id`
  직접 컬럼.
- `WorkspaceScopedEntity` mixin 으로 일괄 강제.
- transitive FK + join 패턴 거부 — 직접 컬럼이 RLS / repository 패턴 양쪽에 유리.

---

## Consequences (결과)

### 긍정적 결과

- **Single source of truth 확보**: Pydantic v2 모델이 LLM / API / DB / 에디터 / 렌더러
  5개 경계의 spine 으로 동작 (ADR-0001 정신 구현).
- **24개 유형 enum + variant_kind 패턴**으로 CLAUDE.md §6.2 정정과 정합. 새 type
  도입 없이 변형이 표현됨 → exam-generator → 새 스키마 마이그레이션 거의 lossless
  (audit §6.1).
- **영상 레퍼런스 모델이 그대로 v0.1 SyntaxAnnotation 으로 흡수**되어 Phase 1 작업 시
  대부분의 구조 결정이 이미 끝남. frontend-dev 는 단축키 / 직렬화 / span 식별만 확정.
- **PM 결정 D-1/D-2/D-3 정식 ADR 흡수**로 결정 흐름이 한 곳에 기록됨 (PM 메모 →
  ADR 승격).

### 부정적 결과 / 비용

- **Span 식별 방식 placeholder**: ADR-0003 미확정 상태에서 frontend-dev / backend-dev
  모두 `AnnotationSpan.data: dict[str, Any]` 로 다뤄야 함. 타입 안정성이 일시적으로
  약함. ADR-0003 진입 시 `AnnotationSpan` 을 discriminated union 으로 교체하면서
  마이그레이션 필요.
- **마커 분리 미결**: ADR-0004 (Phase 1 진입 전) 까지는 `Passage.body_text` 의
  마커 inline 여부가 중립. 그 사이의 데이터는 ADR 결정에 따라 마이그레이션 가능.
- **VariantKind enum 1차 안**: domain-expert 의 `docs/variant-type-catalog.md` 재작성
  결과로 enum value 정정/보강 필요. 후속 PR 로 처리.
- **Vocabulary Passage 종속 only**: v0.1 은 글로벌 dedup 미지원. `headword_normalized`
  필드만 박아 retrofit 비용 줄임. Phase 2/3 진입 전 별 ADR.
- **mypy strict 통과 비용**: `dict[str, Any]` placeholder 가 strict 환경에서 annotation
  소비 측 코드에 cast 부담 유발 가능. 본 PR 은 placeholder 만 작성하므로 직접 영향
  없음.

### 후속 결정 트리거 (미해결 ADR)

| ID | 주제 | 시점 | 담당 |
|---|---|---|---|
| ADR-0003 | Annotation span 식별 방식 (character offset / token id / ProseMirror pos) | Phase 1 진입 전 | architect + frontend-dev + domain-expert |
| ADR-0004 | 마커/텍스트 분리 정책 (Gap K) — Annotation 통합 vs 별 카테고리 | Phase 1 진입 전 | architect + domain-expert |
| ADR-0005 | Vocabulary 글로벌 마스터 도입 시점 (Gap E) | Phase 2 진입 전 | architect + domain-expert |
| ADR-0006 | Question / VariantQuestion 단일 테이블 vs 별 테이블 | Phase 3 진입 전 | architect + domain-expert |
| ADR-0007 | DB 멀티테넌트 격리 — row-level filter vs PostgreSQL RLS | Phase 4 진입 전 | architect + backend-dev |

위 ID 는 잠정. 실제 작성 시 다음 번호 할당.

### 후속 작업 (다음 작업자에게)

#### backend-dev

1. **ORM 동기화** (M-1, M-3 후속 처리): `apps/api/src/worksheet_api/models/tenant.py`
   의 placeholder ORM 을 `shared/schemas/` Pydantic 모델과 합친다. 매핑 도구 선정 시
   ADR (CLAUDE.md §3.6).
2. **`datetime.utcnow` 제거**: 기존 placeholder ORM 의 `datetime.utcnow` (M-3 지적
   사항) 를 `shared.schemas.common.utc_now` 와 정합 — `func.now()` 또는 동일 utility.
3. **`Translation.passage_id` UNIQUE 제약** (PM 결정 D-2): Alembic 마이그레이션에서 박음.
4. **Passage / Translation / Vocabulary / SyntaxAnnotation / Question / Worksheet
   모든 도메인 엔티티 ORM 매핑** + 마이그레이션.
5. **Repository 패턴** (audit §5.2): `tenant_id` + `workspace_id` 자동 필터.

#### frontend-dev

1. **에디터 상태 매핑**: Tiptap PoC 가 `SyntaxAnnotation` Pydantic 모델의 JSON 직렬화
   결과를 입력/출력으로 사용. ProseMirror position ↔ `AnnotationSpan` 변환 어댑터
   필요 (ADR-0003 결정에 따라).
2. **단축키 명세** (`reference-program-analysis.md` §4.4): 클릭+드래그 단어 선택, Shift
   추가, Alt 제거, Esc 취소, Del 삭제.
3. **12색 팔레트 + 5종 카테고리 행** 구현.

#### qa-validator (Phase 3)

1. **Phase 3 입력**: `Question.uniqueness_validated` + `Question.uniqueness_validator_note`
   필드를 채움. variant_kind != ORIGINAL 인 Question 에 대한 별도 LLM call 로 정답
   유일성 검증.

#### domain-expert

1. **`docs/variant-type-catalog.md` 재작성** (CLAUDE.md v0.3 §6.2 정정 반영). 결과로
   `VariantKind` enum value 보강.
2. **24개 type 의 한국어 라벨 매핑** 정정 (parser/renderer 어댑터에 들어갈 매핑 테이블).

---

## Alternatives Considered (검토한 대안)

### A. Question / VariantQuestion 별 테이블 (audit §4-5 (b) 안)

- 장점: 도메인 분리 명확. Phase 3 의 변형 유형이 별 카테고리로 진화할 여지.
- 단점: CLAUDE.md v0.3 §6.2 정정과 충돌 (변형은 기존 24개의 sub-form). 동일 type 이
  두 테이블에 분산되면 검색 / 통계 / 출력 어댑터가 모두 두 곳을 봐야 함.
- 기각 사유: §6.2 정정 + 단일 테이블 + discriminator 가 자연스럽고 Pydantic v2
  discriminated union 패턴과 정합. Phase 3 진입 전 재검토 가능 (ADR-0006).

### B. 변형 유형을 별 `QuestionType` enum 멤버로 추가 (예: `VOCABULARY_VARIANT`)

- 장점: 별 type 으로 변형 식별이 단순.
- 단점: CLAUDE.md v0.3 §6.2 가 명시적으로 거부 — "변형 유형은 별 카테고리가 아니라
  기존 24개 유형의 sub-form".
- 기각 사유: charter 위반.

### C. SyntaxAnnotation 의 `kind` 와 `category` 통합 (단일 enum)

- 장점: 모델 단순.
- 단점: 영상 레퍼런스의 명확한 분리 (시각 표현 vs 분석표 행) 와 충돌. 같은 `kind`
  (예: `highlight`) 가 다른 `category` (예: `note` 또는 `phrase`) 에 속할 수 있음 —
  교차 분류.
- 기각 사유: 영상 레퍼런스 §3.3 의 도메인 모델이 명확.

### D. CEFR 레벨 / subject_domain v0.1 도입 (audit §4-1 권고 일부)

- 장점: 검색·필터 메타 풍부.
- 단점: PM 결정 D-1 명시 거부 ("공식적으로 나눠진 난이도 등급은 없다"). 한국 시장은
  CEFR 보다 학년/수능 빈도 등급이 익숙.
- 기각 사유: PM 결정 우선. v0.2 검토.

### E. Translation 1:N (audit §4-2 / domain-expert 권고)

- 장점: 직역/의역 다중 버전 보관 유연.
- 단점: PM 결정 D-2 거부 — unused 복잡도 누적 비용 > 향후 1:1→1:N 마이그레이션 비용.
- 기각 사유: PM 결정 우선.

### F. ChoiceMatrix 별 모델 (audit §3.1 Gap B 권고안 (1))

- 장점: 매트릭스 case 의 1급 표현.
- 단점: 평탄 `choices: list[str]` 와 별 필드 → 데이터 모델 분기 비대화. 평가원 요약문(40)
  의 lossy 평탄화 데이터 마이그레이션 부담.
- 기각 사유: audit-review-domain §3.2 의 평탄화-우선 + 매트릭스-옵트인 (`choice_format`
  디스크리미네이터) 권고가 마이그레이션 비용이 가장 적음. 본 ADR D2.3 에서 채택.

---

## References

- `CLAUDE.md` v0.3 §3.1 (Canonical Schema), §6.2 (Question 유형 정정), §7.2 (architect 권한)
- `docs/adr/0001-canonical-schema-philosophy.md`
- `docs/schema-coverage-audit.md` §3 (Gap A~N), §4 (엔티티 권고), §5 (멀티테넌트), §7 (검토 요청)
- `docs/audit-review-domain.md` §3 (보완·이견), §4 (위험 신호), §5 (미해결 질문)
- `docs/reference-program-analysis.md` §2 (6종 annotation), §3 (인터랙션), §4.3 (모델 권고)
- `docs/adr/_pm-decisions-sprint-0.md` (PM 결정 D-1/D-2/D-3, 본 ADR 에 흡수)
- exam-generator `shared/schemas/question.py` (24개 type / SubQuestion / QuestionPlan 흡수 출처)
