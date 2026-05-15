# Phase 2-edit 와이프 v0.2 통합 검수 결과 보고서

- **검수 기간**: 2026-05-10 ~ 2026-05-15
- **검수자**: 와이프 (영어 강사)
- **PM**: Dennis
- **fixture**: `74c1a9e0-f973-495c-b1d6-09c33ba194a1` ("Zero waste", playful template, 1 item, 7 paragraphs + 11 annotations)
- **관련 가이드**: `docs/phase-2-edit-wife-review-prep.md` (사전 시나리오)
- **종료 상태**: **합격** — annotation 영역 5건 fix OK + wrap 정합은 ADR-0018 별 sprint 인계

---

## 0. 본 문서의 위치

`docs/phase-2-edit-wife-review-prep.md` 의 검수 시나리오를 진행한 결과 정리. CLAUDE.md §2.2 Phase 2-edit sprint 종료 + Phase 2.5 (unified-rendering) sprint 진입 신호의 근거.

---

## 1. 검수 진행

### 1.1 영역 1 — 편집 UI (E2-3 시리즈, PR #71/#72)

| 항목 | 결과 |
| --- | --- |
| 메타 편집 모달 | OK |
| 문항 추가 (passage 검색/선택) | OK |
| 문항 순서 변경 (↑↓) | OK |
| 문항 삭제 (×) | OK |
| Translation 인라인 편집 | OK |
| Vocabulary 행 편집 / 추가 / 삭제 | OK (D3 모든 항목 삭제 허용 / D6 "+" 버튼) |

**영역 1 등급**: **A** (그대로 사용 가능).

### 1.2 영역 2 — 본문 편집 (Stage E3, PR #74)

| 항목 | 결과 |
| --- | --- |
| paragraph 분할 (textarea Enter) | OK |
| 오타 수정 | OK |
| 본문 변경 시 annotation 충돌 처리 | OK (confirm 후 전체 삭제) |

**영역 2 등급**: **A** (그대로 사용 가능).

### 1.3 영역 3 — PDF 산출물 (annotation 시각)

검수 5단계로 진행 — 각 단계 fix 후 사용자 시각 확인:

| 단계 | 발견 | Fix | 결과 |
| --- | --- | --- | --- |
| 1 | 라벨 글씨가 borderline 색과 같아 가독성 ↓ | `.annot-*-label::after { color: #000 }` 검정 고정 | OK ("라벨 글씨 검정으로 잘 바뀌었어") |
| 2 | highlight 영역 안 underline 자리에 highlight 배경 사라짐 | `_slice_text_runs` 세 layer (highlight / underline / inline_note) 별 map 추적 → 단일 span 안 class 합쳐 emit | OK |
| 3 | highlight segment 분할 시 모서리 라운드 + padding 으로 굴곡 보임 | `.annot-highlight` `border-radius` / `padding` 0 | OK ("이제 잘 보인다") |
| 4 | 같은 color_index 가 에디터/PDF 다른 색 매핑 (예: 8 = 에디터 red-300, PDF deep-purple) | `.annot-highlight--N` 12색을 에디터 `--anno-color-N` (Tailwind 300/200) 정합 | OK |
| 5 | paragraph 간 시각 분리 없음 — line-height 3.4 만으로는 부족 | `.passage-body .annot-passage { padding: 0.5em 0 }` 추가 (에디터 정합) | OK |

**영역 3 등급**: **A** (5건 fix 후 그대로 사용 가능). PR #82 머지 (2026-05-15).

### 1.4 잔존 — wrap 정합 (별 sprint 인계)

영역 3 검수 후반에 발견된 *근본 결함* — 에디터 ↔ PDF 본문 wrap 위치 미세 차이.

**원인**: Tiptap Decoration.widget (에디터 측) 이 inline 흐름에 word break point 를 추가 vs Chromium inline span (PDF 측) 은 동일한 break point 없음. 같은 폭 (626px) 인데도 wrap 위치 1~2 단어 차이.

**시도된 임시방편 4종 (모두 원복)**:
1. PDF 본문 폭 좁힘 (622px / 612px) — 다른 케이스 깨짐
2. label anchor zero-width inline-block — 일부 케이스만 정합
3. bracket open 라벨 span 안/밖 이동 — borderline 시각 vs wrap 정합 trade-off
4. `display: inline-block` → `inline` 전환 — borderline 시각 깨짐 (사용자: "엉망이야 훨씬 나빠졌어")

