"""``BaseEntity.model_config`` 의 ``from_attributes=True`` 회귀 가드.

ADR-0005 §D-5.5 의 ORM → 도메인 변환 패턴 (`Passage.model_validate(passage_orm)`)
이 동작하려면 ``BaseEntity.model_config.from_attributes`` 가 ``True`` 여야 한다.
P0-1 (Repository 레이어) 의 차단 항목으로, 이 옵션이 누락되면 모든 ORM → 도메인
변환이 ``ValidationError`` 로 즉시 실패한다.

본 테스트는 SQLModel / SQLAlchemy 의존성 없이 ORM 객체의 attribute 접근 형태만
재현하는 더미 객체로 검증한다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from shared.schemas.common import BaseEntity
from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade


class _OrmLike:
    """ORM 객체처럼 attribute 접근으로 필드를 노출하는 더미.

    실제 SQLModel / SQLAlchemy ORM 인스턴스는 본 더미와 동일한 attribute 인터페이스를
    가지므로, ``model_validate`` 동작은 동등.
    """

    def __init__(self, **fields: object) -> None:
        for key, value in fields.items():
            setattr(self, key, value)


def test_base_entity_config_has_from_attributes() -> None:
    """``BaseEntity.model_config["from_attributes"]`` 가 ``True``."""

    assert BaseEntity.model_config.get("from_attributes") is True


def test_passage_model_validate_from_orm_like_object() -> None:
    """ORM-like 더미 객체에서 ``Passage.model_validate`` 가 성공한다.

    P0-1 Repository 의 ``_to_domain`` 변환 패턴 (ADR-0005 §D-5.5) 의 회귀 가드.
    """

    tenant_id = uuid4()
    workspace_id = uuid4()
    now = datetime.now(UTC)

    orm_like = _OrmLike(
        id=uuid4(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        topic_tags=["climate"],
        source=SourceMeta(provider=SourceProvider.AINGKA),
        target_grade=TargetGrade.HIGH_2,
        body_text="Climate change is real.",
        paragraphs=["Climate change is real."],
        word_count=4,
        created_at=now,
        updated_at=now,
    )

    passage = Passage.model_validate(orm_like)

    assert passage.tenant_id == tenant_id
    assert passage.workspace_id == workspace_id
    assert passage.body_text == "Climate change is real."
    assert passage.target_grade is TargetGrade.HIGH_2
