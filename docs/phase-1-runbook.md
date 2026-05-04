# Phase 1 운영 — 와이프 검수 직접 사용 가이드

이 문서는 Phase 1 (구문분석 에디터 + HWPX 출력) 의 dev 환경을 기동하고
와이프 검수 사이클을 진행하는 방법을 설명한다.

Phase 0 runbook (`docs/phase-0-runbook.md`) 에서 API 추출 사용법을 다룬다.
본 문서는 **Phase 1 에디터 + HWPX 출력 + fixture 검수** 전용.

---

## 1. 사전 준비

### 1.1 .env 작성

`apps/api/.env` 파일이 없으면 `.env.example` 을 복사해 작성한다.

```bash
# apps/api/ 기준
DATABASE_URL=postgresql+asyncpg://worksheet:worksheet@localhost:5432/worksheet_db
ANTHROPIC_API_KEY=sk-ant-api03-...   # fixture 시드는 LLM 호출 없음 — 빈 값도 OK
MVP_TENANT_ID=00000000-0000-0000-0000-000000000001
MVP_WORKSPACE_ID=00000000-0000-0000-0000-000000000002
LLM_USAGE_LOG_PATH=var/llm_usage.jsonl

# Docker compose 용
POSTGRES_USER=worksheet
POSTGRES_PASSWORD=worksheet
POSTGRES_DB=worksheet_db
```

> fixture 시드는 LLM 을 호출하지 않으므로 `ANTHROPIC_API_KEY` 는 임의 값이어도 무방.
> 실제 추출 기능 (POST /passages/extract) 사용 시에는 실제 키 필요.

### 1.2 Node.js / pnpm 확인

```bash
node --version   # 18+ 권장
pnpm --version   # 8+ 권장
```

---

## 2. Dev 환경 기동 (최초 1회 절차)

### 2.1 DB 컨테이너 시작

```bash
# repo 루트에서
docker compose up -d db
docker compose ps   # worksheet_db_1 가 healthy 상태인지 확인
```

### 2.2 Alembic 마이그레이션

```bash
cd apps/api
uv run alembic upgrade head
```

### 2.3 Tenant / Workspace stub 시드

Phase 0 runbook 과 동일 — 이미 완료됐으면 건너뜀.

```bash
psql "postgresql://worksheet:worksheet@localhost:5432/worksheet_db" << 'SQL'
INSERT INTO tenants (id, name, created_at, updated_at)
VALUES
  ('00000000-0000-0000-0000-000000000001', 'demo-tenant', NOW(), NOW())
ON CONFLICT DO NOTHING;

INSERT INTO workspaces (id, tenant_id, name, created_at, updated_at)
VALUES
  ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'demo-workspace', NOW(), NOW())
ON CONFLICT DO NOTHING;
SQL
```

### 2.4 Phase 1 fixture 시드

```bash
cd apps/api
uv run python -m scripts.seed_phase1_fixtures
```

성공 시 출력 예시:

```
============================================================
Phase 1 fixture 시드 시작
============================================================
tenant_id : 00000000-0000-0000-0000-000000000001
workspace_id: 00000000-0000-0000-0000-000000000002

[1/2] tenant / workspace 존재 확인 ...
  [tenant] 이미 존재 — skip 00000000-0000-0000-0000-000000000001
  [workspace] 이미 존재 — skip 00000000-0000-0000-0000-000000000002

[2/2] fixture 3건 시드 ...

  -- AI 의사결정 투명성 (00000000-0000-0000-0000-000000000101) --
  [passage] UPSERT 00000000-0000-0000-0000-000000000101  (AI 의사결정 투명성)
  [annotation] 7 건 삽입 (passage 00000000-0000-0000-0000-000000000101)

  -- 기억의 재구성 본질 (00000000-0000-0000-0000-000000000102) --
  [passage] UPSERT 00000000-0000-0000-0000-000000000102  (기억의 재구성 본질)
  [annotation] 7 건 삽입 (passage 00000000-0000-0000-0000-000000000102)

  -- 소셜 네트워크와 소비자 행동 (00000000-0000-0000-0000-000000000103) --
  [passage] UPSERT 00000000-0000-0000-0000-000000000103  (소셜 네트워크와 소비자 행동)
  [annotation] 7 건 삽입 (passage 00000000-0000-0000-0000-000000000103)

============================================================
시드 완료 — fixture 목록
============================================================
  [AI 의사결정 투명성]
    passage_id   : 00000000-0000-0000-0000-000000000101
    annotation 수: 7
    editor URL   : http://localhost:5173/editor/00000000-0000-0000-0000-000000000101

  [기억의 재구성 본질]
    passage_id   : 00000000-0000-0000-0000-000000000102
    annotation 수: 7
    editor URL   : http://localhost:5173/editor/00000000-0000-0000-0000-000000000102

  [소셜 네트워크와 소비자 행동]
    passage_id   : 00000000-0000-0000-0000-000000000103
    annotation 수: 7
    editor URL   : http://localhost:5173/editor/00000000-0000-0000-0000-000000000103
```

**멱등성**: 이 스크립트는 2회 연속 실행해도 에러 없이 동일 결과를 냅니다.
fixture 재시드가 필요하면 그냥 한 번 더 실행하면 됩니다.

### 2.5 API 서버 시작

```bash
# apps/api/ 기준
uv run uvicorn worksheet_api.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
```

헬스 체크:

```bash
curl http://127.0.0.1:8000/health
# 기대: {"status":"ok","version":"0.1.0"}
```

