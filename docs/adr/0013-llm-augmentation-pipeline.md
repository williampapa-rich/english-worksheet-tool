# ADR 0013 — LLM 보강 (Translation / Vocabulary) 파이프라인 설계

- **상태(Status)**: Proposed
- **작성일**: 2026-05-07
- **결정일**: TBD (PM 검토 대기)
- **작성자**: architect
- **결정자**: PM (Dennis)
- **유형**: Phase 2 진입 — extractor 가 채우지 못한 (또는 비어있는) Translation /
  Vocabulary 를 LLM 으로 보강하는 별도 파이프라인 설계.
- **범위**: 보강 라우트 (`POST /passages/{id}/translation` /
  `POST /passages/{id}/vocabulary`) 의 호출 흐름 / 영속화 정책 / 재실행 / 사용자 수정
  보존 / 에러 처리 / 비용 추적 / 모델 선택. 본 ADR 결정에 따라 backend-dev 가
  B3 PR 에서 라우트 + 보강 어댑터 구현.
- **관련 문서**:
  - `CLAUDE.md` v0.8 §1.3 (편집 가능한 출력 — AI 결과는 사용자 검수/수정 후 내보냄),
    §2.1 Phase 2 (학생 배포용 자료), §3.1 (canonical schema), §3.6 (No Reinventing the
    Wheel)
  - `docs/adr/0001-canonical-schema-philosophy.md` (스키마 진화 원칙)
  - `docs/adr/0003-phase-0-extraction-pipeline.md` §D-3.2 / §D-3.5 / §G-1
    (LLM 호출 인터페이스, 에러 매핑, ExtractionMetaRef)
  - `docs/adr/0008-phase-1-output-format.md` (HWPX → HTML/PDF 출력 전환)
  - `docs/prompts/extract-text-v0.md` (PM-5 — 자료에 보이는 것만 추출)
  - `shared/schemas/translation.py` (1:1, `created_by` LLM/USER 추적)
  - `shared/schemas/vocabulary.py` (Passage 종속, `selected_by` LLM/USER/system,
    `user_edited` 메타)
  - PR #51 — B1 (extract 결과 Translation/Vocabulary 영속화, 옵션 B 전환)
  - 후속 PR — B3 (보강 라우트), B4 (Worksheet preview 컨텍스트 주입)

---

## Context (배경)

### 1. extract 와 보강의 시맨틱 분리

`POST /passages/extract` 의 시맨틱은 PM-5 (옵션 B) 로 확정 — **자료에 보이는 것만**
추출하고 생성하지 않는다. PM-6 가 명시하듯 실유저 입력의 default 는 영어 지문만
또는 문제만 — **`translation: null` / `vocabulary: []` 가 정상**이다.

Phase 2 에서 학생용 자료를 만들려면 이 비어있는 자리를 **LLM 으로 채워야** 한다.
이를 extract 호출에 묶어서 처리하는 안 (옵션 X — extract 후 자동 보강) 도 검토
가능하지만, 다음 세 가지 이유로 **별도 파이프라인** 으로 분리한다:

1. **시맨틱 충돌 방지** — extract 는 "원자료를 정규화하는" 동작, 보강은 "원자료에
   없던 정보를 LLM 이 생성" 하는 동작. 둘이 한 호출에 묶이면 PM-5 의 "보이는 것만"
   원칙이 흐려지고, 사용자가 결과를 볼 때 "이게 자료에 있던 거야 LLM 이 만든 거야"
   구분이 안 된다 (`created_by` / `selected_by` 메타로 구분 가능하지만 호출
   계약 자체가 모호해짐).
2. **비용 / 지연 분리** — extract 는 자료 1건당 1회 호출이고 보강은 **사용자가 명시적
   원할 때만** 호출. 학생용 자료를 안 만드는 사용자 (구문분석만 하는 사용자) 는
   보강 비용 0. extract 에 묶으면 매 요청마다 +2 LLM call 비용 강제.
3. **사용자 검수 흐름** — CLAUDE.md §1.3 의 "편집 가능한 출력" 원칙: LLM 결과는
   사용자가 검수/수정한 후 내보낸다. 보강은 사용자가 *명시적으로* 트리거하고
   편집한다 — extract 자동 보강은 이 흐름과 어긋난다.

