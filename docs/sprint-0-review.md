# Sprint 0 코드 리뷰

- **리뷰어**: code-reviewer agent
- **작성일**: 2026-05-02
- **상태**: CRITICAL 발견 없음

## 1. 리뷰 대상

- **범위**: `4a6cfb4..5aa4720` (Sprint 0 전체)
- **머지된 commit 11개**:
  - `5aa4720` chore(settings): 자주 쓰는 dev 명령 자동 허용 정책 추가
  - `9b47e2f` feat(db): SQLAlchemy 모델 + Alembic 초기 마이그레이션
  - `da2e5f3` feat(api): FastAPI skeleton + Docker Compose 설정
  - `6fc1406` fix(ruff): FastAPI Depends/Query 등을 B008 예외로 등록
  - `2c28ee6` docs: exam-generator 스키마 audit 보고서 + canonical schema ADR 추가
  - `10cb793` feat(editor): Tiptap PoC — highlight extension + JSON 직렬화
  - `3110918` feat(web): Vite + React 19 + 라우팅 골격 + Tailwind
  - `bef0868` fix(pre-commit): tsconfig/biome JSONC를 check-json 대상에서 제외
  - `a483382` chore: .gitignore에 .claude/worktrees/ 추가
  - `91ff9ed` chore(agents): architect/domain-expert에 Bash 도구 권한 부여
  - `a459e8b` chore: Sprint 0 #1 — 새 repo 부트스트랩

## 2. 종합 평가

Sprint 0 산출물은 **Phase 0 진입 조건을 대체로 충족**한다. 프로젝트 뼈대(uv/pnpm workspace, pre-commit hook), FastAPI skeleton과 health check 엔드포인트, DB 모델 + Alembic 마이그레이션, Tiptap PoC, architect audit 문서가 CLAUDE.md §9의 작업 항목 DoD에 부합한다. CRITICAL 이슈(시크릿 노출, 멀티테넌트 격리 파괴, 의존성 방향 위반)는 없다. 단, `shared/schemas/`가 아직 비어 있어 Sprint 0 작업 #5가 완료되지 않은 상태이며, 이는 Phase 0 전체 DoD 충족을 위한 잔여 작업임을 명시한다. Docker Compose 실 구동 검증이 완료되지 않은 점(Sprint 0 DoD #2의 "Docker compose 로컬 실행" 요건)은 MAJOR로 분류한다.

## 3. CRITICAL 발견 (즉시 처리 필요)

없음.

## 4. MAJOR 발견 (#5 진입 전 처리 권고)

### M-1. `shared/schemas/`가 비어 있음 — Sprint 0 DoD 미완

CLAUDE.md §9 표에서 Sprint 0 작업 #5 ("architect — 콘텐츠 모델 v0.1 PR, `shared/schemas/` 1차 정의")가 머지되지 않았다. `shared/schemas/` 디렉토리 자체는 존재하지만 `passage.py`, `question.py`, `annotation.py`, `worksheet.py`, `tenant.py` 파일이 없다. Phase 0 DoD("shared/schemas/에 Passage, Question, Vocabulary, Translation, SyntaxAnnotation, Worksheet 등 1차 정의 완료")의 전제 조건이 미충족이다.

- **위치**: `shared/schemas/` (파일 없음)
- **영향**: Phase 0 파이프라인 구현(backend-dev) 착수 불가. `apps/api/src/worksheet_api/models/tenant.py`의 ORM 모델이 Pydantic source of truth와 연결되지 못한 채 placeholder 상태임.
- **권고 액션**: architect agent — Sprint 0 작업 #5 PR을 즉시 제출. domain-expert의 audit 코멘트(`docs/schema-coverage-audit.md` §7) 중 작업 #5 진입에 필요한 항목(특히 §4-1 Passage 메타 v0.1 필수 필드, §4-2 Translation 1:1 vs 1:N)을 먼저 결정하고 진행.

### M-2. Docker Compose 실 구동 검증 미완 — Sprint 0 DoD #2 위반 가능

