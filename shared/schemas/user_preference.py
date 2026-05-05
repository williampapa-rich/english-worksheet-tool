"""UserPreference(사용자 환경설정) 도메인 모델.

ADR-0009 (`docs/adr/0009-user-preferences.md`) 의 결정을 닫는 스키마.

배경 (ADR-0009 §Context 요약):
  Phase 1 마감 사이클에서 PM 이 사용자별 커스터마이징 (분석표 성분 preset / 색
  팔레트 / 추후 옵션) 을 백엔드 영속 + Phase 4 OAuth 호환으로 가져가기로 결정.
  본 모듈은 그 인프라의 **단일 key-value 테이블** (단일 ``user_preferences`` 테이블
  / 옵션 도메인별 별 테이블 X) 을 닫는 도메인 모델이다.

핵심 결정:
  - **단일 테이블** + dot-notation key + JSONB value (ADR-0009 §Decision 채택안 C).
  - 키는 ``<domain>.<scope>`` (예: ``preset.sentence_role`` / ``palette.colors``).
  - value 는 JSONB 자유 형식이지만 key 별 schema 를 별 Pydantic 모델로 정의해
    application 레이어에서 검증 (본 파일의 ``SentenceRolePresetValue`` 가 1예시).
  - ``user_id`` 를 처음부터 박아 Phase 4 OAuth 진입 시 데이터 마이그레이션 없이
    사용자별 자동 분리. Phase 1 은 ``MVP_USER_ID`` sentinel UUID 1개로 stub.
  - ``workspace_id`` 는 Optional — 워크스페이스별 분리가 필요한 옵션은 채우고,
    테넌트 전역 옵션은 None.
  - ``version`` 필드로 낙관적 동시성 제어 (ADR-0009 §D8). 같은 사용자가 다른 탭/
    디바이스에서 동시 PATCH 시 후행 요청을 409 로 거절. 응답 직렬화 시 클라이언트가
    echo 해 다음 PATCH 요청에 실음.

멀티테넌트 정책:
  본 엔티티는 ``WorkspaceScopedEntity`` 가 아니다 — ``workspace_id`` 가 Optional
  이기 때문. 대신 ``TenantScopedEntity`` 를 베이스로 하고 ``workspace_id`` 를 직접
  Optional 필드로 박는다. ``tenant_id`` + ``user_id`` 조합으로 모든 쿼리에 격리
  강제 (repository 레이어 책임 — 본 PR 범위 밖).

관련 문서:
  - ``docs/adr/0009-user-preferences.md`` (본 모듈의 결정 기록)
  - ``docs/adr/0001-canonical-schema-philosophy.md`` (canonical schema 척추)
  - ``apps/api/src/worksheet_api/repositories/tenant_context.py`` (``user_id`` 주입)
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.schemas.common import EntityId, TenantScopedEntity

# ─── key 명명 규칙 ────────────────────────────────────────────────────────
# dot-notation: ``<domain>.<scope>`` 또는 ``<domain>.<scope>.<sub>``.
# - 도메인 prefix 가 충돌 방지 (예: ``preset.``, ``palette.``, ``editor.``).
# - 영문 소문자 + 숫자 + ``_`` 만 허용. 각 segment 는 영문자로 시작.
# - 최소 2 segment (도메인 + scope) 필수.
# - 최대 길이 128 (DB 인덱스 효율 / 식별자 가독성).
#
# 예시:
#   - ``preset.sentence_role``     (성분 preset 리스트)
#   - ``palette.colors``           (색 팔레트)
#   - ``editor.layout``            (에디터 레이아웃 환경설정)
#   - ``editor.font_size``         (에디터 폰트 크기)
#
# 규칙 변경은 ADR-0009 갱신 + 마이그레이션 동반.
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
_KEY_MAX_LENGTH = 128


# ─── value schema 예시 — 'preset.sentence_role' ───────────────────────────


class SentenceRolePresetValue(BaseModel):
    """``key='preset.sentence_role'`` 의 value JSONB schema (1예시).

    분석표 성분 preset — 사용자가 자주 쓰는 성분 라벨 목록 (예: ``["S", "V", "O",
    "OC", "SC", "M"]``). 에디터의 라벨 chip palette 에 노출된다.

    본 모델은 application 레이어 (FastAPI 라우터 / repository) 가 ``UserPreference.value``
    JSONB 를 key 에 따라 ``SentenceRolePresetValue.model_validate(value)`` 로 검증할
    때 사용한다. 검증 실패 시 422 Unprocessable Entity.

    다른 key (palette.colors 등) 의 value schema 는 후속 PR 에서 본 패턴 그대로
    추가 — 본 PR 은 ``preset.sentence_role`` 만 1예시로 정의 (스키마 패턴 시연).

    필드 정책:
      - ``presets``: 빈 list 허용 (사용자가 모든 preset 을 비워둘 수 있음).
        각 항목은 1~16자 자유 문자열 (긴 라벨 방지). 중복 허용 — 사용자가 같은 라벨을
        의도적으로 두 번 쓸 가능성 (예: 다른 색으로 같은 라벨) 을 데이터 모델이 막지 않음.
    """

    model_config = ConfigDict(extra="forbid")

    presets: list[str] = Field(
        default_factory=list,
        description=(
            "성분 라벨 preset 리스트 (예: ``['S', 'V', 'O', 'OC', 'SC']``). 빈 list 허용. "
            "각 항목은 1~16자 자유 문자열."
        ),
    )

    @field_validator("presets")
    @classmethod
    def _validate_label_lengths(cls, value: list[str]) -> list[str]:
        """각 라벨이 1~16자 범위인지 검증."""
        for idx, label in enumerate(value):
            if not isinstance(label, str):
                raise ValueError(f"presets[{idx}] 은 str 이어야 한다 (got {type(label).__name__}).")
            if len(label) < 1 or len(label) > 16:
                raise ValueError(f"presets[{idx}] 길이는 1~16자 (got {len(label)}자: {label!r}).")
        return value


# ─── UserPreference (도메인 엔티티) ───────────────────────────────────────


class UserPreference(TenantScopedEntity):
    """사용자별 환경설정 1건 (단일 key-value 테이블의 1행).

    ADR-0009 §Decision 채택안 C — 도메인별 별 테이블 대신 단일 ``user_preferences``
    테이블 + dot-notation key + JSONB value. 미래 옵션 추가 시 마이그레이션 비용 0.

    테이블 정합성 (ORM 책임 — 본 PR 범위 밖):
      ``UNIQUE(tenant_id, user_id, workspace_id, key)`` — 같은 사용자가 같은 워크스페이스
      범위 (또는 None=테넌트 전역) 에서 같은 key 를 두 번 갖지 못함. 업데이트는 in-place
      (``updated_at`` 갱신).

    Phase 1 stub 운영:
      ``user_id`` 는 ``MVP_USER_ID`` sentinel UUID (env). Phase 4 OAuth 도입 시 실제
      ``sub`` 클레임 매핑 — 마이그레이션 정책은 ADR-0009 §Phase 4 마이그레이션.

    멀티테넌트:
      ``tenant_id`` 는 ``TenantScopedEntity`` 에서 NOT NULL 상속. ``workspace_id`` 는
      여기서 Optional 직접 박음 (``WorkspaceScopedEntity`` 와 다름) — 워크스페이스
      범위 분리가 필요한 옵션과 테넌트 전역 옵션을 같은 테이블로 다룸.
    """

    user_id: EntityId = Field(
        ...,
        description=(
            "사용자 ID (NOT NULL). Phase 1: ``MVP_USER_ID`` sentinel UUID stub. "
            "Phase 4: OAuth ``sub`` 클레임 매핑 (ADR-0009 §Phase 4 마이그레이션)."
        ),
    )
    workspace_id: EntityId | None = Field(
        default=None,
        description=(
            "워크스페이스 ID (Optional). 워크스페이스 범위 분리가 필요한 옵션은 채우고, "
            "테넌트 전역 옵션은 None. ``WorkspaceScopedEntity`` 와 달리 직접 Optional 필드."
        ),
    )
    key: str = Field(
        ...,
        max_length=_KEY_MAX_LENGTH,
        description=(
            "환경설정 key (dot-notation). ``<domain>.<scope>`` (예: "
            "``'preset.sentence_role'`` / ``'palette.colors'`` / ``'editor.layout'``). "
            "영문 소문자 + 숫자 + ``_`` + 최소 2 segment."
        ),
    )
    value: dict[str, Any] = Field(
        ...,
        description=(
            "JSONB 자유 형식 value. key 에 따라 application 레이어가 별 Pydantic 모델 "
            "(예: ``SentenceRolePresetValue``) 로 검증. dict (object) 가 아닌 raw scalar "
            "/ list 가 필요하면 dict 안에 wrapping (예: ``{'items': [...]}``)."
        ),
    )
    version: int = Field(
        default=1,
        ge=1,
        description=(
            "낙관적 동시성 제어 버전 (ADR-0009 §D8). 행이 처음 생성될 때 1, PATCH 마다 +1. "
            "클라이언트는 GET 응답의 ``version`` 을 다음 PATCH 요청 body 에 echo 해야 한다 — "
            "DB 의 현재 버전과 다르면 409 Conflict (다른 탭/디바이스의 선행 PATCH 와 충돌). "
            "최초 생성 (DB 행이 없는 상태) 시 검사 안 함. ``ge=1`` — 0 또는 음수 거절."
        ),
    )

    @field_validator("key")
    @classmethod
    def _validate_key_format(cls, value: str) -> str:
        """key 가 dot-notation 규칙을 따르는지 검증.

        규칙:
          - 영문 소문자 + 숫자 + ``_`` 만 허용.
          - 각 segment 는 영문자로 시작.
          - 최소 2 segment (도메인 + scope).
          - 최대 길이 128 (Field max_length 와 중복 가드).
        """
        if not _KEY_PATTERN.match(value):
            raise ValueError(
                f"key 는 dot-notation 규칙을 따라야 한다 (예: 'preset.sentence_role'). "
                f"영문 소문자 + 숫자 + '_' + 최소 2 segment. got: {value!r}"
            )
        return value


# ─── DTO — API 입력 (PATCH body) ──────────────────────────────────────────


class UserPreferencePatchInput(BaseModel):
    """``PATCH /preferences/{key}`` 요청 body DTO (ADR-0009 §D7 / §D8).

    server-side 컨텍스트 (``tenant_id`` / ``user_id``) 와 path param (``key``) 을 제외한
    PATCH body 모델. 라우터는 ``TenantContext`` Depends 로 ``tenant_id`` / ``user_id``
    를 주입받고, path param ``key`` 와 본 DTO 의 ``value`` / ``workspace_id`` /
    ``version`` 을 합쳐 upsert 한다.

    멀티테넌트 격리 (ADR-0009 §D7):
      본 DTO 에 ``tenant_id`` / ``user_id`` 가 없는 것은 의도. 클라이언트가 임의의
      tenant/user 로 위장하는 것을 데이터 모델 레벨에서 차단. ``model_config =
      ConfigDict(extra="forbid")`` 로 ``tenant_id`` / ``user_id`` / ``key`` 가 들어오면
      즉시 422 거절.

    낙관적 동시성 (ADR-0009 §D8):
      ``version`` 이 None 이면 최초 생성 분기 (DB 행 없음). 행이 있는 상태에서 None 또는
      DB 와 다른 값이 들어오면 409. 정상 갱신 흐름은: GET → 서버가 현재 ``version`` 반환
      → 클라이언트가 PATCH body 에 echo → 서버가 일치 확인 후 ``version + 1`` 로 저장.

    이 DTO 는 PR #33 의 ``UserPreferenceInput`` 을 PATCH body 형태에 맞춰 재정의한
    것 — ``key`` 제거 (path param 으로 이동), ``version`` 추가. ``apps/api`` 의
    ``PreferencePatchRequest`` 는 본 DTO 로 통합 예정 (PR #34 후속 수정).
    """

    model_config = ConfigDict(extra="forbid")

    value: dict[str, Any] = Field(
        ...,
        description=(
            "JSONB value. key 에 따라 라우터가 별 Pydantic 모델로 추가 검증 (실패 시 422)."
        ),
    )
    workspace_id: EntityId | None = Field(
        default=None,
        description=(
            "워크스페이스 ID (Optional). 워크스페이스 범위 분리가 필요한 옵션은 채우고, "
            "테넌트 전역 옵션은 None."
        ),
    )
    version: int | None = Field(
        default=None,
        ge=1,
        description=(
            "낙관적 동시성 버전 (Optional, ADR-0009 §D8). 클라이언트가 직전 GET 응답의 "
            "``version`` 을 echo. DB 의 현재 버전과 다르면 409 Conflict. 최초 생성 (DB 행 "
            "없음) 시 None 또는 임의 값 — 행이 없으므로 검사 안 함. ``ge=1`` — 0 또는 "
            "음수 거절."
        ),
    )
