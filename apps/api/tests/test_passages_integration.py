"""POST /passages/extract + GET /passages/{id} 통합 테스트.

@pytest.mark.integration — 실행 시 필요:
  - 실행 중인 PostgreSQL (Docker compose)
  - ANTHROPIC_API_KEY 환경변수

실행 방법:
  pytest -m integration apps/api/tests/test_passages_integration.py

이 테스트는 CI 에서는 기본 skip (DB/API key 없는 환경).
실제 LLM 비용이 발생하므로 단순한 텍스트 입력으로 최소 토큰 사용.

테스트 패턴:
  - end-to-end: POST text → DB 저장 → GET /{id} 조회 → 동일 데이터.
  - 멀티테넌트 격리: 서로 다른 tenant_id 환경에서 cross-tenant 조회 불가.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from worksheet_api.main import app
from worksheet_api.repositories.passage import PassageRepository
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context
from worksheet_api.repositories.translation import TranslationRepository
from worksheet_api.repositories.vocabulary import VocabularyRepository

from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade
from shared.schemas.translation import Translation, TranslationCreatedBy
from shared.schemas.vocabulary import Vocabulary, VocabularySelectedBy

# 통합 테스트 marker
pytestmark = pytest.mark.integration

# conftest.py 에서 시드된 표준 테넌트 UUID
from apps.api.tests.conftest import (  # noqa: E402
    TEST_TENANT_A,
    TEST_TENANT_B,
    TEST_WORKSPACE_A,
    TEST_WORKSPACE_B,
)


@pytest.fixture
def _skip_if_no_api_key() -> None:
    """ANTHROPIC_API_KEY 없으면 skip."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY 없음 — 통합 테스트 skip")


@pytest.fixture
async def integration_client(pg_session: Any):  # type: ignore[return]
    """실제 DB session + 실제 LLM client 를 사용하는 통합 테스트 클라이언트.

    tenant_ctx 는 TEST_TENANT_A / TEST_WORKSPACE_A 로 고정 (conftest 시드 데이터와 일치).
    get_db 는 pg_session 으로 오버라이드 — rollback 기반 격리.
    """
    from worksheet_api.db import get_db

    async def _get_db():  # type: ignore[return]
        yield pg_session

    async def _get_tenant() -> TenantContext:
        return TenantContext(tenant_id=TEST_TENANT_A, workspace_id=TEST_WORKSPACE_A)

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_tenant_context] = _get_tenant

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_e2e_text_extract_then_get(
    integration_client: AsyncClient,
    _skip_if_no_api_key: None,
) -> None:
    """end-to-end: POST /passages/extract (text) → DB 저장 → GET /{id} 조회.

    추출 결과가 DB 에 올바르게 저장되고, GET 으로 동일 데이터를 반환하는지 검증.
    실제 LLM 을 호출하므로 최소 토큰 텍스트 사용.
    """
    # 1. 추출 요청 — 짧은 텍스트로 비용 최소화
    extract_resp = await integration_client.post(
        "/passages/extract",
        json={
            "kind": "text",
            "payload": "The sun rises in the east. This is a simple English sentence.",
        },
    )
    assert extract_resp.status_code == 200, f"extract failed: {extract_resp.text}"

    body = extract_resp.json()
    assert len(body["results"]) >= 1

    passage_id = body["results"][0]["passage"]["id"]

    # 2. GET 으로 조회 — 동일 데이터 반환 확인
    get_resp = await integration_client.get(f"/passages/{passage_id}")
    assert get_resp.status_code == 200, f"get failed: {get_resp.text}"

    get_body = get_resp.json()
    assert get_body["passage"]["id"] == passage_id
    # tenant_id 는 TEST_TENANT_A
    assert get_body["passage"]["tenant_id"] == str(TEST_TENANT_A)


@pytest.mark.asyncio
async def test_e2e_multitenant_isolation(pg_session: Any) -> None:
    """멀티테넌트 격리 — TENANT_A 가 저장한 Passage 를 TENANT_B 는 조회 불가.

    실제 DB 에서 tenant_id 필터가 올바르게 동작하는지 검증.
    LLM 호출 없이 PassageRepository 를 직접 사용.
    """
    ctx_a = TenantContext(tenant_id=TEST_TENANT_A, workspace_id=TEST_WORKSPACE_A)
    ctx_b = TenantContext(tenant_id=TEST_TENANT_B, workspace_id=TEST_WORKSPACE_B)

    repo_a = PassageRepository(pg_session, ctx_a)
    repo_b = PassageRepository(pg_session, ctx_b)

    # TENANT_A 로 Passage 저장
    passage_a = Passage(
        tenant_id=TEST_TENANT_A,
        workspace_id=TEST_WORKSPACE_A,
        body_text="Tenant A exclusive passage.",
        word_count=4,
        source=SourceMeta(provider=SourceProvider.USER_INPUT),
        target_grade=TargetGrade.HIGH_3,
    )
    saved = await repo_a.create(passage_a)
    await pg_session.flush()

    # TENANT_B 로 같은 passage_id 조회 → None (다른 tenant)
    result = await repo_b.get(saved.id)
    assert result is None, "멀티테넌트 격리 실패: TENANT_B 가 TENANT_A 의 Passage 를 조회했다"

    # TENANT_A 로 조회 → 성공
    result_a = await repo_a.get(saved.id)
    assert result_a is not None
    assert result_a.id == saved.id