Sprint 0 작업 #2의 DoD는 "Docker compose 로컬 실행"이다. Docker daemon이 동작하지 않아 실제 실행 검증이 이루어지지 않은 채 머지된 것으로 판단된다. `docker-compose.yml`의 구조는 이상 없으나, `api` 서비스 Dockerfile에서 `uv sync --frozen`이 `uv.lock`을 필요로 하는데 이 lock 파일이 실제로 커밋됐는지, 또한 Alembic 마이그레이션 실행 단계가 진입점(CMD)에 없다는 점도 미검증 상태다.

- **위치**: `docker-compose.yml`, `apps/api/Dockerfile`
- **영향**: 팀원이 처음 클론할 때 `docker compose up` 실패 위험. Alembic 마이그레이션이 앱 기동 전에 자동으로 실행되지 않으므로 DB 스키마 불일치 가능성.
- **권고 액션**: backend-dev — Docker daemon이 가용한 환경에서 `docker compose up --build` 를 실제로 실행하고 health check까지 통과하는 것을 검증 후 결과를 PR 또는 README에 기록. Dockerfile CMD에 Alembic `upgrade head` 실행 단계 추가 여부도 결정 필요 (entrypoint 스크립트 vs 별도 init container).

### M-3. `datetime.utcnow` deprecated 사용 — Python 3.12 경고

`apps/api/src/worksheet_api/models/tenant.py` 37, 43, 80, 84행에서 `default=datetime.utcnow`를 사용하고 있다. `datetime.utcnow()`는 Python 3.12에서 deprecated이며, timezone-aware datetime을 반환하지 않아 `DateTime(timezone=True)` 컬럼과 의미론적 불일치가 있다. 올바른 방법은 `default=lambda: datetime.now(tz=timezone.utc)` 또는 DB 측 `server_default=func.now()`를 사용하는 것이다.

- **위치**: `apps/api/src/worksheet_api/models/tenant.py:37`, `43`, `80`, `84`
- **영향**: timezone-naive datetime이 timezone-aware 컬럼에 입력됨. asyncpg가 경고 또는 에러를 발생시킬 수 있음. Python 3.13+에서 제거 예정.
- **권고 액션**: backend-dev — `from datetime import datetime, timezone` 후 `default=lambda: datetime.now(tz=timezone.utc)`로 교체. 또는 SQLAlchemy `server_default=func.now()`로 DB 측에서 처리.

### M-4. `.env.example`의 `SECRET_KEY`와 `POSTGRES_PASSWORD` 기본값이 실사용 가능한 값

`.env.example:8`의 `POSTGRES_PASSWORD=worksheet`와 `:27`의 `SECRET_KEY=change-me-in-production`은 예제 파일이지만 실제 개발 환경에서 그대로 복사해 쓰기 쉬운 값이다. 특히 `SECRET_KEY`는 Phase 4에서 JWT 서명에 사용 예정이므로, 예제 파일에서도 빈 값이거나 `<replace-with-strong-random-secret>` 형태의 명확한 placeholder여야 한다. `docker-compose.yml:8`에서 `POSTGRES_PASSWORD:?POSTGRES_PASSWORD 환경변수를 설정하세요`로 강제하는 패턴은 좋으나, `.env.example`에서 `worksheet`라는 값이 제공되어 있어 강제가 우회될 수 있다.

- **위치**: `.env.example:8`, `.env.example:27`
- **영향**: CRITICAL 수준은 아님(예제 파일이므로). 그러나 개발자가 복사 후 수정을 잊으면 프로덕션에 약한 시크릿이 배포될 수 있음.
- **권고 액션**: backend-dev — `SECRET_KEY` 값을 빈 문자열이나 `CHANGE_ME_REPLACE_WITH_STRONG_RANDOM_SECRET`으로 교체. `POSTGRES_PASSWORD`도 동일하게 명확한 placeholder로 변경.

### M-5. `HealthResponse` 모델이 `shared/schemas/`가 아닌 라우터 내부에 정의됨

