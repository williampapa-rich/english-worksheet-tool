"""LLM 사용 로그 도메인 모델.

PM-4 (ADR-0003 §"PM 결정") 에 따라 **LLM 호출 1건당 1 row** 의 사용 통계 / 에러 /
토큰 메타를 영속화한다. 본 모듈은 그 영속화 단위의 **Pydantic v2 도메인 모델** 을
정의한다 — 시스템의 척추 (ADR-0001 §5경계 척추) 에서 LLM 운영/관측 데이터의 single
source of truth.

운영 흐름 (PM-4 안전망):
  1차 보관: ``DbUsageSink`` 가 ``llm_usage_logs`` 테이블에 insert.
  2차 백업: ``JsonlUsageSink`` 가 동시 기록 (MultiplexUsageSink 패턴).
  안전망: DB 실패 시 ``DbUsageSink`` 는 swallow + log. jsonl 은 계속 기록 →
         **데이터 손실 없음**. 본 모델은 두 sink 가 공통으로 사용하는 표현이다.

ADR-0001 §5경계 척추 정합성:
  본 모델이 도메인 척추로 자리 잡은 후, 다음 3개 표현이 같은 필드 집합을 공유한다.

    1. ``LlmUsageLog`` (이 파일) — 도메인 척추 (Pydantic v2)
    2. ``LlmUsageLogORM`` (``apps/api/.../models/llm_usage_log.py``) — DB 매핑 (SQLModel)
    3. ``UsageEvent`` (``packages/llm/.../sinks/base.py``) — sink 입력 (dataclass)

  세 표현의 필드 집합은 본 모델을 1차 source 로 정렬되어야 한다. 본 PR 은 도메인
  모델 신설만 수행하며, ORM / sink 코드의 본 모델 채택은 **후속 cleanup PR** 에서
  처리한다 (architect 권한 분리 — CLAUDE.md §7.2).

멀티테넌트 정책 (PM-4):
  ``tenant_id`` / ``workspace_id`` 는 nullable. 시스템 호출 (헬스 체크의 LLM ping
  등) 또는 pre-tenant 호출 (테넌트 컨텍스트가 아직 결정되지 않은 단계의 LLM 호출)
  을 허용해야 하기 때문이다. 본 테이블은 멀티테넌트 격리 대상이 아니라 **운영 /
  비용 분석용** 이다 — repository 레이어의 sentinel UUID 검증 / tenant_id 강제는
  ``LlmUsageLogRepository`` 에 적용되지 않는다.

join 키:
  ``LlmUsageLog.request_id`` 는 ``ExtractionMetaRef.request_id`` 와 동일 키. 추출
  결과 1건 ↔ 그 결과를 만든 LLM 호출 1건의 1:1 join 이 가능하다 (재시도 chain 의
  최종 성공 호출만 ``ExtractionMetaRef`` 에 기록됨).

cost 정밀도:
  ``cost_usd`` 는 ``Decimal`` — float 는 silent precision loss 위험으로 ORM
  (``Numeric(precision=12, scale=8)``) 과 정합 위해 금지. PM-4 의 "numeric" 명세를
  도메인 모델에서도 그대로 유지.

관련 문서:
  - ``docs/adr/0001-canonical-schema-philosophy.md``
  - ``docs/adr/0003-phase-0-extraction-pipeline.md`` §"PM 결정" PM-4
  - ``apps/api/src/worksheet_api/models/llm_usage_log.py`` (ORM)
  - ``packages/llm/src/llm/sinks/base.py`` (UsageEvent)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ``LlmUsageStatus`` — sink 의 status 와 동일 어휘. shared 에서 정의해 enum 어휘
# 일관성 강제. 새 status 가 필요하면 본 Literal 을 1차로 갱신하고, 그 후 sink /
# ORM 의 자유 문자열 컬럼이 본 어휘를 따르도록 후속 PR 에서 정렬한다.
LlmUsageStatus = Literal[
    "success",
    "schema_invalid",
    "timeout",
    "network_error",
    "rate_limited",
    "other",
]


class LlmUsageLog(BaseModel):
    """LLM 호출 1건의 사용 통계 / 에러 / 토큰 메타.

    PM-4 명세의 DB 컬럼과 1:1 매핑. ``request_id`` 는
    ``ExtractionMetaRef.request_id`` 와 동일 join 키.

    필드 정책:
      - ``id``: 본 로그 row 의 PK. ``request_id`` 와는 다르다 — 한 ``request_id`` 가
        여러 row 에 등장할 수 있다 (재시도 chain 의 모든 호출이 같은
        ``request_id`` 를 공유하지 않으며, ``parent_request_id`` 로 chain 추적).
        실제로 PM-4 명세상 ``request_id`` 는 호출 1건의 식별자이지만, 향후 동일
        request_id 가 여러 sink 결과에서 등장할 수 있는 경우를 대비해 row PK 는
        분리.
      - ``tenant_id`` / ``workspace_id``: nullable — 시스템 호출 / pre-tenant 호출
        허용 (PM-4). 한쪽만 None 도 허용 (예: tenant 는 알지만 workspace 결정 전).
      - ``input_tokens`` / ``output_tokens`` / ``cache_read_tokens`` / ``latency_ms``:
        ``ge=0`` — 음수는 ValidationError.
      - ``cost_usd``: ``Decimal | None`` — 추후 백필 가능. ORM 의 NUMERIC(12, 8) 과
        정합. ``float`` 는 silent precision loss 위험으로 금지.
      - ``created_at``: timezone-aware UTC 강제 — naive datetime 거절 (CLAUDE.md
        / ``ExtractionMetaRef`` 와 동일 정책).

    멀티테넌트:
      본 모델이 들어가는 ``llm_usage_logs`` 테이블은 격리 대상이 아니다 (운영/비용
      분석용). repository 레이어가 멀티테넌트 필터를 강제하지 않는다.
    """

    model_config = ConfigDict(
        # 알 수 없는 필드 거부 — ``BaseEntity`` 와 동일 어휘. LLM 출력의 silent
        # drift / sink 에서 모르는 필드 추가 / ORM 컬럼 증가가 본 모델을 우회하는
        # 것을 방지.
        extra="forbid",
        # ORM (``LlmUsageLogORM``) 객체의 attribute 접근으로 ``model_validate``
        # 가능하게 한다. 후속 cleanup PR 에서 ``LlmUsageLog.model_validate(orm)``
        # 으로 ORM → 도메인 변환을 닫는다.
        from_attributes=True,
    )

    id: UUID = Field(
        ...,
        description=(
            "본 로그 row 의 PK (UUID v4). ORM ``llm_usage_logs.id`` 와 매핑. "
            "``request_id`` 와는 다른 식별자 — row 단위 PK."
        ),
    )
    request_id: UUID = Field(
        ...,
        description=(
            "LLM 호출 1건의 식별자 (NOT NULL). ``ExtractionMetaRef.request_id`` 와 "
            "join 키. 재시도 체인 추적은 ``parent_request_id`` 로."
        ),
    )
    parent_request_id: UUID | None = Field(
        default=None,
        description=(
            "재시도 chain 에서 직전 실패 요청의 ``request_id``. 첫 시도면 None. "
            "ADR-0003 §D-3.5 의 LLM 래퍼 내부 재시도 chain 추적용."
        ),
    )
    tenant_id: UUID | None = Field(
        default=None,
        description=(
            "테넌트 ID. nullable — 시스템 호출 / pre-tenant 호출 허용 (PM-4). "
            "``llm_usage_logs`` 는 멀티테넌트 격리 대상이 아니라 운영/비용 분석용."
        ),
    )
    workspace_id: UUID | None = Field(
        default=None,
        description=(
            "워크스페이스 ID. nullable — ``tenant_id`` 와 동일 정책. 한쪽만 None "
            "(예: tenant 는 알지만 workspace 결정 전) 도 허용."
        ),
    )
    model: str = Field(
        ...,
        max_length=128,
        description=(
            "사용한 LLM 모델 ID (예: 'claude-sonnet-4-20250514'). LLM 래퍼가 응답 "
            "메타에서 받은 값 그대로."
        ),
    )
    purpose: str = Field(
        ...,
        max_length=64,
        description=(
            "호출 목적 식별자. 호출자가 지정 — 예: 'extract_text', "
            "'extract_pdf_vision', 'extract_pdf_text'. 비용 집계 / 사용 패턴 분석의 "
            "1차 grouping 키."
        ),
    )
    input_tokens: int = Field(
        ...,
        ge=0,
        description="입력 토큰 수 (>= 0).",
    )
    output_tokens: int = Field(
        ...,
        ge=0,
        description="출력 토큰 수 (>= 0).",
    )
    cache_read_tokens: int = Field(
        default=0,
        ge=0,
        description=(
            "prompt cache 에서 읽은 토큰 수 (>= 0). 0 이면 캐시 미사용. "
            "Anthropic prompt caching 정밀 비용 산정 입력."
        ),
    )
    latency_ms: int = Field(
        ...,
        ge=0,
        description="LLM 호출 시작 ~ 응답 완료까지 경과 시간 (ms, >= 0).",
    )
    status: LlmUsageStatus = Field(
        ...,
        description=(
            "호출 결과 상태. ``LlmUsageStatus`` Literal — 'success' | 'schema_invalid' "
            "| 'timeout' | 'network_error' | 'rate_limited' | 'other'. 새 status 가 "
            "필요하면 본 Literal 을 1차로 갱신."
        ),
    )
    error_class: str | None = Field(
        default=None,
        max_length=128,
        description="예외 클래스명 (실패 시). 성공 (``status == 'success'``) 시 None.",
    )
    cost_usd: Decimal | None = Field(
        default=None,
        description=(
            "USD 환산 비용 (nullable — 추후 백필 가능). ``Decimal`` — ORM "
            "``Numeric(precision=12, scale=8)`` 과 정합. ``float`` 는 silent precision "
            "loss 위험으로 금지."
        ),
    )
    created_at: datetime = Field(
        ...,
        description=(
            "이벤트 생성 시각 (UTC, **timezone-aware 강제**). naive datetime 은 거절 — "
            "``ExtractionMetaRef.extracted_at`` 과 동일 정책."
        ),
    )

    @field_validator("created_at")
    @classmethod
    def _validate_timezone_aware(cls, value: datetime) -> datetime:
        """``created_at`` 은 timezone-aware 강제 (naive datetime 금지).

        ``shared.schemas.common.utc_now()`` 는 timezone-aware UTC 를 반환한다.
        naive datetime (예: ``datetime.utcnow()``) 으로 채워지면 즉시 거절.
        ``ExtractionMetaRef._validate_timezone_aware`` 와 같은 정책.
        """
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError(
                "created_at 은 timezone-aware datetime 이어야 한다 "
                "(naive datetime 거절 — utc_now() 사용)."
            )
        return value
