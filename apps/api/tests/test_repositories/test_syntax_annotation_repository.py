"""SyntaxAnnotationRepository 단위 + 통합 테스트 (P1-5).

단위 테스트: mock session 으로 sentinel / tenant 검증.
통합 테스트: 실제 PostgreSQL (@pytest.mark.integration) 으로 replace_all + 멀티테넌트 격리.

P1-3 follow-up: "Docker 환경 integration 검증 1회" 는 본 테스트의
``pytest -m integration`` 으로 충족된다.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from worksheet_api.models.base import SENTINEL_UUID
from worksheet_api.repositories.syntax_annotation import SyntaxAnnotationRepository
from worksheet_api.repositories.tenant_context import TenantContext

from shared.schemas.annotation import (
    AnnotationKind,
    CharacterOffsetV1Span,
    SpanFormat,
    SyntaxAnnotation,
)
from shared.schemas.passage import Passage, SourceMeta, SourceProvider

# ─── 공통 픽스처 ─────────────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TENANT_B = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
WORKSPACE_B = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

_PASSAGE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _ctx_a() -> TenantContext:
    return TenantContext(tenant_id=TENANT_A, workspace_id=WORKSPACE_A)


def _ctx_b() -> TenantContext:
    return TenantContext(tenant_id=TENANT_B, workspace_id=WORKSPACE_B)


def _make_span(start: int = 0, end: int = 5) -> CharacterOffsetV1Span:
    return CharacterOffsetV1Span(
        span_format=SpanFormat.CHARACTER_OFFSET_V1,
        start=start,
        end=end,
    )


def _make_annotation(
    passage_id: uuid.UUID = _PASSAGE_ID,
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
    kind: AnnotationKind = AnnotationKind.HIGHLIGHT,
    start: int = 0,
    end: int = 5,
) -> SyntaxAnnotation:
    """테스트용 SyntaxAnnotation 생성 헬퍼."""
    return SyntaxAnnotation(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        passage_id=passage_id,
        kind=kind,
        span=_make_span(start=start, end=end),
        color_index=1,
    )


def _make_arrow_annotation(
    passage_id: uuid.UUID = _PASSAGE_ID,
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
) -> SyntaxAnnotation:
    """arrow kind 전용 헬퍼 (arrow_target_span 필수)."""
    return SyntaxAnnotation(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        passage_id=passage_id,
        kind=AnnotationKind.ARROW,
        span=_make_span(start=0, end=3),
        arrow_target_span=_make_span(start=10, end=15),
    )


def _make_passage(
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
) -> Passage:
    return Passage(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        body_text="The economy is growing steadily.",
        word_count=5,
        source=SourceMeta(provider=SourceProvider.EVALUATOR),
        target_grade="high_3",
    )


# ─── 단위 테스트 (mock session) ───────────────────────────────────────────────


class TestSyntaxAnnotationRepositoryUnit:
    """sentinel / tenant 검증 단위 테스트 (DB 없음)."""

    @pytest.mark.asyncio
    async def test_create_sentinel_tenant_id_raises(self) -> None:
        """sentinel UUID (tenant_id) 가 create 까지 누수되면 ValueError (ADR-0003)."""
        mock_session = AsyncMock()
        repo = SyntaxAnnotationRepository(mock_session, _ctx_a())

        ann = _make_annotation()
        ann_with_sentinel = ann.model_copy(update={"tenant_id": SENTINEL_UUID})

        with pytest.raises(ValueError, match="sentinel UUID"):
            await repo.create(ann_with_sentinel)

    @pytest.mark.asyncio
    async def test_create_sentinel_workspace_id_raises(self) -> None:
        """sentinel UUID (workspace_id) 가 create 까지 누수되면 ValueError (ADR-0003)."""
        mock_session = AsyncMock()
        repo = SyntaxAnnotationRepository(mock_session, _ctx_a())

        ann = _make_annotation()
        ann_with_sentinel = ann.model_copy(update={"workspace_id": SENTINEL_UUID})

        with pytest.raises(ValueError, match="sentinel UUID"):
            await repo.create(ann_with_sentinel)

    @pytest.mark.asyncio
    async def test_create_tenant_mismatch_raises(self) -> None:
        """domain.tenant_id != context.tenant_id 이면 ValueError."""
        mock_session = AsyncMock()
        repo = SyntaxAnnotationRepository(mock_session, _ctx_a())

        ann = _make_annotation(tenant_id=TENANT_B, workspace_id=WORKSPACE_B)

        with pytest.raises(ValueError, match="tenant_id 불일치"):
            await repo.create(ann)

    @pytest.mark.asyncio
    async def test_replace_all_passage_id_mismatch_raises(self) -> None:
        """annotation.passage_id 가 요청 passage_id 와 다르면 ValueError."""
        mock_session = AsyncMock()
        # exec() 는 delete 에 사용 — 무해한 mock 반환 충분
        mock_session.exec = AsyncMock(return_value=MagicMock())
        repo = SyntaxAnnotationRepository(mock_session, _ctx_a())

        wrong_passage_id = uuid.uuid4()
        ann = _make_annotation(passage_id=wrong_passage_id)

        with pytest.raises(ValueError, match="passage_id"):
            await repo.replace_all(_PASSAGE_ID, [ann])

    @pytest.mark.asyncio
    async def test_annotation_invalid_span_raises(self) -> None:
        """end <= start 인 span 은 Pydantic validation 에서 거부된다."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _make_annotation(start=5, end=3)  # end < start → invalid

    @pytest.mark.asyncio
    async def test_arrow_without_target_span_raises(self) -> None:
        """arrow kind 에 arrow_target_span 없으면 model validator 에서 거부."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SyntaxAnnotation(
                tenant_id=TENANT_A,
                workspace_id=WORKSPACE_A,
                passage_id=_PASSAGE_ID,
                kind=AnnotationKind.ARROW,
                span=_make_span(),
                arrow_target_span=None,  # arrow 는 target 필수
            )

    @pytest.mark.asyncio
    async def test_non_arrow_with_target_span_raises(self) -> None:
        """arrow 아닌 kind 에 arrow_target_span 설정하면 model validator 에서 거부."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SyntaxAnnotation(
                tenant_id=TENANT_A,
                workspace_id=WORKSPACE_A,
                passage_id=_PASSAGE_ID,
                kind=AnnotationKind.HIGHLIGHT,
                span=_make_span(),
                arrow_target_span=_make_span(start=10, end=20),  # highlight 에 arrow_target 금지
            )