`apps/api/src/worksheet_api/routers/health.py:18`에서 `HealthResponse(BaseModel)`을 직접 정의하고 있다. 현재는 내부 전용 응답 모델이라 도메인 타입은 아니지만, ADR 0001의 canonical schema 원칙("FastAPI request/response도 Pydantic 모델로")에 따르면 위치를 일관되게 관리할 필요가 있다. Phase 0에서 다른 라우터들이 추가되면 각자 모델을 직접 정의하는 패턴이 정착될 위험이 있다.

- **위치**: `apps/api/src/worksheet_api/routers/health.py:18`
- **영향**: 지금은 문제없으나, 나중에 도메인 모델이 라우터에 흩어지는 선례가 될 수 있음.
- **권고 액션**: backend-dev — `HealthResponse`는 도메인 타입이 아닌 API 응답 DTO이므로 `apps/api/src/worksheet_api/schemas/health.py`나 `routers/health.py` 내 유지는 허용 가능. 단, Phase 0에서 Passage/Question 응답 모델이 추가될 때 라우터에 직접 정의하지 않도록 컨벤션을 README 또는 CLAUDE.md에 명시할 것.

## 5. MINOR 발견 (다음 sprint 정리)

### N-1. `HighlightMark` 적용/해제 단위 테스트 미작성

`apps/web/tests/editor-poc.test.tsx`의 주석(`tests/editor-poc.test.tsx:1~13`)에 "jsdom 환경에서 텍스트 선택(Selection API) + 마크 적용이 불안정하므로 하이라이트 적용 자체는 수동 검증"이라고 명시되어 있다. 현재 테스트 5개는 마운트, 초기 텍스트, JSON 직렬화, JSON 구조, 홈 링크만 검증하며, highlight mark의 실제 mark 구조(`{ type: "highlight", attrs: { color: "#fef08a" } }`)가 직렬화 JSON에 있는지 검증하는 케이스가 없다. jsdom에서 불안정한 이유는 Selection API 비지원이나, `editor.commands.setHighlight()` + `getJSON()` 방식으로는 Selection 없이도 mark 적용이 가능하므로 테스트 가능하다.

- **위치**: `apps/web/tests/editor-poc.test.tsx`
- **권고 액션**: frontend-dev — Phase 1 진입 전에 `editor.chain().setTextSelection({ from: 5, to: 12 }).toggleHighlight({ color: '#fef08a' }).run()` 방식으로 Selection API 없이 mark를 강제 적용하는 테스트 케이스 추가.

### N-2. pre-commit의 `check-json` exclude 패턴이 biome.json을 전역으로 제외

`.pre-commit-config.yaml:11`의 exclude 패턴 `^(.*/)?(tsconfig.*\.json|biome\.json|\.vscode/.*\.json)$`이 경로에 무관하게 `biome.json` 파일명 자체를 모두 제외한다. 악의적 또는 실수로 `biome.json`이라는 이름으로 다른 용도의 JSON이 생기더라도 검사가 생략된다. 현실적 위험은 낮지만 패턴이 과도하게 넓다.

- **위치**: `.pre-commit-config.yaml:11`
- **권고 액션**: backend-dev — 필요하다면 `^(apps/web|packages/editor)/biome\.json$` 처럼 실제 경로로 좁히는 것을 검토. 현재는 수용 가능 수준.

### N-3. `packages/editor`의 `package.json`에 build 스크립트 없음

`packages/editor/package.json`에는 `test`, `lint`, `typecheck` 스크립트만 있고 `build` 스크립트가 없다. `main`과 `exports`가 `./src/index.ts` (TypeScript 소스)를 직접 가리키고 있어, pnpm workspace 내부에서는 vite의 TypeScript 처리로 동작하지만 향후 publish나 외부 패키지로 분리할 때는 build step이 필요하다.

- **위치**: `packages/editor/package.json:7~10`
- **권고 액션**: frontend-dev — Phase 1 에디터 extensions 추가 시 vite library mode build 스크립트 추가 검토.