@pytest.mark.asyncio
async def test_e2e_translation_vocabulary_roundtrip(pg_session: Any) -> None:
    """B1 — Translation / Vocabulary 영속화 라운드트립.

    PassageRepository.create() → TranslationRepository.create() →
    VocabularyRepository.create() x2 → 같은 tenant 로 read 시 정확히 복원.
    LLM 호출 없이 repository 만 직접 호출.
    """
    ctx_a = TenantContext(tenant_id=TEST_TENANT_A, workspace_id=TEST_WORKSPACE_A)
    p_repo = PassageRepository(pg_session, ctx_a)
    t_repo = TranslationRepository(pg_session, ctx_a)
    v_repo = VocabularyRepository(pg_session, ctx_a)

    passage = await p_repo.create(
        Passage(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            body_text="The economy is growing steadily.",
            word_count=5,
            source=SourceMeta(provider=SourceProvider.USER_INPUT),
            target_grade=TargetGrade.HIGH_3,
        )
    )

    saved_translation = await t_repo.create(
        Translation(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            passage_id=passage.id,
            text="경제는 꾸준히 성장하고 있다.",
            created_by=TranslationCreatedBy.LLM,
        )
    )
    assert saved_translation.passage_id == passage.id

    saved_v1 = await v_repo.create(
        Vocabulary(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            passage_id=passage.id,
            word="economy",
            headword_normalized="economy",
            meaning_ko="경제",
            selected_by=VocabularySelectedBy.LLM,
        )
    )
    saved_v2 = await v_repo.create(
        Vocabulary(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            passage_id=passage.id,
            word="growing",
            headword_normalized="growing",
            meaning_ko="성장하는",
            selected_by=VocabularySelectedBy.LLM,
        )
    )
    await pg_session.flush()

    # read 라운드트립
    fetched_t = await t_repo.get_by_passage(passage.id)
    assert fetched_t is not None
    assert fetched_t.id == saved_translation.id
    assert fetched_t.text == "경제는 꾸준히 성장하고 있다."

    fetched_v = await v_repo.list_by_passage(passage.id)
    assert {v.id for v in fetched_v} == {saved_v1.id, saved_v2.id}
    assert {v.word for v in fetched_v} == {"economy", "growing"}

    # cross-tenant 격리: TENANT_B 로 조회하면 모두 차단
    ctx_b = TenantContext(tenant_id=TEST_TENANT_B, workspace_id=TEST_WORKSPACE_B)
    t_repo_b = TranslationRepository(pg_session, ctx_b)
    v_repo_b = VocabularyRepository(pg_session, ctx_b)
    assert await t_repo_b.get_by_passage(passage.id) is None
    assert await v_repo_b.list_by_passage(passage.id) == []


@pytest.mark.asyncio
async def test_e2e_extract_persists_translation_and_vocab_when_present(
    integration_client: AsyncClient,
    _skip_if_no_api_key: None,
) -> None:
    """B1 — extract 후 GET /{id} 가 translation / vocabulary 를 반환 (옵션 B).

    LLM 이 자료에서 translation / vocabulary 를 채워주는 경우는 운영에서 드물지만 (PM-6),
    채웠을 때 DB 영속화 + GET 라운드트립이 동작하는지 검증. LLM 결과가 비어있어도
    테스트는 통과 — 통합 테스트는 "비어있어도 정상" 가드를 같이 검증한다.
    """
    extract_resp = await integration_client.post(
        "/passages/extract",
        json={
            "kind": "text",
            "payload": "The sun rises in the east. This is a simple English sentence.",
        },
    )
    assert extract_resp.status_code == 200, f"extract failed: {extract_resp.text}"

    body = extract_resp.json()
    passage_id = body["results"][0]["passage"]["id"]
    extract_translation = body["results"][0]["translation"]
    extract_vocabulary = body["results"][0]["vocabulary"]

    # 응답 schema 정합성
    assert extract_translation is None or "text" in extract_translation
    assert isinstance(extract_vocabulary, list)

    # GET 라운드트립 — extract 응답과 동일한 translation / vocabulary
    get_resp = await integration_client.get(f"/passages/{passage_id}")
    assert get_resp.status_code == 200
    get_body = get_resp.json()
    if extract_translation is None:
        assert get_body["translation"] is None
    else:
        assert get_body["translation"] is not None
        assert get_body["translation"]["text"] == extract_translation["text"]
    assert len(get_body["vocabulary"]) == len(extract_vocabulary)


# ─── B3 — 보강 라우트 DB 라운드트립 (LLM mock + 실 DB) ────────────────────────


