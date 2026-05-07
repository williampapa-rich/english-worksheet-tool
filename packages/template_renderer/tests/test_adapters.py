"""branding_to_academy_dict / worksheet_to_template_context 단위 테스트.

검증 케이스 (branding_to_academy_dict):
  1. 모든 필드 채워진 케이스 — 정상 매핑
  2. 모든 필드 None 케이스 — None 그대로 통과
  3. partial 케이스 — logo_url 만 있음
  4. 반환 dict 키 집합 고정 검증 — secondary_color 포함되지 않음

검증 케이스 (worksheet_to_template_context):
  5. full — worksheet + branding + passages 모두 있음
  6. minimal — items 없음 (빈 questions 반환)
  7. multi_items — items 여러 개, order 역순 정렬도 올바르게 처리
  8. branding=Branding() — 기본값 (all None) 도 안전하게 동작
"""

import uuid

import pytest
from template_renderer.adapters import branding_to_academy_dict, worksheet_to_template_context

from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade
from shared.schemas.worksheet import Branding, Worksheet, WorksheetItem, WorksheetKind

# ─── 헬퍼 팩토리 ─────────────────────────────────────────────────────────────

_TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_WORKSPACE_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _make_passage(passage_id: uuid.UUID | None = None, body_text: str = "Test passage body.") -> Passage:
    """테스트용 Passage 팩토리."""
    pid = passage_id or uuid.uuid4()
    return Passage(
        id=pid,
        tenant_id=_TENANT_ID,
        workspace_id=_WORKSPACE_ID,
        body_text=body_text,
        paragraphs=[body_text],
        word_count=len(body_text.split()),
        target_grade=TargetGrade.HIGH_3,
        topic_tags=[],
        source=SourceMeta(provider=SourceProvider.USER_INPUT),
    )


def _make_worksheet(
    items: list[WorksheetItem] | None = None,
    branding: Branding | None = None,
) -> Worksheet:
    """테스트용 Worksheet 팩토리."""
    return Worksheet(
        tenant_id=_TENANT_ID,
        workspace_id=_WORKSPACE_ID,
        title="테스트 워크시트",
        subtitle="Week 01",
        kind=WorksheetKind.STUDENT,
        template_id="playful",
        instruction="다음 지문을 읽고 물음에 답하시오.",
        branding=branding or Branding(
            academy_name="테스트학원",
            primary_color="#1F4E79",
        ),
        items=items or [],
    )


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


class TestWorksheetToTemplateContext:
    """worksheet_to_template_context 테스트 스위트."""

    def test_full_context(self) -> None:
        """worksheet + branding + passages 모두 채워진 full 케이스 — 모든 key 정상 매핑."""
        passage_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        passage = _make_passage(passage_id=passage_id, body_text="Hello world.")
        item = WorksheetItem(passage_id=passage_id, order=0, label="독해 연습")
        worksheet = _make_worksheet(items=[item])

        ctx = worksheet_to_template_context(worksheet, [passage])

        # academy 매핑
        assert ctx["academy"]["name"] == "테스트학원"
        assert ctx["academy"]["theme_color"] == "#1F4E79"
        # worksheet 매핑
        assert ctx["worksheet"]["title"] == "테스트 워크시트"
        assert ctx["worksheet"]["subtitle"] == "Week 01"
        assert ctx["worksheet"]["orientation"] == "portrait"
        assert ctx["worksheet"]["page_number"] == 1
        assert ctx["worksheet"]["total_pages"] == 1
        # student 빈칸 default
        assert ctx["student"] == {"name": "", "class_name": "", "date": ""}
        # instruction
        assert ctx["instruction"] == "다음 지문을 읽고 물음에 답하시오."
        # questions
        assert len(ctx["questions"]) == 1
        q = ctx["questions"][0]
        assert q["number"] == 1
        assert q["label"] == "독해 연습"
        # content_html 은 body_text 를 <p> wrap — 이 PR 의 한계 (annotation 렌더 미구현)
        assert "Hello world." in q["content_html"]
        assert q["content_html"].startswith("<p>")

    def test_minimal_no_items(self) -> None:
        """items 없는 worksheet — questions 빈 리스트 반환, 다른 key 는 정상."""
        worksheet = _make_worksheet(items=[])

        ctx = worksheet_to_template_context(worksheet, [])

        assert ctx["questions"] == []
        assert ctx["worksheet"]["title"] == "테스트 워크시트"
        assert ctx["student"] == {"name": "", "class_name": "", "date": ""}

    def test_multi_items_order_respected(self) -> None:
        """items 여러 개 — order 기준으로 정렬되고 1-indexed number 부여."""
        pid_a = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
        pid_b = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
        passage_a = _make_passage(passage_id=pid_a, body_text="First passage.")
        passage_b = _make_passage(passage_id=pid_b, body_text="Second passage.")

        # order 를 역순 (1, 0) 으로 줘서 정렬 검증
        item_a = WorksheetItem(passage_id=pid_a, order=1, label="두 번째")
        item_b = WorksheetItem(passage_id=pid_b, order=0, label="첫 번째")
        worksheet = _make_worksheet(items=[item_a, item_b])

        ctx = worksheet_to_template_context(worksheet, [passage_a, passage_b])

        assert len(ctx["questions"]) == 2
        # order=0 인 item_b 가 먼저 와야 한다
        assert ctx["questions"][0]["label"] == "첫 번째"
        assert ctx["questions"][0]["number"] == 1
        assert "Second passage." in ctx["questions"][0]["content_html"]
        assert ctx["questions"][1]["label"] == "두 번째"
        assert ctx["questions"][1]["number"] == 2
        assert "First passage." in ctx["questions"][1]["content_html"]

    def test_branding_none_fields_safe(self) -> None:
        """Branding 기본값 (모든 필드 None) 이어도 안전하게 동작한다."""
        worksheet = _make_worksheet(branding=Branding())

        ctx = worksheet_to_template_context(worksheet, [])

        assert ctx["academy"]["name"] is None
        assert ctx["academy"]["theme_color"] is None
        assert ctx["academy"]["logo_url"] is None
        # 다른 key 는 정상
        assert ctx["student"] == {"name": "", "class_name": "", "date": ""}
        assert ctx["questions"] == []
