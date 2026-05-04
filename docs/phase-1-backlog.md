# Phase 1 백로그 — 구문분석 에디터

- **작성일**: 2026-05-03
- **작성자**: architect agent
- **상태**: Phase 0 종료 직후 작성. Phase 1 진입 전 PM 승인 대상.
- **관련 문서**:
  - `CLAUDE.md` v0.5 §2.1 Phase 1 정의 + DoD, §11 Open Questions
  - `docs/adr/0004-annotation-span-identification.md` (span 식별 — character offset + ProseMirror position 하이브리드)
  - `docs/adr/0006-marker-processing-policy.md` (출제용 마커 분리 / 단락·지칭 라벨 inline 보존)
  - `shared/schemas/annotation.py` (Phase 0 1차 정의)
  - `packages/editor/src/extensions/highlight.ts` (Sprint 0 #7 Tiptap PoC)
  - `apps/web/src/pages/EditorPoc.tsx` (PoC 페이지)

본 문서는 **백로그 정의만** 한다. 실제 설계 결정, 코드/스키마 변경은 각 task 의 PR
에서 진행한다.

---

## 1. Phase 1 DoD 재확인 (CLAUDE.md §2.1 인용)

> **목표**: 정규화된 Passage 를 웹 에디터에 로드 → 구문분석 작업 → HWPX 출력
>
> **DoD**:
> - Tiptap 기반 에디터에서 텍스트 위에 상단 라벨 / 하단 라벨 / 괄호 / 하이라이트 /
>   밑줄 / 화살표 작업 가능
> - 작업 결과가 `SyntaxAnnotation[]` 으로 직렬화되고 DB 에 저장
> - 단일 지문에 대해 HWPX 출력이 와이프가 검수해서 OK 받을 수준 (1차 baseline)

본 백로그는 위 3개 DoD 를 모두 닫는 task 를 분해한다.

---

## 2. Task 분해

각 task 는 다음 형식을 따른다.

- **담당**: 단일 agent
- **의존**: 선행 task ID (없으면 `-`)
- **DoD**: 무엇이 동작/존재하면 task 완료인가
- **PR 단위**: 커밋 1~3개로 끝나는 단위 — 큰 task 는 `a/b/c` 분할

### 2.1 전제조건 — 미완 산출물 / ADR (P1-0 시리즈)

#### P1-0a — 레퍼런스 영상 분석 완료 [done — 인터랙션 카탈로그]

- **담당**: domain-expert (관찰) + architect (모델 매핑)
- **의존**: -
- **DoD**:
  - `docs/reference-program-analysis.md` 가 §1~§6 모두 완성 — 현재 §3.1, §4.1, §4.2,
    §4.3 은 ADR-0004/0006 작성 시 부분 인용된 상태. 미완 섹션 (UI 인터랙션, 단축키,
    단어 단위 선택 정책, 분석표 자동 누적 동작) 보완.
  - Phase 1 에디터의 UI 결정에 입력될 **인터랙션 카탈로그** 가 §6 으로 추가
    (마우스 / 키보드 / 컨텍스트 메뉴 동작별 표).
- **PR 단위**: 1 PR.
- **머지**: `docs: P1-7 follow-up + P1-0a §7 인터랙션 카탈로그` PR (예정). §6 은 이미 "작업 #5 인계 메모" 로 점유되어 있어 신규 §7 "인터랙션 카탈로그" 로 추가 — 마우스 / 키보드 / 컨텍스트 메뉴 / 단어 단위 선택 / 분석표 자동 누적 / P1-2 입력 정리. PM 인터뷰 필요 항목은 [미정] 표기로 남김.

#### P1-0b — HWPX 텍스트박스 align PoC [done]

- **담당**: backend-dev
- **의존**: -
- **DoD**:
  - `packages/hwpx_renderer/tests/` 에 단일 문장 + 상단 라벨 1개 + 하단 라벨 1개 +
    괄호 1쌍 + 하이라이트 1개를 포함한 HWPX 출력 fixture 1건.
  - 한글 오피스에서 열어 라벨 / 도형이 본문 텍스트 런 위에 정확히 align 되는지
    스크린샷 첨부.
  - 결과 요약: "정확히 align 가능 / 부분 / 불가능 + 우회안" 1페이지 메모를
    `docs/hwpx-align-poc.md` 로 산출.
- **PR 단위**: 1 PR. (CLAUDE.md §11 Open Question 해소)
- **머지**: PR #2 (`c04e935`) — fix 3라운드 후 머지. follow-up: (1) `docs/hwpx-align-poc.md` §7 에 PM 한글 오피스 스크린샷 첨부 (2) P1-8 착수 전 `test_poc_align.py` 에 한컴 스펙 핵심 값 (container.xml media-type, content.hpf 루트 요소 등) 검증 케이스 추가 (3) `poc_align._label_para_xml` 의 미사용 `indent` 파라미터 정리.
- **완료**: fixture `packages/hwpx_renderer/tests/fixtures/poc_align.hwpx` + 28 unit tests
  passed + `docs/hwpx-align-poc.md`. PM 수동 확인(한글 오피스 열기) 대기 중.

#### P1-0c — Vocabulary 글로벌 마스터 ADR (선택적, Phase 2 차단이 우선)

- **담당**: architect + domain-expert
- **의존**: -
- **DoD**: ADR 문서 머지. 단 **Phase 1 진입 자체는 차단하지 않음** — Phase 2 직전에
  처리해도 무방. 본 백로그에 명시만 하고 우선순위는 PM 결정.
- **PR 단위**: 1 PR.

> **주의**: P1-0a 와 P1-0b 는 Phase 1 의 핵심 task (P1-2, P1-5) 의 입력 — 권장 작업
> 순서 (§3) 에서 선행으로 둠.

---

### 2.2 에디터 (frontend-dev) — P1-1 ~ P1-4

#### P1-1 — Tiptap 확장 골격 + 직렬화 계약

- **담당**: frontend-dev
- **의존**: -
- **DoD**:
  - `packages/editor/src/extensions/` 에 7종 `AnnotationKind` (top_label, bottom_label,
    highlight, bracket, arrow, inline_note, underline) 별 Tiptap mark/extension
    스텁 — 동작은 비어 있어도 됨, 등록/직렬화 라우팅만.
  - `packages/editor/src/serialization/` 신설 — ProseMirror doc ↔
    `SyntaxAnnotation[]` (character offset 기반, ADR-0004 §결정 따른) 양방향 변환
    함수 1쌍 + 단위 테스트 (vitest) 5건 이상 (각 kind 1건 + 다중 mark 1건).
  - 직렬화 계약은 `shared/schemas/annotation.py` 의 현 placeholder 를 그대로 사용 —
    schema 변경은 P1-3 에서.
- **PR 단위**: 2 PR (a: extension 스텁, b: serialization + 테스트)

#### P1-2 — 인터랙션 UI (선택 → annotation 적용)

- **담당**: frontend-dev
- **의존**: P1-1, P1-0a (인터랙션 카탈로그)
- **DoD**:
  - 텍스트 선택 → 컨텍스트 메뉴 / 툴바에서 7종 annotation 중 하나 적용 가능.
  - color_index 12색 팔레트 picker (영상 레퍼런스 §3.3 흡수).
  - category 5종 (note / sentence_role / phrase / clause / other) 선택 UI.
  - `apps/web/src/pages/EditorPoc.tsx` 를 정식 `EditorPage.tsx` 로 승격 + 라우팅 등록.
  - 수동 QA 시나리오 5건 통과 (Playwright 도 좋고, 체크리스트 형태도 OK).
  - ArrowMark / BracketMark 의 Decoration API 전환 검토 포함 (P1-1 에서 Mark 로 등록됐으나 시각 구현은 Decoration 또는 nodeView 가 자연스러울 수 있음).
- **PR 단위**: 2~3 PR (a: 컨텍스트 메뉴 + 툴바, b: 색/카테고리 picker, c: 페이지
  승격 + QA 시나리오)

#### P1-3 — Annotation 스키마 v0.2 (placeholder 해소)

- **담당**: architect
- **의존**: P1-1 의 직렬화 결과 관찰 후
- **DoD**:
  - `shared/schemas/annotation.py` 의 `AnnotationSpan` placeholder 를 ADR-0004 결정에
    맞게 discriminated union 으로 교체 (`character_offset_v1` 확정 + 필요 시 미래
    `prosemirror_pos_v1` 자리만).
  - `arrow` kind 의 양 끝점 표현 (start_span / end_span) 정식화 — Phase 0 에선
    placeholder 였음.
  - Pydantic 단위 테스트 갱신.
  - **breaking change 가능** — 마이그레이션 스크립트 + Alembic revision 동봉.
- **PR 단위**: 1 PR (작은 schema PR + 마이그레이션).
- **머지**: PR #5 (`a03df2d`). follow-up: (1) `apps/api/src/worksheet_api/models/syntax_annotation.py` docstring 의 "ADR-0003 미확정/placeholder" 표기 정리 (2) `packages/editor/src/serialization/annotationSerializer.ts` arrow null 가드 (silent drop → console.warn or drop) (3) P1-5 착수 전 Docker 환경에서 `pytest -m integration` 1회 검증 (4) `charOffsetToPmPos` 다중 단락 정책 follow-up 명시 수정.

#### P1-4 — Annotation 충돌 시각 처리 정책

- **담당**: frontend-dev + domain-expert
- **의존**: P1-2
- **DoD**:
  - 같은 span 에 라벨 2개 이상 적용 시 시각 처리 (스택 / 줄바꿈 / 색 구분 등) 정책
    1페이지 메모 — CLAUDE.md §11 Open Question 해소.
  - 정책 결정 후 Tiptap 렌더 코드 반영.
- **PR 단위**: 1 PR (메모 + 코드 변경).

---

### 2.3 영속화 (backend-dev) — P1-5 ~ P1-6

#### P1-5 — Annotation DB 영속화 + API

- **담당**: backend-dev
- **의존**: P1-3
- **DoD**:
  - `apps/api/src/worksheet_api/` 에 annotation CRUD 엔드포인트:
    - `POST /passages/{id}/annotations` (replace-all 또는 batch upsert — PR 에서 결정)
    - `GET /passages/{id}/annotations`
  - SQLAlchemy 모델 + Alembic revision (multi-tenant `tenant_id` 강제).
  - 단위 테스트 (cross-tenant 격리 1건 포함).
- **PR 단위**: 1~2 PR (a: 모델 + 마이그레이션, b: 엔드포인트 + 테스트).
- **머지**: PR #12 (`1570ae1`). API 설계 결정: replace-all + 결과 리스트 반환 (id 포함). Alembic revision 추가 없음 (P1-3 0003 에서 ORM 컬럼 확정). 단위 7건 + 라우터 3건 통과. follow-up: (1) [보류] Docker 환경에서 `pytest -m integration` 으로 5건 (정상/덮어쓰기/빈 리스트/cross-tenant/arrow JSONB round-trip) 검증 1회 — P1-3 follow-up "integration 검증" 도 함께 충족 (Docker 인프라 부재로 본 세션 미처리, 다음 인프라 확보 시) (2) [done] `routers/annotations.py` GET 엔드포인트에 `async with session.begin()` 명시 — `chore: P1 follow-up 묶음` PR 에서 처리.

#### P1-6 — 에디터 ↔ API 통합

- **담당**: frontend-dev (+ backend-dev 보조)
- **의존**: P1-2, P1-5
- **DoD**:
  - 에디터 페이지가 passage_id 를 URL 로 받아 본문 + 기존 annotation 로드.
  - 저장 버튼 → API 호출 → 성공 토스트.
  - 새 annotation 생성 / 기존 수정 / 삭제 모두 라운드트립 동작.
  - **7종 `AnnotationKind` (`top_label` / `bottom_label` / `highlight` / `bracket` /
    `arrow` / `inline_note` / `underline` — `shared/schemas/annotation.py`
    `AnnotationKind` enum 기준) 각각 1건 이상이 포함된 라운드트립 시나리오 통과** —
    에디터에서 작성 → API 저장 → 재로드 → 동일 렌더 확인.
  - **Playwright E2E 골격 1케이스** (passage load → annotation 작성·저장 → HWPX
    download) — 회귀 누적 방지용 최소 baseline. 자세한 시나리오는 후속 task 에서
    확장. (P1-9 의 HWPX 다운로드 버튼이 머지된 후 1케이스 골격 확정.)
- **PR 단위**: 1~2 PR (a: 라운드트립, b: Playwright 골격 — P1-9 직후).
- **머지 (b)**: Playwright E2E 골격 1케이스 — `apps/web/tests/e2e/editor-roundtrip.spec.ts`. mock 전략: `page.route()` 로 backend API 가로챔 (FastAPI 미기동). chromium 1개 프로젝트. `apps/web/playwright.config.ts` + `apps/web/tests/e2e/api-mock.ts` 신설. 후속: 7종 annotation 라운드트립 시나리오 확장 (P1-10 또는 별도 task), 다중 브라우저, CI 통합.

---

### 2.4 HWPX 출력 (backend-dev) — P1-7 ~ P1-9

#### P1-7 — Annotation → HWPX 매핑 카탈로그

- **담당**: architect + backend-dev
- **의존**: P1-0b
- **DoD**:
  - `docs/annotation-hwpx-mapping.md` — 7종 annotation × HWPX 출력 표현 매트릭스
    (텍스트 런 속성 / 도형 / 텍스트박스 / SVG fallback 어디로 보낼지).
  - CLAUDE.md §3.5 결정 (하이라이트·밑줄 = 텍스트 런 / 라벨 = 텍스트박스 / 화살표 =
    도형 우선) 을 표 형태로 구체화.
- **PR 단위**: 1 PR (문서만).
- **머지**: PR #7 (`1bdf1c2`). follow-up: (1) `docs/annotation-hwpx-mapping.md` §0/§2/§6 에 P1-0b follow-up 미완 (test_poc_align.py 한컴 스펙 검증 / `poc_align.py` indent 정리) 이 P1-8a 착수 차단임을 명시 (2) §6 미해결 #3, #4 결정 주체를 "구현 레벨 (PM 불필요)" 로 분리 (3) §6 #6 (multi-line arrow) 비고에 "c-1 PoC 결과 후 단일 줄 arrow Phase 1 포함 여부도 PM 재결정" 명시 (4) CLAUDE.md §3.5 갱신 별 PR (라벨 = 텍스트박스 → 3단 단락 구조 / bracket 표현 추가 / 라벨 수평 align 한계 명시).

#### P1-8 — HWPX 렌더러 구현 (단일 지문 + annotation)

- **담당**: backend-dev
- **의존**: P1-7, P1-5
- **DoD**:
  - `packages/hwpx_renderer/` 에 `render_passage_with_annotations(passage, annotations)
    -> bytes` 함수.
  - 7종 annotation 모두 1건 이상 포함된 fixture passage 1건이 정상 HWPX 로 출력.
  - 단위 테스트: HWPX zip 구조 검증 + 핵심 XML 요소 존재 검증.
  - **구현은 기존 `hwpx-auto-parser-for-template` 컴포넌트를 어댑터/래퍼로 재활용한다**
    (CLAUDE.md §3.6, §4 — No Reinventing the Wheel). 재활용 불가 영역이 발견되면 해당
    PR 에 근거 기록.
- **PR 단위**: 2~3 PR (kind 별로 묶음 — a: 텍스트 런 계열 (highlight, underline,
  inline_note), b: 라벨 계열 (top, bottom, bracket), c: 화살표).
- **머지 (a)**: PR #14 (`aaa9885`) — fix 3라운드 후 머지. 한컴 호환성 fix: (1) `content.hpf opf:item id` 확장자 제거 (id="section0.xml" → "section0") (2) `<hh:underline type>` 값 교정 (SINGLE → BOTTOM, 한컴 스펙 외 값). 결정 기록: inline_note=inline run 후보 A / 12색 highlight 사전 정의 / underline #000000 고정 (P1-7 §6 #2/#3/#4 닫음). 69 단위 테스트 통과. follow-up: (1) [done] `_RunSpec` / `_build_body_para` 데드 코드 정리 — `chore: P1 follow-up 묶음` PR (P1-8b 가 자체 3단 단락 구조를 빌드하므로 데드 코드 제거가 안전 — 잘못된 API 시그널 제거) (2) [done] `xe` / `_xe_local` 중복 제거 — 동일 PR (3) [done] `charpr_xml` bold/italic 파라미터가 항상 켜진 상태로 출력되는 버그 정리 — 동일 PR (조건부 emission 으로 변경) (4) [보류] `inline_note` 의 `ann.text` 값 (예: "(=foster)") 미삽입 — domain-expert 결정 필요, Phase 1 baseline 충분한지 별도 검토 (5) [보류] `mcp__hwpx__open_document` 자동 회귀 테스트 추가 — pytest 안에서 MCP 도구 호출 인프라 부재 (6) `docs/hwpx-align-poc.md` §6 한컴 스펙 함정 추가 기록 (charPr id 비연속 / opf:item id 확장자 / underline type=SINGLE 등 P1-8a fix 라운드 발견 사항).

#### P1-9 — HWPX 출력 API + 와이프 검수 사이클

- **담당**: backend-dev (+ PM)
- **의존**: P1-8, P1-6
- **DoD**:
  - `GET /passages/{id}/export/hwpx` 엔드포인트 — DB 의 annotation 을 읽어 HWPX 반환.
  - 에디터 페이지에 "HWPX 다운로드" 버튼.
  - **와이프 검수 1라운드 완료** — fixture 3건 (각 다른 유형) 에 대해 OK / NG 피드백
    수집 → `docs/phase-1-wife-feedback.md` 에 기록. NG 항목은 P1-10 으로.
- **PR 단위**: 2 PR (a: 엔드포인트 + 버튼, b: 검수 피드백 문서).

#### P1-10 — 와이프 피드백 반영 라운드 (가변)

- **담당**: backend-dev / frontend-dev (피드백 내용에 따라)
- **의존**: P1-9
- **DoD**:
  - P1-9 의 NG 항목이 모두 OK 또는 PM 가 "Phase 1 baseline 으로 충분" 판정.
  - DoD 3 ("와이프가 검수해서 OK 받을 수준") 충족 선언.
- **PR 단위**: 가변 (1~5 PR). 큰 변경 발생 시 백로그 갱신.

---

### 2.5 추출 파이프라인 보완 (선택적, backend-dev) — P1-11

#### P1-11 — 마커 분리 정책 추출 단계 적용 (ADR-0006 후속)

- **담당**: backend-dev
- **의존**: -
- **DoD**:
  - ADR-0006 에서 결정된 "출제용 마커 분리 / 단락·지칭 라벨 inline 보존" 정책을 추출
    파이프라인 (`packages/extractor/`) 의 LLM 프롬프트 + 후처리에 반영.
  - Phase 0 fixture (PDF 1건, 이미지 1건) 재추출 → `body_text` 가 정책대로 정제.
  - 단위 테스트 갱신.
- **PR 단위**: 1~2 PR. **Phase 1 차단은 아님** — Phase 1 에디터는 정제 본문이 없어도
  raw text 로 동작 가능. 단 P1-9 와이프 검수 품질에 영향 → 가능하면 P1-8 전에 처리.

---

## 3. 권장 작업 순서

의존성 그래프를 풀어 직렬 + 병렬 묶음으로 제시.

```
[Wave 1 — 전제조건, 병렬 가능]
  P1-0a (영상 분석 보완)         ─┐
  P1-0b (HWPX align PoC)         ─┤
  P1-1  (Tiptap 확장 골격)       ─┤
  P1-11 (마커 분리 추출 적용)     ─┘   ← 선택적, 가능하면 여기서

[Wave 2 — Wave 1 산출물 의존, 병렬 가능]
  P1-2 (인터랙션 UI)              ← P1-1 + P1-0a
  P1-3 (Annotation schema v0.2)   ← P1-1 직렬화 관찰 후
  P1-7 (Annotation→HWPX 매핑)     ← P1-0b

[Wave 3]
  P1-5 (DB + API)                 ← P1-3
  P1-4 (충돌 시각 정책)            ← P1-2

[Wave 4]
  P1-6 (에디터↔API 통합)          ← P1-2 + P1-5
  P1-8 (HWPX 렌더러)              ← P1-7 + P1-5

[Wave 5 — 닫기]
  P1-9 (HWPX API + 와이프 검수)    ← P1-8 + P1-6
  P1-10 (피드백 반영)              ← P1-9
```

**예상 PR 수 합계**: 16~22 PR (P1-10 가변 포함).

**critical path**: P1-0b → P1-7 → P1-8 → P1-9 → P1-10. 가장 먼저 P1-0b 착수 권장.

---

## 4. Phase 1 진입 시 미해결 리스크

1. **P1-0a (영상 분석) 미완** — 인터랙션 카탈로그가 없어 P1-2 UI 결정에 추측 개입
   가능. Wave 1 에서 즉시 보완.
2. **P1-0b (HWPX align PoC) 미완** — 만약 한글 오피스에서 텍스트박스를 본문 텍스트
   런 위에 픽셀 단위 align 하기 어렵다면, P1-8 의 라벨/화살표 표현 방식 자체 (도형 vs
   SVG fallback) 가 흔들린다. **Phase 1 가장 큰 기술 리스크**.
3. **Annotation 충돌 정책 미결정** (CLAUDE.md §11) — P1-4 에서 닫힐 예정이나, 같은
   span 에 라벨 2개 이상이 빈도 높게 발생하면 UX 가 무너질 가능성. domain-expert
   조기 의견 권장.
4. **`shared/schemas/annotation.py` 의 `arrow` 표현 placeholder** — Phase 0 에선
   start/end 표현이 명확하지 않음. P1-3 에서 정식화 필요. ADR 신설은 필요 없을
   가능성 높지만, 양 끝점 표현이 character offset 만으로 부족하면 (예: 단어 중앙을
   가리키는 화살표) ADR 신설 task 가 추가될 수 있음.
5. **Vocabulary 글로벌 마스터 미결정** (P1-0c) — Phase 1 차단은 아님. Phase 2 직전에
   처리해야 함을 PM 이 잊지 않도록 본 백로그에 명시.
6. **와이프 검수 (P1-9) 의 OK 기준이 주관적** — "1차 baseline 수준" 의 정의가
   느슨함. P1-9 직전에 PM 이 합격 기준 (예: "수업에서 그대로 인쇄해서 사용할 수
   있는 수준" / "약간 수기 보완 후 사용 가능" 등 등급 정의) 을 명문화 권장.
7. **테스트 자동화 부재** — Phase 1 에 E2E (Playwright) 가 없으면 회귀가 빠르게
   누적될 가능성. P1-2 또는 P1-6 에서 기본 골격이라도 도입하면 좋음 — 본 백로그에
   별 task 로 빼지 않았으나 PM 이 우선순위 결정.

---

## 5. 백로그 갱신 정책

- 각 task PR 가 머지될 때 본 문서의 해당 task 항목에 `[done]` + PR URL 1줄 추가
  (별도 PR 불필요, task PR 안에 포함).
- 새 task 발견 시 본 문서에 `P1-12`, `P1-13` … 형태로 append + 권장 작업 순서 갱신.
- Phase 1 종료 시 `docs/phase-1-runbook.md` (Phase 0 와 동일한 패턴) 작성으로 마감.
