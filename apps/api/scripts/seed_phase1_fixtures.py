"""Phase 1 와이프 검수용 fixture 3건 시드 스크립트.

사용법::

    cd apps/api
    uv run python -m scripts.seed_phase1_fixtures

멱등성: passage_id 가 고정되어 있으므로 재실행 시 기존 Passage 를 upsert (삭제 후 재삽입),
SyntaxAnnotation 은 replace-all (기존 삭제 후 재삽입).
즉, 2회 연속 실행해도 에러 없이 동일 결과.

사전 조건:
  - PostgreSQL 컨테이너 실행 중 (`docker compose up -d db`)
  - Alembic 마이그레이션 완료 (`uv run alembic upgrade head`)
  - tenants / workspaces stub 시드 완료 (phase-0-runbook §1 의 psql INSERT)
  - apps/api/.env 에 DATABASE_URL / MVP_TENANT_ID / MVP_WORKSPACE_ID 설정됨
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

# ─── sys.path 보정 ──────────────────────────────────────────────────────────
# uv run python -m scripts.seed_phase1_fixtures 는 apps/api/ 에서 실행.
# shared/ 가 sys.path 에 없으면 import 실패 → repo 루트를 추가.
_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # apps/api/scripts/ → repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# apps/api/src/ 도 path 에 있어야 worksheet_api 패키지를 찾는다
_API_SRC = Path(__file__).parent.parent / "src"
if str(_API_SRC) not in sys.path:
    sys.path.insert(0, str(_API_SRC))

from sqlalchemy import delete, select  # noqa: E402
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: E402

from scripts._fixtures_data import (  # noqa: E402
    ALL_FIXTURES,
    AnnotationSpec,
    FixtureSpec,
    _span,
)
from shared.schemas.annotation import (  # noqa: E402
    AnnotationCategory,
    AnnotationKind,
    CharacterOffsetV1Span,
    SyntaxAnnotation,
)
from shared.schemas.passage import SourceProvider  # noqa: E402
from worksheet_api.db import _get_session_factory  # noqa: E402
from worksheet_api.models.passage import PassageORM  # noqa: E402
from worksheet_api.models.syntax_annotation import SyntaxAnnotationORM  # noqa: E402
from worksheet_api.models.tenant import Tenant, Workspace  # noqa: E402
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context  # noqa: E402

# ─── stub UUID (phase-0-runbook 기준) ────────────────────────────────────────

MVP_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
MVP_WORKSPACE_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")

WEB_BASE_URL = "http://localhost:5173"


# ─── tenant / workspace 시드 ─────────────────────────────────────────────────


async def _ensure_tenant_workspace(session: AsyncSession) -> None:
    """MVP tenant / workspace 가 없으면 INSERT (ON CONFLICT DO NOTHING 동등).

    Phase 0 runbook 의 psql INSERT 가 이미 실행됐으면 이 함수는 no-op.
    """
    # Tenant
    existing_tenant = await session.exec(  # type: ignore[call-overload]
        select(Tenant).where(Tenant.id == MVP_TENANT_ID)
    )
    if existing_tenant.first() is None:
        session.add(
            Tenant(
                id=MVP_TENANT_ID,
                name="demo-tenant",
            )
        )
        print(f"  [tenant] INSERT {MVP_TENANT_ID}")
    else:
        print(f"  [tenant] 이미 존재 — skip {MVP_TENANT_ID}")

    # Workspace
    existing_ws = await session.exec(  # type: ignore[call-overload]
        select(Workspace).where(Workspace.id == MVP_WORKSPACE_ID)
    )
    if existing_ws.first() is None:
        session.add(
            Workspace(
                id=MVP_WORKSPACE_ID,
                tenant_id=MVP_TENANT_ID,
                name="demo-workspace",
            )
        )
        print(f"  [workspace] INSERT {MVP_WORKSPACE_ID}")
    else:
        print(f"  [workspace] 이미 존재 — skip {MVP_WORKSPACE_ID}")


# ─── annotation 변환 헬퍼 ────────────────────────────────────────────────────


def _build_annotation(
    spec: AnnotationSpec,
    body_text: str,
    tenant_ctx: TenantContext,
    passage_id: uuid.UUID,
) -> SyntaxAnnotation:
    """AnnotationSpec + 본문 → SyntaxAnnotation Pydantic 모델.

    _span() 으로 offset 을 동적 계산 — 본문 변경 시 자동 동기화.
    arrow_target_span 은 arrow kind 일 때만 채움.

    Raises:
        ValueError: span_phrase 또는 arrow_target_phrase 가 본문에 없을 때.
        pydantic.ValidationError: SyntaxAnnotation 모델 invariant 위반 시.
    """
    span_dict = _span(body_text, spec.span_phrase, nth=spec.span_nth)
    span = CharacterOffsetV1Span(
        start=span_dict["start"],
        end=span_dict["end"],
    )

    arrow_target_span = None
    if spec.kind == "arrow":
        if spec.arrow_target_phrase is None:
            raise ValueError(
                f"annotation_id={spec.annotation_id}: kind='arrow' 인데 "
                "arrow_target_phrase 가 None 입니다."
            )
        target_dict = _span(body_text, spec.arrow_target_phrase)
        arrow_target_span = CharacterOffsetV1Span(
            start=target_dict["start"],
            end=target_dict["end"],
        )

    return SyntaxAnnotation(
        id=uuid.uuid4(),
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
        passage_id=passage_id,
        kind=AnnotationKind(spec.kind),
        category=AnnotationCategory(spec.category) if spec.category else None,
        span=span,
        color_index=spec.color_index,
        text=spec.text,
        bracket_style=spec.bracket_style,
        arrow_target_span=arrow_target_span,
        annotation_id=spec.annotation_id,
    )


# ─── passage upsert ──────────────────────────────────────────────────────────


async def _upsert_passage(
    session: AsyncSession,
    fixture: FixtureSpec,
    tenant_ctx: TenantContext,
) -> None:
    """Passage upsert — 고정 ID 로 기존 행 삭제 후 재삽입 (멱등성).

    주의: DELETE + INSERT 는 annotation 의 CASCADE DELETE 를 트리거하므로
    annotation 시드는 반드시 passage upsert 이후에 실행.
    """
    word_count = len(fixture.body_text.split())

    # 기존 행 삭제 (없어도 에러 없음)
    await session.exec(  # type: ignore[call-overload]
        delete(PassageORM).where(PassageORM.id == fixture.passage_id)
    )

    orm = PassageORM(
        id=fixture.passage_id,
        tenant_id=tenant_ctx.tenant_id,
        workspace_id=tenant_ctx.workspace_id,
        body_text=fixture.body_text,
        paragraphs=fixture.paragraphs,
        word_count=word_count,
        source={"provider": SourceProvider.USER_INPUT.value},
        topic_tags=fixture.topic_tags,
        target_grade=fixture.target_grade,
    )
    session.add(orm)
    await session.flush()
    print(f"  [passage] UPSERT {fixture.passage_id}  ({fixture.title})")


# ─── annotation replace-all ──────────────────────────────────────────────────


async def _seed_annotations(
    session: AsyncSession,
    fixture: FixtureSpec,
    tenant_ctx: TenantContext,
) -> int:
    """Passage 의 annotation 을 전체 교체 (replace-all).

    1. 기존 annotation 전체 삭제 (tenant + passage 필터 강제)
    2. 새 annotation INSERT
    Returns: 삽입된 annotation 수.
    """
    # 1. 기존 삭제
    await session.exec(  # type: ignore[call-overload]
        delete(SyntaxAnnotationORM)
        .where(SyntaxAnnotationORM.tenant_id == tenant_ctx.tenant_id)
        .where(SyntaxAnnotationORM.passage_id == fixture.passage_id)
    )

    # 2. 새 annotation 빌드 + INSERT
    count = 0
    for spec in fixture.annotations:
        ann = _build_annotation(spec, fixture.body_text, tenant_ctx, fixture.passage_id)
        data = ann.model_dump(mode="python")
        orm = SyntaxAnnotationORM.model_validate(data)
        session.add(orm)
        count += 1

    await session.flush()
    print(f"  [annotation] {count} 건 삽입 (passage {fixture.passage_id})")
    return count


# ─── 메인 ────────────────────────────────────────────────────────────────────


async def main() -> None:
    """fixture 3건 시드 + 완료 보고."""
    print("=" * 60)
    print("Phase 1 fixture 시드 시작")
    print("=" * 60)

    # tenant context (환경변수 기반 stub)
    tenant_ctx = await get_tenant_context()
    print(f"tenant_id : {tenant_ctx.tenant_id}")
    print(f"workspace_id: {tenant_ctx.workspace_id}")
    print()

    factory = _get_session_factory()
    async with factory() as session:
        async with session.begin():
            # tenant / workspace 시드
            print("[1/2] tenant / workspace 존재 확인 ...")
            await _ensure_tenant_workspace(session)
            print()

            # fixture 3건 처리
            print("[2/2] fixture 3건 시드 ...")
            results: list[tuple[FixtureSpec, int]] = []
            for fixture in ALL_FIXTURES:
                print(f"\n  -- {fixture.title} ({fixture.passage_id}) --")
                await _upsert_passage(session, fixture, tenant_ctx)
                ann_count = await _seed_annotations(session, fixture, tenant_ctx)
                results.append((fixture, ann_count))

    # 완료 보고
    print()
    print("=" * 60)
    print("시드 완료 — fixture 목록")
    print("=" * 60)
    for fixture, ann_count in results:
        url = f"{WEB_BASE_URL}/editor/{fixture.passage_id}"
        print(f"  [{fixture.title}]")
        print(f"    passage_id   : {fixture.passage_id}")
        print(f"    annotation 수: {ann_count}")
        print(f"    editor URL   : {url}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