### N-4. `Settings.mvp_tenant_id`가 `str` 타입 (UUID 타입이 더 적절)

`apps/api/src/worksheet_api/config.py:29`에서 `mvp_tenant_id: str`로 선언되어 있다. DB 모델과 Pydantic 스키마에서 `tenant_id`는 `uuid.UUID`이므로 설정 로드 시점에 UUID로 파싱하는 것이 일관성에 맞다. 현재는 직접 사용하는 코드가 없어 문제가 없지만, 후속 PR에서 `str(settings.mvp_tenant_id)`를 `UUID(settings.mvp_tenant_id)`로 변환하는 것을 잊으면 타입 오류가 런타임에 발생한다.

- **위치**: `apps/api/src/worksheet_api/config.py:29`
- **권고 액션**: backend-dev — `from uuid import UUID`를 추가하고 `mvp_tenant_id: UUID = UUID("00000000-0000-0000-0000-000000000001")`로 변경.

## 6. NIT (의견 / 스타일)

### NIT-1. `except Exception` broad catch — 상세 로깅 없음

`apps/api/src/worksheet_api/routers/health.py:41`의 `except Exception:` catch는 DB 연결 실패 원인을 로그에 남기지 않는다. 운영 중 `db=unreachable`이 발생해도 원인(연결 timeout인지, 인증 실패인지, DNS 오류인지) 파악이 불가능하다. 구조상 크게 문제는 아니나, `logger.warning("DB health check failed: %s", exc)`라도 추가하면 디버깅 편의성이 높아진다.

- **위치**: `apps/api/src/worksheet_api/routers/health.py:41~42`

### NIT-2. `EditorPoc`의 `INITIAL_CONTENT`가 하드코딩된 예시 문장

`apps/web/src/pages/EditorPoc.tsx:34`의 초기 문장이 하드코딩되어 있다. PoC이므로 문제없으나, Phase 1에서 실제 Passage를 에디터에 로드할 때 이 상수를 삭제하는 것을 잊지 않도록 `// TODO(Phase 1): Passage 객체로 대체` 주석을 달아두는 것을 권고한다.

### NIT-3. Conventional Commits 형식 일부 미준수

`2c28ee6` 커밋(`docs: exam-generator 스키마 audit 보고서 + canonical schema ADR 추가`)의 scope가 없다. CLAUDE.md §8.1은 `type(scope): description` 형식을 명시한다. `docs(architect):` 또는 `docs(schema):` 처럼 scope를 붙이는 것이 일관성에 맞다. 머지 후 규칙이므로 이번엔 소급 적용 불필요하나 이후 커밋에서 준수 요망.

## 7. 체크리스트별 상세

### 7.1 canonical schema

**상태: 부분 미충족 (MAJOR M-1)**

`shared/schemas/` 디렉토리가 존재하지만 내부 파일이 없다. Sprint 0 작업 #5 (architect agent)가 미완이다. 현재 `apps/api/src/worksheet_api/models/tenant.py`의 `Tenant`, `Workspace` ORM 모델은 명시적으로 "architect 작업 #5 완료 전까지 placeholder"임을 주석으로 밝히고 있어 의도된 임시 상태임은 확인됐다. `HealthResponse`가 라우터 내에 정의된 것은 도메인 타입이 아니므로 위반으로 보지 않지만, 향후 패턴으로 정착되지 않도록 주의가 필요하다 (MAJOR M-5).

### 7.2 멀티테넌트

**상태: 양호 (구조적 준비 완료)**

- `Workspace` 테이블에 `tenant_id` FK + `ix_workspaces_tenant_id` 단일 인덱스가 박혀 있다 (`apps/api/src/worksheet_api/models/tenant.py:65`).
- `ondelete="CASCADE"` 정책이 설정되어 있다 (`tenant.py:72`).
- `Settings.mvp_tenant_id`로 Phase 4 이전 단일 테넌트 stub이 준비되어 있다.
- 현재 단계에서 실제 쿼리 코드가 없으므로 tenant_id 필터 누락 여부는 해당 없음 (N/A).
- architect audit(`docs/schema-coverage-audit.md` §5)에 repository 패턴 강제 설계가 명시됐다. Phase 0 구현 시 이를 반드시 따를 것.
- `Tenant` 모델 자체는 `tenant_id` FK를 갖지 않는 것이 설계상 정상이다.

