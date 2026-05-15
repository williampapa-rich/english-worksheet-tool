"""Stage E1-c: VocabularyMaster 통합 단위 테스트.

POST /passages/{id}/vocabulary/manual 및 POST /passages/{id}/vocabulary (LLM 보강)
라우트가 VocabularyMaster 와 올바르게 연결되는지 검증한다.

커버 케이스:
  1. manual add — 새 단어 → 신규 master 생성 + Vocabulary.master_id 채워짐
  2. manual add — 기존 단어 → master reuse + usage_count += 1
  3. manual add — 대소문자 다른 입력 (Endeavor vs endeavor) → 같은 headword_normalized 매칭
  4. manual add — 다른 tenant 의 같은 단어 → 별 master (UNIQUE per tenant)
  5. LLM 보강 — 신규 master 들 일괄 생성 + Vocabulary 들 master_id 채워짐
  6. LLM 보강 — 기존 master reuse + usage_count 증가
  7. meaning_ko override — master default 와 다른 meaning_ko 입력 시 Vocabulary 에 저장,
     master default 는 변경 없음 (ADR-0016 D2-c)
  8. DELETE vocabulary → master.usage_count -= 1 (Stage E1-d 연동)

mock session + mock repository 패턴 — 실제 DB 없이 실행.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from worksheet_api.db import get_db
from worksheet_api.llm_setup import get_llm_client
from worksheet_api.main import app
from worksheet_api.repositories.tenant_context import TenantContext, get_tenant_context

from shared.schemas.passage import Passage, SourceMeta, SourceProvider, TargetGrade
from shared.schemas.vocabulary import Vocabulary, VocabularySelectedBy
from shared.schemas.vocabulary_master import VocabularyMaster, VocabularyMasterCreatedBy

# ─── 테스트용 고정 UUID ──────────────────────────────────────────────────────

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_A = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TENANT_B = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
WORKSPACE_B = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
PASSAGE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
MASTER_ID_1 = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
MASTER_ID_2 = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
VOCAB_ID_1 = uuid.UUID("12121212-1212-1212-1212-121212121212")


# ─── 헬퍼 팩토리 ────────────────────────────────────────────────────────────


def _make_passage(
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
) -> Passage:
    return Passage(
        id=PASSAGE_ID,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        body_text="She made an endeavor to succeed in her career.",
        word_count=9,
        source=SourceMeta(provider=SourceProvider.EVALUATOR),
        target_grade=TargetGrade.HIGH_3,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )


def _make_master(
    master_id: uuid.UUID = MASTER_ID_1,
    headword_normalized: str = "endeavor",
    word_canonical: str = "endeavor",
    default_meaning_ko: str = "노력",
    usage_count: int = 0,
    created_by: VocabularyMasterCreatedBy = VocabularyMasterCreatedBy.USER,
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
) -> VocabularyMaster:
    return VocabularyMaster(
        id=master_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        headword_normalized=headword_normalized,
        word_canonical=word_canonical,
        default_meaning_ko=default_meaning_ko,
        usage_count=usage_count,
        created_by=created_by,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )


def _make_saved_vocabulary(
    vocab_id: uuid.UUID = VOCAB_ID_1,
    word: str = "endeavor",
    meaning_ko: str = "노력",
    master_id: uuid.UUID | None = MASTER_ID_1,
    selected_by: VocabularySelectedBy = VocabularySelectedBy.USER,
    passage_id: uuid.UUID = PASSAGE_ID,
    tenant_id: uuid.UUID = TENANT_A,
    workspace_id: uuid.UUID = WORKSPACE_A,
) -> Vocabulary:
    return Vocabulary(
        id=vocab_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        passage_id=passage_id,
        word=word,
        headword_normalized=word.lower().strip(),
        meaning_ko=meaning_ko,
        master_id=master_id,
        selected_by=selected_by,
        user_edited=False,
        created_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
    )


# ─── 픽스처 ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = begin_cm
    return session


@pytest.fixture
def mock_llm_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def tenant_ctx_a() -> TenantContext:
    return TenantContext(tenant_id=TENANT_A, workspace_id=WORKSPACE_A)


@pytest.fixture
def tenant_ctx_b() -> TenantContext:
    return TenantContext(tenant_id=TENANT_B, workspace_id=WORKSPACE_B)


@pytest.fixture
def override_deps_a(
    mock_session: AsyncMock,
    mock_llm_client: MagicMock,
    tenant_ctx_a: TenantContext,
) -> dict[Any, Any]:
    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def _get_tenant() -> TenantContext:
        return tenant_ctx_a

    def _get_llm() -> MagicMock:
        return mock_llm_client

    return {get_db: _get_db, get_tenant_context: _get_tenant, get_llm_client: _get_llm}


@pytest.fixture
def override_deps_b(
    mock_session: AsyncMock,
    mock_llm_client: MagicMock,
    tenant_ctx_b: TenantContext,
) -> dict[Any, Any]:
    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def _get_tenant() -> TenantContext:
        return tenant_ctx_b

    def _get_llm() -> MagicMock:
        return mock_llm_client

    return {get_db: _get_db, get_tenant_context: _get_tenant, get_llm_client: _get_llm}


@pytest.fixture
async def client_a(override_deps_a: dict[Any, Any]) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides.update(override_deps_a)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def client_b(override_deps_b: dict[Any, Any]) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides.update(override_deps_b)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ─── 테스트: manual add ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_add_new_word_creates_master(client_a: AsyncClient) -> None:
    """새 단어 → 신규 master 생성 + Vocabulary.master_id 채워짐.

    master_repo.find_by_headword 가 None 을 반환하면
    master_repo.create 가 호출되고 생성된 master.id 가
    Vocabulary 에 채워져야 한다.
    """
    passage = _make_passage()
    new_master = _make_master(master_id=MASTER_ID_1)
    saved_vocab = _make_saved_vocabulary(master_id=MASTER_ID_1)

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.VocabularyMasterRepository") as mock_mrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=passage)
        mock_mrepo.return_value.find_by_headword = AsyncMock(return_value=None)
        mock_mrepo.return_value.create = AsyncMock(return_value=new_master)
        mock_mrepo.return_value.increment_usage_count = AsyncMock()
        mock_vrepo.return_value.create = AsyncMock(return_value=saved_vocab)

        resp = await client_a.post(
            f"/passages/{PASSAGE_ID}/vocabulary/manual",
            json={"word": "endeavor", "meaning_ko": "노력"},
        )

    assert resp.status_code == 201
    body = resp.json()
    # master_id 가 응답에 포함되어야 함
    assert body["master_id"] == str(MASTER_ID_1)

    # find_by_headword("endeavor") 호출 확인
    mock_mrepo.return_value.find_by_headword.assert_awaited_once_with("endeavor")
    # 신규 생성이므로 create 호출됨, increment 는 미호출
    mock_mrepo.return_value.create.assert_awaited_once()
    mock_mrepo.return_value.increment_usage_count.assert_not_awaited()

    # 생성된 master 의 created_by = USER
    create_call_arg: VocabularyMaster = mock_mrepo.return_value.create.call_args[0][0]
    assert create_call_arg.created_by == VocabularyMasterCreatedBy.USER
    assert create_call_arg.headword_normalized == "endeavor"
    assert create_call_arg.usage_count == 1


@pytest.mark.asyncio
async def test_manual_add_existing_word_reuses_master(client_a: AsyncClient) -> None:
    """기존 단어 → master reuse + usage_count += 1.

    find_by_headword 가 기존 master 를 반환하면
    create 는 호출되지 않고 increment_usage_count 가 호출되어야 한다.
    """
    passage = _make_passage()
    existing_master = _make_master(master_id=MASTER_ID_1, usage_count=3)
    saved_vocab = _make_saved_vocabulary(master_id=MASTER_ID_1)

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.VocabularyMasterRepository") as mock_mrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=passage)
        mock_mrepo.return_value.find_by_headword = AsyncMock(return_value=existing_master)
        mock_mrepo.return_value.create = AsyncMock()
        mock_mrepo.return_value.increment_usage_count = AsyncMock()
        mock_vrepo.return_value.create = AsyncMock(return_value=saved_vocab)

        resp = await client_a.post(
            f"/passages/{PASSAGE_ID}/vocabulary/manual",
            json={"word": "endeavor", "meaning_ko": "노력"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["master_id"] == str(MASTER_ID_1)

    # reuse → create 미호출 + increment 호출
    mock_mrepo.return_value.create.assert_not_awaited()
    mock_mrepo.return_value.increment_usage_count.assert_awaited_once_with(MASTER_ID_1)


@pytest.mark.asyncio
async def test_manual_add_case_insensitive_headword(client_a: AsyncClient) -> None:
    """대소문자 다른 입력 (Endeavor) → headword_normalized="endeavor" 로 조회.

    word="Endeavor" 로 입력해도 headword_normalized 는 "endeavor" 로 계산되어
    find_by_headword("endeavor") 를 호출해야 한다.
    """
    passage = _make_passage()
    existing_master = _make_master(
        master_id=MASTER_ID_1,
        headword_normalized="endeavor",
        word_canonical="Endeavor",
    )
    saved_vocab = _make_saved_vocabulary(word="Endeavor", master_id=MASTER_ID_1)

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.VocabularyMasterRepository") as mock_mrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=passage)
        mock_mrepo.return_value.find_by_headword = AsyncMock(return_value=existing_master)
        mock_mrepo.return_value.increment_usage_count = AsyncMock()
        mock_vrepo.return_value.create = AsyncMock(return_value=saved_vocab)

        resp = await client_a.post(
            f"/passages/{PASSAGE_ID}/vocabulary/manual",
            # 대문자 E
            json={"word": "Endeavor", "meaning_ko": "노력"},
        )

    assert resp.status_code == 201
    # "endeavor" (소문자) 로 조회되었는지 확인
    mock_mrepo.return_value.find_by_headword.assert_awaited_once_with("endeavor")
    # 기존 master 를 찾았으므로 reuse
    mock_mrepo.return_value.increment_usage_count.assert_awaited_once_with(MASTER_ID_1)


@pytest.mark.asyncio
async def test_manual_add_different_tenant_separate_master(
    client_b: AsyncClient,
) -> None:
    """다른 tenant 는 같은 단어라도 별 master (UNIQUE per tenant).

    tenant B 로 요청 시 find_by_headword 가 None 을 반환하면 (tenant B 에 master 없음)
    신규 master 를 생성해야 한다.
    """
    passage_b = _make_passage(tenant_id=TENANT_B, workspace_id=WORKSPACE_B)
    new_master_b = _make_master(
        master_id=MASTER_ID_2,
        tenant_id=TENANT_B,
        workspace_id=WORKSPACE_B,
        created_by=VocabularyMasterCreatedBy.USER,
    )
    saved_vocab_b = _make_saved_vocabulary(
        master_id=MASTER_ID_2,
        tenant_id=TENANT_B,
        workspace_id=WORKSPACE_B,
    )

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.VocabularyMasterRepository") as mock_mrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=passage_b)
        # tenant B 에는 master 없음
        mock_mrepo.return_value.find_by_headword = AsyncMock(return_value=None)
        mock_mrepo.return_value.create = AsyncMock(return_value=new_master_b)
        mock_mrepo.return_value.increment_usage_count = AsyncMock()
        mock_vrepo.return_value.create = AsyncMock(return_value=saved_vocab_b)

        resp = await client_b.post(
            f"/passages/{PASSAGE_ID}/vocabulary/manual",
            json={"word": "endeavor", "meaning_ko": "노력"},
        )

    assert resp.status_code == 201
    body = resp.json()
    # tenant B 의 master_id 가 채워짐
    assert body["master_id"] == str(MASTER_ID_2)
    # 신규 생성됨 (tenant B 에 없으니)
    mock_mrepo.return_value.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_add_meaning_ko_override_does_not_change_master_default(
    client_a: AsyncClient,
) -> None:
    """ADR-0016 D2-c: 사용자가 다른 meaning_ko 입력 시 master.default_meaning_ko 변경 없음.

    기존 master 의 default_meaning_ko = "노력" 이고
    사용자가 "분투" 를 입력해도 master 의 default 는 변경되지 않고
    Vocabulary 행의 meaning_ko 에만 "분투" 가 저장되어야 한다.
    """
    passage = _make_passage()
    existing_master = _make_master(
        master_id=MASTER_ID_1,
        default_meaning_ko="노력",  # master 기본값
        usage_count=5,
    )
    # 사용자 입력 "분투" 가 Vocabulary 에 저장된 시뮬레이션
    saved_vocab = _make_saved_vocabulary(
        master_id=MASTER_ID_1,
        meaning_ko="분투",  # passage-specific override
    )

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.VocabularyMasterRepository") as mock_mrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=passage)
        mock_mrepo.return_value.find_by_headword = AsyncMock(return_value=existing_master)
        mock_mrepo.return_value.increment_usage_count = AsyncMock()
        mock_mrepo.return_value.create = AsyncMock()
        mock_vrepo.return_value.create = AsyncMock(return_value=saved_vocab)

        resp = await client_a.post(
            f"/passages/{PASSAGE_ID}/vocabulary/manual",
            # 다른 meaning_ko
            json={"word": "endeavor", "meaning_ko": "분투"},
        )

    assert resp.status_code == 201
    body = resp.json()
    # Vocabulary 에는 "분투" 가 저장됨
    assert body["meaning_ko"] == "분투"

    # master.create 는 호출되지 않음 (reuse)
    mock_mrepo.return_value.create.assert_not_awaited()

    # Vocabulary.create 에 전달된 인자에 master_id 가 있고
    # meaning_ko 는 "분투" (override)
    vocab_create_arg: Vocabulary = mock_vrepo.return_value.create.call_args[0][0]
    assert vocab_create_arg.meaning_ko == "분투"
    assert vocab_create_arg.master_id == MASTER_ID_1


# ─── 테스트: LLM 보강 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_augment_creates_new_masters(client_a: AsyncClient) -> None:
    """LLM 보강 — 신규 master 들 일괄 생성 + Vocabulary 들 master_id 채워짐.

    LLM 이 2개 어휘를 반환하고 둘 다 master 가 없는 경우
    master create 가 2회 호출되어야 한다.
    """
    from shared.schemas.vocabulary import VocabularySelectedBy

    passage = _make_passage()
    llm_vocab_1 = _make_saved_vocabulary(
        vocab_id=uuid.uuid4(),
        word="endeavor",
        meaning_ko="노력",
        master_id=None,
        selected_by=VocabularySelectedBy.LLM,
    )
    llm_vocab_2 = _make_saved_vocabulary(
        vocab_id=uuid.uuid4(),
        word="career",
        meaning_ko="경력",
        master_id=None,
        selected_by=VocabularySelectedBy.LLM,
    )
    master_1 = _make_master(master_id=MASTER_ID_1, headword_normalized="endeavor")
    master_2 = _make_master(master_id=MASTER_ID_2, headword_normalized="career")

    saved_1 = _make_saved_vocabulary(
        word="endeavor", meaning_ko="노력", master_id=MASTER_ID_1,
        selected_by=VocabularySelectedBy.LLM,
    )
    saved_2 = _make_saved_vocabulary(
        word="career", meaning_ko="경력", master_id=MASTER_ID_2,
        selected_by=VocabularySelectedBy.LLM,
    )

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.VocabularyMasterRepository") as mock_mrepo,
        patch("worksheet_api.routers.passages.augment_vocabulary") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=passage)
        mock_aug.return_value = [llm_vocab_1, llm_vocab_2]
        mock_vrepo.return_value.list_user_edited_headwords = AsyncMock(return_value=set())
        # 두 단어 모두 master 없음
        mock_mrepo.return_value.find_by_headword = AsyncMock(return_value=None)
        mock_mrepo.return_value.create = AsyncMock(side_effect=[master_1, master_2])
        mock_mrepo.return_value.increment_usage_count = AsyncMock()
        mock_vrepo.return_value.create = AsyncMock(side_effect=[saved_1, saved_2])
        mock_vrepo.return_value.list_by_passage = AsyncMock(return_value=[saved_1, saved_2])

        resp = await client_a.post(
            f"/passages/{PASSAGE_ID}/vocabulary",
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["vocabulary"]) == 2

    # master create 가 2회 호출됨
    assert mock_mrepo.return_value.create.await_count == 2
    # 두 master 의 created_by = LLM
    create_calls = mock_mrepo.return_value.create.call_args_list
    assert all(
        c[0][0].created_by == VocabularyMasterCreatedBy.LLM
        for c in create_calls
    )


@pytest.mark.asyncio
async def test_llm_augment_reuses_existing_masters(client_a: AsyncClient) -> None:
    """LLM 보강 — 기존 master reuse + usage_count 증가.

    find_by_headword 가 기존 master 를 반환하면 create 는 호출되지 않고
    increment_usage_count 가 호출되어야 한다.
    """
    from shared.schemas.vocabulary import VocabularySelectedBy

    passage = _make_passage()
    llm_vocab = _make_saved_vocabulary(
        word="endeavor",
        meaning_ko="노력",
        master_id=None,
        selected_by=VocabularySelectedBy.LLM,
    )
    existing_master = _make_master(master_id=MASTER_ID_1, usage_count=7)
    saved_vocab = _make_saved_vocabulary(
        word="endeavor", meaning_ko="노력", master_id=MASTER_ID_1,
        selected_by=VocabularySelectedBy.LLM,
    )

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.VocabularyMasterRepository") as mock_mrepo,
        patch("worksheet_api.routers.passages.augment_vocabulary") as mock_aug,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=passage)
        mock_aug.return_value = [llm_vocab]
        mock_vrepo.return_value.list_user_edited_headwords = AsyncMock(return_value=set())
        mock_mrepo.return_value.find_by_headword = AsyncMock(return_value=existing_master)
        mock_mrepo.return_value.create = AsyncMock()
        mock_mrepo.return_value.increment_usage_count = AsyncMock()
        mock_vrepo.return_value.create = AsyncMock(return_value=saved_vocab)
        mock_vrepo.return_value.list_by_passage = AsyncMock(return_value=[saved_vocab])

        resp = await client_a.post(
            f"/passages/{PASSAGE_ID}/vocabulary",
        )

    assert resp.status_code == 200

    # reuse → create 미호출 + increment 호출
    mock_mrepo.return_value.create.assert_not_awaited()
    mock_mrepo.return_value.increment_usage_count.assert_awaited_once_with(MASTER_ID_1)


# ─── 테스트: DELETE → usage_count 감소 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_vocabulary_decrements_master_usage_count(
    client_a: AsyncClient,
) -> None:
    """DELETE vocabulary → master.usage_count -= 1 (Stage E1-d 연동).

    master_id 가 있는 Vocabulary 를 삭제하면
    master_repo.decrement_usage_count 가 호출되어야 한다.
    """
    passage = _make_passage()
    existing_vocab = _make_saved_vocabulary(
        vocab_id=VOCAB_ID_1,
        master_id=MASTER_ID_1,
    )

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.VocabularyMasterRepository") as mock_mrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=passage)
        mock_vrepo.return_value.get = AsyncMock(return_value=existing_vocab)
        mock_vrepo.return_value.delete_by_id = AsyncMock(return_value=True)
        mock_mrepo.return_value.decrement_usage_count = AsyncMock()

        resp = await client_a.delete(
            f"/passages/{PASSAGE_ID}/vocabulary/{VOCAB_ID_1}",
        )

    assert resp.status_code == 204
    # decrement 호출됨
    mock_mrepo.return_value.decrement_usage_count.assert_awaited_once_with(MASTER_ID_1)


@pytest.mark.asyncio
async def test_delete_vocabulary_without_master_no_decrement(
    client_a: AsyncClient,
) -> None:
    """master_id 없는 (legacy) Vocabulary 삭제 → decrement 미호출."""
    passage = _make_passage()
    existing_vocab = _make_saved_vocabulary(
        vocab_id=VOCAB_ID_1,
        master_id=None,  # master 미연결 legacy
    )

    with (
        patch("worksheet_api.routers.passages.PassageRepository") as mock_prepo,
        patch("worksheet_api.routers.passages.VocabularyRepository") as mock_vrepo,
        patch("worksheet_api.routers.passages.VocabularyMasterRepository") as mock_mrepo,
    ):
        mock_prepo.return_value.get = AsyncMock(return_value=passage)
        mock_vrepo.return_value.get = AsyncMock(return_value=existing_vocab)
        mock_vrepo.return_value.delete_by_id = AsyncMock(return_value=True)
        mock_mrepo.return_value.decrement_usage_count = AsyncMock()

        resp = await client_a.delete(
            f"/passages/{PASSAGE_ID}/vocabulary/{VOCAB_ID_1}",
        )

    assert resp.status_code == 204
    # master 없으므로 decrement 미호출
    mock_mrepo.return_value.decrement_usage_count.assert_not_awaited()
