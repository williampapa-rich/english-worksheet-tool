# Phase 0 운영 — 직접 사용 가이드

이 문서는 Phase 0 DoD 충족 시점의 도구를 직접 사용하는 방법을 설명한다.
와이프가 직접 실행하기보다는 PM 이 demo 시 사용하는 절차에 가깝다 (UI 는 Phase 1 부터).

---

## 1. 준비

### 환경변수 (`/.env` 작성)

```bash
# 필수 — asyncpg 드라이버
DATABASE_URL=postgresql+asyncpg://worksheet:worksheet@localhost:5432/worksheet_db

# Anthropic API 키 — https://console.anthropic.com 에서 발급
ANTHROPIC_API_KEY=sk-ant-api03-...

# 멀티테넌트 stub (Phase 4 OAuth 전까지 고정)
MVP_TENANT_ID=00000000-0000-0000-0000-000000000001
MVP_WORKSPACE_ID=00000000-0000-0000-0000-000000000002

# LLM 사용량 백업 로그
LLM_USAGE_LOG_PATH=var/llm_usage.jsonl

# Docker compose 용
POSTGRES_USER=worksheet
POSTGRES_PASSWORD=worksheet
POSTGRES_DB=worksheet_db
```

### 실행 순서

```bash
# 1. PostgreSQL 컨테이너 시작
docker compose up -d db

# 2. Alembic 마이그레이션 실행 (최초 1회 또는 스키마 변경 시)
cd apps/api && uv run alembic upgrade head && cd ../..

# 3. tenants / workspaces 시드 (최초 1회)
#    alembic 마이그레이션이 자동 시드 미포함이면 아래 psql 로 직접 삽입:
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

# 4. API 서버 시작
uv run uvicorn worksheet_api.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
```

---

## 2. 추출 사용

### 헬스 체크

```bash
curl http://127.0.0.1:8000/health
# 기대: {"status":"ok","version":"0.1.0"}
```

### text 입력

```bash
curl -X POST http://127.0.0.1:8000/passages/extract \
  -H "Content-Type: application/json" \
  -d '{
    "kind": "text",
    "payload": "Climate change is one of the most pressing issues of our time. Scientists have warned that without immediate action, the consequences could be catastrophic.\n\n1. What is the main idea of the passage?\n(A) Climate change is solved\n(B) Climate change requires immediate action\n(C) Scientists are wrong\n(D) Action is unnecessary\n(E) None of the above"
  }'
```

### image 입력 (base64)

```bash
# 이미지 파일을 base64 로 인코딩 후 payload 에 담아 전송
PAYLOAD=$(base64 -i sample.png)
curl -X POST http://127.0.0.1:8000/passages/extract \
  -H "Content-Type: application/json" \
  -d "{\"kind\":\"image\",\"media_type\":\"image/png\",\"payload\":\"$PAYLOAD\"}"
```

지원 media_type: `image/png`, `image/jpeg`, `image/webp`

### PDF 입력

```bash
# 텍스트 레이어 있는 PDF (저비용 경로 — PyMuPDF 텍스트 추출)
PAYLOAD=$(base64 -i sample.pdf)
curl -X POST http://127.0.0.1:8000/passages/extract \
  -H "Content-Type: application/json" \
  -d "{\"kind\":\"pdf\",\"payload\":\"$PAYLOAD\",\"force_vision\":false}"

# 스캔본 PDF (Vision 경로 강제)
curl -X POST http://127.0.0.1:8000/passages/extract \
  -H "Content-Type: application/json" \
  -d "{\"kind\":\"pdf\",\"payload\":\"$PAYLOAD\",\"force_vision\":true}"
```

### Passage 조회

```bash
# 추출 응답의 results[0].passage.id 값 사용
curl http://127.0.0.1:8000/passages/{passage_id}
```

---

## 3. 결과 해석

응답 JSON 구조:

```json
{
  "results": [
    {
      "passage": {
        "id": "...",
        "tenant_id": "...",
        "workspace_id": "...",
        "body_text": "영어 본문",
        "word_count": 42,
        "source": { "provider": "user_input" },
        "target_grade": "high_3"
      },
      "questions": [
        {
          "id": "...",
          "passage_id": "...",
          "type": "주제 / 요지",
          "stem": "What is the main idea?",
          "choices": { "A": "...", "B": "..." },
          "correct_answer": "B"
        }
      ],
      "translation": null,
      "vocabulary": []
    }
  ]
}
```

