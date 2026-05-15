"""VocabularyMasterRepository — Stage E1-c VocabularyMaster 조회/생성/갱신.

ADR-0016 D1 권장안 (a) — 별 테이블 + Vocabulary.master_id nullable FK.

책임:
  - ``find_by_headword``: (tenant_id, headword_normalized) 기준 단건 조회.
    Stage E1-c manual add + LLM 보강 라우트에서 master reuse 여부 결정에 사용.
  - ``increment_usage_count``: master link 시 usage_count += 1 SQL UPDATE.
    DELETE 시 -1 은 Stage E1-d 연동 (vocabulary DELETE 훅 — Phase 4 트리거 검토).

멀티테넌트:
  모든 조회/갱신에 ``tenant_ctx.tenant_id`` 필터 강제.
  ``workspace_id`` 는 master 생성 시에만 사용 (조회는 tenant_id + headword 충분).

commit 금지:
  BaseRepository 원칙과 동일 — caller (API 핸들러 session.begin()) 가 담당.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.schemas.vocabulary_master import VocabularyMaster
from worksheet_api.models.vocabulary_master import VocabularyMasterORM
from worksheet_api.repositories.base import BaseRepository
from worksheet_api.repositories.tenant_context import TenantContext


class VocabularyMasterRepository(BaseRepository[VocabularyMasterORM, VocabularyMaster]):
    """VocabularyMaster (글로벌 어휘 dedup 마스터) repository.

    ADR-0016 D3: tenant_id 별 UNIQUE (headword_normalized) 을 활용한 조회.
    Stage E1-c 에서 manual add / LLM 보강 양쪽 모두 이 repository 를 통해 master
    를 조회하거나 신규 생성한다.

    Args:
        session: SQLModel AsyncSession.
        tenant_ctx: 현재 요청의 TenantContext — 모든 필터에 자동 적용.
    """

    _orm_class = VocabularyMasterORM
    _domain_class = VocabularyMaster

    def __init__(self, session: AsyncSession, tenant_ctx: TenantContext) -> None:
        super().__init__(session, tenant_ctx)

    def _to_domain(self, orm: VocabularyMasterORM) -> VocabularyMaster:
        """VocabularyMasterORM → VocabularyMaster 변환."""
        return VocabularyMaster.model_validate(orm)

    # ─── 핵심 헬퍼 ──────────────────────────────────────────────────────────

    async def find_by_headword(
        self,
        headword_normalized: str,
    ) -> VocabularyMaster | None:
        """(tenant_id, headword_normalized) 기준 master 단건 조회.

        Stage E1-c 흐름:
          1. manual add / LLM 보강에서 headword_normalized 계산 후 이 메서드 호출.
          2. 결과가 None → 신규 master 생성 (``BaseRepository.create``).
          3. 결과가 있음 → reuse (``increment_usage_count`` 호출).

        ADR-0016 D3: UNIQUE (tenant_id, headword_normalized) 이므로 결과는 0 or 1.
        workspace_id 필터를 *제외* — master 는 tenant 전체 단어장 자산이므로
        workspace 를 넘어 공유된다 (ADR-0016 D3 정합).

        Args:
            headword_normalized: 정규화된 표제어 (소문자 + strip).

        Returns:
            VocabularyMaster 인스턴스 또는 None (해당 tenant 에 없음).
        """
        stmt = (
            select(self._orm_class)
            .where(self._orm_class.tenant_id == self._tenant_ctx.tenant_id)
            .where(self._orm_class.headword_normalized == headword_normalized)
        )
        result = await self._session.exec(stmt)
        orm = result.first()
        return self._to_domain(orm) if orm is not None else None

    async def increment_usage_count(self, master_id: uuid.UUID) -> None:
        """master.usage_count += 1 원자적 UPDATE.

        Stage E1-c 에서 master reuse 시 호출. DB 레벨 atomic UPDATE 로
        concurrent write 안전 (ORM 객체 로드 후 +1 패턴의 race 회피).

        tenant_id 필터 포함 — cross-tenant update 구조적 차단.

        Args:
            master_id: usage_count 를 +1 할 VocabularyMaster UUID.
        """
        stmt = text(
            "UPDATE vocabulary_master "
            "SET usage_count = usage_count + 1, updated_at = NOW() "
            "WHERE id = :master_id AND tenant_id = :tenant_id"
        )
        await self._session.exec(  # type: ignore[call-overload]
            stmt,
            params={
                "master_id": master_id,
                "tenant_id": self._tenant_ctx.tenant_id,
            },
        )
        await self._session.flush()

    async def decrement_usage_count(self, master_id: uuid.UUID) -> None:
        """master.usage_count -= 1 원자적 UPDATE (0 하한 보호).

        Stage E1-d (vocabulary DELETE) 연동 — Vocabulary 행 삭제 시 master 의
        usage_count 를 감소. 0 미만으로 내려가지 않도록 GREATEST(0, usage_count - 1) 사용.

        ADR-0016 D4-a: usage_count = 0 인 master 는 삭제하지 않는다
        (개인 단어장 자산 보존).

        Args:
            master_id: usage_count 를 -1 할 VocabularyMaster UUID.
        """
        stmt = text(
            "UPDATE vocabulary_master "
            "SET usage_count = GREATEST(0, usage_count - 1), updated_at = NOW() "
            "WHERE id = :master_id AND tenant_id = :tenant_id"
        )
        await self._session.exec(  # type: ignore[call-overload]
            stmt,
            params={
                "master_id": master_id,
                "tenant_id": self._tenant_ctx.tenant_id,
            },
        )
        await self._session.flush()
