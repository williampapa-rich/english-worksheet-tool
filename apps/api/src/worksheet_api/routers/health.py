"""헬스체크 엔드포인트.

DB ping을 포함해 실제 연결 상태를 확인한다.
DB가 연결 불가능한 경우에도 API 자체는 살아있음을 알 수 있도록
두 가지 상태를 분리해서 반환한다.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from worksheet_api.db import get_db

router = APIRouter(tags=["헬스체크"])


class HealthResponse(BaseModel):
    """헬스체크 응답 모델."""

    status: str
    db: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="서비스 상태 확인",
    description="API 서버 및 DB 연결 상태를 반환한다.",
)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    """API 서버와 DB 상태를 확인한다.

    Returns:
        HealthResponse: status="ok", db="ok" 또는 db="unreachable"
    """
    db_status = "ok"
    try:
        # 가장 가벼운 쿼리로 DB 연결 확인
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unreachable"

    return HealthResponse(status="ok", db=db_status)
