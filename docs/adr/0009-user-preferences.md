# ADR 0009 — user_preferences 인프라 (사용자별 환경설정 영속화)

- **상태(Status)**: Accepted
- **작성일**: 2026-05-04
- **결정일**: 2026-05-04
- **작성자**: architect
- **결정자**: PM (Dennis)
- **채택안**: **C — 단일 ``user_preferences`` 테이블 + dot-notation key + JSONB value**
- **유형**: Phase 1 마감 사이클 인프라 ADR — 분석표 성분 preset / 색 팔레트 / 추후
  옵션의 백엔드 영속 + Phase 4 OAuth 호환 전제.
- **범위**: schema + ADR + 환경변수 stub 만. ORM / Alembic / 라우터 / 클라이언트
  코드는 후속 PR (C-2) 에서 backend-dev / frontend-dev 가 진행.
- **관련 문서**:
  - `CLAUDE.md` v0.7 §3.1 (canonical schema), §3.3 (멀티테넌트), §3.6 (No Reinventing
    the Wheel)
  - `docs/adr/0001-canonical-schema-philosophy.md` (시스템의 척추)
  - `apps/api/src/worksheet_api/repositories/tenant_context.py` (``user_id`` 주입)
  - `shared/schemas/user_preference.py` (본 ADR 의 결정을 닫는 도메인 모델)

---

## Context (배경)

### 1. PM 결정 배경

Phase 1 마감 사이클에서 사용자별 커스터마이징 요구가 누적됐다.

- **분석표 성분 preset**: 강사가 자주 쓰는 성분 라벨 (S / V / O / OC / SC / M ...) 을
  preset 으로 저장 → 에디터의 chip palette 에 노출.
- **색 팔레트**: 사용자가 선호하는 highlight 색 12개 중 즐겨쓰는 순서.
- **추후 옵션**: 에디터 레이아웃 / 폰트 크기 / 로고 / 컬러 프리셋 (Phase 2) — 미래
  옵션이 계속 추가될 게 자명.

PM 합의 사항:

1. **백엔드 영속** — localStorage 가 아니라 DB.
2. **Phase 4 OAuth 호환** — ``user_id`` 필드를 처음부터 박아두면 OAuth 진입 시 데이터
   마이그레이션 없이 사용자별 자동 분리.
3. **범용 key-value JSONB 모델** — 분석표 성분 preset 외에도 색 팔레트, 추후 옵션 등
   같은 모델 재사용.
4. **Phase 1 stub user**: 현재 OAuth 도입 전이라 ``MVP_USER_ID`` sentinel UUID 1개로
   모든 작업이 같은 ``user_preferences`` 행 공유. Phase 4 OAuth 도입 시 실제 ``sub``
   클레임 매핑.

### 2. 기존 멀티테넌트 stub 패턴 정합성

`tenant_context.py` 의 ``TenantContext`` 는 이미 ``user_id: uuid.UUID | None = None`` 필드를
보유 (ADR-0003 §D-3.6 의 Phase 4 OAuth 도입 준비). 단지 ``get_tenant_context()`` 에서
환경변수로 주입하는 로직만 추가하면 backward compatible 하게 ``user_id`` 가 흐른다.

기존 ``MVP_TENANT_ID`` / ``MVP_WORKSPACE_ID`` 패턴 그대로 ``MVP_USER_ID`` 를 도입한다.

---

## 옵션 비교

### A. 클라이언트 ``localStorage`` 만

- **구현**: 브라우저 ``localStorage`` 에 JSON 저장. 백엔드 영속 없음.
- **장점**: 구현 비용 0. 백엔드 인프라 / 마이그레이션 불요.
- **단점**:
  - 디바이스 / 브라우저 간 동기화 불가 — 와이프가 학원 PC ↔ 집 PC 다른 환경에서 같은
    preset 못 봄.
  - Phase 4 OAuth 도입 시 모든 사용자의 환경설정을 서버로 마이그레이션해야 함 — 사용자
    개입 (수동 export/import) 또는 첫 로그인 시 자동 sync 로직 필요. **마이그레이션
    비용 高**.