필드 설명:
- `results[]` — 다중 지문 분리됨. 한 입력에 지문 여러 개 있으면 길이 > 1.
- `passage` — 영어 본문 + 메타 (`target_grade`, `source` 등).
- `questions[]` — 추출된 문제 (`type`, `stem`, `choices`, `correct_answer`).
- `translation` — 자료에 한글 해석이 있으면 포함, 없으면 `null` (정상 — PM-6).
- `vocabulary[]` — 자료에 어휘 박스 있으면 포함, 없으면 빈 list (정상 — PM-6).

---

## 4. 트러블슈팅

### "DATABASE_URL 환경변수가 설정되지 않았습니다"
→ `.env` 파일 확인 또는 `export DATABASE_URL=...` 로 직접 설정.

### LLM schema validation 실패 (502)
→ LLM 출력이 스키마 위반 — 재시도 로직이 1회 자동 처리. 2회째 실패 시 502.
→ 입력 텍스트가 너무 짧거나 비표준 형식이면 발생. 더 명확한 지문/문제 형식 사용.

### LLM timeout (504)
→ 입력이 너무 큼. 단일 지문 단위로 분할 입력 권고.

### "image payload base64 디코딩 실패" (422)
→ `base64 -i` (macOS) 또는 `base64 -w0` (Linux) 로 인코딩 후 전송.

### DB 연결 실패
→ `docker compose up -d db` 로 PostgreSQL 컨테이너 재시작.
→ `docker compose ps` 로 상태 확인.

---

## 5. LLM 사용량 확인

```bash
# DB 에서 최근 10건 조회
psql "postgresql://worksheet:worksheet@localhost:5432/worksheet_db" \
  -c "SELECT created_at, model, purpose, status, input_tokens, output_tokens
      FROM llm_usage_logs
      ORDER BY created_at DESC
      LIMIT 10;"

# jsonl 백업 로그 확인
tail -10 var/llm_usage.jsonl
```

---

## 6. Phase 0 의 한계

Phase 0 는 CLI/API only. 다음은 Phase 0 범위 밖이다:

- **UI 없음** — Phase 1 부터 React 웹 에디터 제공.
- **translation / vocabulary DB 영속화 안 됨** — 추출 응답에는 포함되지만 DB 에 저장 안 함. Phase 2 에서 추가.
- **출력 (HWPX / PDF) 없음** — 추출만. 학생용 자료 / 변형문제 출력은 Phase 2 / 3.
- **변형문제 생성 없음** — Phase 3.

---

## 7. Phase 0 DoD 체크리스트

Phase 0 를 종료하고 Phase 1 에 진입하기 전 확인:

| DoD 항목 | 확인 방법 | 상태 |
|---|---|---|
| (1) `shared/schemas/` 1차 정의 완료 | `ls shared/schemas/*.py` — passage, question, annotation, worksheet, tenant, extraction | 완료 |
| (2) Vision LLM 추출 파이프라인 — text / image / pdf 각 1건 | smoke test 통과 또는 위 curl 예시 실행 | 완료 |
| (3) DB 에 Passage 저장/조회 | POST extract → GET /{id} 동일 데이터 확인 | 완료 |
| (4) 멀티테넌트 스키마 + 인증 stub | 응답에 sentinel UUID 없음 + cross-tenant 404 확인 | 완료 |
| (5) architect `docs/schema-coverage-audit.md` 산출 | `cat docs/schema-coverage-audit.md` | 완료 |

---

## 8. Phase 1 진입 전 차단 항목

Phase 1 시작 전 반드시 ADR 로 결정해야 할 항목:

- **ADR-0004 (Annotation span 식별 방식)**: character offset vs ProseMirror position vs token id.
  Tiptap 에디터 구현 전 필수. frontend-dev + architect 협의.
- **ADR (마커 분리 vs inline 유지)**: `①②③④⑤`, `_..._`, `______` 등 마커 처리 방식.
  구문분석 에디터 초기 상태 로딩에 영향.
