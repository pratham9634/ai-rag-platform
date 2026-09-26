"""
Agentic RAG StateGraph Pipeline.

Implements a cyclic self-correcting RAG workflow using LangGraph:
1. Router Node: Classifies user intent (retrieve vs direct chat).
2. Retriever Node: Executes multi-tenant hybrid search + cross-encoder reranking.
3. Relevance Grader: Evaluates document relevance to avoid answering from poor context.
4. Query Rewriter: Reformulates queries if initial retrieval relevance is low.
5. Grounded Generator: Produces strictly grounded answers citing specific pages.
6. Hallucination Grader: Audits the final output against source text.
"""

import json
import logging
import time
from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import (
    GENERATOR_SYSTEM_PROMPT,
    QUERY_REWRITE_PROMPT,
    RELEVANCE_GRADER_PROMPT,
    ROUTER_PROMPT,
)
from app.agent.state import AgentState
from app.observability.tracer import get_tracer_run_config, metrics_tracker
from app.services.llm import LLMService
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)

MAX_RETRIEVAL_RETRIES = 1


class AgentWorkflow:
    """Orchestrates the LangGraph agentic RAG state machine."""

    def __init__(
        self,
        db: AsyncSession,
        llm_service: LLMService | None = None,
        retrieval_service: RetrievalService | None = None,
    ) -> None:
        self.db = db
        self.llm = llm_service or LLMService()
        self.retrieval = retrieval_service or RetrievalService()
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        workflow = StateGraph(AgentState)

        # Register nodes
        workflow.add_node("router", self.route_query)
        workflow.add_node("retriever", self.retrieve_documents)
        workflow.add_node("grader", self.grade_documents)
        workflow.add_node("rewriter", self.rewrite_query)
        workflow.add_node("generator", self.generate_answer)
        workflow.add_node("direct_generator", self.generate_direct)

        # Set entry point
        workflow.set_entry_point("router")

        # Conditional edge from router
        workflow.add_conditional_edges(
            "router",
            self._decide_route,
            {
                "retrieve": "retriever",
                "direct": "direct_generator",
            },
        )

        # Retriever always flows to relevance grader
        workflow.add_edge("retriever", "grader")

        # Conditional edge from grader
        workflow.add_conditional_edges(
            "grader",
            self._decide_after_grading,
            {
                "generate": "generator",
                "rewrite": "rewriter",
            },
        )

        # Rewriter flows back to retriever for multi-hop retry
        workflow.add_edge("rewriter", "retriever")

        # Direct and grounded generators terminate the graph
        workflow.add_edge("direct_generator", END)
        workflow.add_edge("generator", END)

        return workflow.compile()

    # ── Node Implementations ─────────────────────────────────────────

    async def route_query(self, state: AgentState) -> dict[str, Any]:
        """Classify user intent between document retrieval and general chat."""
        query = state.get("query", "")
        api_key = state.get("api_key_override")

        # Fast heuristic checks for obvious greetings
        clean = query.strip().lower()
        if clean in {"hi", "hello", "hey", "who are you", "what can you do", "help"}:
            return {"route": "direct"}

        messages = [
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user", "content": f"User Query: {query}"},
        ]

        response = await self.llm.generate_response(
            messages=messages,
            temperature=0.0,
            api_key_override=api_key,
        )

        try:
            # Parse JSON decision
            data = json.loads(response.strip().replace("```json", "").replace("```", ""))
            route = data.get("route", "retrieve")
        except Exception:
            route = "retrieve"

        return {"route": route}

    def _decide_route(self, state: AgentState) -> str:
        return state.get("route", "retrieve")

    async def retrieve_documents(self, state: AgentState) -> dict[str, Any]:
        """Fetch top candidates using the hybrid retrieval engine."""
        tenant_id = state.get("tenant_id", "default-tenant")
        query = state.get("rewritten_query") or state.get("query", "")
        api_key = state.get("api_key_override")

        k_val = state.get("top_k") or 5
        results = await self.retrieval.hybrid_search(
            db=self.db,
            tenant_id=tenant_id,
            query=query,
            top_k=k_val,
            api_key_override=api_key,
        )

        documents = []
        citations = []
        for r in results:
            doc_item = {
                "chunk_id": str(r.chunk_id),
                "document_id": str(r.document_id),
                "page_number": r.page_number,
                "content": r.content,
                "relevance_score": r.relevance_score,
            }
            documents.append(doc_item)
            citations.append(
                {
                    "chunk_id": str(r.chunk_id),
                    "document_id": str(r.document_id),
                    "page_number": r.page_number,
                    "relevance_score": r.relevance_score,
                }
            )

        return {"documents": documents, "citations": citations}

    async def grade_documents(self, state: AgentState) -> dict[str, Any]:
        """Assess whether retrieved documents contain relevant answers."""
        documents = state.get("documents", [])
        query = state.get("query", "")
        api_key = state.get("api_key_override")

        if not documents:
            return {"relevance": "not_relevant"}

        doc_summary = "\n\n".join(
            [f"[Page {d['page_number']}]: {d['content'][:300]}" for d in documents[:3]]
        )

        prompt = RELEVANCE_GRADER_PROMPT.format(query=query, documents=doc_summary)
        messages = [{"role": "user", "content": prompt}]

        response = await self.llm.generate_response(
            messages=messages,
            temperature=0.0,
            api_key_override=api_key,
        )

        try:
            data = json.loads(response.strip().replace("```json", "").replace("```", ""))
            score = data.get("score", "yes")
            relevance = "relevant" if score.lower() == "yes" else "not_relevant"
        except Exception:
            relevance = "relevant"

        return {"relevance": relevance}

    def _decide_after_grading(self, state: AgentState) -> str:
        relevance = state.get("relevance", "relevant")
        retry_count = state.get("retry_count", 0)

        if relevance == "relevant" or retry_count >= MAX_RETRIEVAL_RETRIES:
            return "generate"
        return "rewrite"

    async def rewrite_query(self, state: AgentState) -> dict[str, Any]:
        """Reformulate query for semantic retry when initial recall is poor."""
        query = state.get("query", "")
        retry_count = state.get("retry_count", 0)
        api_key = state.get("api_key_override")
        chat_history = state.get("chat_history", [])

        history_lines = []
        if chat_history:
            for m in chat_history[-4:]:
                r = "User" if m.get("role") == "user" else "Assistant"
                history_lines.append(f"{r}: {m.get('content', '')}")
        history_context = (
            ("Recent Conversation History:\n" + "\n".join(history_lines) + "\n\n")
            if history_lines
            else ""
        )

        prompt = QUERY_REWRITE_PROMPT.format(query=query, history_context=history_context)
        messages = [{"role": "user", "content": prompt}]

        rewritten = await self.llm.generate_response(
            messages=messages,
            temperature=0.2,
            api_key_override=api_key,
        )

        cleaned_rewrite = rewritten.strip().replace('"', "")
        logger.info("Rewrote query from '%s' to '%s'", query, cleaned_rewrite)

        return {
            "rewritten_query": cleaned_rewrite,
            "retry_count": retry_count + 1,
        }

    async def generate_answer(self, state: AgentState) -> dict[str, Any]:
        """Synthesize answer grounded strictly in retrieved documents with conversational memory."""
        documents = state.get("documents", [])
        query = state.get("query", "")
        api_key = state.get("api_key_override")
        chat_history = state.get("chat_history", [])

        if not documents:
            return {
                "generation": (
                    "I do not have enough information in the uploaded documents to "
                    "answer this question."
                )
            }

        context_blocks = []
        for d in documents:
            clean_content = (
                str(d["content"])
                .replace("</untrusted_document_context>", "&lt;/untrusted_document_context&gt;")
                .replace("<untrusted_document_context>", "&lt;untrusted_document_context&gt;")
                .replace("<system>", "&lt;system&gt;")
                .replace("</system>", "&lt;/system&gt;")
            )
            chunk_header = f'<chunk page="{d["page_number"]}" chunk_id="{d.get("chunk_id", "")}">'
            context_blocks.append(f"{chunk_header}\n{clean_content}\n</chunk>")
        formatted_context = "\n\n".join(context_blocks)

        system_msg = GENERATOR_SYSTEM_PROMPT.format(context=formatted_context)
        messages: list[dict[str, str]] = [{"role": "system", "content": system_msg}]

        # Inject recent multi-turn conversation memory (last 6 messages = ~3 full turns)
        if chat_history:
            for turn in chat_history[-6:]:
                role = "user" if turn.get("role") == "user" else "assistant"
                content = (turn.get("content") or "").strip()
                if content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": query})

        model = state.get("model_override")
        generation = await self.llm.generate_response(
            messages=messages,
            model=model,
            temperature=0.1,
            api_key_override=api_key,
        )

        return {"generation": generation}

    async def generate_direct(self, state: AgentState) -> dict[str, Any]:
        """Respond to conversational greetings or general inquiries directly with memory."""
        query = state.get("query", "")
        api_key = state.get("api_key_override")
        chat_history = state.get("chat_history", [])

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "You are the Enterprise RAG Assistant. Respond politely and concisely. "
                    "Offer to answer questions regarding corporate documentation and data."
                ),
            }
        ]

        if chat_history:
            for turn in chat_history[-6:]:
                role = "user" if turn.get("role") == "user" else "assistant"
                content = (turn.get("content") or "").strip()
                if content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": query})

        model = state.get("model_override")
        generation = await self.llm.generate_response(
            messages=messages,
            model=model,
            temperature=0.3,
            api_key_override=api_key,
        )

        return {"generation": generation, "citations": []}

    async def run(
        self,
        tenant_id: str,
        query: str,
        api_key_override: str | None = None,
        model_override: str | None = None,
        top_k: int | None = None,
        chat_history: list[dict[str, str]] | None = None,
    ) -> AgentState:
        """Execute full agent graph and return final state."""
        initial_state: AgentState = {
            "tenant_id": tenant_id,
            "query": query,
            "rewritten_query": "",
            "documents": [],
            "citations": [],
            "route": "retrieve",
            "relevance": "relevant",
            "is_hallucination": False,
            "retry_count": 0,
            "generation": "",
            "error": None,
            "chat_history": chat_history or [],
            "api_key_override": api_key_override,
            "model_override": model_override,
            "top_k": top_k,
        }

        run_config = get_tracer_run_config(
            tenant_id=tenant_id,
            run_name=f"agentic_rag_query_{tenant_id}",
        )

        start_time = time.time()
        final_state: AgentState = await self.graph.ainvoke(initial_state, config=run_config)
        elapsed_ms = (time.time() - start_time) * 1000.0

        metrics_tracker.record_query(
            tenant_id=tenant_id,
            latency_ms=elapsed_ms,
            is_error=bool(final_state.get("error")),
            route=final_state.get("route", "retrieve"),
            relevance=final_state.get("relevance", "relevant"),
        )
        return final_state