### 2. 영속화 베이스는 B1 에서 깔림

PR #51 (B1) 머지로 `Translation` / `Vocabulary` 영속화가 활성화됐다. extract 시점에
자료에 들어있던 것은 이미 DB 에 있고 (`created_by=LLM` 으로, extractor 가 LLM 이라).
보강 라우트는 **DB 의 기존 상태를 보고** "기존 있으면 어떻게 할 것인가" 를 결정해야
한다.

**결정 가능 분기**:
- Translation (1:1): 이미 있는데 다시 보강 호출하면? → 덮어쓰기 / skip / append (1:1 라
  append 불가) / 사용자 확인.
- Vocabulary (1:N): 이미 있는데 다시? → 누적 / 교체 / 부분 갱신 / 사용자 확인.

`created_by=USER` / `user_edited=True` 메타가 이 결정의 1차 입력이다 — 사용자가 손댄
레코드는 LLM 이 다시 덮어쓰지 않아야 한다 (CLAUDE.md §1.3).

### 3. 보강 결과의 source of truth 는 schema

ADR-0001 의 canonical schema 원칙 — 보강 결과도 `shared/schemas/translation.py` /
`vocabulary.py` 의 Pydantic 모델을 그대로 사용한다. LLM 의 structured output 도 같은
모델로 검증 (`extract_structured[Translation]`).

### 4. 프롬프트 카탈로그는 별도 파일

본 ADR 과 함께 `docs/prompts/augment-translation-v0.md` /
`docs/prompts/augment-vocabulary-v0.md` 초안을 추가한다. 프롬프트 *내용* 은
domain-expert 검토 후 확정되며, 본 ADR 은 **프롬프트 *호출 계약*** (입력 변수, 출력
schema, 모델 hint, 재시도 정책) 만 결정.

---

## Decision (결정)

### D1. 라우트 분리 — 보강은 별 endpoint

```
POST /passages/{passage_id}/translation
POST /passages/{passage_id}/vocabulary
```

- extract 와 분리. extract 는 PM-5 그대로 "보이는 것만".
- 두 라우트 모두 **단일 트랜잭션** 으로 LLM 호출 → 영속화 → 응답 (ADR-0003 §D-3.4
  패턴 동일).
- 응답 스키마: 보강된 `Translation` 또는 `list[Vocabulary]` 그대로 반환 (
  `PassageWithRelations` 통째 반환은 안 함 — 호출자가 필요하면 GET /{id} 별도 호출).

#### D1-a. Idempotency / 사용자 의도 표현 — `mode` 쿼리 파라미터

```
POST /passages/{passage_id}/translation?mode=replace
POST /passages/{passage_id}/vocabulary?mode=append
```

- **`mode`** 가 "기존 데이터에 어떻게 쓸 것인가" 를 명시. **D2 / D3 의 정책과 동일**.
- default 는 **보수적 모드** (`skip_if_user_edited`) — 사용자 수정 보존 우선.

### D2. Translation 보강 정책 (1:1)

**3가지 mode**:

| `mode` | 동작 |
|---|---|
| `skip_if_user_edited` (default) | 기존 translation 의 `created_by=USER` 면 LLM 호출하지 않고 기존 반환. 그 외 (`LLM` 또는 없음) 는 LLM 호출 → 덮어쓰기. |
| `replace` | 기존 무시. 항상 LLM 호출 → 덮어쓰기. `created_by=USER` 였어도 덮어씀 — 사용자가 명시 의도 표현한 경우. 응답에 `created_by=LLM` 으로 갱신. |
| `skip_if_exists` | 기존 translation 이 있으면 (LLM/USER 무관) skip + 기존 반환. 없을 때만 LLM 호출. |

- DB UNIQUE(passage_id) 제약 그대로 — 항상 1건만 존재.
- 덮어쓰기는 in-place UPDATE (`text` / `created_by` / `updated_at` 갱신, `id` 유지).
  이전 버전 보존 안 함 (Translation schema docstring 의 PM 결정 인용).

### D3. Vocabulary 보강 정책 (1:N)

**3가지 mode**:

