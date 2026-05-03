# PR #16 (P1-2a-draft) 검수 가이드

- **PR**: https://github.com/williampapa-rich/english-worksheet-tool/pull/16
- **브랜치**: `frontend-dev/p1-2a-draft-editor`
- **작성**: 2026-05-03
- **목적**: PM 이 외부 복귀 후 빠르게 검수 + 6항목 결정을 내릴 수 있게 정리.

---

## 1. dev 서버 띄우기

```bash
git fetch origin
git checkout frontend-dev/p1-2a-draft-editor
pnpm install               # 신규 의존성 없음, 기존 lockfile 그대로
pnpm -C apps/web dev
```

→ 브라우저에서 http://localhost:5173/editor

main 으로 돌아갈 때:
```bash
git checkout main
```

---

## 2. 7종 annotation 시각 체크리스트

각 항목 하나씩 확인. 동작 OK / 시각 식별 가능 / 직렬화 JSON 결과 정상 — 3가지 모두 OK 면 ✅.

| # | kind | 기대 동작 | OK / NG | 비고 |
|---|---|---|---|---|
| 1 | highlight | 선택 영역에 색 배경. 12색 picker 변경 시 색 반영. | | |
| 2 | underline | 선택 영역에 밑줄. | | |
| 3 | top_label | 선택 영역 위에 위 첨자처럼 라벨 텍스트 (prompt 입력) | | |
| 4 | bottom_label | 선택 영역 아래에 아래 첨자 라벨 | | |
| 5 | bracket | 선택 영역 양 끝에 `[` `]` (또는 선택한 style) | | |
| 6 | arrow | 선택 영역에 점선 underline. 끝점 등록 prompt 동작. | | |
| 7 | inline_note | 선택 영역 뒤에 ` (=note)` 형식 표시 | | |

추가 동작:
- [ ] 12색 swatch 클릭 → 선택된 swatch 강조 → 다음 적용 mark 에 색 반영
- [ ] category select (5종) 변경 → JSON 패널의 `category` 필드 반영
- [ ] "JSON 보기" 버튼 → 직렬화된 `SerializedAnnotation[]` 출력
- [ ] "초기화" 버튼 → fixture 문장으로 doc 리셋 (구현되어 있다면)
- [ ] 같은 텍스트에 mark 재적용 (toggle off) 동작

---

## 3. PM 결정 6항목 (PR description 참조)

각 항목 결정 후 PR #16 코멘트로 남기시면, P1-2 후속 PR 들이 그걸 입력으로 진행.

### 3.1 12색 팔레트 색 코드 (영상 §3.3 / §5.1 미해결)
- **현재 상태**: tailwind palette 임의 12색
- **결정 옵션**:
  - (a) 임의 디폴트 유지 → §5.1 와이프 인터뷰 후 교체
  - (b) 영상 캡처 색 추출해서 12색 명시
  - (c) 임의 결정 (예: 분홍/파랑/노랑/초록 + 파스텔 변형 12색)
- **추천**: (a) — 와이프 의도가 더 중요

### 3.2 color_index 별 의미 (sentence_role 매핑 등)
- **현재 상태**: 의미 없는 순수 색 팔레트
- **결정 옵션**:
  - (a) 의미 없음 유지 (사용자가 자유롭게 사용)
  - (b) 카테고리별 권장 색 매핑 (예: 1-2=note, 3-5=phrase, 6-8=clause)
  - (c) 강제 매핑 (color_index 가 자동으로 category 설정)
- **추천**: (a) — 영상도 자유 사용 패턴

### 3.3 단어 단위 선택 정책 (§7.4 미정)
- **현재 상태**: ProseMirror 디폴트 (글자 단위)
- **결정 옵션**:
  - (a) soft snap (글자 단위 selection 받고 저장 시 단어 경계 확장)
  - (b) hard snap (drag 중 단어 단위 강제 — ProseMirror plugin 자작)
  - (c) 디폴트 유지 (글자 단위)
- **추천**: 검수 후 직접 사용 느낌으로 결정. 영상은 hard snap.

### 3.4 컨텍스트 메뉴 도입
- **현재 상태**: 없음 (툴바만)
- **결정 옵션**:
  - (a) Radix UI ContextMenu 도입 → P1-2 후속 PR
  - (b) Floating UI / Headless UI 등 더 가벼운 라이브러리
  - (c) 자작 (가장 무거움)
  - (d) 컨텍스트 메뉴 없음 — 툴바만 유지 (드래프트 영구화)
- **추천**: (a) — 검증된 라이브러리 (CLAUDE.md §3.6)

### 3.5 inline_note text 위치 / 분리 단락 여부 (§6 #2 — P1-8a 에서 inline 채택)
- **현재 상태**: P1-8a 에서 inline run 후보 A 채택 — HWPX 도 inline. 에디터도 inline 표시.
- **결정 옵션**: domain-expert 검토 follow-up — Phase 1 baseline 충분한지
  - (a) inline 유지 (현재)
  - (b) 별 단락 라벨로 변경 (top_label 과 역할 겹침 위험)
- **추천**: (a) 유지, Phase 1 baseline 검수에서 와이프 피드백 후 재평가

### 3.6 bracket style 표현 (() / {} / [])
- **현재 상태**: 3종 attrs 정의됨 (`bracket_style`). 에디터는 3종 모두 선택 가능 (드래프트).
- **HWPX 측**: P1-8b 에서 bracket 표현 미정 (Unicode / hp:rect / hp:tbl 중)
- **결정 옵션**:
  - (a) 3종 모두 유지
  - (b) `[]` 만 사용 (PoC 검증된 것)
  - (c) HWPX 결정 (P1-8b) 후 정합성 보고 결정
- **추천**: (c) — bracket HWPX 결정 (`docs/annotation-hwpx-mapping.md` §6 #1) 과 묶어서

---

## 4. 검수 결과 기록 템플릿

PR #16 코멘트로 다음 양식 사용 권장:

```
## 검수 결과 (2026-05-XX)

### 시각 체크리스트
- highlight: ✅ / NG (사유)
- underline: ...
- (7종 모두)

### 6항목 결정
1. 12색 팔레트: (a) 임의 디폴트 유지
2. color_index 의미: (a) 의미 없음
3. 단어 단위 선택: (b) hard snap — 영상 패턴
...

### 추가 피드백 (있으면)
- ...

### 다음 단계
- [ ] PR #16 머지
- [ ] P1-2 후속 PR (컨텍스트 메뉴 / 색 picker 정식화 / 페이지 승격) — frontend-dev
- [ ] P1-6 (에디터 ↔ API 통합) — frontend-dev + backend-dev
```

---

## 5. 검수 후 다음 작업 후보

검수 OK / 머지 후 진행 가능:

| # | 작업 | 의존 | 비고 |
|---|---|---|---|
| 1 | P1-2 후속 (컨텍스트 메뉴 + picker 정식화 + 페이지 승격) | PR #16 머지 + 결정사항 | frontend-dev |
| 2 | P1-6 (에디터 ↔ API 통합) | PR #16 머지 + P1-5 (이미 머지) | frontend + backend |
| 3 | P1-8b (라벨 / 괄호 렌더러) | bracket 결정 (3.6) | backend, HWPX 검수 필요 |
| 4 | P1-11 (마커 분리 추출 정책) | - | backend, P1-9 검수 품질 향상 |
| 5 | 로컬 commit 2건 push + PR | git 권한 | f598804 + 8e2efc7 |

검수 NG 시:
- NG 항목별 P1-2 후속 PR 에서 수정
- 큰 NG (예: 7종 중 3종 이상 동작 안 함) 면 별 hotfix PR
