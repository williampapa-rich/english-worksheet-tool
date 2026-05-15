# ADR 0016 — VocabularyMaster (글로벌 어휘 dedup) 도입 방향

- **상태(Status)**: Accepted
- **작성일**: 2026-05-10
- **결정일**: 2026-05-15 (PM Dennis — D1=(a) 별 테이블 / D2-c override 인정 / D3 tenant 별 UNIQUE / D5 학년 분리 X + homonym 별 행 / D6 Phase 2-edit 종료 후 별 PR)
- **작성자**: architect
- **결정자**: PM (Dennis)
- **유형**: Phase 3 진입 차단 ADR — `Vocabulary` 의 passage 종속 모델 (v0.1) 을
  글로벌 dedup 자산으로 진화시키는 방향 결정. 본 ADR 은 *코드 변경 0* — `shared/schemas/`
  v0.2 PR + Alembic 마이그레이션은 별 PR.
- **범위**: VocabularyMaster (글로벌 어휘 풀) 의 *도입 방식* / *멀티테넌트 정합* /
  *Phase 2-edit / Phase 3 보강 파이프라인 정합* / *도입 시점*. 어휘 등급 enum 정규화
  (`level_label` → enum) 는 본 ADR 범위 외 (별 chore).
- **관련 문서**:
  - `CLAUDE.md` v0.10.1 §1.3 (콘텐츠 자산화 — 한 번 만든 어휘는 재사용 가능한 자산),
    §3.1 (canonical schema), §6 (콘텐츠 모델), §11 Open Questions —
    "Vocabulary 글로벌 마스터 도입 시점 — Phase 2/3 진입 전 ADR (audit §4-3)"
  - `docs/schema-coverage-audit.md` §3.2 Gap E (Vocabulary 표현 없음 → Passage 종속
    only 권고 + 글로벌 마스터는 Phase 2/3 별 ADR), §4.2 Vocabulary 권고 (`passage_id`
    nullable 두고 글로벌 마스터에 dedup, v0.1 은 passage 종속 only 출시)
  - `docs/adr/0001-canonical-schema-philosophy.md` (스키마 진화 — 새 필드 추가
    위주, 기존 필드 변경 지양)
  - `docs/adr/0013-llm-augmentation-pipeline.md` D3 (Vocabulary 보강 정책) +
    "후속 작업 / 별 ADR (Phase 2/3 진입 전): 글로벌 `VocabularyMaster` — Vocabulary
    dedup + `headword_normalized` UNIQUE 제약 / 마이그레이션 정책"
  - `docs/adr/0015-phase-2-edit-sprint.md` D2 Stage E1-c (`POST
    /passages/{id}/vocabulary/manual` — 사용자 직접 어휘 추가 통로)
  - `shared/schemas/vocabulary.py` — 현재 v0.1 모델 (`headword_normalized` 필드는
    이미 자리 박힘 — Phase 2/3 의 글로벌 dedup 마스터 도입 시 join 키)

---

## Context (배경)

### 1. v0.1 의 의도적 단순화 — 그리고 박혀있는 retrofit hook

`shared/schemas/vocabulary.py` (v0.1) 은 audit §3.2 Gap E + §4.2 권고대로 **Passage
종속** 으로 출시했다. 동일 단어 (예: "endeavor") 가 다른 passage 에 등장하면 매번 새
`Vocabulary` 행이 생성된다 — DB 레벨에서 dedup 안 됨.

단 audit §4.2 가 권고한 retrofit hook 두 개는 이미 박혀있다:

1. **`headword_normalized: str`** — 정규화된 표제어 (`LOWER(word)` 또는 lemmatizer
   결과). v0.1 docstring 명시 — *"Phase 2/3 의 글로벌 dedup 마스터 도입 시 join
   키"*. 즉 master 테이블이 도입되면 `Vocabulary.master_id` 가 추가될 때 join 후보
   키가 이미 데이터에 들어있다.
