"""Branding ↔ 템플릿 academy dict 매핑 어댑터.

ADR-0010 §D3 / §D6 구현.

매핑 결정 (``docs/template-rendering-analysis.md`` §2.3 인용):
  - ``academy.name``        ← ``branding.academy_name``  (ADR-0010 §D3)
  - ``academy.theme_color`` ← ``branding.primary_color``
  - ``academy.logo_url``    ← ``branding.logo_url``
  - ``secondary_color``     매핑하지 않음 (현 템플릿 미사용 — 보관 ADR-0010 §D6)

사용 예시::

    from shared.schemas.worksheet import Branding
    from template_renderer.adapters import branding_to_academy_dict

    branding = Branding(
        academy_name="윌리엄 영어학원",
        primary_color="#1F4E79",
        logo_url="https://example.com/logo.png",
    )
    academy = branding_to_academy_dict(branding)
    # {"name": "윌리엄 영어학원", "theme_color": "#1F4E79", "logo_url": "https://..."}
"""

from shared.schemas.worksheet import Branding


def branding_to_academy_dict(branding: Branding) -> dict[str, str | None]:
    """``Branding`` Pydantic 모델을 템플릿 ``academy.*`` 변수 dict 로 변환.

    templates/{classic,modern,playful}.html 의 ``academy.name`` / ``academy.theme_color``
    / ``academy.logo_url`` 변수와 1:1 매핑.

    Args:
        branding: ``shared.schemas.worksheet.Branding`` 인스턴스.
            모든 필드가 None 이어도 안전하게 None 을 그대로 통과한다.

    Returns:
        템플릿 Jinja2 컨텍스트의 ``academy`` key 에 직접 전달할 dict.
        keys: ``name``, ``theme_color``, ``logo_url``.

    Note:
        - ``secondary_color`` 는 매핑하지 않는다 (현 템플릿 3종 미사용 — ADR-0010 §D6).
        - 반환값이 None 인 필드는 템플릿에서 폴백 처리 (예: 기본 파란색, 텍스트/아이콘 폴백).
    """
    return {
        "name": branding.academy_name,
        "theme_color": branding.primary_color,
        "logo_url": branding.logo_url,
    }
