# PM 결정 기록 — Sprint 0 작업 #5 차단 해제

- **결정자**: Dennis (PM)
- **결정일**: 2026-05-02
- **목적**: `docs/schema-coverage-audit.md`가 던진 9개 Open Question 중 작업 #5 진입 전 결정 필요한 3개에 대한 답.
- **참조**: `docs/schema-coverage-audit.md` §4, `docs/audit-review-domain.md`, `CLAUDE.md` v0.3 §6.2

이 문서는 ADR이 아니라 **PM 결정 기록**이다. architect가 작업 #5에서 직접 입력으로
사용한다. 작업 #5가 끝나면 본 결정들이 정식 ADR(`0002-content-model-v0_1.md` 등)에
흡수되며 본 문서는 그때 점진적으로 obsolete 처리한다.

---

## D-1. Passage 메타 v0.1 필수 필드 (audit §4-1)

**질문**: Passage(영어 지문) 한 건당 함께 저장할 메타 필드를 v0.1에 어디까지 박을지.

**결정**: **topic / source / 학년 정보 모두 v0.1 필수**. CEFR은 제외.

### v0.1 메타 필드 명세

| 필드 | 타입 | 필수/선택 | 설명 |
|---|---|---|---|
| `topic_tags` | `list[str]` | 필수 (빈 list 허용) | 자유 문자열 키워드. domain-expert의 후속 카탈로그에서 enum 정규화 검토. |
| `source` | `SourceMeta` (객체) | 필수 | 자료 출처 — 아래 SourceMeta 명세 |
| `target_grade` | `enum` | 필수 | 학년 (`middle_1`, `middle_2`, `middle_3`, `high_1`, `high_2`, `high_3`, `suneung`, `other`) |
| `body_text` | `str` | 필수 | 본문 (마커 분리 정책은 §4-6 ADR에서 결정) |
| `paragraphs` | `list[str]` | 필수 | 단락 분할 |
| `word_count` | `int` | 필수 (시스템 자동) | body_text 단어 수 |

### SourceMeta 객체 명세

```python
class SourceMeta(BaseModel):
    provider: Literal[
        "aingka",         # 아잉카 (유료 멤버십)
        "evaluator",      # 평가원 (수능/모평)
        "ebsi",           # EBSi
        "school_internal",# 학교 내신 기출
        "user_input",     # 사용자 직접 입력 (출처 미상 또는 자체 작성)
        "other",
    ]
    # provider == "school_internal" 일 때 필수
    school_name: Optional[str]   # 예: "강남고등학교"
    # 출처별 부가 식별자 (자유 문자열, optional)
    exam_year: Optional[int]      # 예: 2025
    exam_round: Optional[str]     # 예: "6월 모의평가", "1학기 중간고사"
    original_question_number: Optional[int]   # 원자료에서의 문항 번호
    note: Optional[str]           # 자유 텍스트
```

**검증 로직**:
- `provider == "school_internal"`이면 `school_name` NOT NULL.
- 다른 provider에서 `school_name`은 무시 또는 메타용으로 허용.

### 제외된 것 (PM 명시 결정)

- **CEFR 레벨 (`cefr_level`)**: 제외. PM 답: "공식적으로 나눠진 난이도 등급은 없다."
- **subject_domain** (과학/인문/사회 등): v0.1 제외. v0.2 검토.
- **수능 빈도 등급**: domain-expert가 권고한 한국 시장 실용 메타이지만 v0.1 미포함.
  v0.2 검토.

### domain-expert 권고와의 관계

domain-expert (`docs/audit-review-domain.md`)는 Passage에 `target_grade` 추가를
권고했고 (Gap I 보강), CEFR보다 "수능 빈도 등급"이 한국 시장 실용이라고 평가했다.
PM은 `target_grade` 채택, CEFR 제외, 수능 빈도 등급은 v0.2로 미룸.

---

## D-2. Translation 카디널리티 (audit §4-2)

**질문**: Passage 1건당 한국어 해석을 1개만 둘지, 여러 버전 둘지.

**결정**: **1:1**. 1 Passage = 1 Translation. 다중 버전 보관 불필요.

### 모델 명세

```python
class Translation(BaseModel):
    id: UUID
    passage_id: UUID    # FK, UNIQUE 제약 (1:1)
    tenant_id: UUID
    language: Literal["ko"]   # v0.1은 ko 고정
    text: str           # 전체 해석
    created_by: Literal["llm", "user"]
    created_at: datetime
    updated_at: datetime
```

