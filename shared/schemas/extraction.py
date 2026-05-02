"""Extraction(추출 결과 컨테이너) 도메인 모델.

ADR-0003 §D-3.1 의 ``Extractor.extract(request) -> result`` 시그니처를 닫는 스키마.
PM-5 (추출 스코프 옵션 B) + PM-6 (실유저 입력 분포) + ADR-0003 §G-1 / §G-5 권고를
그대로 반영한다.

본 모듈은 다음 3개 모델을 정의한다:
  - ``ExtractionRequest`` — extractor 입력 페이로드 (text / image / pdf).
  - ``ExtractionMetaRef`` — 어떤 LLM 호출에서 만들어진 결과인가 메타 (G-1 통합).
  - ``ExtractionResult`` — Passage + Question[] + (옵션) Translation / Vocabulary[].

PM-6 가정 (운영 핵심):
  실유저 입력의 default 는 "영어만" / "문제만" 이라 ``translation`` 은 거의 항상
  ``None``, ``vocabulary`` 는 거의 항상 빈 list. **이게 정상이다 — 에러가 아니다**.
  모든 후속 코드 (validator / qa-validator stub / UI 미리보기) 가 이 가정을 전제로
  설계된다. "translation 은 항상 채워져야 한다" 같은 잘못된 가정이 들어오는 것을
  본 docstring 이 가드레일.

ADR-0003 §D-3.6 — sentinel UUID 패턴:
  ``ExtractionResult.passage.tenant_id`` / ``workspace_id`` 는 extractor 호출 시점에
  ``uuid.UUID(int=0)`` (sentinel) 로 채워질 수 있다. 본 컨테이너는 이 사실을
  *모르고 그대로 받는다* — sentinel 검증은 repository 책임 (멀티테넌트 강제 단일
  지점). 본 PR 범위에서 sentinel 검증 추가하지 않음.

본 모듈은 ``extraction.py`` 단일 파일로 둔다. ``ExtractionMetaRef`` 를 별 파일
(``llm.py`` 등) 로 분리하면 ``ExtractionResult`` ↔ ``ExtractionMetaRef`` 간
import cycle 위험이 있어 (양쪽 모두 ``passage`` / ``question`` 등을 참조하지는 않
지만 미래 확장 시 양방향 의존이 생길 가능성), 같은 모듈에 묶는다 (architect 판단).

관련 문서:
  - ``docs/adr/0003-phase-0-extraction-pipeline.md`` §D-3.1, §G-1, §G-5
  - ``docs/phase-0-task-breakdown.md`` §6 (P0-0)
  - PM 결정 PM-5 / PM-6 (`docs/adr/0003-...` §"PM 결정")
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shared.schemas.passage import Passage
from shared.schemas.question import Question
from shared.schemas.translation import Translation
from shared.schemas.vocabulary import Vocabulary


# ─── ExtractionRequest ─────────────────────────────────────────────────────
class ExtractionRequest(BaseModel):
    """Extractor 입력 페이로드.

    ADR-0003 §D-3.1 의 ``Extractor.extract(request) -> result`` 시그니처를 닫는다.
    `kind` 디스크리미네이터에 따라 ``payload`` 의 의미가 달라진다:

      - ``kind == "text"``: ``payload: str`` — UTF-8 영어 지문 텍스트.
      - ``kind == "image"``: ``payload: bytes`` — PNG/JPEG/WEBP 이미지 raw bytes.
        ``media_type`` 필수 (``image/png`` 등).
      - ``kind == "pdf"``: ``payload: bytes`` — PDF raw bytes. ``force_vision`` 만
        의미 있음 (PM-3).

    표현 형태 (architect 판단):
      v0.1 은 단순 ``BaseModel + model_validator`` 로 둔다. Pydantic discriminated
      union 은 v0.1 에서 과한 추상화 — payload 가 ``str | bytes`` 두 종류이고
      kind 가 3종이라 cross-product 가 작아 validator 1개로 충분.
      Phase 1+ 에서 호출 패턴이 늘어나면 discriminated union 으로 교체 검토.

    ``force_vision`` 의미 (PM-3 확정):
      - ``kind == "pdf"`` 일 때만 의미 있음. PyMuPDF 휴리스틱 우회 + 즉시 Vision
        경로 (ADR-0003 §D-3.3).
      - ``kind == "text" / "image"`` 일 때 ``force_vision`` 은 무시 (validator 가
        명시적으로 거절하지는 않는다 — 호출자 편의 위해 default False 만 보장).
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["text", "image", "pdf"] = Field(
        ...,
        description="입력 페이로드 종류 디스크리미네이터.",
    )
    payload: str | bytes = Field(
        ...,
        description=(
            "입력 페이로드. ``kind == text`` 일 때 ``str``, ``kind == image / pdf`` 일 "
            "때 ``bytes`` (raw). 현 v0.1 은 단순 union — 과한 추상화 회피."
        ),
    )
    media_type: str | None = Field(
        default=None,
        description=(
            "이미지 입력의 MIME type (예: ``image/png``, ``image/jpeg``, ``image/webp``). "
            "``kind == image`` 일 때 NOT NULL (model_validator 가 강제). 그 외에서는 "
            "None."
        ),
    )
    force_vision: bool = Field(
        default=False,
        description=(
            "PDF 입력에서 PyMuPDF 텍스트 추출 우회 + 즉시 Vision 경로 (PM-3, ADR-0003 "
            "§D-3.3). ``kind == pdf`` 에서만 의미 있음. ``text / image`` 에서는 무시 — "
            "호출자 편의를 위해 default False 만 보장하고 validator 가 거절하지는 않는다."
        ),
    )

    @model_validator(mode="after")
    def _validate_payload_kind_consistency(self) -> ExtractionRequest:
        """``kind`` 와 ``payload`` / ``media_type`` 정합성 강제.

        - ``kind == "text"`` → ``payload`` 는 ``str``. ``media_type`` 은 None 이어야
          의미가 명확 (str payload 에 media_type 무의미).
        - ``kind == "image"`` → ``payload`` 는 ``bytes``, ``media_type`` 은 NOT NULL.
        - ``kind == "pdf"`` → ``payload`` 는 ``bytes``. ``media_type`` 은 None 권장
          (PDF 는 항상 ``application/pdf`` 로 고정 가정).
        """
        if self.kind == "text":
            if not isinstance(self.payload, str):
                raise ValueError("kind == 'text' 일 때 payload 는 str 이어야 한다.")
            if self.media_type is not None:
                raise ValueError(
                    "kind == 'text' 일 때 media_type 은 None 이어야 한다 (text payload 에 무의미)."
                )
        elif self.kind == "image":
            if not isinstance(self.payload, bytes):
                raise ValueError("kind == 'image' 일 때 payload 는 bytes 이어야 한다.")
            if self.media_type is None:
                raise ValueError(
                    "kind == 'image' 일 때 media_type 은 NOT NULL 이어야 한다 "
                    "(예: 'image/png', 'image/jpeg', 'image/webp')."
                )
        elif self.kind == "pdf":
            if not isinstance(self.payload, bytes):
                raise ValueError("kind == 'pdf' 일 때 payload 는 bytes 이어야 한다.")
        return self


