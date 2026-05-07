# ADR 0015 — Phase 2-edit Sprint 정의 (사용자 편집 UI)

- **상태(Status)**: Proposed
- **작성일**: 2026-05-07
- **결정일**: TBD (PM 검토 대기)
- **작성자**: architect (Claude — PM 직접 작성 전용)
- **결정자**: PM (Dennis)
- **유형**: Phase 2 baseline 종료 후 신규 sprint 정의 — 학생 자료 워크플로우의
  사용자 편집 UI + 백엔드 PATCH 라우트 범위 / 우선순위 / DoD.
- **범위**: Phase 2 baseline (B5 와이프 v0.1 검수 OK) 이후 본격 시작될 *사용자
  편집 영역* sprint 의 작업 항목 정의. 본 ADR 자체는 코드 변경 0 — 후속 sprint
  PR 들의 가이드.
- **관련 문서**:
  - `CLAUDE.md` v0.9 §1.3 핵심 가치 명제 #3 — *"편집 가능한 출력: AI 가 만든
    결과는 항상 사용자가 검수/수정한 후 내보낸다 (자동 = 신뢰 부족 ≠ 완성)"*
  - `CLAUDE.md` v0.9 §2.1 Phase 2 DoD — "학생용 템플릿 v0.1 — 기본 레이아웃이
    와이프가 실사용 OK 하는 수준"
  - `docs/adr/0009-user-preferences.md` (사용자 프리셋 저장 인프라 — 본 sprint
    에서 재사용)
  - `docs/adr/0013-llm-augmentation-pipeline.md` §사용자 검수 흐름 — `created_by=USER`
    / `user_edited=True` 메타가 LLM 보강의 1차 입력. 본 sprint 가 그 메타를
    *입력하는* 라우트 + UI 를 구현.
  - `docs/adr/0014-annotation-html-renderer.md` (구문분석 annotation 편집 —
    Phase 1 에디터 이미 구현됨, 본 sprint 의 영향 영역 아님)
  - `docs/phase-2-wife-review-prep.md` §6 (B5 검수 결과 — 본 sprint 시작 트리거)
  - `shared/schemas/translation.py` — `TranslationCreatedBy` enum (LLM / USER)
  - `shared/schemas/vocabulary.py` — `VocabularySelectedBy` enum + `user_edited`
    플래그
  - `shared/schemas/passage.py` — `paragraphs: list[str]` 필드 (paragraph 분할
    입력)
  - `apps/api/src/worksheet_api/routers/passages.py` — passage extract / read,
    PATCH 미구현
  - `apps/api/src/worksheet_api/routers/worksheets.py` — A1/A2 (CRUD) + B3
    (LLM 보강) + B4 (preview/PDF) 머지됨, 콘텐츠 PATCH 미구현
  - `apps/web/src/pages/EditorPoc.tsx` — 구문분석 에디터 (Phase 1 baseline)

---

## Context (배경)

### 1. 현재 미구현 영역 — 와이프가 *코드를 통해서만* 닿을 수 있는 흐름