### 7.3 시크릿

**상태: 양호 (MAJOR M-4 주의 필요)**

- `.gitignore`에 `.env`, `.env.local`, `.env.*.local`, `*.pem`, `*.key`가 모두 포함됨 (`.gitignore:37~39`).
- `detect-private-key` pre-commit hook이 활성화되어 있다 (`.pre-commit-config.yaml:15`).
- `docker-compose.yml`에서 시크릿이 빌드 이미지에 ARG로 박히는 패턴은 없다. 환경변수는 `environment:` 섹션을 통해 런타임에 주입된다.
- `.env.example`의 `POSTGRES_PASSWORD=worksheet`와 `SECRET_KEY=change-me-in-production`은 실제 값처럼 보이는 placeholder로 교체를 권고한다 (MAJOR M-4).
- `alembic/env.py:39`에서 DATABASE_URL이 환경변수에서만 로드되고 설정 파일에 박히지 않는 패턴은 올바르다.
- `.claude/settings.json`의 deny 규칙에 `Read(.env)`, `Read(.env.local)` 등이 있어 시크릿 파일 읽기를 차단한다.

### 7.4 LLM 호출

**N/A** — Sprint 0 범위에 LLM 호출 코드 없음.

### 7.5 테스트

**상태: 부분 충족 (MINOR N-1)**

FastAPI:
- `apps/api/tests/test_health.py`에 3개 테스트(정상/DB unreachable/응답 스키마 검증)가 있다. DB unreachable case가 명시적으로 커버됨. config 단위 테스트는 없으나 `get_settings()`가 `lru_cache` 싱글턴이고 pydantic-settings가 검증을 담당하므로 별도 테스트가 없어도 현 단계에선 허용 수준.

Frontend:
- `apps/web/tests/editor-poc.test.tsx`에 5개 테스트가 있다. highlight mark 적용/해제의 직렬화 결과 검증이 빠져 있다 (MINOR N-1). 파일 주석에서 "수동 검증"이라고 밝히고 있으나, Selection API 없이도 자동화 가능하다.

### 7.6 네이밍/구조 일관성

**상태: 양호**

- Python 패키지명: `worksheet_api` (snake_case). CLAUDE.md 명시 없으나 Python 컨벤션 준수.
- Node 패키지명: `@english-worksheet-tool/web`, `@english-worksheet-tool/editor` — scoped package 방식으로 일관성 있음.
- 디렉토리 구조가 CLAUDE.md §5와 대체로 일치한다. `admin/data_collector/`, `admin/eval/`, `packages/extractor/`, `packages/llm/`, `packages/hwpx_renderer/`는 아직 비어있으나 구조는 잡혀 있다.
- `apps/api/src/worksheet_api/routers/` vs `apps/api/src/worksheet_api/routes/` — 현재 `routers/`를 사용하고 있다. `main.py:8`에서 `from worksheet_api.routers import health`로 일관됨.

### 7.7 의존성 방향

**상태: 양호**

- `apps/web/`이 `@english-worksheet-tool/editor`(pnpm workspace)를 의존하는 방향은 올바르다. (`apps/web/package.json:17`)
- `packages/editor/`가 `apps/web/`을 역참조하는 import는 없다.
- `shared/`는 현재 비어있으므로 다른 곳을 import할 수 없다. `shared/pyproject.toml`의 의존성은 `pydantic>=2.0.0`만 있어 leaf 조건 충족.
- `apps/`가 `admin/`을 import하는 코드는 없다.
- `alembic/env.py`가 `worksheet_api.models`를 import하는 것은 의도된 구조이며 위반 아님.