### 2.6 Web dev 서버 시작

```bash
# repo 루트 기준
pnpm --filter @english-worksheet-tool/web dev
```

브라우저 자동 오픈 또는 수동으로 `http://localhost:5173` 접속.

---

## 3. 와이프 검수 절차

### 3.1 fixture URL 접속

API 서버 + web dev 서버가 모두 기동된 상태에서:

| fixture | 주제 | URL |
|---|---|---|
| Fixture 1 | AI 의사결정 투명성 (어법 변형) | http://localhost:5173/editor/00000000-0000-0000-0000-000000000101 |
| Fixture 2 | 기억의 재구성 본질 (빈칸 추론) | http://localhost:5173/editor/00000000-0000-0000-0000-000000000102 |
| Fixture 3 | 소셜 네트워크와 소비자 행동 (어휘 변형) | http://localhost:5173/editor/00000000-0000-0000-0000-000000000103 |

### 3.2 에디터에서 확인

각 URL 접속 시 에디터에 본문 + annotation 이 자동 로드됩니다:

- 상단 라벨 (주어구, 관계절, 선택지 A/B/C 등)
- 하단 라벨 (S, V, 명사절)
- 형광펜 (색상 1, 3, 4, 5번)
- 밑줄 (it)
- 괄호 `()`, `[]`
- 인라인 노트 ((it / them), (삽입구))
- 화살표 (purchasing decisions → peer recommendations)

에디터에서 annotation 을 추가/수정해도 됩니다. 저장 후 HWPX 출력으로 이어집니다.

### 3.3 HWPX 다운로드

에디터 우상단 **"HWPX 다운로드"** 버튼 클릭 → `.hwpx` 파일 다운로드.

### 3.4 한컴오피스에서 열기

다운로드된 `.hwpx` 파일을 한컴오피스(한글)에서 엽니다.

### 3.5 검수 기록 작성

`docs/phase-1-wife-feedback.md` 의:
1. **§2 평가 기준** — 아직 비어 있으면 먼저 채우기 (등급 정의, 가중치, 검수 환경)
2. **§3 검수 기록** — fixture 별 OK/NG + 코멘트 기입

---

## 4. 트러블슈팅

### DB 연결 실패

```bash
docker compose ps   # DB 컨테이너 상태 확인
docker compose up -d db   # 재시작
```

### "MODULE_NOT_FOUND" 또는 import 오류 (시드 스크립트)

```bash
# apps/api/ 에서 실행 중인지 확인
cd apps/api
uv run python -m scripts.seed_phase1_fixtures
```

### PORT 5173 충돌 (web dev)

```bash
lsof -ti:5173 | xargs kill -9   # 점유 프로세스 종료
pnpm --filter @english-worksheet-tool/web dev
```

### PORT 8000 충돌 (API 서버)

```bash
lsof -ti:8000 | xargs kill -9
uv run uvicorn worksheet_api.main:app --host 127.0.0.1 --port 8000 --reload
```

### annotation 이 에디터에 로드 안 됨

fixture 가 DB 에 없거나 tenant/workspace 불일치일 가능성.

```bash
# fixture 재시드
cd apps/api
uv run python -m scripts.seed_phase1_fixtures

# API 로 직접 확인
curl http://127.0.0.1:8000/passages/00000000-0000-0000-0000-000000000101
curl http://127.0.0.1:8000/passages/00000000-0000-0000-0000-000000000101/annotations
```

기대: passage 조회 성공 + annotations 배열에 7건.

### alembic "Target database is not up to date"

```bash
cd apps/api
uv run alembic upgrade head
```

### psql 명령 없음

`brew install libpq` 또는 `brew install postgresql` 로 psql 클라이언트 설치.
또는 docker exec 로 직접 접속:

```bash
docker compose exec db psql -U worksheet -d worksheet_db
```

---

## 5. 검수 후 정리

- **fixture 데이터 삭제**: 별도 스크립트 없음. `docker compose down -v` 로 DB 볼륨 초기화하면 자연 정리. 영구 보존이 필요하면 fixture 그대로 두면 됩니다.
- **재시드**: fixture 본문/annotation 수정 후 `uv run python -m scripts.seed_phase1_fixtures` 재실행하면 됩니다 (멱등성 보장).
- **NG 항목 인계**: `docs/phase-1-wife-feedback.md` §4 에 기록 → PM 이 P1-10 백로그로 전환.

---

## 6. fixture 구성 요약

| fixture | 주제 | annotation 종류 |
|---|---|---|
| Fixture 1 | AI 의사결정 투명성 (어법 변형) | top_label(×2), bottom_label, highlight, underline, bracket, inline_note |
| Fixture 2 | 기억의 재구성 본질 (빈칸 추론) | top_label, bracket, bottom_label(×2), highlight(×2), inline_note |
| Fixture 3 | 소셜 네트워크와 소비자 행동 (어휘 변형) | top_label(×3), bracket, bottom_label, highlight, arrow |

7종 annotation 모두 3건 fixture 에 분산 포함되어 각 종류의 HWPX 렌더링을 검증 가능.

---

## 7. 관련 문서

- Phase 0 runbook: `docs/phase-0-runbook.md`
- Phase 1 와이프 검수 양식: `docs/phase-1-wife-feedback.md`
- HWPX annotation 매핑 카탈로그: `docs/annotation-hwpx-mapping.md`
- fixture 데이터 정의: `apps/api/scripts/_fixtures_data.py`
- fixture 시드 스크립트: `apps/api/scripts/seed_phase1_fixtures.py`