- **결론**: 탈락. PM 결정 #1 (백엔드 영속) 에 정면 반함.

### B. 도메인별 별 테이블 (``sentence_role_presets`` / ``color_palettes`` / ...)

- **구현**: 옵션마다 전용 테이블. 각 테이블에 ``tenant_id`` / ``user_id`` / ``workspace_id`` +
  도메인 전용 컬럼 (``presets: text[]`` / ``colors: text[]`` 등).
- **장점**:
  - DB 레벨 타입 안전성 — 각 컬럼이 정확한 타입.
  - SQL 쿼리 가독성 / 인덱스 / 통계 분석 시 도메인별 분리 깔끔.
- **단점**:
  - **미래 옵션 추가 시 매번 마이그레이션** — 새 옵션 (에디터 레이아웃 / 폰트 크기 /
    로고 등) 마다 새 테이블 + 새 ORM + 새 라우터 + 새 마이그레이션. PM 결정 #3 (범용
    모델) 의 본질 위반.
  - **반복 코드 누적** — 모든 도메인 테이블이 같은 구조 (tenant/user/workspace + value).
- **결론**: 탈락. 미래 옵션 추가 비용이 누적적으로 高.

### C. 단일 ``user_preferences`` 테이블 + dot-notation key + JSONB value (**채택**)

- **구현**:

  ```
  user_preferences
    id              uuid PK
    tenant_id       uuid NOT NULL FK
    user_id         uuid NOT NULL
    workspace_id    uuid NULL FK   -- 워크스페이스별 분리 옵션은 채움
    key             text NOT NULL  -- dot-notation
    value           jsonb NOT NULL
    created_at      timestamptz NOT NULL
    updated_at      timestamptz NOT NULL
    UNIQUE (tenant_id, user_id, workspace_id, key)
  ```

- **장점**:
  - **미래 옵션 추가 비용 0** — 새 key 정의 + 새 value Pydantic 모델만 추가, 마이그레이션
    없음. PM 결정 #3 의 본질.
  - **단일 repository / 단일 라우터** — 모든 옵션 도메인이 같은 CRUD 로직 공유.
  - **JSONB 의 schema 자유** — value 구조가 도메인마다 달라도 같은 컬럼.
- **단점**:
  - DB 레벨 타입 안전성 약화 — value 의 schema 강제는 application 레이어 (Pydantic)
    가 책임. ADR-0009 §value 검증 전략 으로 보강.
  - JSONB 인덱싱이 도메인 컬럼 인덱스보다 약함 — Phase 1 ~ Phase 3 의 환경설정 read 빈도
    가 낮아 성능 문제 없음 (사용자별 ~수 KB 데이터).
- **결론**: **채택**. 미래 확장 비용 0 + 범용성 + 운영 단순성.

### 평가 매트릭스

| 기준 | A: localStorage | B: 도메인별 별 테이블 | C: 단일 key-value 테이블 |
|---|---|---|---|
| PM 결정 #1 (백엔드 영속) | ❌ | ✅ | ✅ |
| PM 결정 #2 (Phase 4 OAuth 호환) | ❌ 마이그레이션 高 | ✅ | ✅ |
| PM 결정 #3 (범용성 / 미래 옵션) | ⚠️ schema 자유하나 영속 X | ❌ 옵션마다 마이그레이션 | ✅ 추가 비용 0 |
| PM 결정 #4 (Phase 1 stub user) | ⚠️ 사용자 분리 자체 없음 | ✅ ``user_id`` 컬럼 | ✅ ``user_id`` 컬럼 |
| DB 타입 안전성 | N/A | ✅ | ⚠️ application 레이어 책임 |
| 미래 옵션 추가 비용 | ✅ 0 | ❌ 마이그레이션 + 라우터 매번 | ✅ 0 |
| 인덱싱 / 쿼리 성능 | N/A | ✅ | ⚠️ Phase 1~3 환경설정 빈도 낮아 무관 |

---

## Decision (결정)

### D1. 채택안 C — 단일 ``user_preferences`` 테이블

