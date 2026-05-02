# ADR 0001 — Canonical Schema 중심 설계 (시스템의 척추)

- **상태(Status)**: Accepted
- **작성일**: 2026-05-02
- **작성자**: architect agent
- **유형**: 기존 결정의 기록 (CLAUDE.md §3.1을 ADR 포맷으로 정리)
- **관련 문서**: `CLAUDE.md` §1.3, §3.1, §6, `docs/schema-coverage-audit.md`

---

## Context (배경)

이 프로젝트는 "한 입력 → 세 출력" (학생 배포용 자료 / 변형문제 / 구문분석 자료) 워크플로우를
구현한다. 동일한 콘텐츠가 다음 5가지 경계를 동시에 통과한다.

1. **LLM structured output 타입** — Anthropic SDK + Pydantic으로 추출/생성된 객체.
2. **FastAPI request/response** — API 경계에서 직렬화/검증.
3. **DB ORM 모델의 source of truth** — SQLAlchemy 매핑이 Pydantic 스키마에서 파생.
4. **에디터 초기 상태** — React/Tiptap이 동일 객체를 받아 편집 가능한 형태로 로드.
5. **출력 렌더러 입력** — HWPX 빌더, PDF 어댑터가 동일 객체를 입력으로 받음.

이 5개 경계가 서로 다른 표현(JSON / DTO / DB row / 에디터 상태 / 렌더 모델)을 사용하면
다음 비용이 발생한다.

- 경계마다 변환 코드와 매핑 테이블 필요 — N개 경계에서 N(N-1)/2 변환쌍.
- 한 곳을 고치면 다른 곳이 silent 하게 깨진다 (특히 nullable / default 처리).
- LLM 출력이 DB 저장 시 lossy 하게 변형되면, 출력물이 LLM이 만든 것과 미세하게 달라지는
  드리프트가 발생.
- 다중 표현은 멀티테넌트 강제(`tenant_id` 누락 검증)를 한 곳에서 보장하기 어렵다.

선행 사례인 `~/workspace/exam-generator`는 이미 이 결정을 한 단계 적용해
`shared/schemas/question.py` 한 파일이 LLM / parser / renderer / FastAPI 4개 경계의
공유 모델로 동작한다. 본 프로젝트는 그 결정을 **DB 영속성 + 에디터 상태**까지 확장한다.

## Decision (결정)

`shared/schemas/`의 Pydantic v2 모델을 **시스템의 척추(spine)** 로 둔다.

핵심 규칙:

1. **위 5개 경계 모두 같은 Pydantic 모델을 직접 사용한다.**
   - SQLAlchemy ORM은 Pydantic 모델에서 파생하거나, 같은 필드 집합을 1:1 매핑한다.
     매핑 도구는 SQLAlchemy 2.x의 imperative mapping 또는 SQLModel/`pydantic-sqlalchemy`
     같은 검증된 어댑터를 채택 (직접 ORM 코드 손작성 지양 — CLAUDE.md §3.6).
   - LLM 호출은 `packages/llm/`이 Pydantic 모델을 그대로 structured output 스키마로 사용
     (Anthropic tool_use `input_schema=Model.model_json_schema()` 패턴, exam-generator
     `app/llm/anthropic.py`에서 검증된 패턴 그대로 재활용).
   - 에디터는 Pydantic 모델의 JSON 직렬화 결과를 받아 Tiptap 초기 상태로 사용.
   - HWPX/PDF 렌더러는 Pydantic 모델 인스턴스를 입력으로 받는다.

2. **모든 도메인 엔티티에 `tenant_id`를 처음부터 박는다.**
   - 인증은 stub이지만 스키마는 완전한 멀티테넌트.
   - Tenant/Workspace 외 모든 엔티티는 `tenant_id` 또는 `workspace_id`(transitive) 보유.

3. **Breaking change 최소화 원칙을 PR 단위로 강제.**
   - 새 필드 추가 위주.
   - 필드 제거 / 타입 변경은 ADR + 마이그레이션 계획을 동반한 PR로만 가능.
   - exam-generator의 v1 스키마와 1:1 호환 가능한 영역은 그대로 흡수
     (낮은 마이그레이션 비용 우선).

4. **스키마 진화는 전부 PR + ADR로 관리.**
   - `docs/adr/NNN-*.md`에 변경 사유 기록.
   - architect agent가 owner. domain-expert agent가 도메인 적절성 검토.

## Consequences (결과)

### 긍정적 결과