@pytest.mark.asyncio
async def test_e2e_translation_repo_update_text_roundtrip(pg_session: Any) -> None:
    """B3 — TranslationRepository.update_text 의 in-place UPDATE 라운드트립.

    LLM 호출 없이 repository 만 직접 호출. ``update_text`` 가 same-id row 를 갱신
    (passage_id UNIQUE 그대로) + ``created_by`` 변경 + ``updated_at`` 갱신.
    """
    ctx_a = TenantContext(tenant_id=TEST_TENANT_A, workspace_id=TEST_WORKSPACE_A)
    p_repo = PassageRepository(pg_session, ctx_a)
    t_repo = TranslationRepository(pg_session, ctx_a)

    passage = await p_repo.create(
        Passage(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            body_text="The economy is growing.",
            word_count=4,
            source=SourceMeta(provider=SourceProvider.USER_INPUT),
            target_grade=TargetGrade.HIGH_3,
        )
    )
    initial = await t_repo.create(
        Translation(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            passage_id=passage.id,
            text="초기 LLM 해석",
            created_by=TranslationCreatedBy.LLM,
        )
    )
    await pg_session.flush()

    updated = await t_repo.update_text(
        passage.id,
        text="갱신된 사용자 해석",
        created_by=TranslationCreatedBy.USER,
    )
    assert updated is not None
    assert updated.id == initial.id  # same row
    assert updated.text == "갱신된 사용자 해석"
    assert updated.created_by == TranslationCreatedBy.USER

    # 다시 조회해도 동일 (1:1 UNIQUE 그대로)
    fetched = await t_repo.get_by_passage(passage.id)
    assert fetched is not None
    assert fetched.id == initial.id


@pytest.mark.asyncio
async def test_e2e_vocabulary_delete_llm_preserves_user(pg_session: Any) -> None:
    """B3 — VocabularyRepository.delete_llm_for_passage 가 USER 항목 보존 (D4).

    LLM 항목 + USER 항목 + LLM-but-user_edited 항목 mix → delete 후 USER /
    user_edited 만 남음.
    """
    ctx_a = TenantContext(tenant_id=TEST_TENANT_A, workspace_id=TEST_WORKSPACE_A)
    p_repo = PassageRepository(pg_session, ctx_a)
    v_repo = VocabularyRepository(pg_session, ctx_a)

    passage = await p_repo.create(
        Passage(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            body_text="Test.",
            word_count=1,
            source=SourceMeta(provider=SourceProvider.USER_INPUT),
            target_grade=TargetGrade.HIGH_3,
        )
    )

    # LLM 항목 — 삭제 대상
    await v_repo.create(
        Vocabulary(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            passage_id=passage.id,
            word="economy",
            headword_normalized="economy",
            meaning_ko="경제",
            selected_by=VocabularySelectedBy.LLM,
            user_edited=False,
        )
    )
    # USER 항목 — 보존
    await v_repo.create(
        Vocabulary(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            passage_id=passage.id,
            word="growing",
            headword_normalized="growing",
            meaning_ko="성장하는 (사용자 추가)",
            selected_by=VocabularySelectedBy.USER,
            user_edited=False,
        )
    )
    # LLM 산출이지만 사용자가 수정한 항목 — 보존 (user_edited=True)
    await v_repo.create(
        Vocabulary(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            passage_id=passage.id,
            word="steadily",
            headword_normalized="steadily",
            meaning_ko="꾸준히 (사용자 수정)",
            selected_by=VocabularySelectedBy.LLM,
            user_edited=True,
        )
    )
    await pg_session.flush()

    deleted_count = await v_repo.delete_llm_for_passage(passage.id)
    assert deleted_count == 1  # economy 만 삭제

    remaining = await v_repo.list_by_passage(passage.id)
    headwords = {v.headword_normalized for v in remaining}
    assert headwords == {"growing", "steadily"}  # USER + user_edited 보존


@pytest.mark.asyncio
async def test_e2e_vocabulary_list_user_edited_headwords(pg_session: Any) -> None:
    """B3 — VocabularyRepository.list_user_edited_headwords 가 USER / user_edited 만 반환."""
    ctx_a = TenantContext(tenant_id=TEST_TENANT_A, workspace_id=TEST_WORKSPACE_A)
    p_repo = PassageRepository(pg_session, ctx_a)
    v_repo = VocabularyRepository(pg_session, ctx_a)

    passage = await p_repo.create(
        Passage(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            body_text="Test.",
            word_count=1,
            source=SourceMeta(provider=SourceProvider.USER_INPUT),
            target_grade=TargetGrade.HIGH_3,
        )
    )

    await v_repo.create(
        Vocabulary(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            passage_id=passage.id,
            word="economy",
            headword_normalized="economy",
            meaning_ko="경제",
            selected_by=VocabularySelectedBy.LLM,
            user_edited=False,
        )
    )
    await v_repo.create(
        Vocabulary(
            tenant_id=TEST_TENANT_A,
            workspace_id=TEST_WORKSPACE_A,
            passage_id=passage.id,
            word="growing",
            headword_normalized="growing",
            meaning_ko="성장하는",
            selected_by=VocabularySelectedBy.USER,
            user_edited=False,
        )
    )
    await pg_session.flush()

    headwords = await v_repo.list_user_edited_headwords(passage.id)
    assert headwords == {"growing"}
