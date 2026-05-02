"""애플리케이션 설정 — pydantic-settings로 환경변수를 타입-세이프하게 로드."""

from functools import lru_cache

from pydantic import PostgresDsn
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
    )

    # ── DB ──────────────────────────────────────────────────────────────────
    # asyncpg 드라이버 사용: postgresql+asyncpg://user:pass@host/db
    database_url: PostgresDsn

    # ── 멀티테넌트 stub ──────────────────────────────────────────────────────
    # Phase 4 OAuth 도입 전까지 단일 테넌트를 환경변수로 고정
    # 실제 사용은 후속 PR의 Depends(get_current_tenant)에서 처리
    mvp_tenant_id: str = "00000000-0000-0000-0000-000000000001"

    # ── 서버 ─────────────────────────────────────────────────────────────────
    debug: bool = False
    app_title: str = "영어 학습 자료 생성 도구 API"
    app_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    """Settings 싱글턴 팩토리.

    lru_cache로 한 번만 생성한다.
    테스트에서는 app.dependency_overrides나 monkeypatch로 교체 가능.

    Returns:
        Settings: 파싱된 설정 인스턴스
    """
    return Settings()  # type: ignore[call-arg]