# ─── ExtractionMetaRef ─────────────────────────────────────────────────────
class ExtractionMetaRef(BaseModel):
    """추출 출처 메타 (ADR-0003 §G-1 통합).

    "어떤 LLM 호출에서 만들어진 결과인가" 를 식별. 디버깅 / 회귀 분석 / 동일 입력
    중복 추출 방지 / 비용 추적의 1차 키.

    ``request_id`` 는 ``packages/llm/`` 의 ``StructuredLLMResult`` 또는
    ``llm_usage_logs.request_id`` (PM-4) 와 join 키.

    PM-4 (확정) 의 ``llm_usage_logs`` 테이블과 연결:
      ``ExtractionMetaRef.request_id == llm_usage_logs.request_id``.
      재시도 체인은 ``llm_usage_logs.parent_request_id`` 로 추적 — 본 모델은 1회
      성공 호출 1건만 가리킨다.
    """

    model_config = ConfigDict(extra="forbid")

    request_id: UUID = Field(
        ...,
        description=(
            "LLM 호출 1건의 식별자 (NOT NULL). ``llm_usage_logs.request_id`` 와 join. "
            "재시도 체인 추적은 ``llm_usage_logs.parent_request_id`` 로."
        ),
    )
    model: str = Field(
        ...,
        max_length=128,
        description=(
            "실제 사용된 모델 ID (예: 'claude-sonnet-4-20250514'). LLM 래퍼가 응답 "
            "메타에서 받은 값 그대로."
        ),
    )
    prompt_template_id: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "``docs/prompts/`` 의 템플릿 식별자 (예: 'extract-text-v0'). 직접 텍스트 "
            "주입 (템플릿 미사용) 호출의 경우 None."
        ),
    )
    extracted_at: datetime = Field(
        ...,
        description="추출 완료 시각 (UTC, **timezone-aware 강제**).",
    )

    @field_validator("extracted_at")
    @classmethod
    def _validate_timezone_aware(cls, value: datetime) -> datetime:
        """``extracted_at`` 은 timezone-aware 강제 (CLAUDE.md naive datetime 금지).

        common.utc_now() 는 timezone-aware UTC 를 반환한다. naive datetime (예:
        ``datetime.utcnow()``) 으로 채워지면 즉시 거절.
        """
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError(
                "extracted_at 은 timezone-aware datetime 이어야 한다 "
                "(naive datetime 거절 — utc_now() 사용)."
            )
        return value