### 7.8 No Reinventing the Wheel

**상태: 양호 (CLAUDE.md §3.6 준수)**

각 신규 의존성의 대안 검토 기록:
- `ruff` (`.pre-commit-config.yaml:18~19`): "black+flake8+isort 조합 vs ruff — ruff가 단일 도구로 모두 대체, 속도 10~100배 빠름" 기록됨.
- `biome` (`.pre-commit-config.yaml:27~28`): "eslint+prettier vs biome — biome이 단일 바이너리로 통합, 속도 빠름" 기록됨.
- `pydantic-settings` (`apps/api/pyproject.toml:11`): "python-dotenv 단독 사용은 Pydantic 통합이 없어서 탈락" 기록됨.
- `sqlalchemy+asyncpg` (`apps/api/pyproject.toml:13`): "databases 라이브러리는 SQLAlchemy 생태계(Alembic)와 통합이 약해서 탈락" 기록됨.
- `httpx` (`apps/api/pyproject.toml:25~27`): "requests 대신 httpx를 선택한 이유는 ASGITransport가 httpx에만 있어서" 기록됨.
- `HighlightMark` (`packages/editor/src/extensions/highlight.ts:1~13`): "@tiptap/extension-highlight 공식 채택 이유 + 직접 구현 기각 이유" 기록됨.
- `Dockerfile` (`apps/api/Dockerfile:4`): "python:3.12-alpine은 glibc 미포함으로 asyncpg 빌드가 복잡해서 탈락" 기록됨.

`react-router-dom`, `tailwindcss`의 대안 검토 기록은 commit message나 코드 주석에 없다. CLAUDE.md §8.4의 요건상 누락이지만, 이 두 라이브러리는 이미 CLAUDE.md §4 기술 스택 표에 확정된 선택이므로 PR 단위 재검토 생략이 합리적이다.

## 8. Sprint 0 특수 항목

### 8.1 architect audit의 Open Question 9개 적절성

`docs/schema-coverage-audit.md` §8.2 표에 9개의 Open Question이 명시되어 있다. 이 중 작업 #5 진입 전 결정 가능한 것과 아닌 것을 구분하면:

