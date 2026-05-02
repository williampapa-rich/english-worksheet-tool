"""``shared.schemas.llm_usage`` 단위 테스트.

F1 PR (LlmUsageLog 도메인 모델 신설) 의 DoD 충족 검증:
  - PM-4 (ADR-0003) 명세의 모든 필드가 정상 생성 / 검증 / 거절 동작.
  - tenant_id / workspace_id nullable (시스템 호출 / pre-tenant 호출 허용).
  - 토큰 / 지연 시간 음수 거절 (``ge=0``).
  - status Literal 외 값 거절 (silent drift 방지).
  - naive datetime 거절 (timezone-aware 강제 — ``ExtractionMetaRef`` 와 동일 정책).
  - ``extra="forbid"`` — 알 수 없는 필드 거절 (LLM/sink/ORM silent drift 방지).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.schemas.common import utc_now
from shared.schemas.llm_usage import LlmUsageLog

# ─── 공통 fixture 헬퍼 ────────────────────────────────────────────────────


def _make_kwargs(**overrides: object) -> dict[str, object]:
    """최소 valid LlmUsageLog kwargs. override 로 부분 변경."""
    base: dict[str, object] = {
        "id": uuid4(),
        "request_id": uuid4(),
        "tenant_id": uuid4(),
        "workspace_id": uuid4(),
        "model": "claude-sonnet-4-20250514",
        "purpose": "extract_text",
        "input_tokens": 1234,
        "output_tokens": 567,
        "cache_read_tokens": 0,
        "latency_ms": 890,
        "status": "success",
        "created_at": utc_now(),
    }
    base.update(overrides)
    return base


# ─── 정상 케이스 ──────────────────────────────────────────────────────────


class TestLlmUsageLogHappyPath:
    """정상 생성 케이스."""

    def test_full_field_set(self) -> None:
        """모든 필드를 채운 정상 생성."""
        kwargs = _make_kwargs(
            parent_request_id=uuid4(),
            error_class=None,
            cost_usd=Decimal("0.00123456"),
        )
        log = LlmUsageLog(**kwargs)  # type: ignore[arg-type]
        assert log.status == "success"
        assert log.input_tokens == 1234
        assert log.output_tokens == 567
        assert log.cache_read_tokens == 0
        assert log.latency_ms == 890
        assert log.cost_usd == Decimal("0.00123456")

    def test_minimal_required_fields(self) -> None:
        """필수 필드만 채운 정상 생성 — optional 은 default 값."""
        log = LlmUsageLog(
            id=uuid4(),
            request_id=uuid4(),
            model="claude-sonnet-4-20250514",
            purpose="extract_text",
            input_tokens=0,
            output_tokens=0,
            latency_ms=10,
            status="success",
            created_at=utc_now(),
        )
        # default 값 검증
        assert log.parent_request_id is None
        assert log.tenant_id is None
        assert log.workspace_id is None
        assert log.cache_read_tokens == 0
        assert log.error_class is None
        assert log.cost_usd is None

    def test_failure_status_with_error_class(self) -> None:
        """실패 케이스 — status=schema_invalid + error_class."""
        kwargs = _make_kwargs(
            status="schema_invalid",
            error_class="pydantic.ValidationError",
        )
        log = LlmUsageLog(**kwargs)  # type: ignore[arg-type]
        assert log.status == "schema_invalid"
        assert log.error_class == "pydantic.ValidationError"


# ─── 멀티테넌트 nullable 정책 (PM-4) ──────────────────────────────────────


class TestTenantWorkspaceNullable:
    """PM-4: tenant_id / workspace_id 는 nullable — 시스템 호출 / pre-tenant 호출 허용."""

    def test_tenant_id_none_is_valid(self) -> None:
        """시스템 호출 (헬스체크의 LLM ping 등) — tenant_id None 허용."""
        kwargs = _make_kwargs(tenant_id=None, workspace_id=None)
        log = LlmUsageLog(**kwargs)  # type: ignore[arg-type]
        assert log.tenant_id is None
        assert log.workspace_id is None

    def test_only_workspace_id_none(self) -> None:
        """tenant 는 알지만 workspace 결정 전 — 한쪽만 None 도 허용."""
        tenant_id = uuid4()
        kwargs = _make_kwargs(tenant_id=tenant_id, workspace_id=None)
        log = LlmUsageLog(**kwargs)  # type: ignore[arg-type]
        assert log.tenant_id == tenant_id
        assert log.workspace_id is None

    def test_only_tenant_id_none(self) -> None:
        """대칭 — workspace 만 채워진 비정상에 가깝지만 schema 레벨에선 거절 안 함."""
        workspace_id = uuid4()
        kwargs = _make_kwargs(tenant_id=None, workspace_id=workspace_id)
        log = LlmUsageLog(**kwargs)  # type: ignore[arg-type]
        assert log.tenant_id is None
        assert log.workspace_id == workspace_id


# ─── 토큰 / 지연 시간 음수 거절 (ge=0) ────────────────────────────────────


class TestNonNegativeIntFields:
    """``input_tokens`` / ``output_tokens`` / ``cache_read_tokens`` / ``latency_ms`` 는 >= 0."""

    def test_negative_input_tokens_rejected(self) -> None:
        """input_tokens < 0 → ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            LlmUsageLog(**_make_kwargs(input_tokens=-1))  # type: ignore[arg-type]
        # ge=0 위반 메시지 확인 (pydantic v2 의 'greater_than_equal' type)
        assert any(err["type"] == "greater_than_equal" for err in exc_info.value.errors())

    def test_negative_output_tokens_rejected(self) -> None:
        """output_tokens < 0 → ValidationError."""
        with pytest.raises(ValidationError):
            LlmUsageLog(**_make_kwargs(output_tokens=-5))  # type: ignore[arg-type]

    def test_negative_cache_read_tokens_rejected(self) -> None:
        """cache_read_tokens < 0 → ValidationError."""
        with pytest.raises(ValidationError):
            LlmUsageLog(**_make_kwargs(cache_read_tokens=-100))  # type: ignore[arg-type]

    def test_negative_latency_rejected(self) -> None:
        """latency_ms < 0 → ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            LlmUsageLog(**_make_kwargs(latency_ms=-1))  # type: ignore[arg-type]
        assert any(err["type"] == "greater_than_equal" for err in exc_info.value.errors())


# ─── status Literal 강제 ─────────────────────────────────────────────────


class TestStatusLiteral:
    """``status`` 는 LlmUsageStatus Literal 외 값 거절 (silent drift 방지)."""

    @pytest.mark.parametrize(
        "valid_status",
        [
            "success",
            "schema_invalid",
            "timeout",
            "network_error",
            "rate_limited",
            "other",
        ],
    )
    def test_all_valid_statuses(self, valid_status: str) -> None:
        """6개 valid status 모두 통과."""
        log = LlmUsageLog(**_make_kwargs(status=valid_status))  # type: ignore[arg-type]
        assert log.status == valid_status

    def test_unknown_status_rejected(self) -> None:
        """'partial', 'unknown' 등 사전 정의 외 status → ValidationError."""
        with pytest.raises(ValidationError):
            LlmUsageLog(**_make_kwargs(status="partial"))  # type: ignore[arg-type]

    def test_empty_status_rejected(self) -> None:
        """빈 문자열 status 도 거절."""
        with pytest.raises(ValidationError):
            LlmUsageLog(**_make_kwargs(status=""))  # type: ignore[arg-type]


# ─── created_at timezone-aware 강제 ──────────────────────────────────────


class TestCreatedAtTimezoneAware:
    """``created_at`` 은 timezone-aware UTC — naive datetime 거절."""

    def test_naive_datetime_rejected(self) -> None:
        """``datetime.utcnow()`` 같은 naive datetime → ValidationError."""
        naive = datetime(2026, 5, 2, 12, 0, 0)  # naive (tzinfo None)
        assert naive.tzinfo is None
        with pytest.raises(ValidationError) as exc_info:
            LlmUsageLog(**_make_kwargs(created_at=naive))  # type: ignore[arg-type]
        # 본 모델의 _validate_timezone_aware 메시지가 포함되어야 함
        assert "timezone-aware" in str(exc_info.value)

    def test_timezone_aware_utc_accepted(self) -> None:
        """timezone-aware UTC datetime 통과."""
        aware = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
        log = LlmUsageLog(**_make_kwargs(created_at=aware))  # type: ignore[arg-type]
        assert log.created_at == aware

    def test_utc_now_helper_accepted(self) -> None:
        """``shared.schemas.common.utc_now()`` 결과는 통과."""
        log = LlmUsageLog(**_make_kwargs(created_at=utc_now()))  # type: ignore[arg-type]
        assert log.created_at.tzinfo is not None


# ─── extra="forbid" — 알 수 없는 필드 거절 ───────────────────────────────


class TestExtraForbid:
    """``model_config = ConfigDict(extra="forbid")`` — silent drift 방지."""

    def test_unknown_field_rejected(self) -> None:
        """알 수 없는 필드 추가 → ValidationError."""
        kwargs = _make_kwargs()
        kwargs["unexpected_field"] = "should_not_be_allowed"
        with pytest.raises(ValidationError) as exc_info:
            LlmUsageLog(**kwargs)  # type: ignore[arg-type]
        # pydantic v2 의 extra=forbid 위반 메시지
        assert any(err["type"] == "extra_forbidden" for err in exc_info.value.errors())

    def test_typo_field_rejected(self) -> None:
        """필드명 오타 (예: 'lateny_ms') → ValidationError, 무음 누락 방지."""
        kwargs = _make_kwargs()
        # latency_ms 를 빼고 오타로 대체
        del kwargs["latency_ms"]
        kwargs["lateny_ms"] = 100  # typo
        with pytest.raises(ValidationError) as exc_info:
            LlmUsageLog(**kwargs)  # type: ignore[arg-type]
        # 두 에러 모두 발생: 'latency_ms' missing + 'lateny_ms' extra_forbidden
        error_types = {err["type"] for err in exc_info.value.errors()}
        assert "missing" in error_types
        assert "extra_forbidden" in error_types


# ─── cost_usd Decimal 정책 ───────────────────────────────────────────────


class TestCostUsdDecimal:
    """``cost_usd`` 는 Decimal | None — float silent precision loss 회피."""

    def test_decimal_cost_accepted(self) -> None:
        """Decimal 입력 통과."""
        log = LlmUsageLog(**_make_kwargs(cost_usd=Decimal("0.12345678")))  # type: ignore[arg-type]
        assert log.cost_usd == Decimal("0.12345678")

    def test_none_cost_accepted(self) -> None:
        """None — 추후 백필 가능 정책."""
        log = LlmUsageLog(**_make_kwargs(cost_usd=None))  # type: ignore[arg-type]
        assert log.cost_usd is None
