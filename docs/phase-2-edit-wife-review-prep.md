---
name: Phase 2-edit 와이프 v0.2 통합 검수 가이드
description: ADR-0015 Phase 2-edit sprint 종료 시점에서 와이프가 학생 자료 1건을 UI 만으로 완성하는 검수 시나리오. PR #70~74 머지 후 진행.
type: project
---

# Phase 2-edit 와이프 v0.2 통합 검수 가이드

- **작성일**: 2026-05-09
- **작성자**: PM (Dennis)
- **검수자**: 와이프 (영어 강사)
- **관련 PR (open, 머지 대기)**: #70 / #71 / #72 / #73 / #74
- **관련 ADR**: 0015 (Phase 2-edit sprint, Accepted)
- **상태**: 검수 시작 대기 — PR 5건 머지 후 본 문서 §3 ~ §5 채움

---

## 0. 본 문서의 목적

ADR-0015 Phase 2-edit sprint 의 코드 작업 (Stage E1 백엔드 PATCH 라우트 / Stage
E2 학생 자료 편집 UI / Stage E3 Passage 편집 UI) 이 모두 종료된 시점에서, **와이프
v0.2 통합 검수 시작 직전** 의 정리.

**v0.1 검수 (B5, `docs/phase-2-wife-review-prep.md`) 와의 차이**:

| 항목 | v0.1 검수 (B5) | v0.2 통합 검수 |
| --- | --- | --- |
| 워크플로우 | curl 7단계 (PM 이 대신 실행) | UI 만으로 완성 (와이프 단독) |
| 검수 영역 | PDF 산출물 퀄리티 | 편집 UI + PDF 산출물 + 본문 편집 |
| 종료 조건 | PDF 등급 ≥ C | 와이프가 학생 자료 1건 UI 만으로 완성 + PDF 등급 ≥ C |
| 합격 시 다음 | Phase 2-edit sprint 시작 | Phase 3 (변형문제) 진입 신호 |

본 검수가 **CLAUDE.md §1.3 핵심 가치 명제 #3 ("편집 가능한 출력") 의 종료
판정** 이다.

---

## 1. 검수 대상

### 1.1 학생 배포용 자료 1건 — UI 만으로 완성

검수자 (와이프) 가 다음 흐름으로 1건 생성 후 결과 검토:

```
1. /worksheets/new
   - 제목 / subtitle / branding / theme / instruction 입력
   - "신규 worksheet 생성" 클릭
   → /worksheets/{id} 자동 이동

2. /worksheets/{id} (편집 페이지)
   - "메타 편집" 모달 → 제목/subtitle/branding/theme/instruction 수정 (E2-3d, PR #72)
   - "+ 문항 추가" → AddItemModal → passage 검색/선택 (E2-3e, PR #71)
   - 추가된 item 의 ↑↓ 로 순서 변경, × 로 삭제

3. 각 문항 카드 안에서:
   3-a. 본문 편집 (Stage E3, PR #74) — paragraph 분할 / 오타 수정
   3-b. Translation 편집 — 인라인 textarea
   3-c. Vocabulary 행 편집 / 추가 / 삭제

4. "미리보기" → 새 탭 HTML preview (브라우저 자동 새로고침)

5. "PDF 다운로드" → playful 템플릿 PDF
```

**curl / SQL 직접 실행은 불필요**. PR #70~74 머지 후 와이프가 **UI 만으로** 1~5
완료 가능해야 합격.

### 1.2 비교 baseline

- v0.1 (B5) PDF 등급 = `A` (퀄리티 자체).
- 본 v0.2 검수는 **편집 워크플로우가 PDF 퀄리티 A 를 유지하는지** 추가 검증.
- 편집 후 다시 PDF 추출했을 때 v0.1 와 동등 또는 이상 퀄리티가 나와야 함.

---

## 2. 평가 기준 (와이프 작성)

### 2.1 합격 등급 정의 (영역별)

영역 3개 — **편집 UI** / **본문 편집** / **PDF 산출물** — 각각 등급.