도메인 모델은 ``shared/schemas/user_preference.py`` 의 ``UserPreference`` /
``UserPreferencePatchInput`` / value schema 1예시 (``SentenceRolePresetValue``).

ORM / Alembic 마이그레이션 / 라우터는 후속 PR C-2 에서 backend-dev 가 진행 — 본 ADR
은 schema + ADR + 환경변수 stub 까지만.

### D2. key 명명 규칙 — dot-notation ``<domain>.<scope>``

- **형식**: ``<domain>.<scope>`` 또는 ``<domain>.<scope>.<sub>``. 영문 소문자 + 숫자
  + ``_`` 만 허용. 각 segment 는 영문자로 시작. 최소 2 segment. 최대 길이 128자.
- **도메인 prefix 가 충돌 방지**:
  - ``preset.*`` — 사용자 preset (성분 / 변형 유형 등).
  - ``palette.*`` — 색 팔레트.
  - ``editor.*`` — 에디터 환경설정 (레이아웃, 폰트, 단축키 등).
- **신규 key 추가 시**: 별 Pydantic value schema 정의 권장 (예시:
  ``SentenceRolePresetValue``). 검증 없이 임의 dict 만 저장하면 silent drift 위험.
- **regex**: ``^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`` (Pydantic field_validator 강제).
- **규칙 변경**: ADR-0009 갱신 + 마이그레이션 동반.

예시 — 본 PR 에서 정의 / 시연한 key:

| key | value schema | 의미 |
|---|---|---|
| ``preset.sentence_role`` | ``SentenceRolePresetValue`` | 성분 라벨 preset 리스트 |

후속 추가 예정 (PR C-2 / Phase 2):

| key | 의미 |
|---|---|
| ``palette.colors`` | 색 팔레트 즐겨쓰기 순서 |
| ``editor.layout`` | 에디터 레이아웃 (1단/2단 등) |
| ``editor.font_size`` | 에디터 폰트 크기 |

### D3. value 검증 전략

- 본 도메인 모델 ``UserPreference.value`` 는 ``dict[str, Any]`` — JSONB 자유 형식.
- API 라우터 / repository 가 ``key`` 에 따라 적절한 Pydantic 모델 (예:
  ``SentenceRolePresetValue``) 로 ``model_validate(value)`` 호출. 검증 실패 시 422
  Unprocessable Entity (FastAPI 표준).
- key → value Pydantic 모델 매핑은 라우터 (PR C-2) 가 dict 또는 dispatch 함수로 관리.
- DB 컬럼 자체는 ``jsonb NOT NULL`` — schema 강제는 application 레이어 책임.

### D4. ``workspace_id`` Optional — 테넌트 전역 / 워크스페이스별 옵션 공존

- 워크스페이스별 분리가 필요한 옵션 (예: 학년별 다른 색 팔레트) 은 ``workspace_id``
  채움.
- 테넌트 전역 옵션 (예: 사용자 개인 favorite preset 모음) 은 ``workspace_id == NULL``.
- 본 엔티티는 ``WorkspaceScopedEntity`` 가 아니라 ``TenantScopedEntity`` 를 베이스로
  하고 ``workspace_id`` 를 직접 Optional 필드로 박는다 (``shared/schemas/common.py``
  의 기존 mixin 과 다름 — 의도적).
- DB UNIQUE 제약은 ``UNIQUE(tenant_id, user_id, workspace_id, key)`` — PostgreSQL
  의 NULL 동등 처리 정책 (NULL ≠ NULL) 때문에 ``workspace_id IS NULL`` 행은 같은
  tenant/user/key 로 1행만 갖도록 별 조건부 unique 인덱스 필요. 마이그레이션 시 PR
  C-2 에서 처리:

  ```sql
  CREATE UNIQUE INDEX user_preferences_unique_tenant_global
    ON user_preferences (tenant_id, user_id, key)
    WHERE workspace_id IS NULL;

  CREATE UNIQUE INDEX user_preferences_unique_workspace
    ON user_preferences (tenant_id, user_id, workspace_id, key)
    WHERE workspace_id IS NOT NULL;
  ```