| `mode` | 동작 |
|---|---|
| `skip_if_user_edited` (default) | `selected_by=USER` 또는 `user_edited=True` 인 항목은 보존. LLM 보강 결과 중 기존 USER 항목과 `headword_normalized` 가 충돌하면 LLM 항목 skip. 나머지 LLM 항목은 INSERT. |
| `replace` | passage 의 모든 LLM 산출 vocabulary (`selected_by=LLM` 그리고 `user_edited=False`) 를 DELETE, USER 항목은 보존. 그 후 LLM 보강 결과 INSERT. |
| `append` | 기존 그대로 두고 LLM 보강 결과만 INSERT. `headword_normalized` 충돌은 INSERT 시 무시 (DB UNIQUE 제약 없음 — Phase 2/3 의 글로벌 마스터 도입 ADR 에서 중복 정책 결정). |

- **`headword_normalized` 충돌 검출**: passage 안에서 동일 `headword_normalized` 가
  두 번 나오면 silent drift — `skip_if_user_edited` / `replace` 모드는 LLM 결과끼리도
  중복 제거 (LLM 응답에서 첫 항목만 INSERT). `append` 모드는 호출자 책임 (모드 의미가
  "그냥 다 추가").
- **글로벌 마스터 (`VocabularyMaster`)**: CLAUDE.md §11 Open Questions — Phase 2/3
  진입 전 별 ADR. 본 ADR 은 Passage 종속 v0.1 가정.

### D4. 사용자 수정 보존 (CLAUDE.md §1.3)

핵심 원칙: **`created_by=USER` / `user_edited=True` 는 LLM 보강이 덮어쓰지 않는다**.

- Translation: `skip_if_user_edited` 가 default — 사용자 수정 보존.
- Vocabulary: `skip_if_user_edited` / `replace` 모두 `selected_by=USER` 또는
  `user_edited=True` 항목은 절대 DELETE / UPDATE 안 함.
- 사용자가 LLM 결과를 *덮어쓸* 의도라면 `mode=replace` 명시 필수 — 의도 명시 강제로
  실수 차단.

#### D4-a. PATCH (사용자 수정 라우트) 는 본 ADR 범위 외

사용자가 LLM 결과를 직접 수정하는 라우트 (`PATCH /translations/{id}`,
`PATCH /vocabulary/{id}`) 는 본 ADR 범위 밖. `created_by` / `selected_by` 를
`USER` 로 변경하는 시점이 PATCH 이고, 보강 라우트는 *읽기만* 한다 (보강 시 사용자
수정 보존 결정 입력으로).

PATCH 라우트는 별 PR (B3 후속 또는 와이프 검수 피드백 시점) 에서 다룸.

### D5. LLM 호출 인터페이스

ADR-0003 §D-3.2 의 `StructuredLLMClient.extract_structured[T: BaseModel]` 그대로
사용. 보강 어댑터는 `packages/llm/` 의 기존 클라이언트만 호출하고, 직접 SDK 호출 X
(CLAUDE.md §8.3).

#### D5-0. `target_grade` enum → 한국어 라벨 매핑 (도메인 검토 반영)

`shared/schemas/passage.py` 의 `TargetGrade` enum 값은 snake_case 영어
(`high_2`, `suneung`, `middle_3`, `other`). 프롬프트는 한국어 라벨 ("고2", "수능") 을
가정하므로 라우트 / 어댑터 책임으로 매핑한다. LLM 이 enum 값을 직접 받으면 한국어
해석에 silent drift 위험.

```python
# packages/llm/augment.py (B3 PR 신규)
from shared.schemas.passage import TargetGrade

GRADE_LABELS_KO: dict[TargetGrade, str] = {
    TargetGrade.MIDDLE_1: "중1",
    TargetGrade.MIDDLE_2: "중2",
    TargetGrade.MIDDLE_3: "중3",
    TargetGrade.HIGH_1: "고1",
    TargetGrade.HIGH_2: "고2",
    TargetGrade.HIGH_3: "고3",
    TargetGrade.SUNEUNG: "수능",
}


def _grade_label_for_prompt(grade: TargetGrade | None) -> str:
    """`target_grade` → 프롬프트용 한국어 라벨. None / OTHER → "고등" fallback."""
    if grade is None or grade == TargetGrade.OTHER:
        return "고등"
    return GRADE_LABELS_KO[grade]
```

#### D5-1. 어댑터 함수 시그니처

