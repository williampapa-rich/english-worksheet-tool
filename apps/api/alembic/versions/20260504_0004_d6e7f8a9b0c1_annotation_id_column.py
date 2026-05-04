"""annotation_id_column: syntax_annotations 에 annotation_id (nullable UUID) 추가

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-05-04 00:00:00.000000

P1-annotation-input-dto — SyntaxAnnotation.annotation_id 영속화 (옵션 A 채택).

배경:
  에디터(Tiptap P1-2c Phase B) 는 chip 단위 논리 ID (annotation_id) 를 각 mark 에
  부여한다. 같은 chip 의 여러 mark 가 동일 annotation_id 를 공유하여 일괄 수정/삭제를
  가능하게 한다. 이 ID 는 DB PK (id) 와 별개.

옵션 A 채택 근거 (ADR-Lite):
  - 옵션 A (영속화): annotation_id 를 DB 에 저장 → 에디터 라운드트립 시 동일 chip ID
    복원 가능. P1-2c Phase B 의 핵심 기능(chip 단위 분석표 그룹핑) 이 라운드트립 후에도
    유지됨.
  - 옵션 B (무시): 저장하지 않으면 reload 시 chip 재구성이 heuristic (kind+span 조합) 에
    의존 — 분기 케이스 증가, 에디터 복원 로직 복잡화.
  - 옵션 C (거부, 현재 동작): 클라이언트 422, 저장 불가 — 기능 차단.
  → 옵션 A 가 라운드트립 강건성과 클라이언트 단순성 양쪽에서 우위.

변경:
  - syntax_annotations.annotation_id: UUID nullable 추가.
  - 기존 행에는 NULL (하위 호환).

Downgrade:
  - 컬럼 DROP.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "d6e7f8a9b0c1"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "syntax_annotations",
        sa.Column(
            "annotation_id",
            PG_UUID(as_uuid=True),
            nullable=True,
            comment="에디터 chip 단위 논리 식별자 (Tiptap). DB PK 와 별개. nullable.",
        ),
    )


def downgrade() -> None:
    op.drop_column("syntax_annotations", "annotation_id")
