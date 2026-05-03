"""마이그레이션 양방향 동작 테스트 — ADR-0005 §D-5.7.

통합 테스트 (pytest -m integration):
  - Docker compose 의 PostgreSQL 에 연결 (DATABASE_URL 환경변수).
  - JSONB 컬럼 등 PostgreSQL 전용 기능 검증.
  - alembic upgrade head / downgrade -1 / 순환 테스트.

단위 수준 검증 (항상 실행):
  - 마이그레이션 파일 syntax (import 가능 여부).
  - down_revision 체인 정합성.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# ─── 마이그레이션 파일 정적 검증 (DB 불필요) ─────────────────────────────────


class TestMigrationFileStructure:
    """마이그레이션 파일 구조를 정적으로 검증한다."""

    def _get_versions_dir(self) -> Path:
        return Path(__file__).parent.parent / "alembic" / "versions"

    def test_migration_files_exist(self) -> None:
        """Sprint 0 + P0-1 + P1-3 + P1-annotation-input-dto 마이그레이션 파일이 존재한다."""
        versions = self._get_versions_dir()
        files = list(versions.glob("*.py"))
        names = [f.name for f in files]
        assert any("a1b2c3d4e5f6" in n for n in names), "Sprint 0 마이그레이션 (a1b2c3d4e5f6) 누락"
        assert any("b3c4d5e6f7a8" in n for n in names), "P0-1 마이그레이션 (b3c4d5e6f7a8) 누락"
        assert any("c5d6e7f8a9b0" in n for n in names), "P1-3 마이그레이션 (c5d6e7f8a9b0) 누락"
        assert any("d6e7f8a9b0c1" in n for n in names), (
            "P1-annotation-input-dto 마이그레이션 (d6e7f8a9b0c1) 누락"
        )

    def test_p1_3_migration_chain(self) -> None:
        """P1-3 마이그레이션의 down_revision 이 P0-1 을 가리킨다."""
        import importlib.util

        versions = self._get_versions_dir()
        p1_3_files = list(versions.glob("*c5d6e7f8a9b0*"))
        assert p1_3_files, "P1-3 마이그레이션 파일을 찾을 수 없다"

        spec = importlib.util.spec_from_file_location("migration_p1_3", p1_3_files[0])
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)  # type: ignore[attr-defined]

        assert hasattr(module, "upgrade")
        assert hasattr(module, "downgrade")
        assert module.revision == "c5d6e7f8a9b0"
        assert module.down_revision == "b3c4d5e6f7a8"

    def test_annotation_id_migration_chain(self) -> None:
        """P1-annotation-input-dto 마이그레이션의 down_revision 이 P1-3 을 가리킨다."""
        import importlib.util

        versions = self._get_versions_dir()
        files = list(versions.glob("*d6e7f8a9b0c1*"))
        assert files, "P1-annotation-input-dto 마이그레이션 파일을 찾을 수 없다"

        spec = importlib.util.spec_from_file_location("migration_annotation_id", files[0])
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)  # type: ignore[attr-defined]

        assert hasattr(module, "upgrade")
        assert hasattr(module, "downgrade")
        assert module.revision == "d6e7f8a9b0c1"
        assert module.down_revision == "c5d6e7f8a9b0"

    def test_p0_1_down_revision(self) -> None:
        """P0-1 마이그레이션의 down_revision 이 Sprint 0 revision 을 가리킨다."""
        versions = self._get_versions_dir()
        p0_1_files = list(versions.glob("*b3c4d5e6f7a8*"))
        assert p0_1_files, "P0-1 마이그레이션 파일을 찾을 수 없다"

        content = p0_1_files[0].read_text()
        assert "down_revision" in content
        assert "a1b2c3d4e5f6" in content, (
            "P0-1 의 down_revision 이 Sprint 0 revision 을 가리키지 않는다"
        )

    def test_p0_1_migration_importable(self) -> None:
        """P0-1 마이그레이션 파일이 import 가능하다 (syntax 오류 없음)."""
        import importlib.util

        versions = self._get_versions_dir()
        p0_1_files = list(versions.glob("*b3c4d5e6f7a8*"))
        assert p0_1_files

        spec = importlib.util.spec_from_file_location("migration_p0_1", p0_1_files[0])
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)  # type: ignore[attr-defined]

        assert hasattr(module, "upgrade")
        assert hasattr(module, "downgrade")
        assert module.revision == "b3c4d5e6f7a8"
        assert module.down_revision == "a1b2c3d4e5f6"


# ─── 통합 테스트 (PostgreSQL 필요) ─────────────────────────────────────────────


def _get_test_db_url() -> str:
    """테스트용 DATABASE_URL 을 환경변수에서 가져온다."""
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL 또는 TEST_DATABASE_URL 환경변수가 없어 통합 테스트 건너뜀")
    return url


@pytest.mark.integration
class TestMigrationRoundTrip:
    """alembic upgrade / downgrade 양방향 동작 통합 테스트.

    Docker compose 의 PostgreSQL 이 실행 중이어야 한다.
    ``pytest -m integration`` 으로 실행.
    """

    @pytest.fixture(autouse=True)
    def _check_db(self) -> None:
        """PostgreSQL 연결 가능 여부 확인."""
        url = _get_test_db_url()
        if "sqlite" in url:
            pytest.skip("통합 테스트는 PostgreSQL 전용 (JSONB 컬럼)")

    def _get_alembic_cfg(self):  # type: ignore[return]
        """Alembic Config 객체를 반환한다.

        ``script_location`` 은 ``alembic.ini`` 에서 ``script_location = alembic`` 으로
        상대경로 — 실행 cwd 에 의존. pytest 를 repo root 에서 돌리면 cwd 가 root 라
        이를 절대경로로 덮어써 안전하게 한다.
        """
        from alembic.config import Config

        api_root = Path(__file__).parent.parent  # apps/api/
        alembic_ini = api_root / "alembic.ini"
        cfg = Config(str(alembic_ini))
        cfg.set_main_option("script_location", str(api_root / "alembic"))
        cfg.set_main_option("sqlalchemy.url", _get_test_db_url())
        return cfg

    def test_upgrade_head(self) -> None:
        """alembic upgrade head 가 모든 테이블을 생성한다."""
        from alembic import command
        from sqlalchemy import create_engine, inspect

        cfg = self._get_alembic_cfg()
        url = _get_test_db_url().replace("+asyncpg", "")
        engine = create_engine(url)

        try:
            # upgrade head
            command.upgrade(cfg, "head")

            inspector = inspect(engine)
            tables = inspector.get_table_names()

            expected_tables = {
                "tenants",
                "workspaces",
                "passages",
                "questions",
                "vocabulary",
                "translations",
                "syntax_annotations",
                "llm_usage_logs",
            }
            missing = expected_tables - set(tables)
            assert not missing, f"upgrade head 후 테이블 누락: {missing}"

        finally:
            engine.dispose()

    def test_downgrade_minus_one(self) -> None:
        """alembic downgrade -1 이 P1-3 의 데이터 변환만 역변환하고 테이블은 보존한다.

        P1-3 (c5d6e7f8a9b0) 은 data-only migration (JSONB payload 평탄화) — 테이블
        스키마 변경 없음. 따라서 downgrade -1 후에도 P0-1 의 모든 테이블이 그대로
        남아있어야 한다.
        """
        from alembic import command
        from sqlalchemy import create_engine, inspect

        cfg = self._get_alembic_cfg()
        url = _get_test_db_url().replace("+asyncpg", "")
        engine = create_engine(url)

        try:
            # upgrade head 먼저
            command.upgrade(cfg, "head")
            # downgrade -1 (head=P1-3 → P0-1)
            command.downgrade(cfg, "-1")

            inspector = inspect(engine)
            tables = set(inspector.get_table_names())

            # P0-1 테이블 모두 보존 (P1-3 는 data-only 라 테이블 영향 없음)
            p0_1_tables = {
                "passages",
                "questions",
                "vocabulary",
                "translations",
                "syntax_annotations",
                "llm_usage_logs",
            }
            missing = p0_1_tables - tables
            assert not missing, f"downgrade -1 (to P0-1) 후 테이블이 사라졌다: {missing}"

            # Sprint 0 테이블 (tenants, workspaces) 은 남아있어야 함
            assert "tenants" in tables
            assert "workspaces" in tables

        finally:
            # 클린업: 다음 테스트를 위해 base 로 롤백
            command.downgrade(cfg, "base")

    def test_downgrade_minus_two_drops_p0_1(self) -> None:
        """alembic downgrade -2 (head=P1-3 → Sprint 0) 가 P0-1 테이블을 깨끗하게 롤백한다."""
        from alembic import command
        from sqlalchemy import create_engine, inspect

        cfg = self._get_alembic_cfg()
        url = _get_test_db_url().replace("+asyncpg", "")
        engine = create_engine(url)

        try:
            command.upgrade(cfg, "head")
            command.downgrade(cfg, "-2")

            inspector = inspect(engine)
            tables = set(inspector.get_table_names())

            p0_1_tables = {
                "passages",
                "questions",
                "vocabulary",
                "translations",
                "syntax_annotations",
                "llm_usage_logs",
            }
            remaining = p0_1_tables & tables
            assert not remaining, f"downgrade -2 후에도 P0-1 테이블이 남아있다: {remaining}"

            assert "tenants" in tables
            assert "workspaces" in tables

        finally:
            command.downgrade(cfg, "base")
            engine.dispose()

    def test_upgrade_downgrade_cycle(self) -> None:
        """빈 DB → upgrade head → downgrade base → upgrade head 순환이 성공한다."""
        from alembic import command
        from sqlalchemy import create_engine, inspect

        cfg = self._get_alembic_cfg()
        url = _get_test_db_url().replace("+asyncpg", "")
        engine = create_engine(url)

        try:
            # 1. 빈 DB (downgrade base)
            command.downgrade(cfg, "base")

            inspector = inspect(engine)
            assert "passages" not in inspector.get_table_names(), "base 후 passages 가 남았다"

            # 2. upgrade head
            command.upgrade(cfg, "head")
            tables = set(inspect(engine).get_table_names())
            assert "passages" in tables, "첫 번째 upgrade head 후 passages 가 없다"

            # 3. downgrade base
            command.downgrade(cfg, "base")
            tables = set(inspect(engine).get_table_names())
            assert "passages" not in tables, "두 번째 downgrade base 후 passages 가 남았다"

            # 4. 다시 upgrade head
            command.upgrade(cfg, "head")
            tables = set(inspect(engine).get_table_names())
            assert "passages" in tables, "두 번째 upgrade head 후 passages 가 없다"
            assert "llm_usage_logs" in tables

        finally:
            engine.dispose()

    def test_jsonb_columns_created(self) -> None:
        """JSONB 컬럼이 PostgreSQL 에서 올바르게 생성된다."""
        from alembic import command
        from sqlalchemy import create_engine, inspect

        cfg = self._get_alembic_cfg()
        url = _get_test_db_url().replace("+asyncpg", "")
        engine = create_engine(url)

        try:
            command.upgrade(cfg, "head")

            inspector = inspect(engine)

            # passages.source 가 jsonb 타입인지 확인
            passage_cols = {col["name"]: col for col in inspector.get_columns("passages")}
            assert "source" in passage_cols, "passages.source 컬럼 없음"
            # PostgreSQL JSONB 는 type 이 'JSONB' 로 표시됨
            source_type = str(passage_cols["source"]["type"]).upper()
            assert "JSON" in source_type, f"passages.source 가 JSONB 가 아님: {source_type}"

        finally:
            command.downgrade(cfg, "base")
            engine.dispose()

    def test_unique_constraint_translations(self) -> None:
        """translations.passage_id UNIQUE 제약이 DB 레벨에서 생성된다."""
        from alembic import command
        from sqlalchemy import create_engine, inspect

        cfg = self._get_alembic_cfg()
        url = _get_test_db_url().replace("+asyncpg", "")
        engine = create_engine(url)

        try:
            command.upgrade(cfg, "head")

            inspector = inspect(engine)
            unique_constraints = inspector.get_unique_constraints("translations")
            uq_names = [uc["name"] for uc in unique_constraints]
            assert "uq_translations_passage_id" in uq_names, (
                "translations.passage_id UNIQUE 제약 누락 (PM 결정 D-2 위반)"
            )

        finally:
            command.downgrade(cfg, "base")
            engine.dispose()