# ─── ExtractionResult ──────────────────────────────────────────────────────
class ExtractionResult(BaseModel):
    """Extractor 1회 호출의 출력 컨테이너.

    PM-1 (다중 지문 / 다중 파일) 에서 호출자가 ``list[ExtractionResult]`` 로 받는
    단위 — *1 ExtractionResult = 1 Passage* (그 Passage 에 딸린 Question / Translation
    / Vocabulary 묶음). 한 PDF 에서 N개 지문이 추출되면 N개의 ``ExtractionResult``.

    PM-5 (추출 스코프 옵션 B):
      자료에 보이는 것만 추출, 생성 안 함.
        - ``passage``: 항상 1개 (NOT NULL).
        - ``questions``: 자료에 문제가 있으면 채움. 없으면 빈 list.
        - ``translation``: 자료에 한글 해석이 있으면 채움. 없으면 None.
        - ``vocabulary``: 자료에 어휘 박스가 있으면 채움. 없으면 빈 list.

    PM-6 (실유저 default — 가드레일):
      실유저 입력의 default 는 "영어만" / "문제만". ``translation`` 은 거의 항상
      None, ``vocabulary`` 는 거의 항상 빈 list. **이게 정상**. Phase 2 의 LLM
      생성 단계가 이후 채운다. 후속 코드는 이 가정을 전제.

    sentinel UUID (ADR-0003 §D-3.6):
      ``passage.tenant_id`` / ``workspace_id`` 가 ``uuid.UUID(int=0)`` 일 수 있음
      (extractor 단계). 본 컨테이너는 검증하지 않음 — repository write 시점에서
      sentinel 차단.
    """

    model_config = ConfigDict(extra="forbid")

    passage: Passage = Field(
        ...,
        description=(
            "추출된 정규화 영어 지문 1개 (NOT NULL). PM-1 에 따라 다중 지문 자료는 "
            "호출자가 ``list[ExtractionResult]`` 형태로 평탄화."
        ),
    )
    questions: list[Question] = Field(
        default_factory=list,
        description=(
            "이 Passage 에 딸린 문제. 자료에 문제가 없으면 빈 list (PM-6 — 실유저 "
            "입력의 default 는 '문제만' 이거나 '지문만' 양쪽 모두 흔함)."
        ),
    )
    translation: Translation | None = Field(
        default=None,
        description=(
            "자료에 명시된 한글 해석 (PM-5 — 보이는 것만 추출). 자료에 없으면 None — "
            "**이게 default 다 (PM-6)**. Phase 2 의 LLM 생성 단계가 이후 채움. "
            "'translation 은 항상 채워져야 한다' 같은 잘못된 가정 금지."
        ),
    )
    vocabulary: list[Vocabulary] = Field(
        default_factory=list,
        description=(
            "자료에 명시된 어휘 박스 (PM-5 — 보이는 것만 추출). 자료에 없으면 빈 list — "
            "**이게 default 다 (PM-6)**. None 은 거절 (default_factory=list 강제). "
            "Phase 2 의 LLM 생성 단계가 이후 채움."
        ),
    )
    extraction_meta: ExtractionMetaRef = Field(
        ...,
        description=(
            "어떤 LLM 호출에서 만들어진 결과인가 메타 (ADR-0003 §G-1 통합). NOT NULL — "
            "추출 호출은 항상 LLM 한 번 이상 거치므로 meta 가 비어있을 수 없음."
        ),
    )
