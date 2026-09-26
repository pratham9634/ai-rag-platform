"""
Dedicated ContextManager Service.

Orchestrates multi-source concurrent retrieval across:
1. Recent conversation messages (sliding window)
2. Running conversation summary
3. Long-term semantic user memories
4. Relevant cross-conversation historical turns
5. Grounded RAG document chunks

Applies token budgeting via tiktoken and packages untrusted reference data
into well-structured, prompt-injection-resistant XML envelopes.
"""

import asyncio
import logging
import uuid
from typing import Any

import tiktoken
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sanitizer import sanitize_text
from app.config import settings
from app.database.models import Conversation, Message
from app.services.memory_cache import MemoryCacheService
from app.services.memory_service import MemoryService
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)


class CompiledContext(BaseModel):
    """Assembled, token-budgeted conversational and grounding context."""

    formatted_context: str = Field(description="Structured XML-formatted reference context")
    recent_messages: list[dict[str, str]] = Field(default_factory=list)
    conversation_summary: str | None = None
    long_term_memories: list[dict[str, Any]] = Field(default_factory=list)
    historical_context: list[dict[str, Any]] = Field(default_factory=list)
    rag_chunks: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    estimated_tokens: int = 0


class ContextManager:
    """Manages context assembly, token limits, and injection resistance."""

    def __init__(
        self,
        memory_service: MemoryService | None = None,
        retrieval_service: RetrievalService | None = None,
        cache_service: MemoryCacheService | None = None,
    ) -> None:
        self.memory = memory_service or MemoryService()
        self.retrieval = retrieval_service or RetrievalService()
        self.cache = cache_service or MemoryCacheService()

        self.tokenizer: Any | None = None
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = None

    def count_tokens(self, text: str) -> int:
        """Count BPE tokens accurately using tiktoken with length fallback."""
        if not text:
            return 0
        if self.tokenizer:
            try:
                return len(self.tokenizer.encode(text))
            except Exception as exc:
                logger.debug("Failed to encode text with tokenizer: %s", exc)
        return len(text) // 4

    # ── Concurrency Tasks ────────────────────────────────────────────────
    async def _fetch_recent_messages(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        conv_id: uuid.UUID | None,
    ) -> list[dict[str, str]]:
        """Fetch recent conversation turns from Redis cache or Postgres."""
        if not conv_id:
            return []

        # 1. Check Redis cache
        cached = await self.cache.get_recent_messages(str(conv_id))
        if cached is not None:
            return cached

        # 2. Query Postgres
        try:
            stmt = (
                select(Message)
                .where(
                    Message.conversation_id == conv_id,
                    Message.tenant_id == tenant_id,
                )
                .order_by(Message.created_at.desc())
                .limit(settings.max_recent_messages)
            )
            res = await db.execute(stmt)
            raw_msgs = list(reversed(res.scalars().all()))

            messages = [{"role": m.role, "content": m.content} for m in raw_msgs]
            await self.cache.set_recent_messages(str(conv_id), messages)
            return messages
        except Exception as exc:
            logger.warning("Error fetching recent messages for conv %s: %s", conv_id, exc)
            return []

    async def _fetch_summary(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        conv_id: uuid.UUID | None,
    ) -> str | None:
        """Fetch running conversation summary from cache or Postgres."""
        if not conv_id:
            return None

        # 1. Check Redis cache
        cached_summary_tuple = await self.cache.get_summary(str(conv_id))
        if cached_summary_tuple is not None:
            return cached_summary_tuple[0]

        # 2. Query Postgres
        try:
            stmt = select(Conversation.summary, Conversation.summary_version).where(
                Conversation.id == conv_id,
                Conversation.tenant_id == tenant_id,
            )
            res = await db.execute(stmt)
            row = res.first()
            if row and row[0]:
                summary_text, version = row[0], row[1] or 0
                await self.cache.set_summary(str(conv_id), summary_text, version)
                return str(summary_text)
            return None
        except Exception as exc:
            logger.warning("Error fetching summary for conv %s: %s", conv_id, exc)
            return None

    # ── Context Builder Orchestrator ─────────────────────────────────────
    async def build_context(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        conv_id: uuid.UUID | None,
        query: str,
        top_k: int | None = None,
        api_key_override: str | None = None,
        skip_rag: bool = False,
    ) -> CompiledContext:
        """
        Concurrently retrieve all memory and knowledge sources and compile context.

        Guarantees:
        - Strict tenant and user isolation
        - Concurrency via asyncio.gather
        - Token budgeting within settings.max_context_tokens
        - Zero single point of failure: failures in memory or RAG degrade gracefully
        """
        rag_k = top_k or settings.max_rag_results

        # Define concurrent retrieval tasks
        async def rag_task() -> list[Any]:
            if skip_rag:
                return []
            try:
                return await self.retrieval.hybrid_search(
                    db=db,
                    tenant_id=tenant_id,
                    query=query,
                    top_k=rag_k,
                    api_key_override=api_key_override,
                )
            except Exception as e:
                logger.warning("RAG retrieval failed in ContextManager: %s", e)
                return []

        async def memory_task() -> list[dict[str, Any]]:
            try:
                return await self.memory.retrieve_user_memories(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    query=query,
                    limit=settings.max_memory_results,
                    api_key_override=api_key_override,
                )
            except Exception as e:
                logger.warning("Memory retrieval failed in ContextManager: %s", e)
                return []

        async def history_task() -> list[dict[str, Any]]:
            try:
                return await self.memory.retrieve_historical_conversations(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    current_conv_id=conv_id,
                    query=query,
                    limit=settings.max_history_results,
                )
            except Exception as e:
                logger.warning("Historical retrieval failed in ContextManager: %s", e)
                return []

        # Execute all 5 retrieval streams concurrently
        results = await asyncio.gather(
            self._fetch_recent_messages(db, tenant_id, user_id, conv_id),
            self._fetch_summary(db, tenant_id, user_id, conv_id),
            memory_task(),
            history_task(),
            rag_task(),
            return_exceptions=True,
        )

        recent_msgs: list[dict[str, str]] = results[0] if isinstance(results[0], list) else []
        summary: str | None = results[1] if isinstance(results[1], str) else None
        memories: list[dict[str, Any]] = results[2] if isinstance(results[2], list) else []
        historical: list[dict[str, Any]] = results[3] if isinstance(results[3], list) else []
        rag_results: list[Any] = results[4] if isinstance(results[4], list) else []

        # Format citations from RAG
        citations: list[dict[str, Any]] = []
        rag_chunks: list[dict[str, Any]] = []
        for r in rag_results:
            chunk_data = {
                "chunk_id": str(r.chunk_id),
                "document_id": str(r.document_id),
                "page_number": r.page_number,
                "content": r.content,
                "relevance_score": r.relevance_score,
            }
            rag_chunks.append(chunk_data)
            citations.append(
                {
                    "chunk_id": str(r.chunk_id),
                    "document_id": str(r.document_id),
                    "page_number": r.page_number,
                    "relevance_score": r.relevance_score,
                }
            )

        # ── Token Budgeting & Section Construction ───────────────────────
        budget = settings.max_context_tokens
        used_tokens = self.count_tokens(query)

        sections: list[str] = []

        # 1. Conversation Summary Section
        if summary and summary.strip():
            clean_summary = sanitize_text(summary.strip())
            summary_tokens = self.count_tokens(clean_summary)
            if used_tokens + summary_tokens < budget:
                sections.append(f"<conversation_summary>\n{clean_summary}\n</conversation_summary>")
                used_tokens += summary_tokens

        # 2. Long-Term User Memory Section
        if memories:
            memory_lines: list[str] = []
            for m in memories:
                line = f"- [{m['type'].upper()}] {m['content']}"
                line_tokens = self.count_tokens(line)
                if used_tokens + line_tokens < budget:
                    memory_lines.append(sanitize_text(line))
                    used_tokens += line_tokens
            if memory_lines:
                formatted_mems = "\n".join(memory_lines)
                sections.append(f"<long_term_memory>\n{formatted_mems}\n</long_term_memory>")

        # 3. Relevant Historical Conversations Section
        if historical:
            hist_lines: list[str] = []
            for h in historical:
                role_label = h.get("role", "user").capitalize()
                line = f"[{role_label} in prior conversation]: {h.get('content', '')}"
                line_tokens = self.count_tokens(line)
                if used_tokens + line_tokens < budget:
                    hist_lines.append(sanitize_text(line))
                    used_tokens += line_tokens
            if hist_lines:
                formatted_hist = "\n".join(hist_lines)
                sections.append(f"<historical_context>\n{formatted_hist}\n</historical_context>")

        # 4. RAG Document Grounding Section
        if rag_chunks:
            rag_blocks: list[str] = []
            for c in rag_chunks:
                clean_chunk = (
                    str(c["content"])
                    .replace("</rag_context>", "&lt;/rag_context&gt;")
                    .replace("<rag_context>", "&lt;rag_context&gt;")
                )
                block = (
                    f'<chunk page="{c["page_number"]}" chunk_id="{c["chunk_id"]}">'
                    f"\n{sanitize_text(clean_chunk)}\n</chunk>"
                )
                block_tokens = self.count_tokens(block)
                if used_tokens + block_tokens < budget:
                    rag_blocks.append(block)
                    used_tokens += block_tokens
            if rag_blocks:
                formatted_rag = "\n\n".join(rag_blocks)
                sections.append(f"<rag_context>\n{formatted_rag}\n</rag_context>")

        # 5. Recent Conversation Window Section
        if recent_msgs:
            recent_lines: list[str] = []
            for msg in recent_msgs:
                r = msg.get("role", "user").capitalize()
                content = msg.get("content", "").strip()
                line = f"{r}: {content}"
                line_tokens = self.count_tokens(line)
                if used_tokens + line_tokens < budget:
                    recent_lines.append(sanitize_text(line))
                    used_tokens += line_tokens
            if recent_lines:
                formatted_recent = "\n".join(recent_lines)
                sections.append(
                    f"<recent_conversation>\n{formatted_recent}\n</recent_conversation>"
                )

        compiled_xml = "\n\n".join(sections)

        return CompiledContext(
            formatted_context=compiled_xml,
            recent_messages=recent_msgs,
            conversation_summary=summary,
            long_term_memories=memories,
            historical_context=historical,
            rag_chunks=rag_chunks,
            citations=citations,
            estimated_tokens=used_tokens,
        )