### D5. Phase 1 stub user — ``MVP_USER_ID`` sentinel UUID

- ``apps/api/src/worksheet_api/config.py`` 의 ``Settings`` 에 ``mvp_user_id: str``
  추가. 기본값: ``"00000000-0000-0000-0000-000000000003"`` (sentinel UUID — 기존
  ``MVP_TENANT_ID`` / ``MVP_WORKSPACE_ID`` 와 같은 패턴, 끝자리 ``001`` / ``002`` /
  ``003`` 순).
- ``TenantContext.user_id`` 는 이미 ``uuid.UUID | None = None`` 필드 보유 — 본 PR
  에서 ``get_tenant_context()`` 가 환경변수에서 읽어 채워주는 로직만 추가
  (backward compatible — ``user_id`` 를 사용 안 하는 기존 라우터/repository 는 영향
  없음).
- ``.env.example`` 에 ``MVP_USER_ID`` 라인 추가.

### D6. Phase 4 마이그레이션 — stub UUID → OAuth ``sub``

Phase 4 OAuth 도입 시 마이그레이션 시나리오:

1. **방안 1 — 첫 로그인 시 transfer**: stub UUID 의 ``user_preferences`` 행을 첫 OAuth
   로그인하는 사용자의 실제 ``user_id`` 로 transfer (UPDATE WHERE user_id = stub_uuid).
   장점: 와이프의 기존 preset 자동 보존. 단점: 동시 사용자 2명 이상이면 누가 가져갈지
   결정 필요.
2. **방안 2 — drop**: stub 데이터는 폐기. 사용자가 OAuth 로그인 후 처음부터 다시 설정.
   장점: 단순. 단점: 사용자 경험 저하.
3. **방안 3 — admin 도구로 manual map**: PM (Dennis) 가 admin 도구로 stub UUID ↔ 실제
   user_id 매핑 결정.

**Phase 1 시점의 결정**: 채택 보류. Phase 4 진입 시 별 ADR (또는 본 ADR 갱신) 으로 결정.
Phase 1 ~ Phase 3 은 단일 사용자 (와이프) 환경이라 사실상 방안 1 + 1명 = 단순 transfer.

### D7. ``UserPreferencePatchInput`` (PATCH body DTO) 의 server-side 컨텍스트 제외

API 입력 DTO 에 ``tenant_id`` / ``user_id`` 가 **없는 것은 의도** — 클라이언트가 임의의
tenant/user 로 위장하는 것을 데이터 모델 레벨에서 차단 (ADR-0001 §"멀티테넌트 함정"
가드레일). 라우터가 ``TenantContext`` Depends 로 주입.

``key`` 도 body 에 없다 — path param ``PATCH /preferences/{key}`` 으로 노출. body 에
``key`` 가 들어와도 ``extra="forbid"`` 가 거절.

``UserPreferencePatchInput`` 의 필드는 ``value`` (필수) + ``workspace_id`` (Optional) +
``version`` (Optional, ADR-0009 §D8). ``model_config = ConfigDict(extra="forbid")`` 로
``tenant_id`` / ``user_id`` / ``key`` 가 들어오면 즉시 422 거절.

**이력 (PR C-2 후속)**: 본 ADR 초안은 ``UserPreferenceInput`` (key 포함) 으로 시작했으나
PR C-2a 라우터 구현 시 ``key`` 가 path param 으로 결정되어, schema 후속 PR 에서 PATCH
body 형태에 맞춰 ``UserPreferencePatchInput`` (key 제거 + version 추가) 으로 재정의.
``apps/api`` 의 ``PreferencePatchRequest`` 는 본 DTO 로 통합.

### D8. 낙관적 동시성 — ``version`` 필드

같은 사용자가 다른 탭/디바이스에서 동시 PATCH 시 lost update 를 방지하기 위해 행마다
``version: int`` (default 1) 를 둔다.