# ─── 통합 테스트 (실제 PostgreSQL) ───────────────────────────────────────────


@pytest.mark.integration
class TestSyntaxAnnotationRepositoryIntegration:
    """실제 PostgreSQL 을 사용한 통합 테스트.

    Docker compose PostgreSQL 이 필요하다.
    pytest -m integration 으로 실행.

    P1-3 follow-up: "Docker 환경 integration 검증 1회" 를 본 클래스가 수행한다.
    """

    @pytest.mark.asyncio
    async def test_replace_all_normal(self, pg_session) -> None:
        """replace_all: 정상 케이스 — 저장 후 id 포함 결과 반환."""
        from worksheet_api.repositories.passage import PassageRepository

        # passage 먼저 생성
        passage_repo = PassageRepository(pg_session, _ctx_a())
        passage = await passage_repo.create(_make_passage())
        passage_id = passage.id

        annotation_repo = SyntaxAnnotationRepository(pg_session, _ctx_a())
        annotations = [
            _make_annotation(passage_id=passage_id, start=0, end=3),
            _make_annotation(passage_id=passage_id, kind=AnnotationKind.TOP_LABEL, start=4, end=7),
        ]

        saved = await annotation_repo.replace_all(passage_id, annotations)

        assert len(saved) == 2
        for ann in saved:
            assert ann.id is not None
            assert ann.tenant_id == TENANT_A
            assert ann.passage_id == passage_id

    @pytest.mark.asyncio
    async def test_replace_all_overwrites_existing(self, pg_session) -> None:
        """replace_all: 기존 annotation 을 완전히 교체 (replace semantics)."""
        from worksheet_api.repositories.passage import PassageRepository

        passage_repo = PassageRepository(pg_session, _ctx_a())
        passage = await passage_repo.create(_make_passage())
        passage_id = passage.id

        annotation_repo = SyntaxAnnotationRepository(pg_session, _ctx_a())

        # 첫 번째 저장: 2건
        first = [
            _make_annotation(passage_id=passage_id, start=0, end=3),
            _make_annotation(passage_id=passage_id, start=4, end=7),
        ]
        await annotation_repo.replace_all(passage_id, first)

        # 두 번째 저장: 1건 (덮어쓰기)
        second = [_make_annotation(passage_id=passage_id, start=10, end=15)]
        saved = await annotation_repo.replace_all(passage_id, second)

        # DB 에는 1건만
        listed = await annotation_repo.list_by_passage(passage_id)
        assert len(listed) == 1
        assert len(saved) == 1
        assert saved[0].span.start == 10  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_replace_all_empty_deletes_all(self, pg_session) -> None:
        """replace_all with empty list: 기존 annotation 전부 삭제."""
        from worksheet_api.repositories.passage import PassageRepository

        passage_repo = PassageRepository(pg_session, _ctx_a())
        passage = await passage_repo.create(_make_passage())
        passage_id = passage.id

        annotation_repo = SyntaxAnnotationRepository(pg_session, _ctx_a())

        # 먼저 1건 저장
        await annotation_repo.replace_all(passage_id, [_make_annotation(passage_id=passage_id)])

        # 빈 리스트로 교체 = 전체 삭제
        saved = await annotation_repo.replace_all(passage_id, [])
        listed = await annotation_repo.list_by_passage(passage_id)

        assert saved == []
        assert listed == []

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation(self, pg_session) -> None:
        """cross-tenant 격리: tenant B 는 tenant A 의 annotation 을 볼 수 없다."""
        from worksheet_api.repositories.passage import PassageRepository

        # tenant A — passage + annotation 생성
        passage_repo_a = PassageRepository(pg_session, _ctx_a())
        passage_a = await passage_repo_a.create(_make_passage())

        annotation_repo_a = SyntaxAnnotationRepository(pg_session, _ctx_a())
        await annotation_repo_a.replace_all(
            passage_a.id, [_make_annotation(passage_id=passage_a.id)]
        )

        # tenant B — 동일 passage_id 로 list_by_passage → 0건
        annotation_repo_b = SyntaxAnnotationRepository(pg_session, _ctx_b())
        result_b = await annotation_repo_b.list_by_passage(passage_a.id)

        assert result_b == []

    @pytest.mark.asyncio
    async def test_arrow_annotation_roundtrip(self, pg_session) -> None:
        """arrow kind (arrow_target_span 포함) 의 JSONB round-trip."""
        from worksheet_api.repositories.passage import PassageRepository

        passage_repo = PassageRepository(pg_session, _ctx_a())
        passage = await passage_repo.create(_make_passage())

        annotation_repo = SyntaxAnnotationRepository(pg_session, _ctx_a())
        arrow_ann = _make_arrow_annotation(passage_id=passage.id)

        saved = await annotation_repo.replace_all(passage.id, [arrow_ann])

        assert len(saved) == 1
        ann = saved[0]
        assert ann.kind == AnnotationKind.ARROW
        assert ann.arrow_target_span is not None
        assert ann.arrow_target_span.start == 10
        assert ann.arrow_target_span.end == 15