Phase 2 baseline (PR #48-57) 머지 시점의 사용자 편집 UI 매트릭스:

| 영역 | 백엔드 | 프론트엔드 | 비고 |
|---|---|---|---|
| Passage extract (지문 등록) | ✓ POST /passages/extract | **✗** | 현재 curl 로만 호출 가능 |
| Passage 본문 직접 수정 (오타 fix) | **✗** PATCH 라우트 없음 | **✗** | schema `body_text` 는 immutable |
| Passage paragraph 분할/합치기 (줄바꿈) | **✗** PATCH 라우트 없음 | **✗** | schema `paragraphs: list[str]` 존재, 편집 통로 없음 |
| Translation 사용자 편집 | **△** PATCH 라우트 없음 (`created_by=USER` 갱신 통로 부재) | **✗** | schema `TranslationCreatedBy.USER` 정의됨 (ADR-0013 핵심 입력) |
| Vocabulary 행 편집 (단어/뜻/level) | **△** PATCH 라우트 없음 (`user_edited=True` 갱신 통로 부재) | **✗** | schema `user_edited` 필드 정의됨 (ADR-0013 핵심 입력) |
| Vocabulary 행 추가/삭제 | **✗** | **✗** | 현재 `selected_by` 분기만 있고 사용자 추가 통로 없음 |
| Worksheet 메타 (제목/branding/orientation) | ✓ A2-a PATCH /worksheets/{id} | **✗** | 백엔드 OK, UI 없음 |
| Worksheet items 추가/삭제/순서 | ✓ A2-b POST/PATCH/DELETE /worksheets/{id}/items | **✗** | 백엔드 OK, UI 없음 |
| Worksheet preview / PDF 다운로드 | ✓ B4 GET preview / POST export.pdf | **✗** | 백엔드 OK, UI 없음 |
| 구문분석 annotation | ✓ POST /passages/{id}/annotations | **✓** EditorPoc | Phase 1 baseline (영향 영역 아님) |

**현재 와이프 입장**: 학생 자료 1건 만들려면 (1) curl 로 extract → (2) curl 로
translation 보강 → (3) curl 로 vocabulary 보강 → (4) Phase 1 에디터로
annotation → (5) curl 로 worksheet 생성 → (6) curl 로 export.pdf. 1/2/3/5/6 은
*개발자만* 할 수 있는 흐름.

### 2. 핵심 가치 명제 #3 (CLAUDE.md §1.3) 와의 갭

> **편집 가능한 출력**: AI 가 만든 결과는 항상 사용자가 검수/수정한 후 내보낸다
> (자동 = 신뢰 부족 ≠ 완성)

ADR-0013 이 LLM 보강 + 사용자 수정 *충돌 처리* 까지 설계 완료 (`created_by=USER` /
`user_edited=True` 가 default `skip_if_user_edited` 모드의 1차 입력). 그러나
**그 메타를 입력하는 통로 자체가 없음** — Phase 2 baseline 까지는 LLM 자동 출력
그대로 인쇄. CLAUDE.md §1.3 정합성 위해 본 sprint 가 차단점.

### 3. B5 검수 결과 트리거

`docs/phase-2-wife-review-prep.md` §6.4 — PDF 등급 부여 결과:
- A 등급 → Phase 2 baseline 종료 → **본 sprint 시작**
- B/C 등급 → v0.2 미세 조정 PR (0~4건) → 그 후 **본 sprint 시작**
- D 등급 → ADR-0008 채택안 한계 → 별 phase 신규 (본 sprint 보류)

본 ADR 은 A/B/C 등급 가정. D 등급 시 별 ADR 로 재시작.

---

## Decision (결정)

### D1. Sprint 명칭 / 범위

**Phase 2-edit** — Phase 2 baseline 의 *읽기 가능한* 학생 자료 출력에 *쓰기
편집 통로* 를 더한다. Phase 3 (변형문제) 진입 전 종료.

**포함**:
- 학생 자료 워크플로우 1~6 단계 전부 와이프가 *UI 만으로* 완료 가능
- LLM 보강 결과 (translation / vocabulary) 인라인 편집 + `created_by=USER` /
  `user_edited=True` 자동 갱신
- Passage 본문 paragraph 분할/합치기 + 단어 단위 오타 수정
- Worksheet 메타 / items / branding 전반 UI

**제외 (별 sprint)**:
- 변형문제 (Phase 3) 편집 UI
- 구문분석 annotation 외 *구문 분석 자체* 의 자동 추론 / 검수 도구
- VocabularyMaster 글로벌 dedup (별 ADR — Phase 2/3 진입 전)
- 다중 템플릿 / 다중 프리셋 UI (CLAUDE.md §2.1 점진 개선 영역)
- HWPX 출력 UI (Phase 1 baseline 종료 후 별 sprint)

### D2. 작업 항목 — 우선순위 / Stage

CLAUDE.md §3.1 canonical schema 중심 + ADR-0013 사용자 수정 메타 정합 + 와이프
실사용 흐름 자연 순서로 3 Stage 구성:

#### Stage E1 — 백엔드 PATCH 라우트 (사용자 수정 메타 입력 통로)

**목표**: 모든 LLM 산출 / passage 콘텐츠를 사용자 수정 메타와 함께 수정 가능
하게.

| # | 라우트 | 동작 | 메타 갱신 |
|---|---|---|---|
| E1-a | PATCH `/passages/{id}/translation` | text 수정 | `created_by=USER`, `updated_at=now()` |
| E1-b | PATCH `/passages/{id}/vocabulary/{vid}` | word/pos/meaning_ko/level_label 수정 | `user_edited=True`, `updated_at=now()` |
| E1-c | POST `/passages/{id}/vocabulary/manual` | 사용자 직접 추가 | `selected_by=USER`, `user_edited=False` |
| E1-d | DELETE `/passages/{id}/vocabulary/{vid}` | 행 삭제 | (선택적: `selected_by=USER` 항목만 허용 또는 모두 허용 — D3 결정 항목) |
| E1-e | PATCH `/passages/{id}` | body_text + paragraphs 동시 수정 | (Passage 자체에는 user_edited 메타 없음 — D4 결정 항목) |

**DoD**:
- 5개 라우트 모두 멀티테넌트 가드 (W-2 패턴 — `tenant_id` 필터 + cross-tenant
  404)
- ADR-0013 의 `skip_if_user_edited` 모드와 정합 — 사용자 수정 후 LLM 보강 호출
  시 보존 검증 단위 테스트
- Pydantic input DTO (`extra="forbid"`) + 단위 테스트 100% 통과

**예상 PR 분량**: 5 PR × 200~300 LOC ≈ 1,200 LOC (1.5주)

#### Stage E2 — 학생 자료 편집 UI (Worksheet 페이지)

**목표**: 와이프가 학생 자료 1건을 UI 만으로 완성.

라우트 추가:
- `/worksheets` — Worksheet 목록 (GET /worksheets 백엔드 활용)
- `/worksheets/new` — 신규 worksheet 생성 (extract 입력 + items 추가)
- `/worksheets/:id` — 편집 페이지 (메타 + items + preview)

핵심 컴포넌트:
- `<PassageExtractor>` — 텍스트 입력 + image/pdf 업로드 + extract 호출
- `<TranslationEditor>` — Tiptap (또는 textarea) 인라인 편집 + 저장 시
  PATCH translation
- `<VocabularyTable>` — 표 형태 인라인 편집 (word / pos / meaning_ko /
  level_label / 행 추가/삭제 버튼)
- `<WorksheetMetaForm>` — 제목/subtitle/orientation/instruction/branding 폼
- `<WorksheetItemList>` — items 추가/순서 변경/삭제 + include_translation /
  include_vocabulary / include_syntax_annotations 토글
- `<WorksheetPreviewFrame>` — `<iframe src="/worksheets/:id/preview">` +
  PDF 다운로드 버튼

**DoD**:
- 와이프가 §1.1 의 1~7 단계 (현재 curl) 를 *UI 만으로* 완료 가능
- TranslationEditor / VocabularyTable 수정 시 자동으로 `user_edited=True` /
  `created_by=USER` 갱신 (Stage E1 라우트 호출)
- 저장 / 변경 사항 indicator (dirty state) 명확
- ADR-0009 user_preferences 재사용 — branding 프리셋 / 색상 chip

**예상 PR 분량**: 7~9 PR × 250~400 LOC ≈ 2,500 LOC (2주)

#### Stage E3 — Passage 편집 UI (paragraph 분할 / 본문 수정)

**목표**: 본문 텍스트 자체의 사용자 편집 (오타 fix, paragraph 줄바꿈 변경).

핵심 컴포넌트:
- `<PassageBodyEditor>` — Tiptap (구문분석 에디터와 *별도* 모드 — annotation
  편집 비활성화) 으로 본문 + paragraph 분할 편집
  - paragraph 분할: Enter = 새 paragraph, Backspace at start = 이전과 합치기
  - body_text 와 paragraphs 동시 갱신 (Stage E1-e PATCH 호출)
  - **annotation 충돌 처리**: body_text 변경 시 기존 annotation 의 character
    offset 이 깨짐 — 단순 정책: PATCH passage 시 *해당 passage 의 annotation
    전부 삭제 + 사용자 알림*. 정밀 보존은 별 ADR.

**DoD**:
- 와이프가 본문 오타 수정 + paragraph 줄바꿈 조정 가능
- annotation 삭제 알림 동의 후 저장 (다이얼로그)
- 단위 테스트 + Playwright E2E 1건 (본문 수정 → annotation 삭제 → 저장 → 재조회)

**예상 PR 분량**: 3~4 PR × 300~500 LOC ≈ 1,500 LOC (1주)

### D3. 결정 항목 — Vocabulary DELETE 정책

E1-d (`DELETE /passages/{id}/vocabulary/{vid}`) 에서:
- (a) `selected_by=USER` 항목만 사용자 삭제 허용. LLM 산출은 *숨김 플래그* 로
  논리 삭제.
- (b) 모든 항목 사용자 삭제 허용. ADR-0013 의 `replace` 모드가 LLM 산출 재생성
  시 다시 채워줌.

**권장**: (b). ADR-0013 의 `skip_if_user_edited` 모드가 사용자 수정 보존이
default 라 사용자 의도 명시적 — 삭제도 사용자 의도. 추가 메타 (숨김 플래그)
없는 단순한 모델. PM 결정 영역.

### D4. 결정 항목 — Passage user_edited 메타

Passage 자체 (body_text / paragraphs) 에는 현재 `user_edited` 메타 없음.
Translation/Vocabulary 와 달리 Passage 는 *원본 자료* 라 LLM 재실행 트리거가
없어서 메타 불필요했음 (ADR-0001 schema 철학). E3 도입 시:
- (a) 새 메타 필드 추가 (`Passage.body_user_edited`) + Alembic 마이그레이션
- (b) 메타 없이 가고 — extract 재실행이 발생할 수 없는 이상 (UI 가 PATCH 만
  허용) 충돌 위험 없음

**권장**: (b). 단순. Phase 3 변형문제 진입 시 *원본 보존* 이 필요해지면 그때
별 ADR.

### D5. 결정 항목 — TranslationEditor / PassageBodyEditor 의 Tiptap 재사용 vs textarea

Phase 1 EditorPoc 의 Tiptap 셋업을 재사용할지 vs 단순 textarea/contenteditable.

| 옵션 | 장점 | 단점 |
|---|---|---|
| (a) Tiptap 재사용 | 향후 placeholder / undo / formatting 확장 자유, EditorPoc 패턴 일관 | annotation 마크가 본 에디터에서 비활성화 필요 — config 분기 |
| (b) textarea / contenteditable | 단순, 빠른 개발 | 향후 풍부 편집 (예: vocabulary 인라인 추출 — *본문에서 단어 선택 → 어휘 추가*) 진입 시 재작업 |

**권장**: (a) Tiptap. CLAUDE.md §3.6 — 검증된 라이브러리 재사용. EditorPoc 의
Tiptap config 를 Phase 2-edit 모드용으로 fork 하지 않고 *prop 기반 분기*
(annotation 마크 enable 플래그) 로 가는 것이 NRTW 정합.

### D6. 결정 항목 — Vocabulary 추가/삭제 UX 패턴

(a) 표 마지막 행 *항상 빈 행* — 입력 시 자동 추가 행 생성 (Excel 패턴)
(b) "+" 버튼 클릭 → 빈 행 명시 추가
(c) 본문에서 단어 드래그 선택 → "어휘 추가" 컨텍스트 메뉴 (Phase 3 / 별 sprint)

**권장**: (b) "+" 버튼. (a) 는 의도하지 않은 빈 행 저장 위험. (c) 는
본격적인 표면 형태로 본 sprint 외.

### D7. Sprint 시작 트리거 / 종료 조건

**시작**: B5 와이프 검수 결과 = A/B/C 등급 + v0.2 미세 조정 PR 머지 완료.

**종료 (Phase 2-edit DoD)**:
1. Stage E1 5개 라우트 머지 + 단위 테스트 100% green.
2. Stage E2 학생 자료 편집 UI 머지 — 와이프가 §1.1 1~7 단계를 UI 만으로 완료
   가능 + 와이프 v0.2 검수 OK (등급 A/B/C).
3. Stage E3 Passage 편집 UI 머지 — annotation 삭제 알림 + Playwright E2E
   green.
4. Phase 1 baseline (구문분석 단독 HWPX 출력) 와 정합 — 동일 passage 가
   학생 자료 / 구문분석 자료 양쪽에서 자연 사용 가능.

**Phase 3 진입 차단 ADR**:
- VocabularyMaster (글로벌 dedup) — Phase 2-edit 종료 후 Phase 3 진입 전.
- Question / VariantQuestion 단일 vs 별 테이블 — Phase 3 진입 전.

본 sprint 종료 = Phase 3 (변형문제) 진입 신호.

---

## Open Questions

- [ ] D3: Vocabulary DELETE 정책 (a) vs (b)
- [ ] D4: Passage user_edited 메타 (a) vs (b)
- [ ] D5: TranslationEditor Tiptap vs textarea — Tiptap 재사용 시 EditorPoc
      config 분기 정책 구체화
- [ ] D6: Vocabulary 추가 UX (a) vs (b)
- [ ] Stage E1-e (PATCH passage) 시 annotation 강제 삭제 vs 사용자 알림 후
      삭제 vs 정밀 offset 재계산 — 단순 강제 삭제로 가되 향후 정밀 보존 ADR
      후속

---

## 후속

본 ADR 결정 후:
1. PM 검토 — D3/D4/D5/D6 결정.
2. architect — `shared/schemas/` 변경 필요 시 (D4 — Passage 메타 추가) v0.2
   PR + Alembic 마이그레이션.
3. backend-dev — Stage E1 5개 라우트 PR 분리 머지 (E1-a → E1-b → E1-c →
   E1-d → E1-e 순).
4. frontend-dev — Stage E2 / E3 UI PR (`<TranslationEditor>` →
   `<VocabularyTable>` → `<WorksheetMetaForm>` → `<WorksheetItemList>` →
   `<WorksheetPreviewFrame>` → `<PassageBodyEditor>` 순).
5. domain-expert — 와이프 v0.2 검수 시나리오 작성 (`docs/phase-2-edit-wife-review-prep.md`).
6. qa-validator — Stage E3 의 annotation 충돌 케이스 회귀 테스트 픽스처.
7. code-reviewer — 각 PR 의 ADR-0013 user_edited 플래그 정합 / 멀티테넌트
   가드 / NRTW 검토.

CLAUDE.md v0.10 — Phase 2-edit sprint 진행 중 표기 + §11 Open Questions 의
*현재 baseline* 갱신.
