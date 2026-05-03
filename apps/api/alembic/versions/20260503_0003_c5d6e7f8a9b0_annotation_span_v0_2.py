"""annotation_span_v0_2: syntax_annotations.span / arrow_target_span 평탄화

Revision ID: c5d6e7f8a9b0
Revises: b3c4d5e6f7a8
Create Date: 2026-05-03 00:00:00.000000

P1-3 — AnnotationSpan v0.2 적용 (ADR-0004).

변경:
  - 컬럼 형태 (JSONB) 는 그대로. payload 의 내부 구조만 변경:
      v0.1 placeholder: {"span_format": "character_offset_v1", "data": {"start": N, "end": N}}
      v0.2 정식       : {"span_format": "character_offset_v1", "start": N, "end": N}
  - syntax_annotations.span (NOT NULL JSONB)
  - syntax_annotations.arrow_target_span (NULLABLE JSONB)

데이터 마이그레이션 정책:
  Phase 0 종료 직후 — Annotation write API (P1-5) 가 아직 없으므로 데이터가 비어 있을
  가능성이 높다. 그래도 안전을 위해 idempotent UPDATE 로 처리:
    - WHERE 조건 (`span ? 'data'`) 으로 v0.1 형태인 행만 평탄화.
    - 이미 v0.2 형태이거나 NULL 인 행은 영향 없음.
    - 행이 0건이어도 무해.

Downgrade:
  v0.2 → v0.1 역변환. 마찬가지로 idempotent.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # span 평탄화: data->{start,end} 를 1급 키로 끌어올림.
    op.execute(
        """
        UPDATE syntax_annotations
        SET span = jsonb_build_object(
            'span_format', span->>'span_format',
            'start', (span->'data'->>'start')::int,
            'end',   (span->'data'->>'end')::int
        )
        WHERE span ? 'data';
        """
    )
    # arrow_target_span 평탄화 (nullable — IS NOT NULL 가드 + ? 가드).
    op.execute(
        """
        UPDATE syntax_annotations
        SET arrow_target_span = jsonb_build_object(
            'span_format', arrow_target_span->>'span_format',
            'start', (arrow_target_span->'data'->>'start')::int,
            'end',   (arrow_target_span->'data'->>'end')::int
        )
        WHERE arrow_target_span IS NOT NULL
          AND arrow_target_span ? 'data';
        """
    )


def downgrade() -> None:
    # v0.2 → v0.1 역변환: start/end 를 data dict 로 다시 감쌈.
    op.execute(
        """
        UPDATE syntax_annotations
        SET span = jsonb_build_object(
            'span_format', span->>'span_format',
            'data', jsonb_build_object(
                'start', (span->>'start')::int,
                'end',   (span->>'end')::int
            )
        )
        WHERE span ? 'start';
        """
    )
    op.execute(
        """
        UPDATE syntax_annotations
        SET arrow_target_span = jsonb_build_object(
            'span_format', arrow_target_span->>'span_format',
            'data', jsonb_build_object(
                'start', (arrow_target_span->>'start')::int,
                'end',   (arrow_target_span->>'end')::int
            )
        )
        WHERE arrow_target_span IS NOT NULL
          AND arrow_target_span ? 'start';
        """
    )
