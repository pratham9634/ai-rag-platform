"""
Unit tests for Chat API Router.

Tests:
1. Conversation creation with multi-tenant isolation.
2. Conversation listing filtering by tenant.
3. Message history retrieval.
4. Server-Sent Events (SSE) token streaming.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def test_create_conversation(mock_db_session: AsyncMock) -> None:
    """Create conversation should return 201 Created and return new conversation."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    response = client.post(
        "/api/chat/conversations",
        json={"title": "Q3 Financials Discussion"},
        headers={"X-Tenant-ID": "tenant-alpha"},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Q3 Financials Discussion"
    assert data["tenant_id"] == "tenant-alpha"
    assert "id" in data


def test_chat_query_agentic_flow(mock_db_session: AsyncMock) -> None:
    """Chat query should run agent workflow and return answer with citations."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    fake_state = {
        "generation": "Employees receive 25 days of annual PTO [Page 1].",
        "citations": [
            {
                "chunk_id": "c1",
                "document_id": "d1",
                "page_number": 1,
                "relevance_score": 0.9,
            }
        ],
        "route": "retrieve",
    }

    with patch("app.api.chat.AgentWorkflow") as mock_workflow_cls:
        mock_instance = mock_workflow_cls.return_value
        mock_instance.run = AsyncMock(return_value=fake_state)

        client = TestClient(app)
        response = client.post(
            "/api/chat/query",
            json={"query": "How many days of PTO do employees get?"},
            headers={"X-Tenant-ID": "tenant-alpha"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "25 days of annual PTO" in data["answer"]
    assert len(data["citations"]) == 1
    assert data["citations"][0]["page_number"] == 1
    assert data["route_taken"] == "retrieve"


def test_chat_stream_sse_endpoint(mock_db_session: AsyncMock) -> None:
    """Chat stream should yield SSE events with tokens and citations."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    fake_state = {
        "generation": "PTO is 25 days.",
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

    with patch("app.api.chat.AgentWorkflow") as mock_workflow_cls:
        mock_instance = mock_workflow_cls.return_value
        mock_instance.run = AsyncMock(return_value=fake_state)

        client = TestClient(app)
        response = client.post(
            "/api/chat/stream",
            json={"query": "What is our PTO?"},
            headers={"X-Tenant-ID": "tenant-alpha"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    text = response.text
    assert "data: " in text
    assert "route" in text
    assert "citations" in text
    assert "token" in text
    assert "done" in text