```python
# packages/llm/augment.py (B3 PR 신규)
async def augment_translation(
    passage: Passage,
    llm_client: StructuredLLMClient,
) -> Translation:
    """LLM 으로 Translation 생성. 호출자 (라우트) 가 영속화 책임."""
    spec = PromptSpec.load("augment-translation-v0")
    prompt = spec.render(
        passage_text=passage.body_text,
        target_grade=_grade_label_for_prompt(passage.target_grade),
    )
    result = await llm_client.extract_structured(
        prompt=prompt,
        response_model=TranslationLLMOutput,  # subset (text 만)
    )
    # LLM output → domain Translation 변환 (passage_id / tenant_id / created_by 주입은
    # 라우트 책임 — sentinel UUID 패턴 동일)
    return Translation(
        tenant_id=SENTINEL_UUID,
        workspace_id=SENTINEL_UUID,
        passage_id=SENTINEL_UUID,
        text=result.value.text,
        created_by=TranslationCreatedBy.LLM,
    )
```

#### D5-a. LLM output schema = domain schema 의 부분집합

LLM 이 채울 수 있는 필드만 별 Pydantic 모델로 정의:

```python
# packages/llm/augment.py (B3)
class TranslationLLMOutput(BaseModel):
    text: str = Field(..., description="전체 한국어 해석")

class VocabularyItemLLMOutput(BaseModel):
    word: str
    headword_normalized: str  # LLM 이 lemma 까지 산출
    pos: str | None = None
    meaning_ko: str
    level_label: str | None = None

class VocabularyLLMOutput(BaseModel):
    items: list[VocabularyItemLLMOutput]
```

- LLM 이 `tenant_id` / `workspace_id` / `passage_id` / `created_by` / `selected_by` /
  `user_edited` 등 시스템 메타를 만들면 안 됨 → schema 자체에 포함 안 함.
- 라우트가 sentinel UUID 패턴으로 시스템 메타 주입 (ADR-0003 §D-3.6 동일).

### D6. 모델 선택

| 라우트 | 모델 hint | 이유 |
|---|---|---|
| `augment-translation-v0` | `claude-sonnet-4-6` (또는 4.5) | 한영 번역은 Sonnet 으로 충분. Opus 비용 정당화 안 됨. |
| `augment-vocabulary-v0` | `claude-sonnet-4-6` | 어휘 선정 + 한국어 뜻 + 품사. Sonnet 으로 충분. |

- 환경변수 `ANTHROPIC_MODEL` 이 최종 결정 (extract 와 동일 패턴) — `model_hint` 는
  hint 만.
- Vision 입력 없음 (이미 정규화된 `Passage.body_text` 만 입력).

### D7. 에러 처리 (ADR-0003 §D-3.5 매핑 그대로)

| 예외 | HTTP 상태 |
|---|---|
| `LLMSchemaValidationError` | 502 |
| `LLMTimeoutError` | 504 |
| `PermanentLLMError` | 500 |
| `LLMNetworkError` / `LLMRateLimitError` | retry 후 504 / 502 |
| Passage 존재 안 함 또는 다른 tenant | 404 |
| `mode` 값 invalid | 422 (Pydantic) |

- 재시도 정책: `packages/llm/retry.py` 그대로 사용. extract 와 동일 — 별 정책 X.

### D8. 비용 추적 (ADR-0003 §G-1 / PM-4)

`llm_usage_logs` 테이블에 `prompt_template_id` (`augment-translation-v0` /
`augment-vocabulary-v0`) 와 `request_id` 기록. extract 와 동일.

- `parent_request_id`: 보강 라우트는 extract 와 다른 호출 — `parent_request_id=None`
  이 default. 재시도 체인은 `packages/llm/` 가 자동 기록.
- 호출 비용 모니터링은 CLAUDE.md §11 의 "LLM 비용 모니터링 / 캐싱 전략" 항목과 함께
  Phase 3 진입 전 별도 ADR.

### D9. 캐싱 — Phase 3 트리거

같은 passage 에 대해 보강을 여러 번 호출할 가능성 (사용자가 result 가 마음에 안 들어
재호출). 단순 캐시 (passage hash → 결과) 도입 가능하지만:

- **현재 (Phase 2 진입 시점)**: 캐싱 없음. 매 호출마다 LLM. PM-6 가정상 보강은 자주
  일어나지 않으므로 비용 부담 작음.