**사용자 결론** (2026-05-15):
> "임시방편으로 이슈건들을 하드코딩하는건 안좋아. 근본적으로 에디터와 pdf 프리뷰 페이지가 동일한 방식으로 렌더링되게해야 모든 케이스에 이슈가 없게 작동하지."

**인계** — **ADR-0018** (Accepted, PR #81) → Phase 2.5 (unified-rendering) sprint:
- 옵션 (a) **server-side Tiptap** (Node.js + jsdom) 채택
- Stage F1~F4 (3.5주 / 6~9 PR)
- ADR-0014 → Superseded
- 사전 가이드 — `docs/stage-f1-server-tiptap-poc-prep.md` (PR #84)

---

## 2. 합격선 평가

`phase-2-edit-wife-review-prep.md` §2.1 의 영역별 등급 + 합격선:

| 영역 | 사전 합격선 | 실제 등급 |
| --- | --- | --- |
| 편집 UI | B 이상 | **A** |
| 본문 편집 | B 이상 | **A** |
| PDF 산출물 | B 이상 | **A** (5건 fix 후) |

**종합**: 합격선 *훌쩍 초과*. 잔존 wrap 정합은 본 검수 범위 외 (별 sprint 영역) 로 합의.

---

## 3. 산출물

### 3.1 머지된 PR

| PR | 내용 | 머지일 |
| --- | --- | --- |
| #82 | annotation 영역 fix 5건 (highlight 다중 layer / 12색 정합 / 굴곡 제거 / 라벨 검정 / paragraph 분리) | 2026-05-15 |
| #79 | chore: lint + stale spec | 2026-05-15 |
| #80 | ADR-0016 (VocabularyMaster) / ADR-0017 (Question variant) Accepted | 2026-05-15 |
| #81 | ADR-0018 (unified rendering) Accepted | 2026-05-15 |
| #83 | ADR Accepted 상태 갱신 + CLAUDE.md v0.12 | 2026-05-15 |
| #84 | Stage F1 PoC 사전 가이드 | 2026-05-15 |

### 3.2 메모리 갱신

- `feedback_pdf_annotation_visual.md` — 5건 교훈 추가 (display:inline 전환 금지 / inline-block 라벨 wrap 한계 / border-radius 0 / 다중 layer / 12색 정합).
- `project_current_session.md` — 검수 종료 + Phase 2.5 진입 신호.
- `MEMORY.md` 인덱스 갱신.

---

## 4. 다음 단계

### 4.1 즉시 진행 (병렬 가능)

- **schema v0.2 PR** (backend-dev agent 진행 중) — ADR-0016/0017 반영. VocabularyMaster 신규 + Question.variant_metadata + qa_validation_results.
- **Phase 2.5 Stage F1** — `docs/stage-f1-server-tiptap-poc-prep.md` 가이드 따라 PoC 진입.

### 4.2 ADR 결정 후 (후속 sprint)

- **Phase 2.5 Stage F2~F4** — F1 PoC 결과에 따라 결정. annotation_html.py 폐기 + 새 라이브러리 통합.
- **Phase 3 진입** — Phase 2.5 종료 + schema v0.2 머지 + 변형문제 카탈로그 v0.4 (domain-expert) 후.

### 4.3 후속 미세 영역 (검수 외)

- v0.2-γ Vocabulary schema 확장 (synonyms / antonyms / example_sentences) — 별 ADR.
- Tiptap 전환 (ADR-0015 D5 a) — ADR-0018 sprint 에 흡수됨.

---

## 5. 결론

Phase 2-edit sprint **목표 달성** — CLAUDE.md §1.3 가치 명제 #3 "편집 가능한 출력" 의 *편집 UI 영역* 완성. 학생 자료 1건을 **UI 만으로** 와이프가 완성 가능.

잔존 (wrap 정합) 은 Phase 2.5 sprint 로 인계되어 *근본 해결* 길 — Phase 3 진입 전에 봉합 예정.

## 변경 이력

| 버전 | 날짜 | 변경 |
| --- | --- | --- |
| v0.1 | 2026-05-15 | 검수 결과 정리 — annotation 5건 fix OK + wrap 정합 ADR-0018 sprint 인계. |