2. **`selected_by` / `user_edited` 메타** — ADR-0013 의 사용자 수정 보존 흐름 (CLAUDE.md
   §1.3 핵심 가치 명제 #3) 이 master 도입 후에도 그대로 동작하도록 설계됨. master 가
   "글로벌" 이 되더라도 *passage 의 어휘 박스에 들어가는 항목* 의 USER vs LLM 구분은
   passage 종속 행에 남는다.

### 2. 와이프 시나리오 — "endeavor 를 평생 100번 가르친다"

audit-review-domain §3.3 도메인 인사이트 (`shared/schemas/vocabulary.py:9-15` docstring
참조):

> 한국 영어 학원 강사의 어휘 관리는 2계층 hybrid 가 표준이다.
>   1. 지문 종속 어휘 박스 (학생용 자료에 들어가는 8~15개 핵심 어휘)
>   2. 개인 단어장 (강사 본인이 평생 누적하는 어휘 자산)

audit §7.4 의 domain-expert 검토 요청:

> 동일 단어가 여러 지문에 등장할 때, 매번 새 Vocabulary 엔트리를 만드는 게 자연스러운가,
> 글로벌 마스터에서 재사용하는 게 자연스러운가? (예: "endeavor"는 한 강사가 평생 100번
> 가르치는 단어 — 매번 의미를 다시 입력하는 건 비효율)

현재 v0.1 만으로는 (2) "개인 단어장" 이 *암묵* 으로 분산 저장된다 — 같은 단어의 100개
복제본. 어휘 자산화 (CLAUDE.md §1.3 가치 명제 #1) 가 lossy 한 상태.

### 3. Phase 3 (변형문제) 와의 정합 — 어휘 변형의 source

CLAUDE.md §6.2 + `docs/schema-coverage-audit.md` §4.2 + `shared/schemas/question.py`
의 `VariantKind.VOCABULARY_SWAP`. Phase 3 의 어휘 변형 시나리오:

- 원본 Question (예: 어휘(30)) 의 `_word1_` 마커 위치에서 *대체 후보* 를 LLM 이 생성.
- 와이프의 *기존 어휘 자산* (개인 단어장) 을 LLM 컨텍스트로 주입하면 변형 품질이 높아짐
  + 와이프가 평소 가르치는 단어 분포와 정합.
- v0.1 (passage 종속) 만으로는 와이프의 단어장이 100개 passage 에 분산 → LLM 컨텍스트
  주입이 비효율 (passage 별로 따로 fetch).

즉 **Phase 3 진입 전에 글로벌 master 가 있으면** 어휘 변형 LLM 호출의 컨텍스트 입력이
단순해진다. Phase 3 진입 후 retrofit 하면 변형 코드가 *passage 어휘 풀 collect* 로직을
별도로 갖게 되고, 글로벌 master 도입 시 그 로직이 죽는다.

### 4. ADR-0013 의 보강 파이프라인과의 정합

ADR-0013 D3 (Vocabulary 보강 정책) 는 `headword_normalized` 충돌을 *passage 안* 에서만
검출한다 — passage A 에 "endeavor" 가 있고 passage B 에 또 추가되는 것은 충돌이 아니라
*당연*. master 도입 후에는 충돌 정의가 바뀌지 않는다 (passage 안에서의 중복만 차단).

단 master 도입 시 보강 라우트의 *동작* 은 확장된다:
- LLM 이 새 어휘를 산출 → `headword_normalized` 로 master 조회 → 있으면 master 의
  `meaning_ko` / `pos` 를 reuse (LLM 호출 비용 절약 가능성).
- 없으면 master 에 신규 행 생성 + passage 행에 `master_id` FK.

이 *reuse* 가 master 의 핵심 가치. 단 *passage 별 의미 변형* (같은 단어가 passage 에
따라 다른 뜻) 은 master 의 default meaning 을 override 가능해야 함 — passage 종속 행의
`meaning_ko` 를 *override* 로 둘지 *master 의 alias* 로 둘지 결정 항목 (D2-c).

### 5. ADR-0015 Stage E1-c 와의 정합 — 사용자 직접 어휘 추가

ADR-0015 D2 Stage E1-c — `POST /passages/{id}/vocabulary/manual` (와이프가 본문에서 단어
드래그 → 어휘 추가). 이 라우트가 master 와 정합:
- 와이프가 입력한 단어가 master 에 이미 있으면 master 의 default 가 form 에 prefill
  → 와이프가 의미 매번 입력 안 해도 됨.
- 없으면 신규 master 항목 생성 + passage 행에 link.

Phase 2-edit Stage E2 의 `<VocabularyTable>` 추가 행 UX (D6 "+" 버튼) 가 master
도입 후 자연스럽게 prefill 동작 추가 가능 — *그러나* 본 ADR 은 UX 변경을 요구하지
않는다. master 가 *읽기 prefill 옵션* 으로만 활용되더라도 Phase 2-edit 가 끝난 후
별 chore 로 도입 가능 (UI 변경 없이 백엔드만 추가).

### 6. 멀티테넌트 정합 — master 가 글로벌인가, tenant 별인가

영어 단어 자체는 글로벌 자산 (예: "endeavor" 의 사전적 정의). 그러나 audit §7.4 의
도메인 인사이트:

- 학원/강사 별 *커스텀 정의* 가능성 (예: 같은 단어를 다른 학년 / 다른 학원 스타일에
  맞춰 다르게 가르침).
- 학원 내부 단어장 (CEFR / 수능 빈도 / 자체 분류 등) 의 customization.

→ master 는 **tenant_id 별 + 동일 `headword_normalized` 1행** 형태가 가장 안전.
*글로벌* (모든 tenant 공유) master 는 cross-tenant 정의 충돌 위험 + 멀티테넌트 정합
복잡화. CLAUDE.md §3.3 의 "모든 도메인 테이블에 `tenant_id` 처음부터 박음" 원칙과 정합.

---

## Decision (결정)

### D1. 도입 방식 — 권장안: (a) 별 테이블 + `Vocabulary.master_id` FK

**3가지 안 검토 + 권장**:

#### (a) [권장] 별 `VocabularyMaster` 테이블 + `Vocabulary.master_id: Optional[FK]`

```
VocabularyMaster (글로벌 dedup, tenant_id 별)
  - id (UUID)
  - tenant_id, workspace_id (FK)
  - headword_normalized (UNIQUE per tenant_id)
  - word_canonical (lemma 표면형, 예: "endeavor")
  - default_meaning_ko (master 기본 뜻)
  - default_pos (master 기본 품사)
  - default_level_label (master 기본 등급 라벨)
  - usage_count (master 가 link 된 Vocabulary 행 수 — 통계용, 캐시)
  - created_by (LLM / USER / IMPORT)
  - created_at, updated_at

Vocabulary (passage 종속, 기존 v0.1 + master_id 추가)
  - id (UUID)
  - tenant_id, workspace_id (FK)
  - passage_id (FK, NOT NULL)            # v0.1 그대로
  - master_id (FK, NULLABLE)              # 신규 — master 와 link 시 NOT NULL
  - word, headword_normalized              # v0.1 그대로 (master link 시 master 에서 sync 가능 — D2-b)
  - pos, meaning_ko, level_label           # v0.1 그대로 — passage 별 override 허용 (D2-c)
  - selected_by, user_edited               # v0.1 그대로
```

**장점**:
- ADR-0013 D3 의 *passage 안 충돌 검출* 동작 변경 0 (외부 동작 100% 유지).
- `master_id NULLABLE` 로 두면 v0.1 데이터 마이그레이션이 *옵션* — null 인 행은
  legacy 로 동작 (BC 보장).
- master 가 자체 lifecycle (생성/소프트삭제/통계) 을 가질 수 있어 *개인 단어장 페이지*
  같은 미래 기능의 source 자연스럽게 됨.
- `usage_count` 캐시로 자주 쓰이는 단어 ranking / 검색 가능.

**단점**:
- 신규 테이블 + Alembic 마이그레이션 + retroactive `master_id` backfill 작업 필요
  (D5 마이그레이션 정책).
- 코드 변경 면적 — Vocabulary CRUD 라우트 (Stage E1-b/-c/-d) 가 master 갱신 흐름 통합
  필요. 단 *읽기* (worksheet preview/PDF) 는 master_id 무시 가능 — 단계적 도입 OK.

#### (b) [대안] `Vocabulary` 그대로 두고 `headword + tenant_id` 기준 dedup view / 쿼리

신규 테이블 X. 기존 `Vocabulary` 위에 SQL view / 쿼리로 dedup:

```sql
CREATE VIEW vocabulary_master_view AS
SELECT
  tenant_id,
  headword_normalized,
  ARRAY_AGG(DISTINCT meaning_ko) AS meanings,
  COUNT(*) AS usage_count,
  MIN(created_at) AS first_seen
FROM vocabulary
WHERE selected_by != 'frequency_filter'  -- 시스템 자동 선정 제외
GROUP BY tenant_id, headword_normalized;
```

**장점**:
- 마이그레이션 0. 스키마 변경 0.
- 즉시 도입 가능 (Phase 2-edit 진행 중에도 OK).

**단점**:
- master 가 *통계* 일 뿐 *자산* 이 아님. 와이프가 단어장에 *직접* 단어 추가 (passage 와
  무관) 못 함 — passage 종속 행이 없는 entry 표현 불가.
- LLM 보강 reuse (§Context 4) 시점에 view 조회 → 결과 inconsistent 가능 (passage 별
  `meaning_ko` 가 다 다르면 어느 걸 reuse?).
- Phase 3 어휘 변형 시 *원본 어휘 자산* 의 source of truth 가 view 라 *update* 불가
  (and-only-from-passage 한계).

→ *읽기 전용 dedup* 만 필요하면 충분, 그러나 자산화 (CLAUDE.md §1.3 가치 명제 #1)
관점에서 master 가 1급 entity 가 아님 → 권장 안 함.

#### (c) [대안] Master 없이 `Vocabulary.master_id` 만 self-FK (canonical row 자기 참조)

```
Vocabulary
  - master_id: Optional[FK → vocabulary.id]  # 같은 word 의 canonical 행 1개 self-link
```

같은 `headword_normalized` 의 행 N개 중 1개를 *canonical* 로 표시 + 나머지는 그것을
참조.

**장점**:
- 신규 테이블 X.

**단점**:
- canonical 과 비-canonical 의 lifecycle 이 다른데 같은 테이블에 섞임 — 의미적 혼란.
- canonical 행이 삭제되면 (passage 삭제 cascade) 다른 행들의 master_id 가 깨짐 → 매번
  promote 로직 필요.
- `usage_count` / *passage 무관 단어장 entry* 표현 못 함 (passage 종속 그대로).

→ 단순해 보이지만 lifecycle 혼란 비용 > 절약 비용. 권장 안 함.

**최종 권장**: **(a) 별 `VocabularyMaster` 테이블 + `Vocabulary.master_id` nullable
FK**. 점진 도입 가능, 자산화 가치 충분.

### D2. shared/schemas/vocabulary.py 변경 영향 (설계만, 코드 작성 X)

#### D2-a. 신규 모델 `VocabularyMaster` (권장 안 (a))

`shared/schemas/vocabulary_master.py` (또는 `vocabulary.py` 내 추가) — Pydantic v2
모델 + SQLAlchemy ORM (Alembic 마이그레이션):

- `id`, `tenant_id`, `workspace_id` — `WorkspaceScopedEntity` 베이스 (기존 패턴).
- `headword_normalized: str` — UNIQUE 제약 per `(tenant_id, headword_normalized)`.
- `word_canonical: str` — lemma 표면형 (대소문자 보존 표시용).
- `default_meaning_ko: str` — master 기본 뜻.
- `default_pos: str | None` — master 기본 품사.
- `default_level_label: str | None` — master 기본 등급.
- `usage_count: int` — 캐시 (트리거 또는 보강 라우트에서 갱신).
- `created_by: VocabularyMasterCreatedBy` — LLM / USER / IMPORT enum.

#### D2-b. `Vocabulary.master_id` 필드 추가 + `Vocabulary` 와 master 의 sync 정책

`Vocabulary` 모델에 `master_id: EntityId | None` 추가. 두 가지 sync 정책:

1. **`headword_normalized` sync**: master link 시 `Vocabulary.headword_normalized =
   master.headword_normalized` 강제 (Pydantic `model_validator`). 그렇지 않으면 link
   끊어짐 가능.
2. **`word` 표면형 보존**: `Vocabulary.word` 는 사용자 입력 표면형 (대소문자/굴절)
   유지. master 의 `word_canonical` 과 *다를 수 있음* (예: master "endeavor", passage
   행 "Endeavored").

#### D2-c. passage 별 의미 override — `meaning_ko` 정책

핵심 결정: `Vocabulary.meaning_ko` 가 master 의 `default_meaning_ko` 와 *다를 때* 어떻게
처리?

- (i) [권장] **passage 행이 우선** — `Vocabulary.meaning_ko` 가 master 와 다르면
  *passage-specific override*. master 의 default 는 prefill / fallback 으로만 활용.
  ADR-0013 의 `user_edited=True` 가 자동 set 되면 사용자 의도 명시. 이 정책이 *passage
  context 별 의미 변형* 을 자연 표현 (audit §7.4 의 도메인 인사이트 정합).
- (ii) master 와 강제 일치 — 모든 passage 행이 master 의 default 를 그대로 사용.
  단순하지만 도메인 (passage 별 의미) 표현 불가.

→ (i) 권장. 단 master prefill 시점 (예: Stage E1-c 의 manual add) 에 default 로 채우는
것은 OK.

#### D2-d. Alembic 마이그레이션 — backfill 정책

backfill (기존 `Vocabulary` 행 → master 생성 + link) 은 두 단계:

1. **Migration 1 (online)**: `vocabulary_master` 테이블 생성 + `vocabulary.master_id`
   nullable column 추가. UNIQUE (`tenant_id`, `headword_normalized`) 인덱스 생성.
2. **Migration 2 (data backfill)**: 기존 `Vocabulary` 행을 `(tenant_id,
   headword_normalized)` 로 group → 각 그룹마다 `VocabularyMaster` 1행 생성 (가장 흔한
   meaning_ko / pos / level 을 default 로 — group MAX 또는 첫 행) → 그룹 안 모든
   `Vocabulary` 의 `master_id` 채움.

backfill 은 *옵션* — 기존 데이터가 적으면 (와이프 검수 단계) 한 번에 처리. 운영 데이터
누적 후라면 chunk 단위 background job (Phase 4 진입 전 검토).

### D3. multi-tenant 정합

D1 권장안 (a) 의 `VocabularyMaster` 는 **tenant_id 별** — UNIQUE 제약은 `(tenant_id,
headword_normalized)`. 다음 결과:

- 강사 A 의 master 와 강사 B 의 master 는 *분리* — 각자 자신의 단어장.
- 같은 영어 단어 "endeavor" 가 강사 A 의 master 에 1행, 강사 B 의 master 에 1행 (총 2행).
- CLAUDE.md §3.3 "모든 도메인 테이블에 `tenant_id` 처음부터 박음" 원칙 그대로.

**이론적 대안 (글로벌 + tenant override)**: master 를 tenant 무관 + 강사별 override
테이블. 단 멀티테넌트 격리 + RLS 호환 (Phase 4) 복잡도 급증 + 글로벌 master 의
*어디서 채우는가* 정책 (사전 데이터 import? 매 보강 호출의 누적?) 결정 비용. → Phase 5
이후 *어휘 사전 자산 공유 marketplace* 같은 별 phase 로 미룸.

### D4. Phase 2-edit / Phase 3 와의 정합

#### D4-a. Phase 2-edit (현재 진행 중) 영향

ADR-0015 Stage E1-b/-c/-d 의 PATCH/POST/DELETE 라우트는 *추가 동작* 만 받는다 (외부
동작 변경 없음 — D1 권장안 (a) 의 `master_id NULLABLE` 이 BC 보장):

| Stage | v0.1 동작 | master 도입 후 추가 |
|---|---|---|
| E1-b PATCH `/.../vocabulary/{vid}` | `meaning_ko` 등 수정 | master 의 default 와 다르면 `master_id` 유지하되 D2-c (i) 정책으로 passage override |
| E1-c POST `/.../vocabulary/manual` | passage 종속 행 생성 | `headword_normalized` 로 master 조회 → 있으면 default prefill + link / 없으면 master 신규 생성 |
| E1-d DELETE `/.../vocabulary/{vid}` | passage 행 삭제 | master 의 `usage_count` 감소 (트리거 또는 라우트). usage_count = 0 인 master 는 *유지* (개인 단어장 자산 보존) |

→ Phase 2-edit Stage E1 자체는 master 없이 출시 가능 (ADR-0013 mode 정합 그대로).
master 도입은 *그 다음* — UI 변경 없이 백엔드 추가만 (Stage E1 머지 후 별 PR).

#### D4-b. Phase 3 (변형문제) 영향

ADR-0017 (별 ADR — Question / VariantQuestion) 와 정합. 어휘 변형 (`VariantKind.
VOCABULARY_SWAP`) 시:

- 원본 Question 의 `_word1_` 마커 위치 → master 조회 → master 의 `default_meaning_ko`
  / `default_level_label` / *유사 어휘 후보* (master 안에서 같은 `default_pos` 또는
  `default_level_label` 인 다른 master 행) 를 LLM 컨텍스트 주입.
- LLM 이 산출한 대체 후보 어휘는 새 master 행 (없으면) + 기존 master link.

→ master 가 *Phase 3 진입 전에* 있으면 변형 코드가 단순. master 없으면 변형 코드가
"passage 어휘 풀 collect → dedup" 로직 자체적으로 가져야 함 (Context 3).

### D5. Open Questions (결정 미루는 항목)

- [ ] **학년별 master 분리 vs 통합** — 같은 강사가 가르치는 학년이 다양 (중3 / 고1 / 고3).
      master 가 학년 무관 (`default_level_label` 만 표시) vs 학년별 분리 (중3 master /
      고3 master). domain-expert 검토 필요.
- [ ] **동음이의어 (homonym) 처리** — "bank" (강둑/은행) 같은 다의어. 같은
      `headword_normalized` 1행 + `default_meaning_ko` 1개 정책으로는 lossy. 다음 옵션:
      - (i) `meaning_ko` 를 `list[str]` 로 — 단순. 단 LLM 보강 reuse 시 어느 의미를 prefill?
      - (ii) `headword_normalized` 를 `(lemma, sense_id)` 튜플로 — 정확. 단 `sense_id`
        결정 정책 추가 비용 (WordNet sense? 자체 enum?).
      - (iii) v0.1 정책 유지 (1행 1뜻) + passage 별 override (D2-c) 로 흡수.
      → (iii) 권장 시작 + Phase 4 클라우드 배포 시 (i) 검토.
- [ ] **master `created_by=IMPORT`** — 와이프가 기존 단어장 (예: Excel / 학원 자체 자료)
      를 *대량 import* 하고 싶은 시나리오. CSV import 라우트 도입 시점은 별 chore.
- [ ] **글로벌 (cross-tenant) master 공유 marketplace** — Phase 4+ 의 별 phase. 본
      ADR 범위 외.

### D6. 도입 시점 — 권장 트리거

#### 권장 시점: **Phase 2-edit Stage E2 머지 후 + Phase 3 진입 전**

이유:
- Phase 2-edit Stage E1/E2 는 master 없이 완성 가능 (D4-a) — ADR-0015 sprint 의 MVP
  scope 보존.
- Stage E2 의 `<VocabularyTable>` 머지 후 운영 데이터가 쌓이면 backfill (D2-d
  Migration 2) 의 그룹 통계 기반 default 결정이 정확해짐 (와이프가 실제 사용한
  meaning_ko 분포 반영).
- Phase 3 진입 전 (변형문제 어휘 변형 LLM 코드 작성 전) master 가 있으면 변형 코드
  단순화 (Context 3, D4-b).

#### 대안 시점: Phase 3 중 첫 어휘 변형 PR 머지와 동시

- 장점: 변형 변별 가치가 *명확히 드러나는* 시점에 도입 → 정당화 명확.
- 단점: 변형 PR 이 master 마이그레이션 + 변형 LLM 코드 동시 처리 → PR 분량 폭증.

#### 비-대안: Phase 4 (클라우드 배포) 까지 미룸

- 장점: master 의 multi-tenant 격리 정책 (D3) 을 RLS 와 함께 결정 가능.
- 단점: Phase 3 어휘 변형 코드가 master 없이 작성됨 → 후일 master 도입 시 변형 코드의
  *passage 어휘 풀 collect* 로직 죽음. retrofit 비용 큼.

→ **Phase 2-edit Stage E2 머지 후** 트리거. PM 결정.

### D7. Phase 별 변경 비용

| 도입 시점 | 변경 비용 | 비고 |
|---|---|---|
| Phase 2-edit Stage E1 직후 | 낮음 — 신규 테이블 + nullable column + backfill (적은 데이터) | 권장 |
| Phase 2-edit Stage E2 머지 후 | 낮음 — backfill 데이터 더 많아 default 통계 정확 | 권장 ✓ |
| Phase 3 진입과 동시 | 중 — 변형 PR 과 master PR 동시 → 분리 권장 | 차선 |
| Phase 3 종료 후 | 높음 — 변형 코드의 *passage 어휘 풀 collect* 로직 retrofit | 회피 |
| Phase 4 (클라우드 배포 후) | 매우 높음 — RLS + 운영 데이터 chunk 마이그레이션 | 회피 |

---

## Consequences (결과)

### 긍정적 결과

1. **콘텐츠 자산화 (CLAUDE.md §1.3 가치 명제 #1) 실현** — 와이프의 평생 단어장이 1급
   entity 로 누적.
2. **Phase 3 어휘 변형 LLM 코드 단순화** — master 가 컨텍스트 입력 source.
3. **Phase 2-edit UI 변경 0** — D1 권장안 (a) 의 nullable FK + 단계적 도입.
4. **ADR-0013 보강 파이프라인 외부 동작 변경 0** — master link 는 *추가 동작*.
5. **CLAUDE.md §3.6 NRTW 정합** — 신규 라이브러리 도입 없음, 기존 SQLAlchemy /
   Pydantic / Alembic 패턴 그대로.

### 부정적 결과 / 리스크

1. **Alembic backfill 비용** — Phase 2-edit Stage E2 후 trigger 시 운영 데이터 수
   100~수천 행 가정 → 한 번에 처리 가능. Phase 4 후 trigger 시 chunk 마이그레이션 필요.
2. **master 의 default vs passage override 혼란** — D2-c (i) 정책 (passage 우선) 이
   일관 — 단 사용자 UX 에서 "왜 master 의 뜻과 passage 행의 뜻이 다른가" 명확화 필요
   (Phase 2-edit Stage E2 머지 후의 별 UX chore — *master prefill 표시 indicator*).
3. **homonym lossy** — D5 의 (iii) 권장 시작 → Phase 4 검토.
4. **`usage_count` 캐시 정합** — 트리거 vs 라우트 명시 갱신 — D1 권장안 (a) 에 결정 미룸,
   별 chore 로 분리.
5. **PR 분량** — `shared/schemas/vocabulary_master.py` + Alembic 1~2건 + 라우트 통합
   + 단위 테스트 ≈ 800~1,200 LOC. 1주 작업 추정.

---

## 후속

본 ADR 결정 (Accepted) 후:

1. **architect** — `shared/schemas/vocabulary_master.py` 신규 + `vocabulary.py` 의
   `master_id` 필드 추가 PR (스키마 only).
2. **backend-dev** — Alembic 마이그레이션 2건 (D2-d 두 단계). Stage E1 라우트 통합 (D4-a)
   별 PR.
3. **domain-expert** — D5 학년별 master 분리 / homonym 정책 검토 (별도 PR 코멘트).
4. **code-reviewer** — backfill 마이그레이션의 멀티테넌트 격리 / sentinel UUID 차단 /
   `headword_normalized` UNIQUE 제약 검토.
5. **CLAUDE.md** — §11 Open Questions 의 *Vocabulary 글로벌 마스터 도입 시점* 항목에
   본 ADR 링크 추가 (Accepted 시점에 close 표시).

---

## 결정 기록

| 날짜 | 상태 | 결정자 | 비고 |
|---|---|---|---|
| 2026-05-10 | Proposed | architect | Phase 3 진입 차단 ADR 1/2 — VocabularyMaster 도입 방향. 권장: 별 테이블 (a) + `Vocabulary.master_id` nullable + tenant 별 + Phase 2-edit Stage E2 머지 후 트리거. PM 결정 대기 — D1/D2-c/D5/D6 4개 항목. |
