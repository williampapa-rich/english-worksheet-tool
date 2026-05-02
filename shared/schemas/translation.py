"""Translation(한글 해석) 도메인 모델.

PM 결정 D-2 (`docs/adr/_pm-decisions-sprint-0.md`) 반영:
  - 1 Passage : 1 Translation (1:1).
  - DB 레벨에서 ``passage_id`` UNIQUE 제약으로 강제 — backend-dev 의 SQLAlchemy
    마이그레이션에서 박는다 (본 Pydantic 모델은 타입만 명시).
  - ``language: Literal["ko"]`` 로 v0.1 고정. 다중 언어는 v0.2+ 검토.
  - 부분 해석 (``SentenceTranslation``) 은 v0.1 제외. Phase 2 에서 별 모델로 추가.
  - 사용자가 LLM 결과를 직접 수정하면 ``text`` 를 in-place 업데이트 +
    ``created_by="user"`` 로 변경 + ``updated_at`` 갱신. **이전 버전 보존 없음**.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from shared.schemas.common import EntityId, WorkspaceScopedEntity


class TranslationCreatedBy(StrEnum):
    """해석 생성 주체."""

    LLM = "llm"  # LLM 자동 생성
    USER = "user"  # 사용자가 직접 작성 또는 LLM 결과를 수정


class Translation(WorkspaceScopedEntity):
    """Passage 1건에 대한 한국어 해석 (1:1).

    한 Passage 는 정확히 하나의 Translation 을 가진다. ``passage_id`` 에 DB UNIQUE
    제약을 박아 1:1 강제 (backend-dev 의 마이그레이션 책임).

    사용자가 LLM 결과를 수정하면 ``text`` 를 in-place 업데이트하고
    ``created_by`` 를 ``USER`` 로 변경한다. 이전 버전은 보존하지 않는다 (PM 결정).
    """

    passage_id: EntityId = Field(
        ...,
        description=(
            "참조 Passage ID (FK → passages.id). DB 레벨에서 UNIQUE 제약 — 1 Passage : "
            "1 Translation (PM 결정 D-2)."
        ),
    )
    language: Literal["ko"] = Field(
        default="ko",
        description="해석 언어. v0.1 은 한국어 (``ko``) 고정.",
    )
    text: str = Field(
        ...,
        description="전체 해석 본문.",
    )
    created_by: TranslationCreatedBy = Field(
        ...,
        description="해석 생성 주체 (LLM / user). 사용자 수정 시 ``user`` 로 변경.",
    )
