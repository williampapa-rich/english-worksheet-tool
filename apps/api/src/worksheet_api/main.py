"""FastAPI 애플리케이션 진입점."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import worksheet_api.models  # noqa: F401  # Alembic autogenerate용 모델 메타데이터 등록
from worksheet_api.config import get_settings
from worksheet_api.routers import annotations, health, passages, preferences, worksheets


# FastAPI 앱 인스턴스
# 설정은 factory 함수에서 가져온다 — 모듈 import 시점이 아닌 앱 생성 시점에 적용
def create_app() -> FastAPI:
    """FastAPI 앱 팩토리.

    테스트에서 app을 직접 import할 때도 설정이 올바르게 적용되도록
    팩토리 패턴을 사용한다.

    CORS middleware 는 cfg.cors_origins (기본값: ["http://localhost:5173"]) 로
    허용 origin 을 제어한다. 환경변수 CORS_ORIGINS 에 comma-separated 로 override 가능.

    Returns:
        FastAPI: 설정된 앱 인스턴스
    """
    cfg = get_settings()
    application = FastAPI(
        title=cfg.app_title,
        version=cfg.app_version,
        debug=cfg.debug,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router)
    application.include_router(passages.router)
    application.include_router(annotations.router)
    application.include_router(preferences.router)
    application.include_router(worksheets.router)
    return application


app = create_app()
