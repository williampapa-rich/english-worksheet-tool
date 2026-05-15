"""애플리케이션 설정 — pydantic-settings로 환경변수를 타입-세이프하게 로드."""

from functools import lru_cache
from pathlib import Path

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 기반 애플리케이션 설정.

    .env 파일 또는 실제 환경변수에서 로드된다.
    필드명은 대소문자 무시(case-insensitive).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # .env 에는 docker-compose / 미래 기능용 변수 (POSTGRES_*, APP_ENV, SECRET_KEY 등)
        # 가 함께 들어 있으므로, 본 Settings 가 명시한 필드 외의 변수는 무시.
        extra="ignore",
    )

    # ── DB ──────────────────────────────────────────────────────────────────
    # asyncpg 드라이버 사용: postgresql+asyncpg://user:pass@host/db
    database_url: PostgresDsn

    # ── 멀티테넌트 stub ──────────────────────────────────────────────────────
    # Phase 4 OAuth 도입 전까지 단일 테넌트/워크스페이스/사용자를 환경변수로 고정.
    # 실제 사용은 repositories/tenant_context.py 의 get_tenant_context() Depends 에서 처리.
    mvp_tenant_id: str = "00000000-0000-0000-0000-000000000001"
    # P0-6 TenantContext 에서 사용. Sprint 0 의 단일 워크스페이스 sentinel 기본값.
    mvp_workspace_id: str = "00000000-0000-0000-0000-000000000002"
    # ADR-0009 — user_preferences 인프라 stub. Phase 4 OAuth 도입 시 실제 ``sub`` 클레임
    # 매핑 — 그 시점에 stub UUID 의 user_preferences 행은 별 마이그레이션 정책으로 처리.
    mvp_user_id: str = "00000000-0000-0000-0000-000000000003"

    # ── LLM ─────────────────────────────────────────────────────────────────
    # Provider 선택 — "anthropic" (기본) 또는 "gemini".
    # 검수 / 비용 절감 단계에는 "gemini" + GOOGLE_API_KEY 사용.
    # 운영 / Phase 3+ 는 "anthropic" + ANTHROPIC_API_KEY.
    llm_provider: str = "anthropic"

    # None 이면 환경변수 ANTHROPIC_API_KEY 에서 읽음. 실제 사용 시점에 None 이면 PermanentLLMError.
    anthropic_api_key: str | None = None

    # Gemini provider 용. None 이면 환경변수 GOOGLE_API_KEY / GEMINI_API_KEY 에서 읽음.
    google_api_key: str | None = None

    # LLM 사용량 JSONL 백업 로그 경로 (PM-4 jsonl sink).
    # DB sink 실패 시 이 파일이 안전망 역할.
    llm_usage_log_path: Path = Path("var/llm_usage.jsonl")

    # ── 서버 ─────────────────────────────────────────────────────────────────
    debug: bool = False
    app_title: str = "영어 학습 자료 생성 도구 API"
    app_version: str = "0.1.0"

    # ── Node.js server-side renderer (ADR-0018 Stage F2) ─────────────────────
    # subprocess로 호출하는 Node.js CLI 설정.
    # NODE_BIN: node 바이너리 경로 (기본: "node" — PATH에서 해석).
    node_bin: str = "node"
    # JITI_BIN: jiti TypeScript 실행기 경로.
    # 기본값: apps/render/node_modules/.bin/jiti (pnpm install 후 자동 생성).
    jiti_bin: str = ""
    # SERVER_RENDERER_PATH: bin.ts 경로.
    # 기본값: apps/render/src/bin.ts (jiti로 실행 — 빌드 불필요).
    server_renderer_path: str = ""
    # LEGACY_ANNOTATION_RENDERER: "true" 이면 annotation_html.py fallback 사용.
    # Stage F2 초기 안전망. 충분한 production 검증 후 제거.
    legacy_annotation_renderer: bool = False
    # SERVER_RENDERER_TIMEOUT: subprocess 타임아웃 (초).
    server_renderer_timeout: int = 30

    # ── CORS ──────────────────────────────────────────────────────────────────
    # 허용할 origin 목록. 환경변수 CORS_ORIGINS 에 comma-separated 로 override 가능.
    # 기본값: Vite dev server (http://localhost:5173).
    # 예: CORS_ORIGINS=http://localhost:5173,https://app.example.com
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        """CORS_ORIGINS 환경변수 comma-separated string 파싱 지원.

        환경변수에서 넘어오는 값이 "a,b,c" 형태일 때 ["a","b","c"] 로 변환.
        이미 list 이면 그대로 반환.
        """
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(item) for item in v]
        return ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    """Settings 싱글턴 팩토리.

    lru_cache로 한 번만 생성한다.
    테스트에서는 app.dependency_overrides나 monkeypatch로 교체 가능.

    Returns:
        Settings: 파싱된 설정 인스턴스
    """
    return Settings()  # type: ignore[call-arg]
