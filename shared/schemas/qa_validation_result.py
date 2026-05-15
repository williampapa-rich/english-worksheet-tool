"""QAValidationResult — qa-validator 정답 유일성 검증 history 모델.

ADR-0017 D3-c 하이브리드 구현:
  - ``Question.uniqueness_validated`` / ``uniqueness_validator_note`` — 최신 상태 캐시.
  - ``QAValidationResult`` 테이블 — 검증 history + LLM 호출 trace.

역할:
  - Phase 3 qa-validator agent 가 채운다 (Phase 3 진입 전 stub).
  - 매 검증 실행마다 새 행 생성 — history 보존.
  - ``Question.uniqueness_validated`` 캐시는 최신 ``QAValidationResult.passed``
    값으로 갱신 (repository 책임).

cascade 정책 (ADR-0017 D6):
  question 삭제 시 QAValidationResult 도 자동 삭제 (ON DELETE CASCADE).
  history 는 원본 question 의 파생 콘텐츠 — 원본 없으면 의미 없음.

Phase 3 활성 시 보강 필드 후보 (D7):
  - ``llm_cost_usd: float | None`` — 비용 모니터링 (ADR-0013 D8 패턴).
  - ``prompt_template_id: str | None`` — 프롬프트 버전 추적.
  - ``request_id: str | None`` — LLM 호출 ID (retry 추적).
  현재는 자리만 (None default).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from shared.schemas.common import EntityId, WorkspaceScopedEntity, utc_now


class QAValidationResult(WorkspaceScopedEntity):
    """qa-validator 1회 실행 결과 (history 단위).

    ``Question.uniqueness_validated`` 는 최신 상태 캐시,
    ``QAValidationResult`` 가 전체 history 를 보존한다 (ADR-0017 D3-c).

    Phase 3 qa-validator 활성 시점에 채워진다. Phase 3 이전에는 행이 생성되지 않음.
    """

    # ─── FK ─────────────────────────────────────────────────────────────────
    question_id: EntityId = Field(
        ...,
        description=(
            "검증 대상 Question ID (FK → questions.id, NOT NULL). "
            "ON DELETE CASCADE — question 삭제 시 history 도 자동 삭제."
        ),
    )

    # ─── 검증 결과 ────────────────────────────────────────────────────────────
    validated_at: datetime = Field(
        default_factory=utc_now,
        description="검증 실행 시각 (UTC, timezone-aware).",
    )
    passed: bool = Field(
        ...,
        description=(
            "정답 유일성 검증 통과 여부. True = 정답이 유일함 (합격), "
            "False = 오답이 정답으로 해석 가능 (불합격)."
        ),
    )
    validator_note: str | None = Field(
        default=None,
        description=(
            "검증 메모 (실패 사유 / 경계 케이스 등). "
            "``Question.uniqueness_validator_note`` 캐시에도 동일 값이 복사됨."
        ),
    )

    # ─── LLM 호출 trace (Phase 3 보강 예정) ──────────────────────────────────
    validator_model: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "검증에 사용한 LLM 모델 ID (예: 'claude-sonnet-4-5'). "
            "Phase 3 qa-validator 활성 시 채워짐."
        ),
    )
    validator_version: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "qa-validator 프롬프트 / 알고리즘 버전 (예: 'v0.1'). "
            "회귀 추적용. Phase 3 활성 시 채워짐."
        ),
    )
