"""
Persistent Memory and Conversational History Service.

Orchestrates:
1. Semantic memory retrieval using pgvector cosine distance + importance weighting
2. Historical conversation retrieval across previous threads
3. Structured long-term memory extraction from dialogue turns
4. Semantic deduplication and memory conflict resolution (superseding old facts)
5. Incremental conversation summarization and version tracking
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import CONVERSATION_SUMMARIZER_PROMPT, MEMORY_EXTRACTION_PROMPT
from app.config import settings
from app.database.models import Conversation, Message, UserMemory
from app.services.embeddings import EmbeddingService
from app.services.llm import LLMService
from app.services.memory_cache import MemoryCacheService

logger = logging.getLogger(__name__)


class MemoryService:
    """Service handling persistent long-term user memories and summaries."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        llm_service: LLMService | None = None,
        cache_service: MemoryCacheService | None = None,
    ) -> None:
        self.embeddings = embedding_service or EmbeddingService()
        self.llm = llm_service or LLMService()
        self.cache = cache_service or MemoryCacheService()

    # ── 1. Semantic Memory Retrieval ─────────────────────────────────────
    async def retrieve_user_memories(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        query: str,
        limit: int | None = None,
        api_key_override: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve relevant active long-term memories for the authenticated user.

        Combines pgvector semantic similarity with memory importance weighting.
        Strict isolation: WHERE tenant_id = :tenant_id AND user_id = :user_id.
        """
        max_results = limit or settings.max_memory_results

        # Check Redis cache for fast return if available and query is empty/broad
        if not query.strip():
            cached_memories = await self.cache.get_user_memories(user_id)
            if cached_memories is not None:
                return cached_memories[:max_results]

        try:
            # Generate query embedding
            query_embedding = await self.embeddings.generate_embedding(
                query, api_key_override=api_key_override
            )

            # Query active memories using pgvector cosine distance
            cosine_dist = UserMemory.embedding.cosine_distance(query_embedding)
            similarity_expr = (1.0 - cosine_dist).label("similarity")

            stmt = (
                select(UserMemory, similarity_expr)
                .where(
                    UserMemory.tenant_id == tenant_id,
                    UserMemory.user_id == user_id,
                    UserMemory.is_active.is_(True),
                    UserMemory.embedding.is_not(None),
                )
                .order_by(cosine_dist.asc(), UserMemory.importance.desc())
                .limit(max_results * 2)
            )

            result = await db.execute(stmt)
            rows = result.all()

            results: list[dict[str, Any]] = []
            for memory_obj, sim in rows:
                sim_float = float(sim) if sim is not None else 0.0
                if sim_float >= settings.memory_similarity_threshold:
                    # Combined rank score: 70% semantic relevance, 30% importance
                    rank_score = (sim_float * 0.7) + (memory_obj.importance * 0.3)
                    results.append(
                        {
                            "id": str(memory_obj.id),
                            "type": memory_obj.memory_type,
                            "content": memory_obj.content,
                            "importance": memory_obj.importance,
                            "confidence": memory_obj.confidence,
                            "similarity": round(sim_float, 4),
                            "score": round(rank_score, 4),
                        }
                    )

            # Sort by combined score descending and slice to limit
            results.sort(key=lambda x: x["score"], reverse=True)
            final_selection = results[:max_results]

            # Cache the top memories for the user
            if final_selection:
                await self.cache.set_user_memories(user_id, final_selection)

            return final_selection

        except Exception as exc:
            logger.warning(
                "Error retrieving semantic user memories (user=%s, tenant=%s): %s",
                user_id,
                tenant_id,
                exc,
            )
            return []

    # ── 2. Historical Conversations Retrieval ─────────────────────────────
    async def retrieve_historical_conversations(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        current_conv_id: uuid.UUID | None,
        query: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve relevant historical turns from other conversation threads.

        Strict user and tenant filtering: prevents leaking other users' history.
        """
        max_results = limit or settings.max_history_results
        if not query.strip():
            return []

        try:
            # Find relevant historical messages from past conversations
            stmt = (
                select(Message)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(
                    Message.tenant_id == tenant_id,
                    Message.user_id == user_id,
                )
            )

            if current_conv_id:
                stmt = stmt.where(Message.conversation_id != current_conv_id)

            # Lexical match on query terms
            stmt = stmt.where(Message.content.ilike(f"%{query}%"))
            stmt = stmt.order_by(Message.created_at.desc()).limit(max_results)

            res = await db.execute(stmt)
            messages = res.scalars().all()

            return [
                {
                    "conversation_id": str(m.conversation_id),
                    "role": m.role,
                    "content": m.content[:300],
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ]

        except Exception as exc:
            logger.warning("Error retrieving historical conversation context: %s", exc)
            return []

    # ── 3. Structured Memory Extraction ───────────────────────────────────
    async def extract_memories_from_turn(
        self,
        user_content: str,
        assistant_content: str,
        api_key_override: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Analyze dialogue turn with LLM and extract durable user facts.

        Filters out transient noise, greetings, or assistant assumptions.
        """
        clean_user = user_content.strip().lower()
        if len(clean_user) < 6 or clean_user in {
            "hi",
            "hello",
            "hello there",
            "hey",
            "hey there",
            "thanks",
            "thank you",
            "bye",
            "goodbye",
            "ok",
            "okay",
        }:
            return []

        dialogue = f"User: {user_content}\nAssistant: {assistant_content}"
        prompt = MEMORY_EXTRACTION_PROMPT.format(dialogue=dialogue)
        messages = [{"role": "user", "content": prompt}]

        try:
            raw_response = await self.llm.generate_response(
                messages=messages,
                temperature=0.0,
                max_tokens=600,
                api_key_override=api_key_override,
            )

            cleaned = raw_response.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)

            extracted = data.get("memories", [])
            valid_memories: list[dict[str, Any]] = []

            allowed_types = {"preference", "project", "goal", "constraint", "decision", "fact"}
            for item in extracted:
                content = str(item.get("content", "")).strip()
                mem_type = str(item.get("type", "fact")).lower().strip()
                if mem_type not in allowed_types:
                    mem_type = "fact"

                try:
                    importance = float(item.get("importance", 0.5))
                    importance = max(0.1, min(1.0, importance))
                except (ValueError, TypeError):
                    importance = 0.5

                if content and len(content) >= 5:
                    valid_memories.append(
                        {
                            "type": mem_type,
                            "content": content,
                            "importance": importance,
                        }
                    )

            return valid_memories

        except Exception as exc:
            logger.warning("Failed to extract memories from turn: %s", exc)
            return []

    # ── 4. Deduplication & Conflict Resolution (Superseding) ──────────────
    async def save_or_update_memories(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        memories: list[dict[str, Any]],
        source_conv_id: uuid.UUID | None = None,
        source_msg_id: uuid.UUID | None = None,
        api_key_override: str | None = None,
    ) -> list[UserMemory]:
        """
        Persist memories with semantic deduplication and superseding.

        If a new memory is highly similar to an existing active memory
        (similarity >= memory_dedup_threshold):
        - Marks existing memory is_active = False (superseded).
        - Inserts new memory as active.
        """
        if not memories:
            return []

        saved: list[UserMemory] = []
        now = datetime.now(UTC)

        for mem_data in memories:
            content = mem_data["content"]
            mem_type = mem_data["type"]
            importance = mem_data.get("importance", 0.5)

            try:
                # 1. Generate embedding for memory
                embedding = await self.embeddings.generate_embedding(
                    content, api_key_override=api_key_override
                )

                # 2. Check for conflicting or duplicate existing active memories
                check_stmt = (
                    select(UserMemory)
                    .where(
                        UserMemory.tenant_id == tenant_id,
                        UserMemory.user_id == user_id,
                        UserMemory.memory_type == mem_type,
                        UserMemory.is_active.is_(True),
                        UserMemory.embedding.is_not(None),
                    )
                    .order_by(UserMemory.embedding.cosine_distance(embedding))
                    .limit(1)
                )
                existing_res = await db.execute(check_stmt)
                existing_memory = existing_res.scalar_one_or_none()

                if existing_memory and existing_memory.embedding:
                    # Calculate cosine similarity via dot product of unit vectors
                    similarity = sum(
                        a * b for a, b in zip(embedding, existing_memory.embedding, strict=False)
                    )

                    if similarity >= settings.memory_dedup_threshold:
                        # Conflict or update detected: supersede old memory
                        logger.info(
                            "Superseding memory (id=%s, sim=%.2f): '%s' -> '%s'",
                            existing_memory.id,
                            similarity,
                            existing_memory.content,
                            content,
                        )
                        existing_memory.is_active = False
                        existing_memory.updated_at = now

                # 3. Insert new memory record
                new_mem = UserMemory(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    user_id=user_id,
                    memory_type=mem_type,
                    content=content,
                    embedding=embedding,
                    importance=importance,
                    confidence=1.0,
                    source_conversation_id=source_conv_id,
                    source_message_id=source_msg_id,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(new_mem)
                saved.append(new_mem)

            except Exception as exc:
                logger.error("Error saving memory '%s': %s", content, exc)

        if saved:
            await db.commit()
            # Invalidate Redis cache for user
            await self.cache.invalidate_user_memories(user_id)

        return saved

    # ── 5. Incremental Conversation Summarization ─────────────────────────
    async def summarize_conversation_if_needed(
        self,
        db: AsyncSession,
        conv_id: uuid.UUID,
        tenant_id: str,
        user_id: str,
        api_key_override: str | None = None,
    ) -> str | None:
        """
        Check if conversation meets the message threshold and update running summary.

        Summarizes messages older than MAX_RECENT_MESSAGES and bumps summary_version.
        """
        try:
            # 1. Count total messages in conversation
            count_stmt = select(func.count(Message.id)).where(
                Message.conversation_id == conv_id,
                Message.tenant_id == tenant_id,
            )
            total_msgs = (await db.scalar(count_stmt)) or 0

            # If under threshold, no summary needed yet
            if total_msgs < settings.summary_message_threshold:
                return None

            # 2. Fetch conversation record
            conv_stmt = select(Conversation).where(
                Conversation.id == conv_id,
                Conversation.tenant_id == tenant_id,
            )
            conv = (await db.execute(conv_stmt)).scalar_one_or_none()
            if not conv:
                return None

            # 3. Retrieve messages that fall outside the recent window
            # i.e. messages older than the last MAX_RECENT_MESSAGES
            offset_limit = max(0, total_msgs - settings.max_recent_messages)
            if offset_limit <= 0:
                return conv.summary

            msgs_stmt = (
                select(Message)
                .where(
                    Message.conversation_id == conv_id,
                    Message.tenant_id == tenant_id,
                )
                .order_by(Message.created_at.asc())
                .limit(offset_limit)
            )
            older_msgs = (await db.execute(msgs_stmt)).scalars().all()
            if not older_msgs:
                return conv.summary

            formatted_new = "\n".join([f"{m.role.capitalize()}: {m.content}" for m in older_msgs])

            # 4. Generate updated summary with LLM
            prompt = CONVERSATION_SUMMARIZER_PROMPT.format(
                existing_summary=conv.summary or "No previous summary.",
                new_messages=formatted_new,
            )
            messages = [{"role": "user", "content": prompt}]

            new_summary = await self.llm.generate_response(
                messages=messages,
                temperature=0.2,
                max_tokens=600,
                api_key_override=api_key_override,
            )
            new_summary = new_summary.strip()

            # 5. Update conversation record
            conv.summary = new_summary
            conv.summary_version = (conv.summary_version or 0) + 1
            conv.updated_at = datetime.now(UTC)
            await db.commit()

            # 6. Update Redis cache
            await self.cache.set_summary(str(conv_id), new_summary, conv.summary_version)
            logger.info(
                "Updated conversation summary (conv=%s, version=%d)",
                conv_id,
                conv.summary_version,
            )
            return new_summary

        except Exception as exc:
            logger.warning("Error generating conversation summary for conv %s: %s", conv_id, exc)
            return None