- **드리프트 0**: 한 객체가 5개 경계를 통과하므로 표현 불일치 자체가 발생하지 않는다.
- **단일 진실 원천**: LLM이 만든 것이 그대로 DB에 들어가고, 그대로 에디터에 뜨고, 그대로
  HWPX로 나간다. 사용자가 에디터에서 수정한 결과도 동일 객체로 다시 흐른다.
- **테스트 단순화**: Pydantic 모델 단위 테스트가 모든 경계의 계약을 동시에 보호.
- **멀티테넌트 enforcement**: `tenant_id` 누락은 Pydantic 검증 단계에서 잡히고 모든
  경계에 자동 전파.
- **LLM 출력 검증 무료**: structured output이 곧 도메인 모델이라 별도 변환 검증 불필요.

### 부정적 결과 / 비용

- **Pydantic 표현 한계 수용**: ORM-friendly한 표현(예: lazy loading, polymorphic
  inheritance)이 Pydantic의 평탄한 모델과 충돌할 수 있다. 우회는 SQLAlchemy 매핑 레이어가
  흡수하되, 도메인 모델은 ORM 편의에 굽히지 않는다.
- **에디터 상태와의 임피던스**: Tiptap의 ProseMirror JSON과 SyntaxAnnotation 모델 간
  변환 어댑터는 필요. Annotation의 span 식별 방식 결정에 따라 변환 비용이 결정됨
  (Open Question — `docs/schema-coverage-audit.md` §4 참조).
- **DB 마이그레이션 부담**: 스키마 변경마다 Alembic 마이그레이션이 필수. CI에서 PR마다
  마이그레이션 dry-run 권장.
- **LLM 호출의 schema 토큰 비용**: 스키마가 크면 매 호출 input 토큰이 늘어난다.
  대응: Phase별로 호출별 필요한 sub-schema만 노출하는 패턴 도입 (예: 추출 호출은
  `Passage`+`Question`만, 변형 호출은 `VariantQuestion`만 노출).

### 후속 결정 트리거

- **Open Question — DB 멀티테넌트 격리 방식 (row-level filter vs PostgreSQL RLS)**:
  Phase 4 진입 직전에 별도 ADR로 확정. 본 결정은 두 방식 모두와 호환.
- **Open Question — SQLAlchemy 매핑 도구 선정**: SQLModel / pydantic-sqlalchemy /
  imperative mapping 중 Sprint 0 backend-dev #3 작업에서 선택. CLAUDE.md §3.6 원칙에
  따라 PR에 대안 비교 기록 필수.
- **Open Question — Annotation span 식별 방식**: schema audit §4에 명시. Phase 1
  진입 전 별도 ADR.

## Alternatives Considered (검토한 대안)

### A. DTO 분리 (LLM DTO / API DTO / DB Entity / Render Model 각각 다른 클래스)

- 장점: 경계별로 최적화 가능. ORM 표현 자유도 높음.
- 단점: 변환 코드 폭증. 드리프트 발생. 멀티테넌트 enforcement가 분산되어 누락 위험.
- 기각 사유: 5개 경계가 본질적으로 같은 도메인 객체를 다루는데, 표현만 다른 비용을 정당화할
  도메인 차이가 없다.

### B. 도메인 모델 + ORM 모델 2계층 (Pydantic은 API 경계만, ORM은 별도)

- 장점: SQLAlchemy의 모든 기능 자유롭게 사용. ORM/Pydantic 라이브러리 모두 idiomatic.
- 단점: 두 모델 간 매핑이 boilerplate. LLM structured output 결과를 ORM에 넣을 때 변환
  단계 추가.
- 기각 사유: LLM 출력이 곧 도메인 객체라는 본 프로젝트의 가치 명제(콘텐츠 자산화)와
  맞지 않는다. 변환 단계에서 lossy 손실 발생 시 자산화 가치 훼손.

### C. JSON Schema 단일 source + Python/TypeScript codegen

- 장점: 백엔드/프론트엔드 동시 보장.
- 단점: codegen은 Pydantic의 풍부한 validator/computed_field 표현을 손실. 에디터/렌더러가
  Python 코드로 작성되므로 codegen 부담 대비 이득이 작음.
- 기각 사유: Pydantic v2가 이미 `model_json_schema()`로 LLM 어댑터에 그대로 전달 가능
  (CLAUDE.md §3.6 No Reinventing the Wheel). 별도 schema-first 도구 불필요.

## References

- `CLAUDE.md` §1.3 (콘텐츠 자산화 가치 명제), §3.1, §3.6, §6
- `docs/schema-coverage-audit.md` (exam-generator 스키마 audit)
- exam-generator `shared/schemas/question.py` (선행 사례)
- exam-generator `app/llm/anthropic.py` (Pydantic → Anthropic tool_use 패턴)
