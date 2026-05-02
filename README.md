# English Worksheet Tool

영어 학원 강사가 하나의 입력(지문 또는 문제)으로부터 **학생 배포용 자료, 변형문제, 구문분석 자료**를 생성/편집/내보내기 할 수 있는 웹 도구.

## 사전 요구사항

| 도구 | 버전 | 설치 방법 |
|------|------|-----------|
| [uv](https://docs.astral.sh/uv/) | 0.5+ | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [pnpm](https://pnpm.io/) | 9+ | `npm install -g pnpm` |
| [pre-commit](https://pre-commit.com/) | 4+ | `uv tool install pre-commit` |
| Python | 3.12+ | uv가 자동 관리 |
| Node.js | 20+ | 별도 설치 필요 |

## 로컬 개발 환경 셋업

```bash
# 1. Python 가상환경 + 의존성 설치 (uv workspace)
uv sync

# 2. Node.js 의존성 설치 (pnpm workspace)
pnpm install

# 3. pre-commit hook 등록 (최초 1회)
pre-commit install

# 4. 환경변수 설정
cp .env.example .env
# .env 파일을 열어 실제 값 입력 (DATABASE_URL, ANTHROPIC_API_KEY 등)
```

## 개발 서버 실행

```bash
# API 서버 (FastAPI) — 작업 #2에서 추가 예정
uv run --package api uvicorn api.main:app --reload

# 웹앱 (React+Vite) — 작업 #6에서 추가 예정
pnpm --filter @english-worksheet-tool/web dev
```

## 코드 품질 검사

```bash
# Python lint + format (ruff)
uv run ruff check .
uv run ruff format .

# Python 타입 검사 (mypy strict)
uv run mypy .

# TypeScript/JavaScript lint + format (biome)
pnpm exec biome check .

# 모든 pre-commit hook 실행
pre-commit run --all-files
```

## 테스트

```bash
# Python 테스트 (pytest)
uv run pytest

# TypeScript 테스트 (vitest)
pnpm --filter @english-worksheet-tool/web test
```

## 프로젝트 구조

```
english-worksheet-tool/
├── apps/
│   ├── api/          # FastAPI 서버 (배포 대상)
│   └── web/          # React 웹앱 (배포 대상)
├── packages/
│   ├── extractor/    # PDF/이미지 → 정규화된 Passage+Question
│   ├── llm/          # Anthropic SDK 래퍼, 프롬프트 관리
│   ├── hwpx_renderer/ # HWPX 출력
│   └── editor/       # Tiptap 구문분석 에디터 extensions
├── shared/
│   └── schemas/      # Pydantic 스키마 — 시스템의 척추 (architect 관리)
├── admin/            # 비배포 관리자 도구 (로컬 전용)
│   ├── data_collector/
│   └── eval/
└── docs/
    ├── adr/          # 아키텍처 결정 기록
    └── prompts/      # LLM 프롬프트 카탈로그
```

자세한 설계 결정은 [CLAUDE.md](./CLAUDE.md) 참조.
