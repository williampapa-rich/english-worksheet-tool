"""branding_to_academy_dict 단위 테스트.

검증 케이스:
  1. 모든 필드 채워진 케이스 — 정상 매핑
  2. 모든 필드 None 케이스 — None 그대로 통과
  3. partial 케이스 — logo_url 만 있음
  4. 반환 dict 키 집합 고정 검증 — secondary_color 포함되지 않음
"""

import pytest
from template_renderer.adapters import branding_to_academy_dict

from shared.schemas.worksheet import Branding


class TestBrandingToAcademyDict:
    """branding_to_academy_dict 테스트 스위트."""

    def test_all_fields_populated(self) -> None:
        """모든 Branding 필드가 채워진 경우 academy dict 로 정확히 매핑된다."""
        branding = Branding(
            academy_name="윌리엄 영어학원",
            primary_color="#1F4E79",
            secondary_color="#E9F0F8",  # 매핑 안 되는 필드 — 반환에 없어야 함
            logo_url="https://example.com/logo.png",
        )
        result = branding_to_academy_dict(branding)

        assert result["name"] == "윌리엄 영어학원"
        assert result["theme_color"] == "#1F4E79"
        assert result["logo_url"] == "https://example.com/logo.png"

    def test_all_fields_none(self) -> None:
        """모든 Branding 필드가 None 인 경우 None 을 그대로 통과한다."""
        branding = Branding()  # 모든 필드 default=None
        result = branding_to_academy_dict(branding)

        assert result["name"] is None
        assert result["theme_color"] is None
        assert result["logo_url"] is None

    def test_partial_logo_url_only(self) -> None:
        """logo_url 만 있는 partial 케이스 — logo_url 만 채워지고 나머지는 None."""
        branding = Branding(logo_url="https://example.com/logo.png")
        result = branding_to_academy_dict(branding)

        assert result["logo_url"] == "https://example.com/logo.png"
        assert result["name"] is None
        assert result["theme_color"] is None

    def test_partial_academy_name_and_color(self) -> None:
        """academy_name + primary_color 만 있는 partial 케이스."""
        branding = Branding(academy_name="테스트학원", primary_color="#FF0000")
        result = branding_to_academy_dict(branding)

        assert result["name"] == "테스트학원"
        assert result["theme_color"] == "#FF0000"
        assert result["logo_url"] is None

    def test_secondary_color_not_in_result(self) -> None:
        """secondary_color 는 현 템플릿 미사용 (ADR-0010 §D6) — 반환 dict 에 없어야 한다."""
        branding = Branding(
            secondary_color="#AABBCC",
            primary_color="#112233",
        )
        result = branding_to_academy_dict(branding)

        assert "secondary_color" not in result

    def test_return_keys_are_fixed(self) -> None:
        """반환 dict 의 키 집합은 항상 {name, theme_color, logo_url} 으로 고정된다."""
        branding = Branding(academy_name="테스트", primary_color="#000000")
        result = branding_to_academy_dict(branding)

        assert set(result.keys()) == {"name", "theme_color", "logo_url"}

    def test_return_type_is_dict(self) -> None:
        """반환 타입이 dict 임을 확인한다."""
        branding = Branding()
        result = branding_to_academy_dict(branding)

        assert isinstance(result, dict)

    @pytest.mark.parametrize(
        "academy_name",
        [
            "단일학원",
            "A Very Long Academy Name That Might Exceed Some Limit",
            "학원 with spaces",
            "",  # 빈 문자열 — Pydantic 허용
        ],
    )
    def test_academy_name_passthrough(self, academy_name: str) -> None:
        """academy_name 은 변환 없이 name 으로 그대로 전달된다."""
        branding = Branding(academy_name=academy_name)
        result = branding_to_academy_dict(branding)

        assert result["name"] == academy_name