- **Phase 3 트리거**: 와이프가 "같은 passage 재보강 비용 너무 든다" 또는 클라우드
  배포 (Phase 4) 진입 시 동시성 / 비용 검토. 그때 별 ADR.

### D10. Worksheet preview 와의 통합 (B4 사전 결정)

B4 (Worksheet preview 컨텍스트 주입) 는 본 ADR 의 보강 결과를 **읽기만** 한다.
preview 는 보강을 트리거하지 않는다 — 사용자가 명시적으로 보강 라우트를 호출한 후
preview 에 반영되는 흐름.

- preview 가 호출 시점에 translation 이 없으면 빈 칸 / placeholder 로 렌더 (와이프가
  보강 해야 함을 알 수 있도록 UX).
- preview 자동 보강은 D1 의 시맨틱 분리 원칙 위반 → 도입 안 함.

---

## Consequences (결과)

### 긍정적 결과

1. **시맨틱 명료** — extract 는 "보이는 것만", 보강은 "LLM 이 채움". `created_by` /
   `selected_by` 메타로 결과 추적 가능.
2. **비용 분리** — 구문분석만 하는 사용자는 보강 비용 0. 학생용 자료 만드는
   사용자만 +2 LLM call.
3. **사용자 수정 보존** — `skip_if_user_edited` default 로 사용자 의도 보호. 덮어쓰기는
   `mode=replace` 명시 강제.
4. **재시도 / 에러 매핑 통일** — extract 와 동일 패턴 (ADR-0003 §D-3.5).
5. **LLM 호출 위치 단일** — `packages/llm/` 만 SDK 접근 (CLAUDE.md §8.3).
6. **schema 변경 0** — 본 ADR 은 라우트 + 어댑터 추가만, `shared/schemas/` 변경 없음.

### 부정적 결과 / 리스크

1. **mode 파라미터의 학습 곡선** — 3가지 mode 의미가 직관적이지 않을 수 있음. UI
   설계 시 명확한 라벨 (예: "기존 보존 / 덮어쓰기 / 추가") 필요. **완화**: default
   가 가장 안전한 `skip_if_user_edited` 라 잘못 호출해도 데이터 손실 X.
2. **`headword_normalized` 충돌 silent drift** — `append` 모드에서 같은 단어가 중복
   저장 가능. **완화**: 글로벌 `VocabularyMaster` ADR (Phase 2/3 진입 전) 에서 dedup
   정책 결정.
3. **재호출 비용** — 캐싱 없이 매번 LLM. PM-6 가정상 보강 빈도 낮으므로 현재는 OK.
   Phase 3 트리거 명시 (D9).
4. **PATCH 라우트 미정** — 사용자 수정 흐름이 본 ADR 범위 밖. B3 후속에서 결정.
   임시로 raw SQL UPDATE 또는 admin 도구로 가능 — 와이프 검수 시점에 우선순위 결정.
5. **LLM output schema 와 domain schema 의 분리 비용** — Pydantic 모델 2종 관리
   (`TranslationLLMOutput` vs `Translation`). **트레이드오프**: domain 모델에
   시스템 메타 (tenant_id 등) 가 강제 필드라 LLM 이 채울 수 없음 → 분리 불가피.
   변환 로직은 어댑터 함수 1개로 격리.

### 와이프 검수 (B5) 와 함께 묻을 항목 (v0.2 미세 조정)

domain-expert 검토에서 "도메인 단독 결정 보류, 와이프 학원 스타일에 따라 갈림" 으로
분류된 항목. B5 (와이프 v0.1 검수) 시점에 함께 묻고 v0.2 PR 로 반영.

1. **paragraph 보존 강도** — 한 paragraph 가 너무 길면 한국어로 줄바꿈 추가 OK / NOT
   OK?
2. **영어 병기 임계** — "잘 알려진 고유명사" 의 기준 (예: `Apple` 영어 그대로 OK?
   `Microsoft` 는?).
3. **idiom / phrasal verb 표기** — 의역만 vs 직역+의역 병기. 학원 스타일 어느 쪽?
4. **어휘 박스 count default** — 학년별 (고1: 5~8, 고3: 12~15) 으로 갈지 학년 무관
   8~15 로 갈지.
5. **`level_label` 추가 라벨** — 와이프가 평소 쓰는 표기 (`"수능 1등급"` /
   `"빈도 A"` 등) 가 있는가?
