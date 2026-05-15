# CLAUDE.md

> 이 문서는 Claude Code CLI가 프로젝트 컨텍스트를 이해하기 위한 헌장(charter)이자, subagent들의 협업 규칙서다.
> 변경 시 PR로 관리한다. 모든 핵심 의사결정은 여기 반영된다.

**버전**: v0.13
**최종 갱신**: 2026-05-15
**상태**: **Phase 2.5 sprint 좌초 → Phase 3 진입** (2026-05-15). ADR-0018 옵션 (a) server-side Tiptap 시도 (PR #89~#93) 가 와이프 검수에서 *추가 회귀* 유발 (ProseMirror View 가 mark + Decoration.widget 둘 다 emit / widget 이 단어 중간 inline 삽입 / 개발용 클래스 노출) — 5건 PR 모두 **revert** (PR #94). annotation 영역 5건 fix (PR #82) 만 유지. wrap 정합 미해결 — 두 엔진 본질적 한계 인정 + 사용자 결정 (2026-05-15): "PR #82 fix 만 유지" → Phase 3 진입. ADR-0018 → **Superseded by acceptance of wrap divergence** (별 메모로 마무리). Phase 3 진입 차단 ADR-0016 (VocabularyMaster) / ADR-0017 (Question variant) Accepted + schema v0.2 + Migration 1/2 적용 완료.

---

## 1. 프로젝트 개요

### 1.1 한 줄 정의

영어 학원 강사가 **하나의 입력(지문 또는 문제)** 으로부터 **학생 배포용 자료, 변형문제, 구문분석 자료** 를 일관된 콘텐츠 모델 위에서 생성/편집/내보내기 할 수 있게 해주는 웹 도구.

### 1.2 사용자

- **1차 사용자(beachhead)**: 와이프 — 영어 강사
- **2차**: 동료 영어 강사 / 학원
- **운영자**: Dennis (개발자 겸 PM)

### 1.3 핵심 가치 명제

1. **콘텐츠 자산화**: 한 번 만든 지문/구문분석/변형문제는 재사용 가능한 자산으로 축적된다 (단순 일회성 생성기가 아님)
2. **HWPX 우선**: 한국 학원 시장의 표준 포맷을 1급으로 지원
3. **편집 가능한 출력**: AI가 만든 결과는 항상 사용자가 검수/수정한 후 내보낸다 (자동 = 신뢰 부족 ≠ 완성)

### 1.4 비-목표 (이 프로젝트가 *하지 않는* 것)

- 학생용 학습 앱 (콘텐츠 생성 도구이지 학습 플랫폼 아님)
- 자동 채점 / 학생 성적 관리
- 한컴오피스 자체의 일반 기능 대체
- HWP(바이너리) 직접 파싱 — HWPX와 PDF만 1급 지원

---

## 2. MVP 범위와 Phase 로드맵

### 2.1 Phase 정의

각 Phase는 **와이프가 즉시 사용 가능한 도구**를 산출한다.

#### Phase 0 — 콘텐츠 모델 + 입력 파이프라인

- **목표**: canonical schema 확정 + 단일 문제(이미지/PDF/텍스트) 입력을 정규화된 `Passage + Question` 객체로 변환
- **범위**: CLI/API only, UI 없음
- **DoD (Definition of Done)**:
  - `shared/schemas/`에 Passage, Question, Vocabulary, Translation, SyntaxAnnotation, Worksheet 등 1차 정의 완료
  - Vision LLM을 사용한 추출 파이프라인이 PDF 1건, 이미지 1건, 텍스트 1건에 대해 정확히 정규화된 객체를 반환
  - DB에 Passage 저장/조회 가능
  - 멀티테넌트 스키마 (`tenant_id`) 박혀 있음, 인증은 stub
  - architect agent가 `docs/schema-coverage-audit.md` 산출

#### Phase 1 — 구문분석 에디터 (Feature 2, 와이프 1순위)

- **목표**: 정규화된 Passage를 웹 에디터에 로드 → 구문분석 작업 → HWPX 출력
- **DoD**:
  - Tiptap 기반 에디터에서 텍스트 위에 상단 라벨 / 하단 라벨 / 괄호 / 하이라이트 / 밑줄 / 화살표 작업 가능
  - 작업 결과가 `SyntaxAnnotation[]`으로 직렬화되고 DB에 저장
  - 단일 지문에 대해 HWPX 출력이 와이프가 검수해서 OK 받을 수준 (1차 baseline)

#### Phase 2 — 학생 배포용 자료 (Feature 1)

- **목표**: 동일 Passage에 LLM으로 해석/어휘를 보강하고 템플릿에 렌더 → HWPX/PDF
- **DoD**:
  - 학생용 템플릿 v0.1 — 기본 레이아웃 (지문 + 한글 해석 + 어휘 박스)이 와이프가 실사용 OK 하는 수준
  - 컬러 / 로고 프리셋 변경 가능
  - HWPX, PDF 양쪽 출력
- **점진 개선 영역 (Phase 2 DoD에 포함되지 않음, Phase 2 종료 후 지속 개선)**:
  - 타이포그래피 (폰트, 크기, 자간)
  - 여백·간격·정렬 세부
  - 어휘 박스 강조 표기
  - 다중 템플릿 (1단/2단, 어휘 위치 변형 등)
  - 로고/컬러 외 추가 프리셋

#### Phase 2.5 — unified-rendering sprint (좌초, 2026-05-15)

**상태**: **Superseded by acceptance of wrap divergence** (2026-05-15).

- ADR-0018 옵션 (a) server-side Tiptap 시도 (PR #89~#93) 가 ProseMirror View 의 *mark + Decoration.widget 동시 emit* 으로 시각 회귀 유발 — 와이프 검수에서 즉시 거부. revert (PR #94).
- 사용자 결정: wrap 차이는 본질적 한계 인정 + Phase 3 진입.
- Phase 4 (클라우드 배포) 전 재검토 가능 — 그 시점에 옵션 (b) ProseMirror Mark + CSS / (c) cross-lang lib / (d) wrap 차이 영구 인정 중 선택.
- 본 sprint 의 ADR-0014 → Superseded 결정은 **무효화** (annotation_html.py 그대로 production 경로).

#### Phase 3 — 변형문제 (Feature 3)

- **목표**: 변형 유형별 프롬프트 카탈로그 + 자동 검증 + 출력
- **DoD**:
  - 변형 유형 5개 이상 지원 (어휘, 어법, 빈칸, 어순, 주제·요지 등)
  - 정답 유일성 자동 검증 (qa-validator agent가 별도 LLM call로)
  - 변형 결과가 다시 정규화된 Question으로 들어가서 Phase 1, 2 파이프라인과 호환
- **진입 전 차단 ADR (모두 Accepted, 2026-05-15)**:
  - ADR-0016 VocabularyMaster (글로벌 어휘 dedup) — 별 테이블 + `Vocabulary.master_id` nullable FK.
  - ADR-0017 Question / VariantQuestion 단일 테이블 + `variant_kind` discriminator + self-FK NULLABLE.
  - ADR-0018 unified-rendering (Phase 2.5 sprint 선행).

#### Phase 4 — 클라우드 배포 + 멀티테넌트 활성화

- Google OAuth, 결제, 테넌트 관리 UI

### 2.2 현재 위치

**Phase 2.5 sprint 좌초 → wrap 정합 미해결 인정 → Phase 3 진입** (2026-05-15).

- ADR-0018 옵션 (a) server-side Tiptap 시도 (PR #89~#93, 1일) 가 와이프 검수에서 *추가 회귀* — ProseMirror View 가 mark + Decoration.widget 둘 다 emit / widget 이 단어 중간 inline 삽입 / 개발용 클래스 노출. 5건 PR 모두 **revert** (PR #94).
- 사용자 결정 (2026-05-15): wrap 차이는 본질적 한계 — PR #82 annotation 영역 5건 fix 만 유지하고 Phase 3 진입.
- 와이프 v0.2 통합 검수 OK 시점 그대로 복원:
  - annotation 영역 5건 fix (highlight 다중 layer / 12색 정합 / 모서리 굴곡 제거 / 라벨 검정 / paragraph 분리) — PR #82.
  - wrap 정합 미세 차이는 *알려진 한계* — PDF 출력물은 학생에게 한 권 자료로 배포되므로 에디터 ↔ PDF 정합 100% 는 사용 흐름에 영향 적음.
- Phase 3 진입 차단 ADR 2건 Accepted + schema v0.2 + Alembic Migration 1/2 적용 완료: **ADR-0016** (VocabularyMaster) / **ADR-0017** (Question variant). 변형문제 카탈로그 v0.4 + VariantKind enum V1~V10 완성.
- 다음 트리거: **Phase 3 (변형문제) 진입** — 카탈로그 §3.4 1순위 5개 (V6 / V2 / V4 / V5 / V7) 부터 LLM 프롬프트 작성 + qa-validator 활성화.
- 보류 영역:
  - ADR-0018 → Superseded by acceptance of wrap divergence (Phase 4 클라우드 배포 전 재검토 가능).
  - Tiptap 전환 (ADR-0015 D5 a) — 별 sprint 보류.
  - 환경 정리 — root `.env` 손상 (1줄만 남음, `apps/api/.env` 가 실제 사용). 사용자 직접 정리 권장.

**이전 마일스톤**:
- Phase 2 baseline 종료 (2026-05-07) — B5 와이프 검수 OK, PDF 퀄리티 A 등급.
- v0.2-α (Chromium native footer + 박스 한계선 + 어휘 표 분리) PR #58 open — 머지 대기.
- ADR-0015 Phase 2-edit sprint **Accepted** (D3 b / D4 b / D5 a / D6 b) — Stage E1 시작 가능 (PR #58 머지 후).
- Phase 1 baseline 결과 (2026-05-04, `docs/phase-1-wife-feedback.md`):
  - Editor 기능 = A 등급 (1차 사용 가능 수준).
  - HWPX 출력 = D 등급 (사용 불가) → ADR-0008 Accepted (HWPX 폐기, HTML→PDF 채택안 A 전환).
  - **Phase 1 baseline 출력 경로는 Phase 2 PDF 로 통합 흡수** — 별도 baseline 검수 없음.

#### Phase 0 — 종료 (2026-05-02)

DoD 5개 모두 충족:
1. `shared/schemas/` 1차 정의 — passage / question / annotation / worksheet / tenant / extraction
2. Vision LLM 추출 파이프라인 — text / image / pdf 각 1건 smoke test 통과
3. DB Passage 저장/조회 — `POST /passages/extract` + `GET /passages/{id}`
4. 멀티테넌트 스키마 (`tenant_id`) + 인증 stub — sentinel UUID 차단 + cross-tenant 격리
5. architect `docs/schema-coverage-audit.md` 산출

운영 가이드: `docs/phase-0-runbook.md`. Phase 0 진입 차단 ADR 모두 해소 (ADR-0004 / ADR-0006).

#### Phase 1 — 진행 중

**머지된 베이스**:
- 구문분석 에디터 — Tiptap 기반 highlight / underline / inline_note / top_label / bottom_label /
  bracket 마크. `apps/web/` + `packages/editor/`.
- HWPX 매핑 카탈로그 — `docs/annotation-hwpx-mapping.md` (P1-7) + 핵심 마크 HWPX 매핑 구현
  (`packages/hwpx_renderer/` — P1-8a inline run 후보 A 채택).
- Worksheet 출력 파이프라인 (Phase 2 산출에 선반영, Phase 1 검수 부담 분산):
  - **Stage 0 (PR #40)**: 외부 워크시트 템플릿 3종 자산 도입 + 분석 문서.
  - **Stage 1 (PR #41 / #42)**: `Worksheet` 출력 파라미터 확장 (subtitle / orientation /
    instruction / WorksheetItem.label) + ADR-0010 + Alembic + Branding 어댑터.
  - **Stage 2 (PR #44 / #45)**: Jinja2 HTML 렌더 (`GET /worksheets/{id}/preview?style=playful`)
    + Playwright PDF (`POST /worksheets/{id}/export.pdf`). XSS escape (markupsafe) + W-2 가드
    (cross-tenant `WorksheetItemORM` 차단) 적용.
- 사용자 환경 — `user_preferences` 백엔드/프론트 (PR #33~38), highlight 자유색상 chip 동기화.

**Phase 1 baseline DoD (와이프 검수 대기)**:
- 단일 지문에 대해 6 마크 (highlight / underline / inline_note / top_label / bottom_label /
  bracket) 작업 → HWPX 출력. 와이프가 검수해서 OK 받는 1차 baseline.

**Phase 1 잔존 / follow-up**:
- P1-8b — top/bottom label 수평 align pillow 폰트 metric 보정 (현재는 단락 indent 근사).
- P1-8c — 화살표/곡선 PoC (좌표계 / anchor 정책).
- HWPX 텍스트박스 align — §11 Open Questions 잔존.

#### Phase 2 — 진입 (B 시리즈 자동 진행 마감)

**머지된 베이스 (2026-05-07)**:
- **A 시리즈 — Worksheet CRUD 라우트**:
  - A1 (PR #48): GET /worksheets/{id} + GET /worksheets (목록).
  - A2-a (PR #49): PATCH /worksheets/{id} (메타) + DELETE.
  - A2-b (PR #50): POST/PATCH/DELETE /worksheets/{id}/items.
- **B 시리즈 — LLM 보강 + 출력 통합**:
  - B1 (PR #51): extract → Translation/Vocabulary 영속화 (옵션 A → B).
    GET /passages/{id} 도 두 관계 함께 조회.
  - B2 (PR #52): ADR-0013 (보강 파이프라인 설계) + 프롬프트 카탈로그 v0.1
    (augment-translation-v0 / augment-vocabulary-v0). domain-expert 검토 high 5건 반영.
  - B3 (PR #54): `packages/llm/augment.py` + 보강 라우트 2개 (POST /passages/{id}/translation /
    /vocabulary). mode=skip_if_user_edited (default) / replace / skip_if_exists / append.
  - ADR-0014 (PR #55): SyntaxAnnotation → HTML 렌더러 (hwpx_renderer 와 대칭, 변형문제
    Phase 3 까지 재사용). `packages/template_renderer/annotation_html.py`.
  - B4 (PR #56): Worksheet preview/PDF 컨텍스트 주입 — annotations 항상 정밀 렌더 +
    translation/vocabulary block (include_translation/include_vocabulary flag 기반 비용 회피).
  - ADR-0011 (PR #53): Worksheet HTML/PDF 파이프라인 사후 정리.

**B5 — 와이프 v0.1 검수 OK (2026-05-07)**:
- 학생 배포용 자료 1건 (playful 템플릿, zero-waste fixture) PDF — **퀄리티 A 등급** (사용자 평가).
- 합격선 "C까지" 훌쩍 초과 → Phase 2 baseline 종료.
- §3 11개 결정 항목: A1 (b 짧게 쪼갬) / A2 (영어 그대로) / A3 (a 의역) / A4 (a 평어) /
  A5/A6 OK / B1/B2 v0.2-γ 흡수 / C1-3 annotation fixture 별도.
- 5차 PDF 채택안 — D안 (Chromium native `display_header_footer` + `margin`):
  fixed footer 트릭 폐기, `pdf.py` + `_pdf_footer.html` 신규, 박스 한계선 footer 위 11mm 자동 분할.
- v0.2-α (CSS overflow + Chromium native footer + 본문 12pt + line-height 2.78 +
  어휘 박스 q 밖으로 분리 + 5컬럼 표) 머지 대기.
- v0.2-β (page counter) — 5차 채택안에서 자동 해소 (Chromium native pageNumber/totalPages).
- v0.2-γ (Vocabulary schema 확장 — synonyms/antonyms/example_sentences) — 별 ADR / Phase 2-edit 외 영역.

#### Phase 2-edit Sprint — 진입 신호 (ADR-0015)

CLAUDE.md §1.3 핵심 가치 명제 #3 ("편집 가능한 출력") 실현 sprint. 학생 자료
워크플로우의 사용자 편집 UI + 백엔드 PATCH 라우트.

- **Stage E1** (백엔드 PATCH 라우트, ~1.5주): translation 편집 / vocabulary 행 편집/추가/삭제 /
  passage body+paragraphs 동시 수정 — `created_by=USER` / `user_edited=True` 메타 갱신 통로.
- **Stage E2** (학생 자료 편집 UI, ~2주): `/worksheets/*` 라우트 + 7개 핵심 컴포넌트.
  와이프가 §1.1 7단계 (현재 curl) 를 UI 만으로 완료. **Stage E2 종료** (PR #65~#73)
  — 신규 (E2-2) / 상세 + 통합 편집 (E2-3a~c) / 인라인 편집 (E2-3b) / 메타 편집 (E2-3d) /
  items 추가·삭제·순서 (E2-3e) / 에디터-PDF wrap 정합 (line-wrap-parity).
- **Stage E3** (Passage 편집 UI): 본문 paragraph 분할 + 오타 수정 + annotation 충돌 처리.
  **Stage E3 종료** — `<PassageBodyEditor>` (textarea 기반, paragraphs 빈 줄 분리,
  body 변경 시 annotation 전체 삭제 + confirm 다이얼로그). Playwright E2E
  (`tests/e2e/passage_body_editor.spec.ts`) 로 회귀 보호. Tiptap 전환
  (ADR-0015 D5 a 채택안) 은 후속 — 별 PR 또는 Phase 3 후 검토.

**시작 트리거**: v0.2-α PR 머지 + ADR-0015 PM 결정 (D3-D6 4개 항목).
**종료**: 와이프 v0.2 검수 OK → Phase 3 (변형문제) 진입 신호.
**현재 (2026-05-09)**: Stage E1/E2/E3 모두 코드 완료 — 와이프 v0.2 통합 검수 대기.

#### Stage / Phase 트리거

- **Phase 1 baseline 와이프 OK** → 구문분석 단독 PDF 출력 검수.
- **B5 와이프 v0.1 검수 OK** → Phase 2 baseline 종료 → Phase 3 (변형문제) 진입 시작.
  - 검수 결과 D 등급 → ADR-0008 채택안 A (HTML→PDF) 의 다음 단계 한계 → 별 phase 신규.
  - C 등급 이상 → v0.2 미세 조정 PR 후 종료.
- **Phase 3 진입 전 별 ADR**:
  - VocabularyMaster (글로벌 dedup) — Phase 2/3 진입 전.
  - Question / VariantQuestion 단일 테이블 vs 별 테이블 — Phase 3 진입 전.
  - 화살표 (annotation arrow) 렌더 — 와이프 요청 트리거 시.

---

## 3. 핵심 아키텍처 결정 (ADR Lite)

### 3.1 Canonical Schema 중심 설계

`shared/schemas/`의 Pydantic 모델이 시스템의 척추다. 다음을 모두 만족한다:
- LLM structured output 타입
- FastAPI request/response
- DB ORM 모델 (또는 그것의 source of truth)
- 에디터 초기 상태
- 출력 렌더러 입력

스키마 변경은 PR로 관리하며, breaking change는 마이그레이션 계획 동반.

### 3.2 "한 입력 → 세 출력" 워크플로우

```
[입력]                    [정규화]                          [출력 어댑터]
PDF (텍스트 레이어)  →                                    → 학생용 자료 (Phase 2)
PDF (스캔본)         →                                    → 변형문제집 (Phase 3)
이미지              →   Passage + Question  →            → 구문분석 에디터 (Phase 1)
직접 입력            →                                       └─ HWPX 출력
HWPX                →
```

### 3.3 멀티테넌트는 처음부터, 인증은 나중에

- 모든 도메인 테이블에 `tenant_id` 컬럼 처음부터 박음
- 모든 쿼리는 `tenant_id` 필터 강제 (레포지토리 패턴)
- MVP는 환경변수의 단일 사용자로 stub
- Phase 4에서 OAuth만 갈아끼우면 됨

### 3.4 PDF 처리 분기

- 텍스트 레이어 있는 PDF → `PyMuPDF` 텍스트 추출 (저비용)
- 스캔본 PDF / 이미지 → 이미지 변환 후 Vision LLM (Anthropic Claude with image input)
- HWP는 직접 파싱하지 않음 — 사용자가 PDF로 변환 후 입력

### 3.5 구문분석 에디터: Tiptap 기반

- ProseMirror의 mark 시스템이 다중 레이어 annotation 겹침을 정확히 처리
- **하이라이트 / 밑줄 / inline_note**: HWPX 텍스트 런 속성 (`hh:charPr` + `charPrIDRef` 교체). P1-8a (PR #14) 머지로 구현 완료. `inline_note` 표현은 후보 A (inline run, 작은 폰트 charPr) 채택 — domain-expert 검토 follow-up 잔존. 12색 highlight 사전 정의 dict, underline `#000000` 고정. 상세는 `docs/annotation-hwpx-mapping.md` §2-1/§2-2/§2-3.
- **라벨 (top_label / bottom_label)**: HWPX **3단 단락 구조** (라벨 단락 / 본문 단락 / 라벨 단락). P1-0b PoC 에서 textBox + `vertOffset` 으로는 본문 위/아래 띄우기 불가 — 한컴이 floating textBox 를 단락 라인 높이로 clamp 해 본문 위/아래로 올라가지 않음. 3단 단락 구조 채택 (PoC fix 3차 검증).
  - **수평 align 한계**: 라벨 수평 위치는 단락 indent 근사 — pillow `ImageFont.getlength()` 폰트 metric 보정은 P1-8b 에서. pixel-level align 은 한계 (Phase 1 baseline 필요 조건 아님).
- **괄호 (bracket)**: **Unicode `[ ]` `( )` `{ }`** 채택 (ADR-0007, 2026-05-03). 본문 inline run 으로 양 끝에 글자 삽입 — P1-0b PoC 검증된 패턴. 와이프 검수 후 (P1-9) 외곽선 박스 (drawObj / tbl) 재검토 가능. 상세는 `docs/adr/0007-bracket-hwpx-representation.md`, `docs/annotation-hwpx-mapping.md` §1, §2-5, §6.
- **화살표 / 곡선**: HWPX 도형 (`hp:line` / `hp:polyLine`) 우선, 복잡할 때만 SVG → 이미지 fallback. 좌표계 / anchor 정책 PoC 는 P1-8c 에서 별도 진행 — `docs/annotation-hwpx-mapping.md` §2-6 참조.

### 3.6 No Reinventing the Wheel — 검증된 솔루션 우선

**원칙**: 새 컴포넌트가 필요할 때, 직접 구현하기 전에 다음 순서로 평가한다.

1. **이미 검증된 라이브러리/프레임워크가 있는가?** — 있으면 채택
2. **있지만 우리 요구를 부분 충족만 하는가?** — 어댑터/래퍼로 보강
3. **없는가, 또는 도메인 특수성이 너무 큰가?** — 그때만 직접 구현

**적용 예시 (이 프로젝트에서 이미 결정된 것)**:
- HWPX 렌더링 → 기존 `hwpx-auto-parser-for-template` 재활용 (직접 OOXML 풀스택 작성 안 함)
- PDF 텍스트 추출 → PyMuPDF (직접 PDF 파서 작성 안 함)
- 에디터 → Tiptap (ProseMirror 직접 다루지 않고 검증된 래퍼 사용)
- LLM structured output → Anthropic SDK + Pydantic (직접 JSON 파싱 안 함)
- DB 마이그레이션 → Alembic (직접 마이그레이션 스크립트 안 짬)

**경계 — 의존성 비대화 방지**:
- 작은 유틸 1~2개 쓰자고 무거운 라이브러리 통째 도입은 지양
- 라이브러리 도입 시 PR에 "왜 이걸 골랐는가 + 대안 검토" 짧게 기록
- 직접 구현 시 PR에 "왜 라이브러리를 쓰지 않았는가" 근거 기록

이 원칙은 **code-reviewer agent의 체크리스트에 포함**된다.

---

## 4. 기술 스택

| 레이어 | 선택 | 비고 |
|---|---|---|
| 언어(백엔드) | Python 3.12+ | |
| API 서버 | FastAPI | |
| 데이터 검증 | Pydantic v2 | |
| DB | PostgreSQL + SQLAlchemy 2.x | 멀티테넌트 RLS 가능성 열어둠 |
| 마이그레이션 | Alembic | |
| LLM | Anthropic Claude (Sonnet 4 기본, 추출은 Vision) | |
| HWPX 렌더링 | 기존 `hwpx-auto-parser-for-template` 컴포넌트 재활용 | 패키지로 분리해서 의존 |
| 프론트엔드 | TypeScript + React + Vite | |
| 에디터 | Tiptap (ProseMirror) | |
| 스타일 | Tailwind CSS | |
| 패키지 매니저 | uv (Python), pnpm (Node) | |
| 테스트 | pytest, vitest | |
| 코드 품질 | ruff, mypy, biome | |

신규 라이브러리 추가는 섹션 3.6 원칙을 따른다.

---

## 5. 디렉토리 구조

```
english-worksheet-tool/                    # 새 git repo
├── CLAUDE.md                              # 이 파일
├── README.md
├── pyproject.toml                         # workspace 루트 (uv)
├── pnpm-workspace.yaml
├── docs/
│   ├── adr/                               # 아키텍처 결정 기록
│   ├── schema-coverage-audit.md           # architect의 1차 산출물
│   ├── variant-type-catalog.md            # domain-expert의 1차 산출물
│   └── prompts/                           # LLM 프롬프트 카탈로그
├── shared/
│   └── schemas/                           # 시스템의 척추
│       ├── passage.py
│       ├── question.py
│       ├── annotation.py
│       ├── worksheet.py
│       └── tenant.py
├── apps/
│   ├── api/                               # FastAPI 앱 (배포 대상)
│   │   ├── src/
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── web/                               # React 웹앱 (배포 대상)
│       ├── src/
│       ├── tests/
│       └── package.json
├── packages/
│   ├── extractor/                         # PDF/이미지 → 정규화
│   ├── llm/                               # Claude API 래퍼, 프롬프트
│   ├── hwpx_renderer/                     # HWPX 출력
│   └── editor/                            # Tiptap extensions (구문분석 마크)
├── admin/                                 # 비배포 관리자 도구
│   ├── data_collector/                    # 아잉카 등 자료 수집
│   └── eval/                              # LLM 출력 평가
└── .claude/
    ├── agents/                            # subagent 정의
    │   ├── architect.md
    │   ├── domain-expert.md
    │   ├── backend-dev.md
    │   ├── frontend-dev.md
    │   ├── qa-validator.md
    │   └── code-reviewer.md
    └── commands/                          # 자주 쓰는 명령
```

배포 경계: `apps/`만 클라우드로 나간다. `admin/`은 로컬 전용.

---

## 6. 콘텐츠 모델 (Placeholder — Phase 0에서 확정)

### 6.1 핵심 엔티티 (개념 수준)

```
Tenant
  └─ Workspace
      ├─ Passage (정규화된 영어 지문 + 메타데이터)
      │   ├─ Translation (한글 해석)
      │   ├─ Vocabulary[] (어휘)
      │   ├─ SyntaxAnnotation[] (구문분석 마크)
      │   ├─ Question[] (원본 문제)
      │   └─ VariantQuestion[] (Phase 3 산출)
      └─ Worksheet (출력물 단위)
          ├─ template (학생용 / 교사용 / 변형문제집)
          ├─ branding (로고, 컬러)
          └─ items[] → Passage 참조
```

### 6.2 Question 유형 — 별도 카테고리가 아니라 기존 유형의 확장

**핵심 전제**: 변형 유형이라는 별도 카테고리는 없다. 모든 문제 유형은 기존
`exam-generator`의 24개 유형 중 하나에 속한다. Phase 3의 "변형문제"도 기존 유형의
파생일 뿐, 새 유형이 아니다.

따라서:
- **exam-generator의 24개 유형 enum을 그대로 흡수**해서 `Question.type`의 1차 source.
- **세부 형태(sub-form)** — 자료 sweep 중 발견되는 새로운 표면 형태(예: 본문 내장형
  어휘 선택, 다중 선택지 매트릭스 등)는 **기존 type 위에 부가 필드를 추가**하는
  방식으로 표현. 새 type을 만들지 않는다.
- **변형문제(VariantQuestion)** — 같은 24개 type 안에서 원본의 `derived_from_question_id`
  + `variant_kind` 필드로 표현. 즉 "어휘 선택 변형 = `type=어휘 선택` + `variant_kind=어휘
  교체`" 식.

검증·추가가 필요한 케이스(자료 sweep으로 발견됨):

- 본문 내장형 어휘 선택 (예: `(A) [long-term / short-term]`이 본문 중간에 박힌 형태)
- 다중 선택지 매트릭스 (A/B/C 컬럼)
- 기타 audit에서 발견되는 케이스

**원칙**: breaking change 최소화. 새 필드 추가 위주, 기존 필드 변경 지양. **새 type은
도입하지 않는다** — 기존 24개로 표현 불가능한 케이스가 발견되면 PM 결정.

---

## 7. Subagent 정의

### 7.1 공통 규칙

- 모든 agent는 `CLAUDE.md`를 먼저 읽고 시작
- 산출물은 PR로 제출
- 다른 agent의 산출물에 의존할 때는 명시적으로 참조
- 막히면 PM(Dennis)에게 질문, 추측으로 진행 금지
- 페르소나가 다른 agent의 영역(코드 vs 도메인 vs 스키마)을 침범하지 않음 — 충돌 시 PM 중재

### 7.2 architect (시스템 / 데이터 모델 설계자)

- **페르소나**: 데이터 모델러 + 소프트웨어 아키텍트
- **책임**: canonical schema 설계와 진화, 시스템 추상화, 정규화 결정, 의존성 방향, 스키마 호환성 관리
- **주 산출물**: `shared/schemas/` 변경 PR, `docs/schema-coverage-audit.md`, `docs/adr/` 아키텍처 결정 기록
- **첫 작업 (Sprint 0)**: `~/workspace/exam-generator`의 기존 JSON 스키마 audit → 새 repo의 `shared/schemas/` v0.1 설계 (domain-expert와 협업)
- **권한**: schema 디렉토리 + docs/adr/ 작성 권한. 다른 영역은 의견만.

### 7.3 domain-expert (영어 출제 / 교육 도메인 전문가)

- **페르소나**: 영어 시험 출제 경험이 있는 베테랑 강사
- **책임**: 변형 유형 카탈로그, 출제 품질 기준, 교육적 적절성 (어휘 수준, 지문 난이도), 자료 sweep
- **주 산출물**: `docs/variant-type-catalog.md`, `docs/prompts/` 변형 생성 프롬프트 초안, schema audit에 도메인 관점 코멘트
- **첫 작업 (Sprint 0)**: architect의 schema audit에 도메인 관점 검토 (이 분류가 영어 교육 관점에서 맞는가?)
- **권한**: docs/ 작성 권한. 코드/스키마 직접 수정 안 함.
- **architect와의 충돌 처리**: 분류·표현이 충돌할 때 양쪽 입장을 PR 코멘트로 제시. 결정은 PM이.

### 7.4 backend-dev

- **책임**: FastAPI 앱, 데이터 추출 파이프라인, LLM 통합, HWPX 렌더러 통합, DB
- **첫 작업 (Sprint 0)**: 새 repo 부트스트랩 (디렉토리 구조, pyproject, pnpm workspace), FastAPI skeleton + health check, DB 연결 + Alembic 초기 마이그레이션

### 7.5 frontend-dev

- **책임**: React 웹앱, Tiptap 구문분석 에디터, 미리보기, 사용자 인터랙션
- **첫 작업 (Sprint 0)**: Vite + React 초기 셋업, 라우팅 골격, Tiptap PoC (텍스트 위에 하이라이트 1개 그리기 + 직렬화)

### 7.6 qa-validator

- **책임**: LLM 출력의 정답 유일성 검증, 스키마 적합성 자동 체크, 회귀 테스트
- **첫 작업**: Phase 3 시작 시 활성화. Phase 0~2에서는 stub.

### 7.7 code-reviewer

- **책임**: 다른 agent의 PR 리뷰
- **체크리스트**:
  - canonical schema 위반 여부
  - 멀티테넌트 함정 (`tenant_id` 누락된 쿼리)
  - 시크릿 / 환경변수 노출
  - 불필요한 LLM 호출 (캐시 가능 여부)
  - 테스트 누락
  - 네이밍 / 구조 일관성
  - 의존성 방향 (예: `apps/`가 `admin/`을 import하면 안 됨)
  - **No Reinventing the Wheel** — 직접 구현된 로직이 검증된 라이브러리로 대체 가능한가? PR에 대안 검토 기록이 있는가?
- **권한**: comment only. 수정은 원래 agent가 함
- **에스컬레이션**: critical 발견 시 PM에게 직접 보고

---

## 8. 작업 흐름 / 컨벤션

### 8.1 Git

- 메인 브랜치: `main` (보호)
- 작업 브랜치: `<agent>/<short-desc>` (예: `architect/schema-audit`, `backend-dev/fastapi-skeleton`)
- 커밋: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)

### 8.2 코드 스타일

- Python: ruff format + ruff lint + mypy strict
- TypeScript: biome
- 모든 PR은 lint/test 통과해야 머지

### 8.3 LLM 호출 규칙

- 모든 LLM 호출은 `packages/llm/`을 거침 (직접 SDK 호출 금지)
- 프롬프트는 `docs/prompts/`에 마크다운으로 버전 관리
- structured output은 항상 Pydantic 모델로 검증

### 8.4 신규 라이브러리 도입

섹션 3.6 원칙을 따른다. 모든 신규 의존성 PR은 다음을 포함:
- 검토한 대안 (최소 1개)
- 선택 이유
- 사용 범위 (어떤 모듈에서 어떤 기능에 쓰는가)

직접 구현하는 PR은 "왜 라이브러리를 쓰지 않았는가" 근거 기록.

### 8.5 비밀

- `.env` 파일 git 무시
- API 키는 절대 커밋 금지 (code-reviewer가 검출)

---

## 9. Sprint 0 — 첫 한 주 작업

### 목표
Phase 0를 시작할 수 있는 기반을 깔고, architect + domain-expert의 audit으로 스키마 v0.1을 확정한다.

### 작업 항목

| # | Agent | 작업 | DoD |
|---|---|---|---|
| 1 | backend-dev | 새 repo 부트스트랩 | 디렉토리 구조, uv/pnpm workspace, pre-commit hook 동작 |
| 2 | backend-dev | FastAPI skeleton | `/health` 엔드포인트 동작, Docker compose 로컬 실행 |
| 3 | backend-dev | DB 셋업 | PostgreSQL 컨테이너 + SQLAlchemy + Alembic 초기 마이그레이션 (`tenants`, `workspaces` 테이블만) |
| 4 | architect | exam-generator 스키마 audit | `~/workspace/exam-generator` 분석, `docs/schema-coverage-audit.md` 작성 |
| 4-1 | domain-expert | audit에 도메인 검토 | architect의 audit PR에 영어 교육 관점 코멘트 |
| 5 | architect | 콘텐츠 모델 v0.1 PR | `shared/schemas/` 1차 정의, 변형 유형 갭 보고서 (domain-expert 의견 반영) |
| 6 | frontend-dev | Vite+React 셋업 | dev server 실행, 라우팅 골격 |
| 7 | frontend-dev | Tiptap PoC | 단일 문장 위에 하이라이트 1개 그리고 JSON으로 직렬화 |
| 8 | code-reviewer | 위 모든 PR 리뷰 | 체크리스트 통과 |

작업 #4가 다른 작업의 blocker는 아니지만, #4-1과 #5는 #4에 의존.

---

## 10. 외부 의존성 / 데이터 사용 정책

### 10.1 학습 자료 출처

- **아잉카**: 유료 멤버십 보유. PDF 우선 다운로드. HWP는 사용하지 않음.
- **수능/모의고사**: 평가원/EBSi 공식 자료
- **학교 내신 기출**: 사용자가 제공 (이미지/스캔본)

### 10.2 저작권 정책

- 개인 사용(와이프) 단계에선 회색지대 허용
- Phase 4 클라우드 배포 시 명확화 필요. 핵심 분기:
  - 원지문 그대로 학생에게 재배포: **잠재 issue** — 인용 한도 / 출처 표기 필요
  - 변형문제 (원지문 + 신규 문항): 상대적으로 안전, 단 출처 표기
  - 정답/해설은 자체 생성

이 부분은 Phase 4 직전에 별도 ADR로 다룸.

---

## 11. Open Questions (계속 갱신)

- [x] 기존 `exam-generator` 스키마 구체 내용 — `docs/schema-coverage-audit.md` (v0.3, 2026-05-02)
- [ ] HWPX 렌더링 시 텍스트 런 위에 텍스트박스를 정확히 align하는 방법 — backend-dev PoC 필요 (P1-8b 후속, 라벨 pillow 폰트 metric 보정)
- [ ] 구문분석 에디터에서 annotation 충돌(같은 span에 라벨 2개 이상) 시 시각적 처리 방식 — frontend-dev + domain-expert 협의
- [ ] DB 멀티테넌트 격리 방식: row-level filter vs PostgreSQL RLS — 결정 시점 Phase 4
- [ ] LLM 비용 모니터링 / 캐싱 전략 — Phase 3 진입 전
- [ ] 프롬프트 평가 / 회귀 테스트 자동화 — `admin/eval/`에서 다룸
- [ ] 학생용 템플릿의 다중 변형 (1단/2단 등) 도입 시점 — Phase 2 종료 후 와이프 피드백 기반
- [x] **Annotation span 식별 방식** — `docs/adr/0004-annotation-span-identification.md` (character offset 채택, 메모리는 ProseMirror position 하이브리드)
- [x] **마커 분리 vs inline 유지** — `docs/adr/0006-marker-processing-policy.md` (출제용 마커 분리 / 단락·지칭 라벨 inline 보존 하이브리드)
- [x] **Vocabulary 글로벌 마스터** — `docs/adr/0016-vocabulary-master-global-dedup.md`
      (Accepted, 2026-05-15). 별 `VocabularyMaster` 테이블 + `Vocabulary.master_id`
      nullable FK + `(tenant_id, headword_normalized)` UNIQUE + Phase 2-edit 종료 후
      별 PR (schema v0.2 + Alembic).
- [x] **Question / VariantQuestion 단일 테이블 vs 별 테이블** —
      `docs/adr/0017-question-variant-table-strategy.md` (Accepted, 2026-05-15).
      단일 `Question` 테이블 + `variant_kind` discriminator + `derived_from_question_id`
      self-FK NULLABLE + 다단계 derive 허용 + cascade SET NULL + qa_validation_results
      별 history 테이블 (하이브리드). Phase 3 진입 전 1회 마이그레이션.
- [ ] **레퍼런스 프로그램 영상 분석** — `/Users/william/Downloads/ScreenRecording_04-24-2026 15-11-52_1.MP4` 프레임 단위 분석 → UI/기능 설계 입력. 산출물 위치: `docs/reference-program-analysis.md` (작업 #5와 병렬, Phase 1 진입 전 완료 권고)
- [x] **annotation split-mark 정밀 렌더 ADR** — `docs/adr/0014-annotation-html-renderer.md`
  (Accepted 2026-05-07 → **Superseded by ADR-0018, 2026-05-15**).
  `packages/template_renderer/annotation_html.py` 는 baseline 역할 완료 — Phase 2.5
  sprint Stage F2 에서 server-side Tiptap 으로 대체 예정.
- [x] **Worksheet CRUD 라우트** — A1 (PR #48) / A2-a (PR #49) / A2-b (PR #50) 머지 완료.
  POST /worksheets / GET /{id} / GET / PATCH /{id} / DELETE /{id} + items POST/PATCH/DELETE.
- [x] **B 시리즈 (Phase 2 진입)** — B1~B4 + ADR-0013 + ADR-0014 머지 완료 (PR #51~56,
  2026-05-07). B5 와이프 검수 대기 — `docs/phase-2-wife-review-prep.md`.
- [x] **ADR-0011 사후 작성** — `docs/adr/0011-worksheet-html-pdf-pipeline.md`
  (Accepted, 2026-05-07). Worksheet HTML 템플릿 + Jinja2 + Playwright PDF
  파이프라인 결정 사항을 단일 ADR 로 통합. dangling reference (`README.md`,
  `template-rendering-analysis.md`, 본 §11) 닫음. ADR-0012 는 v0.8 작성 시 메모리
  가정과 달리 코드 어디에도 참조 없음 — B2 의 ADR-0013 으로 다음 번호 자연 사용.
- [ ] **AnnotationSpan / AnnotationCategory 영속화 검증** — 에디터에서 직렬화된 결과를 DB
  에 저장 / 복원 라운드트립 검증 (Phase 1 baseline 검수 시 자연스럽게 검증됨).
- [x] **에디터 ↔ PDF 본문 렌더 통합** — `docs/adr/0018-unified-rendering-editor-pdf.md`
  (Accepted, 2026-05-15). 옵션 (a) server-side Tiptap (Node.js + jsdom) 채택.
  Phase 2.5 sprint 신설 (Stage F1~F4, 3.5주). ADR-0014 → Superseded. Tiptap 전환
  (ADR-0015 D5 a) 흡수. Phase 3 진입 차단 — Phase 2.5 종료가 Phase 3 진입 트리거.

---

## 12. 변경 이력

| 버전 | 날짜 | 변경 |
|---|---|---|
| v0.1 | 2026-05-02 | 초안 작성 |
| v0.2 | 2026-05-02 | (1) Phase 2 DoD 완화 + 점진 개선 영역 명시 (2) planner를 architect + domain-expert로 분리, agent 6개로 확장 (3) 섹션 3.6 "No Reinventing the Wheel" 원칙 추가, code-reviewer 체크리스트 + 라이브러리 도입 PR 규칙에 반영 (4) Sprint 0 작업 항목 갱신 |
| v0.3 | 2026-05-02 | (1) §6.2 변형 유형 전제 정정 — 변형 유형은 별 카테고리가 아니라 기존 24개 유형의 sub-form/파생. exam-generator type enum 흡수가 1차 source. (2) §11 Open Questions 갱신 — schema audit 완료 표기, audit이 던진 미해결 ADR 항목 추가, 레퍼런스 영상 분석 항목 추가. |
| v0.4 | 2026-05-02 | §2.2 현재 위치 갱신 — Phase 0 종료, Phase 0 DoD 5개 충족 확인, Phase 1 진입 전 차단 ADR 명시. |
| v0.5 | 2026-05-02 | §11 Open Questions 갱신 — Phase 1 진입 차단 ADR 2개 해소 표기 (ADR-0004 Annotation span 식별 방식, ADR-0006 마커 처리 정책). |
| v0.6 | 2026-05-03 | §3.5 라벨 결정 갱신 (P1-0b PoC 반영) + bracket 표현 결정 미정 명시 + inline_note 잠정 표기. P1-7 매핑 카탈로그 (`docs/annotation-hwpx-mapping.md`) 반영. |
| v0.7 | 2026-05-03 | §3.5 inline_note "잠정" 표기 제거 — P1-8a (PR #14) 머지로 inline run 후보 A 채택 확정. 12색 highlight 사전 정의 / underline `#000000` 고정 명시. |
| v0.8 | 2026-05-07 | §2.2 "현재 위치" 전면 갱신 — Phase 1 진행 중 (구문분석 에디터 베이스 + Worksheet 출력 파이프라인 Stage 0~2 머지 완료, baseline 와이프 OK 대기). user_preferences (PR #33~38), Worksheet Stage 0~2 (PR #40~45), bracket / label inline node 전환 (PR #36 / ADR-0011) 흔적 반영. §11 Open Questions 갱신: annotation split-mark 정밀 렌더 ADR / Worksheet CRUD 라우트 / ADR-0011·0012 파일 부재 / AnnotationSpan 영속화 검증 항목 추가. |
| v0.8.1 | 2026-05-07 | (1) ADR-0011 사후 작성 (`docs/adr/0011-worksheet-html-pdf-pipeline.md`) — Worksheet HTML/PDF 파이프라인 결정 사항 통합. (2) §2.2 "구문분석 에디터" 베이스의 잘못된 ADR-0011 참조 (bracket / label inline node 전환 — v0.8 메모리 가정 오류) 제거. (3) §11 "ADR-0011 / ADR-0012 파일 부재" 항목 닫음 — ADR-0011 작성됨, ADR-0012 는 코드 어디에도 참조 없음 (B2 의 ADR-0013 으로 다음 번호 자연 사용). |
| v0.9 | 2026-05-07 | Phase 2 진입 — B 시리즈 자동 진행 마감. (1) §2.2 Phase 2 섹션 신설 (B1~B4 + ADR-0013 + ADR-0014 머지 완료, PR #51~56). (2) Stage / Phase 트리거 갱신 (B5 와이프 검수 → Phase 3 진입 트리거 명시). (3) §11 Open Questions 갱신 — annotation split-mark ADR / Worksheet CRUD 라우트 / B 시리즈 항목 close. (4) `docs/phase-2-wife-review-prep.md` 신규 — 검수 시나리오 + 11건 결정 항목. |
| v0.10 | 2026-05-07 | **Phase 2 baseline 종료** — B5 와이프 검수 OK (PDF 퀄리티 A 등급, 합격선 "C까지" 훌쩍 초과). (1) §2.2 "현재 위치" Phase 2 baseline 종료 + Phase 2-edit 진입 신호로 갱신. (2) v0.2-α 채택안 = D안 (Chromium native `display_header_footer` + `margin`) — fixed footer 트릭 폐기, `pdf.py` + `_pdf_footer.html` 신규, 박스 한계선 footer 위 11mm 자동 분할. v0.2-β 자동 해소 (Chromium native pageNumber/totalPages). (3) ADR-0015 신규 — Phase 2-edit sprint (Stage E1 백엔드 PATCH 라우트 / E2 학생 자료 편집 UI / E3 Passage 편집 UI) 정의. CLAUDE.md §1.3 핵심 가치 명제 #3 "편집 가능한 출력" 실현. (4) §6.4 PDF 등급 기록 + §6.5 v0.2 PR 분리 갱신. |
| v0.10.1 | 2026-05-07 | (1) ADR-0015 Accepted — D3-D6 모두 권장안 채택 (Vocabulary DELETE 모든 항목 / Passage 메타 없음 / Tiptap 재사용 + prop 분기 / "+" 버튼). Stage E1 시작 가능 (PR #58 머지 후). (2) §2.2 "Phase 1 baseline 와이프 OK 별도 대기" 표기 정정 — 2026-05-04 검수 완료 (Editor A / HWPX D), ADR-0008 로 HWPX 폐기 + HTML→PDF 전환. Phase 1 출력 경로는 Phase 2 PDF 로 통합 흡수. |
| v0.11 | 2026-05-09 | **Stage E1/E2/E3 코드 완료** (Phase 2-edit sprint). (1) Stage E2 PR #65~#73 머지: WorksheetNewPage / WorksheetDetailPage / WorksheetEditPage / Translation·Vocabulary·본문 인라인 편집 / 메타 편집 모달 / items 추가·삭제·순서 / 에디터-PDF wrap 정합 (Pretendard webfont + paragraph 분할 emit + bracket 라벨 밖). (2) Stage E3 = `<PassageBodyEditor>` (textarea 기반, paragraphs 빈 줄 분리, body 변경 시 annotation 전체 삭제 + confirm) + Playwright E2E `passage_body_editor.spec.ts`. (3) Tiptap 전환 (ADR-0015 D5 a) 은 후속 — 현재 textarea 로 와이프 검수 가능. (4) §1.3 핵심 가치 명제 #3 "편집 가능한 출력" 실현 완료 — 와이프 v0.2 통합 검수 → Phase 3 (변형문제) 진입 신호. |
| v0.12 | 2026-05-15 | **와이프 v0.2 검수 종료 + Phase 2.5 (unified-rendering) sprint 진입**. (1) PR #82 annotation 영역 fix 5건 머지 — highlight 다중 layer / 12색 정합 / 모서리 굴곡 제거 / 라벨 검정 / paragraph 분리. (2) **ADR-0018 Accepted** (PR #81) — 에디터 ↔ PDF 본문 wrap 미세 차이 (Tiptap vs Chromium 본질적 차이) 해소 위해 server-side Tiptap (Node.js + jsdom) 채택. Stage F1~F4 (3.5주). ADR-0014 → Superseded. (3) **ADR-0016 / ADR-0017 Accepted** (PR #80) — VocabularyMaster 별 테이블 + `Vocabulary.master_id` nullable FK / Question 단일 테이블 + `variant_kind` discriminator + self-FK NULLABLE. 별 PR 에서 schema v0.2 + Alembic. (4) §2.1 Phase 2.5 자리 신설 — Phase 3 진입 전 wrap 정합 봉합. (5) Tiptap 전환 (ADR-0015 D5 a) 은 ADR-0018 sprint 안에 흡수. |
| v0.13 | 2026-05-15 | **Phase 2.5 sprint 좌초 → wrap 정합 미해결 인정 → Phase 3 진입**. (1) ADR-0018 옵션 (a) server-side Tiptap 구현 시도 (PR #89~#93) 가 같은 날 와이프 검수에서 즉시 거부 — ProseMirror View 가 *mark + Decoration.widget 동시 emit* / widget 이 단어 중간 inline 삽입 / 개발용 클래스 (`ProseMirror-widget`) 노출. 5건 PR 모두 revert (PR #94). (2) ADR-0014 Superseded → Accepted 복귀 (annotation_html.py production 경로 유지). (3) ADR-0018 → Superseded by acceptance of wrap divergence. Phase 4 클라우드 배포 전 옵션 (b)/(c)/(d) 재검토. (4) §2.1 Phase 2.5 자리 좌초 표기. (5) §2.2 현재 위치 = Phase 3 (변형문제) 진입 신호. (6) ADR-0016/0017 schema v0.2 + Migration 1/2 + 카탈로그 v0.4 + VariantKind v1~v10 모두 적용 — Phase 3 진입 unblock. |
