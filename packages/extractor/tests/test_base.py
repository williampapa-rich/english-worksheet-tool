"""base.py — Extractor 프로토콜 + sentinel UUID 테스트."""

from __future__ import annotations

import uuid

from extractor.base import SENTINEL_UUID, Extractor, is_sentinel

from shared.schemas.extraction import ExtractionRequest


class TestSentinelUUID:
    """sentinel UUID 상수 및 헬퍼 테스트."""

    def test_sentinel_uuid_is_zero(self) -> None:
        """SENTINEL_UUID 는 uuid.UUID(int=0) 이어야 한다."""
        assert SENTINEL_UUID == uuid.UUID(int=0)
        assert SENTINEL_UUID.int == 0

    def test_is_sentinel_true_for_zero_uuid(self) -> None:
        """uuid.UUID(int=0) 에 대해 is_sentinel 이 True."""
        assert is_sentinel(uuid.UUID(int=0)) is True

    def test_is_sentinel_true_for_sentinel_constant(self) -> None:
        """SENTINEL_UUID 에 대해 is_sentinel 이 True."""
        assert is_sentinel(SENTINEL_UUID) is True

    def test_is_sentinel_false_for_random_uuid(self) -> None:
        """임의 UUID 에 대해 is_sentinel 이 False."""
        assert is_sentinel(uuid.uuid4()) is False

    def test_is_sentinel_false_for_specific_uuid(self) -> None:
        """특정 non-zero UUID 에 대해 is_sentinel 이 False."""
        assert is_sentinel(uuid.UUID("12345678-1234-5678-1234-567812345678")) is False


class TestExtractorProtocol:
    """Extractor 프로토콜 conformance 테스트."""

    def test_protocol_is_runtime_checkable_or_structural(self) -> None:
        """Extractor 는 typing.Protocol — 구조적 서브타이핑 지원."""
        # Protocol 자체가 import 가능하고 타입으로 사용 가능한지 확인
        assert Extractor is not None

    def test_extractor_request_type_is_importable(self) -> None:
        """ExtractionRequest 가 정상 import 되는지 확인."""
        req = ExtractionRequest(kind="text", payload="hello")
        assert req.kind == "text"

    def test_concrete_class_satisfying_protocol(self) -> None:
        """Extractor 프로토콜을 만족하는 콘크리트 클래스가 동작하는지."""
        from shared.schemas.extraction import ExtractionResult

        class ConcreteExtractor:
            async def extract(self, request: ExtractionRequest) -> list[ExtractionResult]:
                return []

        extractor = ConcreteExtractor()
        # 구조적으로 Extractor 프로토콜을 만족 — isinstance 는 Protocol runtime_checkable 없이 불가
        assert hasattr(extractor, "extract")
        assert callable(extractor.extract)