**흐름**:
1. 클라이언트가 ``GET /preferences/{key}`` → 응답에 현재 ``version`` 포함.
2. 클라이언트가 PATCH body 에 ``version`` echo (같은 값).
3. 서버가 DB 의 현재 ``version`` 과 비교:
   - **일치**: ``version + 1`` 로 갱신, 200 응답.
   - **불일치**: 409 Conflict (다른 탭/디바이스가 먼저 갱신함). 클라이언트는 다시 GET
     해서 머지 후 재시도.
4. **최초 생성 분기** (DB 행이 없는 상태): ``version`` 검사 안 함. ``None`` 또는 임의 값
     수용. 첫 행은 ``version=1`` 로 생성.

**필드 정책**:
- ``UserPreference.version`` — ``int, default=1, ge=1``. 응답 직렬화 시 클라이언트가 echo.
- ``UserPreferencePatchInput.version`` — ``int | None, default=None, ge=1``. None 이면
  최초 생성 의미 (DB 행 없을 때만 정상). 행이 있는 상태에서 None 이 들어오면 409.

**왜 ge=1**: 0 또는 음수 ``version`` 은 의미 없음 (낙관적 동시성 카운터는 1부터). schema
레벨에서 차단해 silent drift 방지.

**대안 검토**:
- ``updated_at`` 비교 — 시계 동기화 이슈 / 마이크로초 충돌. 정수 카운터가 더 단순.
- ETag/If-Match — HTTP 표준이지만 본 도메인에선 over-engineering. JSON body 로 충분.

---

## Consequences (결과)

### 긍정적 결과

1. **미래 옵션 추가 비용 0** — 새 key + 새 value Pydantic 모델만 추가.
2. **Phase 4 OAuth 호환** — ``user_id`` 가 stub 단계부터 박혀 마이그레이션 단순.
3. **단일 repository / 단일 라우터** — 운영 / 테스트 단순.
4. **``TenantContext`` 확장이 backward compatible** — 기존 라우터 / repository 영향
   없음.

### 부정적 결과 / 리스크

1. **DB 타입 안전성 약화** — value 의 schema 강제는 application 레이어 책임. silent
   drift 위험은 ``UserPreference.value`` 별 Pydantic 모델 검증으로 보강 (D3).
2. **JSONB 쿼리 효율** — 환경설정 read 빈도 낮아 Phase 1 ~ Phase 3 에서 무관. Phase 4
   다중 사용자 / 분석 쿼리 늘어나면 GIN 인덱스 도입 검토.
3. **Phase 4 마이그레이션 정책 미정** — D6 의 3가지 방안 중 채택 보류. Phase 4 진입 시
   결정.

### 후속 작업 (별 PR)

- **PR C-2** (backend-dev / frontend-dev):
  - ORM 모델 (``apps/api/.../models/user_preference.py``).
  - Alembic 마이그레이션 (``user_preferences`` 테이블 + 조건부 unique 인덱스).
  - Repository 레이어 (``UserPreferenceRepository``) + ``TenantContext`` 의 ``user_id``
    필터.
  - 라우터 (``GET / PUT /user-preferences/{key}`` 또는 batch CRUD — UX 결정 후속).
  - 클라이언트 React 통합 (``apps/web/``).
- **CLAUDE.md / phase-1-backlog.md 갱신**: PR C-2 머지 시점에 일괄 (본 task 범위 밖).

---

## 결정 기록

| 날짜 | 상태 | 결정자 | 비고 |
|---|---|---|---|
| 2026-05-04 | Proposed | architect | Phase 1 마감 사이클 — PM 결정 4건 (영속 / OAuth 호환 / 범용 / stub) 정리 |
| 2026-05-04 | Accepted | PM (Dennis) | 채택안 C — 단일 key-value 테이블 + dot-notation key + JSONB value. PR C-2 진입. |
| 2026-05-05 | Amended | architect | §D7 DTO 재정의 (``UserPreferenceInput`` → ``UserPreferencePatchInput``: key 제거 + version 추가) + §D8 낙관적 동시성 신규. PR C-2a 라우터 구현과 정합. 아키텍처 결정 자체는 불변 (단일 테이블 / dot-notation / JSONB). |
