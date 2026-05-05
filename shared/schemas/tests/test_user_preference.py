"""``shared.schemas.user_preference`` 단위 테스트.

ADR-0009 (`docs/adr/0009-user-preferences.md`) 의 결정을 닫는 모델의 검증:
  - dot-notation key 규칙 강제 (정상 / 부적합 형식).
  - ``UserPreference`` 정상 생성 + tenant_id / user_id 필수 + workspace_id Optional.
  - ``UserPreferenceInput`` (DTO) — tenant_id / user_id 없음 (server-side 주입 가드레일).
  - ``SentenceRolePresetValue`` — value schema 1예시의 정상 / 길이 / 타입 검증.
  - ``extra="forbid"`` — 알 수 없는 필드 거절.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from shared.schemas.user_preference import (
    SentenceRolePresetValue,
    UserPreference,
    UserPreferenceInput,
)

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()


def _make_kwargs(**overrides: Any) -> dict[str, Any]:
    """최소 valid UserPreference kwargs.

    ``Any`` 어노테이션은 ``UserPreference.value`` 가 ``dict[str, Any]`` 라 invariant
    문제로 ``dict[str, object]`` 에서 직접 unpacking 불가이기 때문 (mypy 권고:
    "dict is invariant").
    """
    base: dict[str, Any] = {
        "tenant_id": TENANT_ID,
        "user_id": USER_ID,
        "key": "preset.sentence_role",
        "value": {"presets": ["S", "V", "O"]},
    }
    base.update(overrides)
    return base


# ─── UserPreference happy path ────────────────────────────────────────────


class TestUserPreferenceHappyPath:
    def test_minimal_valid(self) -> None:
        pref = UserPreference(**_make_kwargs())
        assert pref.tenant_id == TENANT_ID
        assert pref.user_id == USER_ID
        assert pref.workspace_id is None
        assert pref.key == "preset.sentence_role"
        assert pref.value == {"presets": ["S", "V", "O"]}

    def test_with_workspace_id(self) -> None:
        pref = UserPreference(**_make_kwargs(workspace_id=WORKSPACE_ID))
        assert pref.workspace_id == WORKSPACE_ID

    def test_palette_key(self) -> None:
        pref = UserPreference(
            **_make_kwargs(
                key="palette.colors",
                value={"colors": ["#ff0000", "#00ff00"]},
            )
        )
        assert pref.key == "palette.colors"

    def test_three_segment_key(self) -> None:
        # 3 segment 도 허용 — `editor.font.size` 처럼 sub-scope 가능.
        pref = UserPreference(**_make_kwargs(key="editor.font.size", value={"px": 14}))
        assert pref.key == "editor.font.size"


# ─── UserPreference 필수 필드 검증 ────────────────────────────────────────


class TestUserPreferenceRequiredFields:
    def test_tenant_id_required(self) -> None:
        kwargs = _make_kwargs()
        kwargs.pop("tenant_id")
        with pytest.raises(ValidationError) as exc:
            UserPreference(**kwargs)
        assert "tenant_id" in str(exc.value)

    def test_user_id_required(self) -> None:
        kwargs = _make_kwargs()
        kwargs.pop("user_id")
        with pytest.raises(ValidationError) as exc:
            UserPreference(**kwargs)
        assert "user_id" in str(exc.value)

    def test_key_required(self) -> None:
        kwargs = _make_kwargs()
        kwargs.pop("key")
        with pytest.raises(ValidationError) as exc:
            UserPreference(**kwargs)
        assert "key" in str(exc.value)

    def test_value_required(self) -> None:
        kwargs = _make_kwargs()
        kwargs.pop("value")
        with pytest.raises(ValidationError) as exc:
            UserPreference(**kwargs)
        assert "value" in str(exc.value)


# ─── key dot-notation 규칙 검증 ───────────────────────────────────────────


class TestUserPreferenceKeyFormat:
    @pytest.mark.parametrize(
        "valid_key",
        [
            "preset.sentence_role",
            "palette.colors",
            "editor.layout",
            "editor.font.size",
            "a.b",  # 최소 형태.
            "domain1.scope_2",  # 숫자 / underscore.
        ],
    )
    def test_valid_keys(self, valid_key: str) -> None:
        pref = UserPreference(**_make_kwargs(key=valid_key))
        assert pref.key == valid_key

    @pytest.mark.parametrize(
        "invalid_key",
        [
            "no_dot",  # 1 segment 거절.
            "Preset.UPPER",  # 대문자 거절.
            "1preset.scope",  # 숫자 시작 거절.
            ".leading_dot",  # leading dot.
            "trailing.",  # trailing dot.
            "preset..double",  # 빈 segment.
            "preset.scope-with-dash",  # dash 거절.
            "preset.scope with space",  # space 거절.
            "",  # 빈 문자열.
            "한글.안됨",  # ASCII only.
        ],
    )
    def test_invalid_keys(self, invalid_key: str) -> None:
        with pytest.raises(ValidationError, match="dot-notation"):
            UserPreference(**_make_kwargs(key=invalid_key))

    def test_max_length(self) -> None:
        # 128자 초과 거절 — Pydantic Field max_length.
        long_key = "a." + ("b" * 128)  # 130자.
        with pytest.raises(ValidationError):
            UserPreference(**_make_kwargs(key=long_key))


# ─── extra="forbid" 강제 ──────────────────────────────────────────────────


class TestUserPreferenceForbidExtra:
    def test_unknown_field_rejected(self) -> None:
        kwargs = _make_kwargs(unknown_field="foo")
        with pytest.raises(ValidationError, match="(?i)extra|unknown|not permitted"):
            UserPreference(**kwargs)


# ─── UserPreferenceInput (DTO) ────────────────────────────────────────────


class TestUserPreferenceInput:
    def test_minimal_valid(self) -> None:
        dto = UserPreferenceInput(
            key="preset.sentence_role",
            value={"presets": ["S", "V"]},
        )
        assert dto.key == "preset.sentence_role"
        assert dto.workspace_id is None

    def test_with_workspace_id(self) -> None:
        dto = UserPreferenceInput(
            workspace_id=WORKSPACE_ID,
            key="editor.layout",
            value={"columns": 2},
        )
        assert dto.workspace_id == WORKSPACE_ID

    def test_tenant_id_rejected(self) -> None:
        # 가드레일 — DTO 에 tenant_id 가 들어오면 거절 (server-side 주입 강제).
        with pytest.raises(ValidationError, match="(?i)extra|not permitted"):
            UserPreferenceInput(  # type: ignore[call-arg]
                tenant_id=TENANT_ID,
                key="preset.sentence_role",
                value={"presets": []},
            )

    def test_user_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="(?i)extra|not permitted"):
            UserPreferenceInput(  # type: ignore[call-arg]
                user_id=USER_ID,
                key="preset.sentence_role",
                value={"presets": []},
            )

    def test_invalid_key_rejected(self) -> None:
        with pytest.raises(ValidationError, match="dot-notation"):
            UserPreferenceInput(key="no_dot", value={})


# ─── SentenceRolePresetValue (value schema 예시) ──────────────────────────


class TestSentenceRolePresetValue:
    def test_default_empty(self) -> None:
        v = SentenceRolePresetValue()
        assert v.presets == []

    def test_typical(self) -> None:
        v = SentenceRolePresetValue(presets=["S", "V", "O", "OC", "SC", "M"])
        assert v.presets == ["S", "V", "O", "OC", "SC", "M"]

    def test_empty_string_label_rejected(self) -> None:
        with pytest.raises(ValidationError, match="1~16자"):
            SentenceRolePresetValue(presets=[""])

    def test_too_long_label_rejected(self) -> None:
        with pytest.raises(ValidationError, match="1~16자"):
            SentenceRolePresetValue(presets=["a" * 17])

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError, match="(?i)extra|not permitted"):
            SentenceRolePresetValue(presets=[], unknown="foo")  # type: ignore[call-arg]

    def test_application_layer_validation_pattern(self) -> None:
        """라우터에서 ``UserPreference.value`` 를 key 에 따라 검증하는 패턴 시연.

        ADR-0009 §value 검증 전략 — 라우터가 key 별로 적절한 Pydantic 모델로 검증.
        """
        pref = UserPreference(**_make_kwargs())
        # key 가 'preset.sentence_role' 이므로 SentenceRolePresetValue 로 검증.
        validated = SentenceRolePresetValue.model_validate(pref.value)
        assert validated.presets == ["S", "V", "O"]

    def test_application_layer_validation_failure(self) -> None:
        """key 에 맞지 않는 value 가 들어오면 application 레이어 검증이 실패."""
        pref = UserPreference(
            **_make_kwargs(value={"presets": ["a" * 100]})  # 너무 긴 라벨.
        )
        with pytest.raises(ValidationError, match="1~16자"):
            SentenceRolePresetValue.model_validate(pref.value)
