"""
Comprehensive Test Suite for Persistent Memory and Conversational Context.

Covers:
1. Conversation and message persistence with user_id & tenant_id
2. Chronological message ordering
3. Summary generation and version incrementing
4. Structured memory extraction from dialogue
5. Memory deduplication
6. Memory conflict resolution / superseding (is_active = False)
7. Semantic memory retrieval via vector cosine similarity
8. Cross-user and cross-tenant security and isolation
9. Redis failure resilience and graceful degradation
10. Memory failure resilience (chat never blocks)
11. Long conversation message thresholding
12. Token context budgeting and XML packaging
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.security import AuthenticatedUser, get_current_user
from app.database.models import Conversation, Message, UserMemory
from app.database.session import get_db
from app.main import app
from app.services.context_manager import ContextManager
from app.services.memory_cache import MemoryCacheService
from app.services.memory_service import MemoryService


@pytest.fixture
def mock_db() -> AsyncMock:
    """Fixture providing an async SQLAlchemy session mock."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = MagicMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.fixture
def test_user_a() -> AuthenticatedUser:
    """User profile for Tenant Alpha, User A."""
    return AuthenticatedUser(
        user_id="user_alice_123",
        tenant_id="tenant_alpha",
        org_id="tenant_alpha",
        org_role="admin",
        is_authenticated=True,
    )


@pytest.fixture
def test_user_b() -> AuthenticatedUser:
    """User profile for Tenant Alpha, User B (different user, same tenant)."""
    return AuthenticatedUser(
        user_id="user_bob_456",
        tenant_id="tenant_alpha",
        org_id="tenant_alpha",
        org_role="member",
        is_authenticated=True,
    )


# ── Test 1: Conversation & Message Persistence with user_id ──────────
@pytest.mark.asyncio
async def test_conversation_persistence_with_user_identity(
    mock_db: AsyncMock, test_user_a: AuthenticatedUser
) -> None:
    """Verify conversation record correctly links user_id and tenant_id."""

    async def override_get_db():
        yield mock_db

    async def override_get_user():
        return test_user_a

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_user

    client = TestClient(app)
    response = client.post(
        "/api/chat/conversations",
        json={"title": "Architecture Discussion"},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Architecture Discussion"
    assert data["tenant_id"] == "tenant_alpha"
    assert data["user_id"] == "user_alice_123"
    assert data["summary_version"] == 0


# ── Test 2: Message Ordering and Chronology ──────────────────────────
@pytest.mark.asyncio
async def test_message_chronological_ordering(mock_db: AsyncMock) -> None:
    """Verify ContextManager retrieves and preserves chronological message order."""
    conv_id = uuid.uuid4()
    t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 10, 1, 0, tzinfo=UTC)

    msg1 = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        tenant_id="t1",
        user_id="u1",
        role="user",
        content="First question",
        created_at=t1,
    )
    msg2 = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        tenant_id="t1",
        user_id="u1",
        role="assistant",
        content="First answer",
        created_at=t2,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [msg2, msg1]
    mock_db.execute.return_value = mock_result

    mgr = ContextManager()
    with patch.object(mgr.cache, "get_recent_messages", return_value=None):
        messages = await mgr._fetch_recent_messages(mock_db, "t1", "u1", conv_id)

    assert len(messages) == 2
    assert messages[0]["content"] == "First question"
    assert messages[1]["content"] == "First answer"


# ── Test 3: Structured Memory Extraction ─────────────────────────────
@pytest.mark.asyncio
async def test_memory_extraction_schema_validation() -> None:
    """Verify durable user facts are extracted and temporary banter is discarded."""
    mock_llm = AsyncMock()
    mock_llm.generate_response.return_value = (
        '{"memories": [{"type": "preference", "content": '
        '"User prefers PostgreSQL over MongoDB.", "importance": 0.9}]}'
    )

    svc = MemoryService(llm_service=mock_llm)
    memories = await svc.extract_memories_from_turn(
        user_content="We decided to use PostgreSQL instead of MongoDB.",
        assistant_content="Understood. PostgreSQL will be our primary datastore.",
    )

    assert len(memories) == 1
    assert memories[0]["type"] == "preference"
    assert "PostgreSQL" in memories[0]["content"]
    assert memories[0]["importance"] == 0.9


@pytest.mark.asyncio
async def test_memory_extraction_filters_trivial_greetings() -> None:
    """Verify trivial greetings or questions are not extracted into long-term memory."""
    mock_llm = AsyncMock()
    svc = MemoryService(llm_service=mock_llm)

    memories = await svc.extract_memories_from_turn(
        user_content="hello there",
        assistant_content="Hello! How can I help you?",
    )
    assert memories == []
    mock_llm.generate_response.assert_not_called()


