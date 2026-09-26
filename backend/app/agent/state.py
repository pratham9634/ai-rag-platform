"""
Agent State Schema for LangGraph Pipeline.

Defines the multi-turn state object passed between nodes in the agent graph.
"""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Execution state maintained across all agent graph nodes."""

    # Tenant context
    tenant_id: str

    # User input and transformed queries
    query: str
    rewritten_query: str

    # Retrieved knowledge chunks
    documents: list[dict[str, Any]]
    citations: list[dict[str, Any]]

    # Agent node routing and evaluation flags
    route: str  # "retrieve" or "direct"
    relevance: str  # "relevant" or "not_relevant"
    is_hallucination: bool
    retry_count: int

    # Final output
    generation: str
    error: str | None

    # User BYOK override if supplied
    api_key_override: str | None