| 등급  | 의미                                                            |
| ----- | --------------------------------------------------------------- |
| **A** | 그대로 실제 수업/작업 흐름에 사용 가능                          |
| **B** | 약간 손이 가지만 사용 가능 (예: 일부 항목은 여전히 curl)        |
| **C** | 사용은 가능하지만 매번 답답함 / 한두 군데 큰 결함               |
| **D** | 사용 불가. 기본 워크플로우가 막힘 또는 결과물이 망가짐          |

**Phase 2-edit sprint 종료 합격선**:

- [ ] 모두 A 만 합격
- [ ] B 까지 합격
- [ ] C 까지 합격

(와이프가 검수 시작 전 체크. 기본 권장: B 까지 합격 — 편집 UI 는 첫 baseline 이라
A 강요는 비현실적.)

### 2.2 영역별 평가 항목

#### 영역 1 — 편집 UI (E2-3 시리즈, PR #71/#72)

| 항목 | 확인 포인트 |
| --- | --- |
| 메타 편집 (PR #72) | 모달 입력 → 저장 → 페이지 새로고침 없이 반영 |
| 문항 추가 (PR #71) | passage 검색 결과 정확 + 선택 후 카드 추가 |
| 문항 순서 변경 | ↑↓ 클릭 → 즉시 반영 + 미리보기 동기화 |
| 문항 삭제 | × 클릭 → 확인 → 카드 제거 |
| Translation 인라인 편집 | textarea 수정 → 저장 → "user 편집" 표시 |
| Vocabulary 행 편집 | 단어/품사/의미 수정 → 저장 |
| Vocabulary 추가 ("+ 버튼", D6 b) | 빈 행 추가 → 입력 → 저장 |
| Vocabulary 삭제 (D3 모든 항목) | × 클릭 → 행 제거 (LLM/USER 구분 없음) |

#### 영역 2 — 본문 편집 (Stage E3, PR #73/#74)

| 항목 | 확인 포인트 |
| --- | --- |
| paragraph 분할 (Enter) | textarea 줄바꿈 → 저장 → paragraph 분리 반영 |
| 오타 수정 | 본문 수정 → 저장 → annotation 충돌 처리 |
| 에디터 ↔ PDF wrap 정합 (PR #73) | 에디터 줄바꿈 위치 = PDF 줄바꿈 위치 (Pretendard webfont, 626px) |
| annotation 충돌 처리 | 본문 길이 변경 시 annotation offset 시프트 X |

#### 영역 3 — PDF 산출물

| 항목 | 확인 포인트 |
| --- | --- |
| 편집 후 PDF 퀄리티 | v0.1 (B5) 의 A 등급 유지? |
| annotation 시각 (PR #70) | offset 시프트 / close 중복 / bracket borderline 모두 fix 정합 |
| 본문 12pt / line-height 2.78 / 박스 한계선 | v0.2-α 픽셀 값 유지 (`feedback_pdf_annotation_visual.md`) |
| 어휘 박스 5컬럼 표 | v0.2-γ 빈 컬럼 (synonyms/antonyms/example_sentences) 시각 OK |

---

## 3. 검수 시작 시 PM 가이드

검수 시작 신호 (와이프 OK) 가 오면 PM 이 다음 순서로 진행:

### 3.1 사전 셋업

1. **PR #70~74 머지 확인** — 머지 순서: #70 → #71 → main → #72 → main → #73
   → main → #74. base chain 자동 main 으로 갱신됨.
2. **로컬 환경**:
   ```bash
   git checkout main && git pull
   uv sync --all-packages
   pnpm install
   docker compose up -d db
   cd apps/api && uv run alembic upgrade head
   ```
3. **fixture worksheet 복원 또는 신규**:
   - 기존 fixture (`239745e7-e1b1-465c-b614-200e1a005b0f`) 가 살아있고 PR #74 의
     E2E 가 Q1 body 에 'X' 만 추가했으면 복원으로 충분.
   - 새 fixture 권장 — 와이프가 *직접* /worksheets/new 부터 시작해야 UI 검수
     의의가 있음.
4. **서버**:
   - API 8000 — `cd apps/api && uv run uvicorn worksheet_api.main:app --reload`
   - Vite 5173 — `cd apps/web && pnpm dev`

### 3.2 검수 진행

1. 와이프 옆에서 §1.1 의 1~5 단계 따라가게 함 (PM 은 옆에서 관찰, 손대지 말기).
2. 막히는 지점 = UX 결함 신호. 어디서 멈췄는지 본 문서 §4 에 기록.
3. 각 영역 (UI / 본문 편집 / PDF) 종료 시 §2.1 등급 채움.
4. NG 항목 → §5 에 즉시 fix vs. 와이프 의견 필요 분류.

### 3.3 자율 진행 차단

- 와이프 시각 검수 필요 부분 (UI 동작 / PDF 미세 조정) 은 OK 신호 받기 전 commit/PR 금지.
- 명백한 결함 (서버 에러 / 페이지 못 띄움) 은 즉시 fix.
- `feedback_review_gate_priority.md` 메모리 정책 준수.

---

## 4. 변경 비용 매트릭스 (v0.2 통합 검수 결과 기반 후속 PR 추정)

| 검수 결과 | 변경 범위 | 추정 PR 수 |
| --- | --- | --- |
| 영역 3개 모두 A, 결함 없음 | v0.2 PR 없음 → Phase 3 진입 신호 | 0 |
| A~B, 일부 UX 결함 (예: 모달 닫힘 / Vocabulary 삭제 confirm) | UI 미세 조정 PR 1~2 | 1~2 |
| C 등급, 본문 편집 wrap 정합 깨짐 또는 annotation 시프트 잔존 | renderer/serializer 추가 fix + 회귀 spec | 2~3 |
| D 등급 (워크플로우 막힘) | Stage 별 회귀 — ADR-0015 종료 조건 미달 | 별 sprint |

---

## 5. 검수 기록 (대기)

### 5.1 검수 fixture (작성 예정)

- 영어 지문: 와이프가 평소 사용하는 학원 자료 1건 (Phase 2 v0.1 에서는 PM 임의 zero-waste,
  본 라운드는 와이프 자료 권장).
- worksheet 메타: 와이프 입력 그대로.
- annotation: Stage E2 검수에 한정해서 0건 → Stage E3 검수에서 본문 편집 후 5건 추가.
- include_translation = true / include_vocabulary = true.

### 5.2 와이프 응답 (대기)

검수 시작 후 §2.1 등급 + §2.2 항목별 OK/NG 채움.

### 5.3 후속 영역 (현 시점 알려진 것)

- **v0.2-γ (Vocabulary schema 확장)** — synonyms/antonyms/example_sentences 컬럼.
  `playful.html` 표 5컬럼 시각 준비 완료, schema/마이그레이션/프롬프트 갱신 대기.
  본 검수와 별개 영역 — 별 ADR.
- **Tiptap 전환 (ADR-0015 D5 a)** — PassageBodyEditor textarea → Tiptap (annotation
  비활성). 후속 PR.
- **Phase 3 진입 전 별 ADR**:
  - VocabularyMaster (글로벌 dedup).
  - Question / VariantQuestion 단일 vs 별 테이블.

---

## 6. Phase 3 진입 트리거

본 검수가 **A 또는 B 등급으로 합격선 통과** 시:

1. ADR-0015 Phase 2-edit sprint **종료 선언** (PR #74 의 CLAUDE.md v0.11 갱신
   머지로 자연 적용).
2. CLAUDE.md §2.2 "현재 위치" → **Phase 3 (변형문제) 진입 신호** 로 갱신.
3. Phase 3 진입 전 별 ADR 2건 작성 — VocabularyMaster / Question vs VariantQuestion.
4. domain-expert agent 호출 → exam-generator 24 type enum 흡수 + 변형 sub-form 정의.

D 등급 시 본 sprint 보류 → Stage 별 회귀 sprint 신규.

---

## 변경 이력

| 버전 | 날짜 | 변경 |
| --- | --- | --- |
| v0.1 | 2026-05-09 | 초안 — PR #70~74 머지 대기 시점에서 검수 가이드 골격 작성. §1~6 가이드 단계, §5 검수 기록은 검수 시작 후 채움. |