6. **해석 문체** — 평어 ("~한다") vs 경어 ("~합니다"). 현 example 은 평어로 통일.

추가 low priority 정리 항목 (v0.2 후속):
- `augment-translation-v0`: 인용문 처리 / 수동태 처리 가이드 추가.
- `augment-translation-v0` Example 2 (서사 → 논설 교체) — 평가원 22번 / 23번 패턴 더
  반영.
- `extract-text-v0` 의 `headword` vs `augment-vocabulary-v0` 의 `word` +
  `headword_normalized` 필드명 통일 (architect 영역 — `shared/schemas/vocabulary.py`
  정식 이름 일관성).

### 후속 작업 (별 PR)

- **PR B3 (backend-dev)**: `packages/llm/augment.py` 신규 — `augment_translation` /
  `augment_vocabulary` 함수 + `GRADE_LABELS_KO` 매핑 (D5-0). 출력 schema
  (`TranslationLLMOutput` / `VocabularyLLMOutput`) 정의. 보강 라우트 2개 추가
  (`apps/api/.../routers/passages.py`). 단위 + 통합 테스트.
- **PR B4 (frontend-dev + backend-dev)**: Worksheet preview 컨텍스트 주입. translation
  / vocabulary 박스 렌더 (`packages/template_renderer/`). 와이프 검수 직전 회귀 그물.
- **PR B5 — 와이프 v0.1 검수**: 학생용 템플릿 v0.1 OK 받기.
- **별 chore PR (architect)**: PATCH `/translations/{id}` / `/vocabulary/{id}` 라우트
  ADR + 구현. `created_by=USER` / `user_edited=True` 변경 시점 명확화.
- **별 ADR (Phase 2/3 진입 전)**: 글로벌 `VocabularyMaster` — Vocabulary dedup +
  `headword_normalized` UNIQUE 제약 / 마이그레이션 정책.

### CLAUDE.md / phase 문서 갱신

본 PR 에서는 안 함. B3 머지 시점에 CLAUDE.md §11 Open Questions 에 본 ADR 링크
추가하고, B5 (와이프 OK) 시점에 §2.2 "현재 위치" 를 Phase 2 baseline 충족으로 갱신.

---

## 대안 검토 요약

| 항목 | 채택 | 탈락 후보 |
|---|---|---|
| 보강 트리거 시점 | 명시적 라우트 (D1) | extract 자동 보강 (시맨틱 충돌, 비용 강제) |
| 재실행 정책 | `mode` 쿼리 파라미터 3종 (D1-a, D2, D3) | 항상 덮어쓰기 / 항상 skip / append-only |
| 사용자 수정 처리 | `skip_if_user_edited` default + replace 명시 (D4) | 무조건 덮어쓰기 / mode 없이 호출자 책임 |
| LLM 출력 검증 | 별 LLM output schema → 도메인 변환 (D5-a) | 도메인 모델 직접 LLM 출력 (시스템 메타 강제 필드 충돌) |
| 모델 | Sonnet 4.6 hint (D6) | Opus (비용 정당화 안 됨) / Haiku (품질 위험) |
| 캐싱 | Phase 3 트리거 (D9) | 즉시 도입 (Phase 2 비용 부담 작음) |

---

## 결정 기록

| 날짜 | 상태 | 결정자 | 비고 |
|---|---|---|---|
| 2026-05-07 | Proposed | architect | B2 — Phase 2 LLM 보강 파이프라인 설계. extract 와 분리, 사용자 수정 보존 우선, mode 파라미터 도입. 프롬프트 카탈로그 (`augment-translation-v0` / `augment-vocabulary-v0`) 동시 추가. |
| 2026-05-07 | Proposed (revised) | architect + domain-expert | domain-expert 검토 반영 — D5-0 `GRADE_LABELS_KO` 매핑 (라우트 책임), 프롬프트 v0.1 high 5건 (target_grade 매핑 / 부정·시제·가정법·대명사 referent / 어법·구문 선정 기준 / level_label 어법·구문 추가 / meaning_ko 품사별 어미 통일 / 하이픈·분사 lemma 정책 / example long-held 라벨). medium / low 항목 6건은 와이프 검수 (B5) 와 함께 v0.2 미세 조정. |