- DB 레벨에서 `passage_id`에 UNIQUE 제약을 박아 1:1 강제.
- 부분 해석(`SentenceTranslation`)은 v0.1 제외. Phase 2에서 별 모델로 추가.
- 사용자가 LLM 결과를 직접 수정하면 `text`를 in-place 업데이트하고 `created_by="user"`로
  변경 + `updated_at` 갱신. **이전 버전 보존 없음** (이건 PM 결정).

### domain-expert 권고와의 관계

domain-expert는 1:N로 갔다가 UI에서 1개만 보여주는 패턴(retrofit 비용 회피)을
권고했지만, PM은 **현재 사용 패턴이 1:1로 충분**하다고 판단. 1:N로 갔다가 unused
복잡도가 누적되는 비용 > 향후 1:1→1:N 마이그레이션 비용. 필요해지면 그때 마이그레이션.

---

## D-3. Workspace 계층 (audit §4-7)

**질문**: Phase 0에서 Tenant → Workspace 계층을 박을지, Tenant만으로 충분한지.

**결정**: **박는다**. Tenant → (1:N) Workspace.

### 모델 명세

```python
class Workspace(BaseModel):
    id: UUID
    tenant_id: UUID    # FK, NOT NULL
    name: str          # 사용자 자유 명명, 예: "고2 내신반", "수능 대비반"
    created_at: datetime
    updated_at: datetime
```

- 모든 도메인 테이블(`Passage`, `Question`, `Worksheet` 등)은 `workspace_id` FK NOT NULL.
- v0.1 운영 stub: Tenant 생성 시 default workspace 1개(`name="default"`) 자동 생성.
  사용자가 첫 자료 입력 시 이 workspace에 들어감.
- 사용자는 추후 직접 추가 workspace 생성 가능 (UI는 Phase 4).

### PM 추가 코멘트

> "와이프가 맡게될 학교/학년도 다양할거라 나누는게 좋아."

→ Workspace의 사용자 멘탈 모델은 **"학교 × 학년 × 시즌"**의 조합 단위.
운영적으로 강사가 자료를 분리해서 관리할 단위. v0.1에서는 단순히 `name` 자유
문자열이지만, 후속에 `school_name`, `grade`, `season` 등 구조화된 필드 추가 검토
가능 (v0.2+).

---

## 영향받는 다른 결정 / 후속 작업

### audit이 던진 나머지 Open Question — 본 결정에 의해 영향받는 부분

- **§4-3 (Vocabulary 글로벌 마스터)**: 작업 #5 진행 중 결정. PM 권고: domain-expert가
  제안한 `headword_normalized` 자리만 박아두기 채택 (retrofit 비용 회피).
- **§4-5 (Question / VariantQuestion 분리)**: Phase 3 진입 전 ADR로 미룸. PM은 §6.2
  정정에서 "변형 유형은 기존 24개의 sub-form" 입장 명확화. 단일 테이블 + discriminator
  방향이 자연스러움.
- **§4-8 (choices 평탄 vs 매트릭스)**: 작업 #5 진행 중 결정. domain-expert는 "Gap A/B는
  같은 유형의 두 측면" 입장. architect 판단 필요.

### domain-expert에게 재요청 사항

`docs/variant-type-catalog.md` 재작성 필요. 사유:

1. 기존 catalog는 "5개 변형 유형"을 별 카테고리로 정의했지만, CLAUDE.md v0.3 §6.2에서
   **변형 유형은 별 카테고리가 아니라 기존 24개 유형의 sub-form**으로 정정됨.
2. 새 catalog 구조 권고:
   - **§1: exam-generator 24개 유형 인벤토리** (각 유형의 출제 의도, 표면 형태,
     원본 → 변형 규칙, 검증 기준)
   - **§2: 자료 sweep으로 발견되는 sub-form** (Gap A 본문 내장 어휘, Gap B 다중 매트릭스
     등) — 어느 유형의 sub-form인지 매핑
   - **§3: 변형 생성 (Phase 3)에서의 variant_kind 후보** — 같은 type 안에서의 파생
     유형 (예: 어휘 type → 어휘 교체 / 어휘 인라인화)
3. 기존 5개 우선순위 추정은 폐기.

### 영상 레퍼런스 분석 (신규 작업)

`/Users/william/Downloads/ScreenRecording_04-24-2026 15-11-52_1.MP4` 프레임 분석 →
`docs/reference-program-analysis.md`. 작업 #5와 병렬, Phase 1 진입 전 완료 권고.

---

## 작업 #5 진입 조건

위 D-1, D-2, D-3 + CLAUDE.md v0.3 §6.2가 architect 작업 #5의 입력이다. architect는
`shared/schemas/` v0.1 PR 작성 시 본 문서를 ADR-0002 작성에 흡수 인용한다.

**작업 #5 차단 해제**.
