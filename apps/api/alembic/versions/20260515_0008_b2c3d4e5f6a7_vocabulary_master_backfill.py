"""vocabulary_master_backfill: 기존 vocabulary 행 → vocabulary_master 생성 + master_id link

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f7
Create Date: 2026-05-15 02:37:00.000000

ADR-0016 D2-d Migration 2 (backfill).

선행 조건:
  - Migration 1 (a1b2c3d4e5f7) 완료:
    - ``vocabulary_master`` 테이블 생성 완료
    - ``vocabulary.master_id`` nullable 컬럼 추가 완료

변경 사항:
  1. 기존 ``vocabulary`` 행을 (tenant_id, workspace_id, headword_normalized) 기준으로
     GROUP BY → 각 그룹마다 ``vocabulary_master`` 1행 INSERT.
     - ``id`` = gen_random_uuid() (PostgreSQL 13+ 내장)
     - ``word_canonical`` = MIN(word) — 그룹 내 알파벳 첫 순 단어
     - ``default_meaning_ko`` = MIN(meaning_ko) — 그룹 첫 행 기준
     - ``default_pos``, ``default_level_label`` = MIN() 기준 첫 행 채택
     - ``usage_count`` = COUNT(*) — 그룹 row count
     - ``created_by`` = 'IMPORT' — 자동 backfill 분류
     - ``created_at`` = MIN(created_at), ``updated_at`` = NOW()

  2. 그룹 안 모든 ``vocabulary`` 행에 ``master_id`` 채움.

외부 동작 변경 0 — 기존 endpoint / 라우트 동작 그대로.
master_id 컬럼만 NULL → (UUID) 로 채워질 뿐.

downgrade:
  backfill 데이터만 선택적으로 되돌림.
  - vocabulary.master_id = NULL (IMPORT master 에 연결된 것만)
  - vocabulary_master WHERE created_by = 'IMPORT' 행 삭제
  USER / LLM 으로 직접 생성된 master 는 보존.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # gen_random_uuid() 는 PostgreSQL 13+ 내장 함수 (uuid-ossp 불필요).
    # uuid_generate_v4() 는 uuid-ossp extension 필요 — 더 이식성 낮음.
    # 이 마이그레이션은 gen_random_uuid() 사용.

    conn = op.get_bind()

    # ── Step 1: 중복 그룹 경고 로그 (informational) ───────────────────────────
    # 같은 (tenant_id, workspace_id, headword_normalized) 그룹에 다른 meaning_ko /
    # pos / level_label 이 있으면 WARNING — 첫 행(MIN 기준) 채택.
    duplicate_check = conn.execute(
        sa.text(
            """
            SELECT
                tenant_id,
                workspace_id,
                headword_normalized,
                COUNT(DISTINCT meaning_ko)  AS meaning_ko_variants,
                COUNT(DISTINCT pos)         AS pos_variants,
                COUNT(DISTINCT level_label) AS level_label_variants
            FROM vocabulary
            WHERE master_id IS NULL
            GROUP BY tenant_id, workspace_id, headword_normalized
            HAVING
                COUNT(DISTINCT meaning_ko)  > 1
                OR COUNT(DISTINCT pos)      > 1
                OR COUNT(DISTINCT level_label) > 1
            """
        )
    )
    duplicate_rows = duplicate_check.fetchall()
    if duplicate_rows:
        import warnings

        for row in duplicate_rows:
            warnings.warn(
                f"vocabulary backfill: headword '{row.headword_normalized}' "
                f"(tenant={row.tenant_id}, workspace={row.workspace_id}) has "
                f"{row.meaning_ko_variants} meaning_ko variants / "
                f"{row.pos_variants} pos variants / "
                f"{row.level_label_variants} level_label variants — "
                "첫 행(MIN 기준) 채택",
                stacklevel=2,
            )

    # ── Step 2: vocabulary_master 행 생성 (INSERT ... SELECT) ─────────────────
    # MIN(word) — 알파벳 순 첫 단어를 word_canonical 로 사용 (안정적 결정론)
    # MIN(meaning_ko) — 첫 행의 뜻 채택 (빈 문자열 없음 — NOT NULL 제약)
    # MIN(pos) / MIN(level_label) — NULL 이 아닌 첫 값 채택 (nullable 컬럼)
    # MIN(created_at) — 그룹 내 가장 이른 생성 시각
    conn.execute(
        sa.text(
            """
            INSERT INTO vocabulary_master (
                id,
                tenant_id,
                workspace_id,
                headword_normalized,
                word_canonical,
                default_meaning_ko,
                default_pos,
                default_level_label,
                usage_count,
                created_by,
                created_at,
                updated_at
            )
            SELECT
                gen_random_uuid()           AS id,
                tenant_id,
                workspace_id,
                headword_normalized,
                MIN(word)                   AS word_canonical,
                MIN(meaning_ko)             AS default_meaning_ko,
                MIN(pos)                    AS default_pos,
                MIN(level_label)            AS default_level_label,
                COUNT(*)                    AS usage_count,
                'IMPORT'                    AS created_by,
                MIN(created_at)             AS created_at,
                NOW()                       AS updated_at
            FROM vocabulary
            WHERE master_id IS NULL
            GROUP BY tenant_id, workspace_id, headword_normalized
            ON CONFLICT DO NOTHING
            """
        )
    )

    # ── Step 3: vocabulary.master_id 채움 (UPDATE ... FROM) ──────────────────
    # 조인 조건: tenant_id + workspace_id + headword_normalized 3-way match
    # WHERE master_id IS NULL — 이미 연결된 행은 건드리지 않음 (멱등성)
    conn.execute(
        sa.text(
            """
            UPDATE vocabulary v
            SET master_id = m.id
            FROM vocabulary_master m
            WHERE v.tenant_id         = m.tenant_id
              AND v.workspace_id      = m.workspace_id
              AND v.headword_normalized = m.headword_normalized
              AND v.master_id IS NULL
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    # ── Step 1: IMPORT master 에 연결된 vocabulary.master_id 해제 ──────────────
    conn.execute(
        sa.text(
            """
            UPDATE vocabulary v
            SET master_id = NULL
            FROM vocabulary_master m
            WHERE v.master_id = m.id
              AND m.created_by = 'IMPORT'
            """
        )
    )

    # ── Step 2: IMPORT master 행 삭제 ──────────────────────────────────────────
    # USER / LLM 으로 직접 생성된 master 는 보존
    conn.execute(
        sa.text(
            """
            DELETE FROM vocabulary_master
            WHERE created_by = 'IMPORT'
            """
        )
    )
