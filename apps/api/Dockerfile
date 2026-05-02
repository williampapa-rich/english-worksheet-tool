# Python 3.12-slim 베이스 — uv로 의존성 설치
# 대안: python:3.12-alpine은 glibc 미포함으로 asyncpg 빌드가 복잡해서 탈락
FROM python:3.12-slim

# uv 설치 (Astral 공식 방식)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# 의존성 파일만 먼저 복사 (레이어 캐시 최적화)
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml ./apps/api/
COPY shared/pyproject.toml ./shared/
COPY packages/extractor/pyproject.toml ./packages/extractor/
COPY packages/llm/pyproject.toml ./packages/llm/
COPY packages/hwpx_renderer/pyproject.toml ./packages/hwpx_renderer/

# workspace 전체 의존성 설치 (--frozen: uv.lock 기반, 재현 가능 빌드)
RUN uv sync --frozen --no-dev

# 소스코드 복사
COPY apps/api/src ./apps/api/src
COPY shared ./shared
COPY packages ./packages

# PYTHONPATH에 apps/api/src를 추가해 worksheet_api 패키지를 찾을 수 있게 함
ENV PYTHONPATH="/app/apps/api/src:/app/shared:/app/packages"

# 8000번 포트 노출
EXPOSE 8000

# uvicorn 실행 — workers는 환경변수로 조정 가능
CMD ["uv", "run", "uvicorn", "worksheet_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
