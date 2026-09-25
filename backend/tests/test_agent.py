"""
Unit tests for LangGraph Agentic RAG Pipeline.

Verifies:
1. Router classification (retrieve vs direct chat).
2. Document relevance evaluation.
3. Query reformulation on poor recall.
4. Grounded answer generation.
5. End-to-end workflow execution.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.graph import AgentWorkflow
from app.agent.state import AgentState
from app.services.llm import LLMService
from app.services.retrieval import RetrievalService


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock(spec=LLMService)
    llm.generate_response = AsyncMock(return_value="Grounded answer citing [Page 1].")
    return llm


@pytest.fixture
def mock_retrieval() -> MagicMock:
    retrieval = MagicMock(spec=RetrievalService)
    item = MagicMock()
    item.chunk_id = "chunk-1"
    item.document_id = "doc-1"
    item.page_number = 1
    item.content = "Employees receive 25 days of annual paid time off."
    item.relevance_score = 0.95
    retrieval.hybrid_search = AsyncMock(return_value=[item])
    return retrieval


@pytest.mark.asyncio
async def test_router_heuristic_greeting(mock_db: AsyncMock) -> None:
    """Greetings should route directly without document retrieval."""
    workflow = AgentWorkflow(db=mock_db)
    state: AgentState = {"query": "Hello", "api_key_override": "sk-dummy"}
    result = await workflow.route_query(state)
    assert result["route"] == "direct"


@pytest.mark.asyncio
async def test_router_document_query(
    mock_db: AsyncMock, mock_llm: MagicMock, mock_retrieval: MagicMock
) -> None:
    """Document questions should classify as 'retrieve'."""
    mock_llm.generate_response = AsyncMock(return_value='{"route": "retrieve"}')
    workflow = AgentWorkflow(db=mock_db, llm_service=mock_llm, retrieval_service=mock_retrieval)

    state: AgentState = {
        "query": "What is our corporate PTO policy?",
        "api_key_override": "sk-dummy",
    }
    result = await workflow.route_query(state)
    assert result["route"] == "retrieve"


@pytest.mark.asyncio
async def test_retriever_node_extracts_citations(
    mock_db: AsyncMock, mock_llm: MagicMock, mock_retrieval: MagicMock
) -> None:
    """Retriever node extracts documents and structured citation metadata."""
    workflow = AgentWorkflow(db=mock_db, llm_service=mock_llm, retrieval_service=mock_retrieval)

    state: AgentState = {
        "tenant_id": "test-tenant",
        "query": "How many days PTO?",
        "api_key_override": "sk-dummy",
    }
    res = await workflow.retrieve_documents(state)

    assert len(res["documents"]) == 1
    assert res["documents"][0]["page_number"] == 1
    assert len(res["citations"]) == 1
    assert res["citations"][0]["chunk_id"] == "chunk-1"


@pytest.mark.asyncio
async def test_grader_node_marks_relevant(
    mock_db: AsyncMock, mock_llm: MagicMock, mock_retrieval: MagicMock
) -> None:
    """Grader node correctly marks documents with matching context as relevant."""
    mock_llm.generate_response = AsyncMock(return_value='{"score": "yes"}')
    workflow = AgentWorkflow(db=mock_db, llm_service=mock_llm, retrieval_service=mock_retrieval)

    state: AgentState = {
        "query": "How much PTO?",
        "documents": [{"page_number": 1, "content": "25 days PTO."}],
        "api_key_override": "sk-dummy",
    }
    res = await workflow.grade_documents(state)
    assert res["relevance"] == "relevant"


@pytest.mark.asyncio
async def test_query_rewriter_increments_retry(
    mock_db: AsyncMock, mock_llm: MagicMock, mock_retrieval: MagicMock
) -> None:
    """Query rewriter increments retry count and produces reformulated text."""
    mock_llm.generate_response = AsyncMock(
        return_value="corporate employee paid vacation entitlement policy"
    )
    workflow = AgentWorkflow(db=mock_db, llm_service=mock_llm, retrieval_service=mock_retrieval)

    state: AgentState = {
        "query": "vacation rules",
        "retry_count": 0,
        "api_key_override": "sk-dummy",
    }
    res = await workflow.rewrite_query(state)
    assert res["retry_count"] == 1
    assert "corporate employee" in res["rewritten_query"]


@pytest.mark.asyncio
async def test_end_to_end_agent_workflow(
    mock_db: AsyncMock, mock_llm: MagicMock, mock_retrieval: MagicMock
) -> None:
    """Full workflow completes and outputs generated answer with citations."""
    mock_llm.generate_response = AsyncMock(
        side_effect=[
            '{"route": "retrieve"}',  # router
            '{"score": "yes"}',  # grader
            "Employees are entitled to 25 days of PTO [Page 1].",  # generator
        ]
    )
    workflow = AgentWorkflow(db=mock_db, llm_service=mock_llm, retrieval_service=mock_retrieval)

    final_state = await workflow.run(
        tenant_id="tenant-alpha",
        query="What is the vacation policy?",
        api_key_override="sk-dummy",
    )

    assert "25 days of PTO" in final_state["generation"]
    assert len(final_state["citations"]) == 1
    assert final_state["citations"][0]["page_number"] == 1