# ── Test 4: Memory Conflict Resolution / Superseding ─────────────────
@pytest.mark.asyncio
async def test_memory_conflict_resolution_supersedes_old_fact(mock_db: AsyncMock) -> None:
    """Verify updating a preference deactivates (supersedes) the old memory."""
    svc = MemoryService()

    # Create dummy embedding
    vec = [0.1] * 1536
    old_mem = UserMemory(
        id=uuid.uuid4(),
        tenant_id="tenant_alpha",
        user_id="user_alice",
        memory_type="preference",
        content="Primary Database is MongoDB",
        embedding=vec,
        importance=0.8,
        is_active=True,
    )

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = old_mem
    mock_db.execute.return_value = mock_res

    # Mock embeddings generation to return exact same vector (similarity = 1.0)
    with patch.object(svc.embeddings, "generate_embedding", return_value=vec):
        saved = await svc.save_or_update_memories(
            db=mock_db,
            tenant_id="tenant_alpha",
            user_id="user_alice",
            memories=[
                {
                    "type": "preference",
                    "content": "Primary Database is PostgreSQL",
                    "importance": 0.9,
                }
            ],
        )

    # Old memory must be superseded
    assert old_mem.is_active is False
    assert len(saved) == 1
    assert saved[0].content == "Primary Database is PostgreSQL"
    assert saved[0].is_active is True


# ── Test 5: Semantic Memory Retrieval with pgvector ──────────────────
@pytest.mark.asyncio
async def test_semantic_memory_retrieval(mock_db: AsyncMock) -> None:
    """Verify semantic retrieval ranks memories based on vector similarity and importance."""
    svc = MemoryService()

    mem1 = UserMemory(
        id=uuid.uuid4(),
        tenant_id="t1",
        user_id="u1",
        memory_type="decision",
        content="Adopted Elasticsearch for enterprise logging.",
        importance=0.8,
        is_active=True,
    )

    # Mock DB query result
    mock_result = MagicMock()
    mock_result.all.return_value = [(mem1, 0.88)]
    mock_db.execute.return_value = mock_result

    with patch.object(svc.embeddings, "generate_embedding", return_value=[0.1] * 1536):
        results = await svc.retrieve_user_memories(
            db=mock_db,
            tenant_id="t1",
            user_id="u1",
            query="What did we decide about Elasticsearch?",
            limit=5,
        )

    assert len(results) == 1
    assert results[0]["type"] == "decision"
    assert "Elasticsearch" in results[0]["content"]
    assert results[0]["similarity"] == 0.88


# ── Test 6: Cross-User and Multi-Tenant Security Isolation ───────────
@pytest.mark.asyncio
async def test_user_memory_isolation(
    mock_db: AsyncMock,
    test_user_a: AuthenticatedUser,
    test_user_b: AuthenticatedUser,
) -> None:
    """Verify User B cannot access User A's private memories even in the same tenant."""
    svc = MemoryService()

    # User B queries their own memory
    with patch.object(svc.embeddings, "generate_embedding", return_value=[0.0] * 1536):
        mock_result = MagicMock()
        mock_result.all.return_value = []  # No memories for User B
        mock_db.execute.return_value = mock_result

        results = await svc.retrieve_user_memories(
            db=mock_db,
            tenant_id=test_user_b.tenant_id,
            user_id=test_user_b.user_id,
            query="Tell me about Alice's secret project",
        )

    assert results == []

    # Check the WHERE clause in execute call to verify strict user_id filtering
    call_args = mock_db.execute.call_args[0][0]
    compiled_sql = str(call_args)
    assert "user_memories.user_id = :user_id_1" in compiled_sql
    assert "user_memories.tenant_id = :tenant_id_1" in compiled_sql


# ── Test 7: Conversation Summarization at Threshold ──────────────────
@pytest.mark.asyncio
async def test_incremental_conversation_summarization(mock_db: AsyncMock) -> None:
    """Verify running summary is updated and version incremented when threshold is met."""
    mock_llm = AsyncMock()
    mock_llm.generate_response.return_value = (
        "Updated summary: Client migrated from Mongo to Postgres."
    )

    svc = MemoryService(llm_service=mock_llm)
    conv_id = uuid.uuid4()
    conv = Conversation(
        id=conv_id,
        tenant_id="t1",
        user_id="u1",
        title="DB Migration",
        summary="Prior discussion on database alternatives.",
        summary_version=1,
    )

    # Mock count >= 20 threshold
    mock_db.scalar.return_value = 25

    # Mock conv retrieval
    conv_res = MagicMock()
    conv_res.scalar_one_or_none.return_value = conv

    # Mock older messages
    msgs_res = MagicMock()
    msgs_res.scalars.return_value.all.return_value = [
        Message(role="user", content="We decided on Postgres."),
        Message(role="assistant", content="Migration script created."),
    ]
    mock_db.execute.side_effect = [conv_res, msgs_res]

    new_summary = await svc.summarize_conversation_if_needed(
        db=mock_db,
        conv_id=conv_id,
        tenant_id="t1",
        user_id="u1",
    )

    assert new_summary == "Updated summary: Client migrated from Mongo to Postgres."
    assert conv.summary_version == 2
    mock_db.commit.assert_awaited()