- **작업 #5에서 결정 (architect + domain-expert)**: §4-1 Passage 메타 v0.1 필수 필드, §4-2 Translation 1:1 vs 1:N, §4-7 Workspace v0.1 필요성. 이 3개는 작업 #5 PR 작성 전에 domain-expert 의견을 받아야 진행 가능.
- **Phase 1 진입 전 ADR**: §4-4 Annotation span 식별 방식, §4-6 마커/텍스트 분리. 이 2개는 Tiptap PoC(작업 #7)의 직렬화 메모(`apps/web/src/pages/EditorPoc.tsx:14~24`)가 중요한 근거를 제공한다.
- **Phase 3 진입 전 ADR**: §4-3, §4-5, §4-8, §4-9.

9개 모두 적절한 시점에 배정되어 있으며, PM에게 던지는 질문 분량이 과도하지 않다. 단, §4-1, §4-2, §4-7은 작업 #5 차단 요소이므로 **PM과 domain-expert가 1주 내 응답**해야 Sprint 0가 완결된다.

### 8.2 Tiptap PoC의 architect Open Question §4-4 기여

`apps/web/src/pages/EditorPoc.tsx:14~24`의 "architect에게 전달 메모"에 ProseMirror 직렬화 방식이 명확히 기록되어 있다: "character offset이 아닌 doc > content[] 트리 구조", "SyntaxAnnotation 변환 시 누적 순회 로직이 필요". 이는 architect의 §4-4 character offset 권고안(audit §4.2)에 대한 concrete evidence를 제공한다. ProseMirror position을 저장 시 character offset으로 변환하는 어댑터가 필요하다는 판단을 지지하는 근거다. **Phase 1 진입 전 ADR 작성 시 이 메모를 참조해야 한다.**

### 8.3 settings.json의 allow/deny 정책 실효성

`.claude/settings.json`의 deny 규칙을 검토한다:

- `Bash(rm -rf /*)`: 절대 경로 루트 삭제 차단. 유효.
- `Bash(rm -rf ~*)`: 홈 디렉토리 삭제 차단. 유효.
- `Bash(rm -rf $HOME*)`: `$HOME` 변수 확장 패턴 차단. 유효.
- `Bash(rm -rf ..*)`: 상위 디렉토리 삭제 차단.

그러나 다음 변형 패턴이 allow 측에서 허용된다:
- `Bash(rm -rf node_modules)`: node_modules만 대상이지만 절대 경로로 `/path/to/important/node_modules`가 아닌 경우를 가정한다.
- `Bash(rm -rf dist)`: `dist/`만 허용. 이건 괜찮다.
- `Bash(mv *)`, `Bash(cp *)`: 이동/복사는 제한 없이 허용되어 `cp /etc/passwd /tmp/leak`같은 패턴이 가능하다. 단 이는 agent 환경에서 현실적 위험이 낮다.

치명적인 누락은 없다. `curl * | sh` 패턴 차단이 있어 공급망 공격을 막는다. 전반적으로 실용적인 수준의 보호를 제공한다.

### 8.4 pre-commit hook 일관성

`.pre-commit-config.yaml`의 `biome-check` hook은 `types_or: [javascript, jsx, ts, tsx, json]`으로 설정되어 있다. `json` 타입이 포함되어 있어 biome가 JSON 파일도 처리한다. 앞서 `check-json`에서 제외된 `biome.json`, `tsconfig*.json`을 biome가 처리한다는 의미인데, biome는 JSONC(주석 있는 JSON)를 기본 지원하므로 실제 충돌은 없다. 논리적으로 일관된 구성이다.

## 9. 권고 액션 목록

| ID | Severity | 처리 담당 | 액션 |
|---|---|---|---|
| M-1 | MAJOR | architect | `shared/schemas/` v0.1 PR 제출. domain-expert의 §4-1, §4-2, §4-7 답변 선행 필요. |
| M-2 | MAJOR | backend-dev | Docker Compose 실 구동 검증 후 결과 기록. Alembic auto-migrate 진입점 추가 여부 결정. |
| M-3 | MAJOR | backend-dev | `datetime.utcnow` → `datetime.now(tz=timezone.utc)` 교체 (`tenant.py:37,43,80,84`). |
| M-4 | MAJOR | backend-dev | `.env.example`의 `POSTGRES_PASSWORD`, `SECRET_KEY`를 명확한 placeholder로 교체. |
| M-5 | MAJOR | PM(Dennis) | API 응답 DTO 위치 컨벤션을 CLAUDE.md 또는 README에 추가. 라우터 내 Pydantic 모델 직접 정의 허용 범위 결정. |
| N-1 | MINOR | frontend-dev | highlight mark 직렬화 검증 테스트 케이스 추가 (Selection API 없이 가능). |
| N-2 | MINOR | backend-dev | `.pre-commit-config.yaml` check-json exclude 패턴 좁히는 것 검토 (현재 허용 수준). |
| N-3 | MINOR | frontend-dev | `packages/editor/package.json`에 vite library mode build 스크립트 추가 (Phase 1 시점). |
| N-4 | MINOR | backend-dev | `Settings.mvp_tenant_id`를 `str`에서 `uuid.UUID` 타입으로 변경. |
| NIT-1 | NIT | backend-dev | health check의 `except Exception` 블록에 로깅 추가. |
| NIT-2 | NIT | frontend-dev | `EditorPoc.tsx`의 `INITIAL_CONTENT`에 Phase 1 대체 TODO 주석 추가. |
| NIT-3 | NIT | 모든 agent | 향후 커밋에서 `docs(scope):` 형식 준수. |
| OQ-1 | — | PM + domain-expert | §4-1, §4-2, §4-7 Open Question 1주 내 결정 → architect 작업 #5 차단 해제. |
