"""Annotation API 엔드포인트.

**API 설계 결정 (P1-5 ADR-Lite)**:

replace-all vs batch upsert:
  replace-all 채택. 에디터의 저장 동작이 본질적으로 "현 상태로 갈아엎기" 이다.
  batch upsert 는 부분 갱신이 필요할 때만 의미 — 현재 요건 없음.
  P1-6 의 에디터 저장 흐름이 더 단순해진다.

응답 스키마:
  저장 후 결과 annotation 리스트 반환 (id 포함).
  204 No Content 대안도 검토했으나, 에디터가 새로 저장된 id 를 즉시 사용 가능하게
  하기 위해 결과 리스트 반환 채택.

트랜잭션 경계:
  P0-7 (passages.py) 패턴과 동일 — async with session.begin() 단일 경계.

멀티테넌트:
  passage 조회 시 tenant_id 필터 포함 → 다른 tenant 의 passage 에는 404 반환.
  annotation write 도 SyntaxAnnotationRepository.replace_all 에서 tenant 필터 강제.

P1-6 frontend 호출 시그니처:
  POST /passages/{passage_id}/annotations
    body: { "annotations": [ <SyntaxAnnotation>, ... ] }
    response: { "annotations": [ <SyntaxAnnotation with id>, ... ] }

  GET /passages/{passage_id}/annotations
    response: { "annotations": [ <SyntaxAnnotation>, ... ] }
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.annotation import SyntaxAnnotation
from worksheet_api.db import get_db
from worksheet_api.repositories import (
    PassageRepository,
    SyntaxAnnotationRepository,
    TenantContext,
    get_tenant_context,
)

router = APIRouter(prefix="/passages", tags=["annotations"])


# ─── 요청 / 응답 스키마 ───────────────────────────────────────────────────────


class AnnotationReplaceRequest(BaseModel):
    """POST /passages/{passage_id}/annotations 요청 body.

    에디터 저장 = 현재 annotation 상태 전체를 전달.
    빈 리스트 = passage 의 모든 annotation 삭제.
    """

    annotations: list[SyntaxAnnotation] = Field(
        default_factory=list,
        description=(
            "저장할 SyntaxAnnotation 리스트. "
            "replace-all 방식 — 기존 annotation 을 전부 교체한다. "
            "빈 리스트를 보내면 해당 passage 의 annotation 이 모두 삭제된다."
        ),
    )


class AnnotationListResponse(BaseModel):
    """annotation 목록 응답 (POST 저장 결과 / GET 조회 결과 공용)."""

    annotations: list[SyntaxAnnotation] = Field(
        default_factory=list,
        description="SyntaxAnnotation 리스트 (DB 부여 id 포함).",
    )


# ─── 엔드포인트 ──────────────────────────────────────────────────────────────


@router.post(
    "/{passage_id}/annotations",
    response_model=AnnotationListResponse,
    status_code=200,
)
async def replace_annotations(
    passage_id: UUID,
    body: AnnotationReplaceRequest,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AnnotationListResponse:
    """Passage 의 annotation 을 replace-all 저장.

    기존 annotation 을 모두 삭제하고 body 의 리스트로 교체한다.
    에디터의 "저장" 동작에 대응 — 항상 현재 에디터 상태 전체를 전달한다.

    멀티테넌트: passage 존재 여부를 먼저 확인 (다른 tenant 소유면 404).
    트랜잭션: 삭제 + 신규 insert 를 단일 session.begin() 으로 원자적 처리.

    Args:
        passage_id: 대상 Passage UUID.
        body: 저장할 annotation 리스트.
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        session: DB 세션.

    Returns:
        저장된 annotation 리스트 (DB 부여 id 포함).

    Raises:
        HTTPException 404: Passage 가 존재하지 않거나 다른 tenant 소유.
        HTTPException 422: annotation validation 실패 (sentinel UUID, passage_id 불일치 등).
    """
    async with session.begin():
        passage_repo = PassageRepository(session, tenant_ctx)
        annotation_repo = SyntaxAnnotationRepository(session, tenant_ctx)

        # passage 존재 + tenant 소유 확인
        passage = await passage_repo.get(passage_id)
        if passage is None:
            raise HTTPException(
                status_code=404,
                detail=f"Passage {passage_id} 를 찾을 수 없습니다.",
            )

        # 요청 annotation 에 tenant_id / workspace_id / passage_id 주입
        # (에디터에서 전달된 모델은 id 가 없거나 sentinel 일 수 있음 — 실제 값으로 교체)
        prepared: list[SyntaxAnnotation] = []
        for ann in body.annotations:
            prepared.append(
                ann.model_copy(
                    update={
                        "tenant_id": tenant_ctx.tenant_id,
                        "workspace_id": tenant_ctx.workspace_id,
                        "passage_id": passage_id,
                    }
                )
            )

        try:
            saved = await annotation_repo.replace_all(passage_id, prepared)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return AnnotationListResponse(annotations=saved)


@router.get(
    "/{passage_id}/annotations",
    response_model=AnnotationListResponse,
    status_code=200,
)
async def get_annotations(
    passage_id: UUID,
    tenant_ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AnnotationListResponse:
    """Passage 의 annotation 목록 조회 — 멀티테넌트 강제.

    다른 tenant 의 passage 를 조회하면 404 반환 (존재 여부 노출 방지).

    Args:
        passage_id: 조회할 Passage UUID.
        tenant_ctx: 현재 요청의 테넌트 컨텍스트.
        session: DB 세션.

    Returns:
        해당 passage 의 annotation 리스트 (빈 리스트 가능).

    Raises:
        HTTPException 404: Passage 가 존재하지 않거나 다른 tenant 소유.
    """
    passage_repo = PassageRepository(session, tenant_ctx)
    annotation_repo = SyntaxAnnotationRepository(session, tenant_ctx)

    # passage 존재 + tenant 소유 확인
    passage = await passage_repo.get(passage_id)
    if passage is None:
        raise HTTPException(
            status_code=404,
            detail=f"Passage {passage_id} 를 찾을 수 없습니다.",
        )

    annotations = await annotation_repo.list_by_passage(passage_id)
    return AnnotationListResponse(annotations=annotations)