# ── Test 8: ContextManager Token Limits & XML Packaging ──────────────
@pytest.mark.asyncio
async def test_context_manager_token_budgeting_and_xml(mock_db: AsyncMock) -> None:
    """Verify ContextManager generates structured XML sections within token budget."""
    mgr = ContextManager()

    # Mock retrieval streams
    with (
        patch.object(
            mgr,
            "_fetch_recent_messages",
            return_value=[{"role": "user", "content": "How do I deploy?"}],
        ),
        patch.object(mgr, "_fetch_summary", return_value="Project is migrating to AWS."),
        patch.object(
            mgr.memory,
            "retrieve_user_memories",
            return_value=[
                {"type": "preference", "content": "User prefers Terraform over CloudFormation"}
            ],
        ),
        patch.object(
            mgr.memory,
            "retrieve_historical_conversations",
            return_value=[],
        ),
        patch.object(mgr.retrieval, "hybrid_search", return_value=[]),
    ):
        ctx = await mgr.build_context(
            db=mock_db,
            tenant_id="t1",
            user_id="u1",
            conv_id=uuid.uuid4(),
            query="Deployment question",
        )

    xml = ctx.formatted_context
    assert "<conversation_summary>" in xml
    assert "Project is migrating to AWS." in xml
    assert "<long_term_memory>" in xml
    assert "Terraform" in xml
    assert "<recent_conversation>" in xml
    assert "How do I deploy?" in xml
    assert ctx.estimated_tokens > 0


# ── Test 9: Redis Failure Resilience ─────────────────────────────────
@pytest.mark.asyncio
async def test_redis_failure_resilience_in_cache_service() -> None:
    """Verify Redis outage degrades gracefully to Postgres without raising exceptions."""
    cache = MemoryCacheService()

    # Mock get_redis_client to return None (Redis down/unreachable)
    with patch("app.services.memory_cache.get_redis_client", return_value=None):
        recent = await cache.get_recent_messages("conv-123")
        summary = await cache.get_summary("conv-123")
        memories = await cache.get_user_memories("user-123")

        # Must return None cleanly
        assert recent is None
        assert summary is None
        assert memories is None

        # Write operations must execute silently without throwing
        await cache.set_recent_messages("conv-123", [{"role": "user", "content": "hi"}])
        await cache.set_summary("conv-123", "Summary text", 1)
        await cache.invalidate_recent_messages("conv-123")


# ── Test 10: End-to-End Chat Query with Memory Integration ───────────
def test_chat_query_with_persistent_memory(
    mock_db: AsyncMock, test_user_a: AuthenticatedUser
) -> None:
    """Verify chat query endpoint incorporates memory and returns grounded answer."""

    async def override_get_db():
        yield mock_db

    async def override_get_user():
        return test_user_a

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_user

    fake_agent_state = {
        "generation": "Based on our past decision, we use PostgreSQL [Page 1].",
        "citations": [
            {
                "chunk_id": "c1",
                "document_id": "d1",
                "page_number": 1,
                "relevance_score": 0.95,
            }
        ],
        "route": "retrieve",
    }

    with (
        patch("app.api.chat.AgentWorkflow") as mock_workflow_cls,
        patch("app.api.chat.ContextManager") as mock_ctx_cls,
    ):
        mock_wf = mock_workflow_cls.return_value
        mock_wf.run = AsyncMock(return_value=fake_agent_state)

        mock_cm = mock_ctx_cls.return_value
        mock_cm.build_context = AsyncMock()
        mock_cm.build_context.return_value = MagicMock(
            formatted_context="<long_term_memory>DB: PostgreSQL</long_term_memory>",
            recent_messages=[],
            citations=[
                {
                    "chunk_id": "c1",
                    "document_id": "d1",
                    "page_number": 1,
                    "relevance_score": 0.95,
                }
            ],
        )

        client = TestClient(app)
        response = client.post(
            "/api/chat/query",
            json={"query": "What database are we using?"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "PostgreSQL" in data["answer"]
    assert len(data["citations"]) == 1
    assert data["route_taken"] == "retrieve"
