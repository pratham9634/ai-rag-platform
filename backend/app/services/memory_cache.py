"""
Persistent Memory & Conversation Redis Cache Service.

Provides fast distributed caching for:
1. Recent messages per conversation thread
2. Conversation summaries & version tracking
3. User long-term memories
4. Cache invalidation on new turn persistence

Resilience Guarantee:
PostgreSQL remains the source of truth. Every Redis operation is wrapped
in safe exception handlers. If Redis is down, unreachable, or unconfigured,
the chatbot continues smoothly using direct database queries without degradation.
"""

import json
import logging
from typing import Any

from app.services.redis_client import get_redis_client

logger = logging.getLogger(__name__)

DEFAULT_CONV_TTL_SECONDS = 3600  # 1 hour
DEFAULT_MEMORY_TTL_SECONDS = 600  # 10 minutes


class MemoryCacheService:
    """Manages Redis caching for conversation context and user memories."""

    @staticmethod
    def _conv_recent_key(conv_id: str) -> str:
        return f"mem:conv:{conv_id}:recent"

    @staticmethod
    def _conv_summary_key(conv_id: str) -> str:
        return f"mem:conv:{conv_id}:summary"

    @staticmethod
    def _user_memories_key(user_id: str) -> str:
        return f"mem:user:{user_id}:active"

    async def get_recent_messages(self, conv_id: str) -> list[dict[str, Any]] | None:
        """
        Retrieve cached recent messages for a conversation thread.

        Returns None if cache miss or Redis error.
        """
        client = get_redis_client()
        if client is None:
            return None

        try:
            raw = await client.get(self._conv_recent_key(conv_id))
            if not raw:
                return None
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            return None
        except Exception as exc:
            logger.warning("Redis read error for recent messages (conv=%s): %s", conv_id, exc)
            return None

    async def set_recent_messages(
        self,
        conv_id: str,
        messages: list[dict[str, Any]],
        ttl: int = DEFAULT_CONV_TTL_SECONDS,
    ) -> None:
        """Cache recent messages for a conversation thread."""
        client = get_redis_client()
        if client is None:
            return

        try:
            serialized = json.dumps(messages)
            await client.setex(self._conv_recent_key(conv_id), ttl, serialized)
        except Exception as exc:
            logger.warning("Redis write error for recent messages (conv=%s): %s", conv_id, exc)

    async def invalidate_recent_messages(self, conv_id: str) -> None:
        """Invalidate cached recent messages upon new turn insertion."""
        client = get_redis_client()
        if client is None:
            return

        try:
            await client.delete(self._conv_recent_key(conv_id))
        except Exception as exc:
            logger.warning("Redis delete error for recent messages (conv=%s): %s", conv_id, exc)

    async def get_summary(self, conv_id: str) -> tuple[str | None, int] | None:
        """
        Retrieve cached running summary and its version.

        Returns None on cache miss, or (summary_text, summary_version).
        """
        client = get_redis_client()
        if client is None:
            return None

        try:
            raw = await client.get(self._conv_summary_key(conv_id))
            if not raw:
                return None
            data = json.loads(raw)
            if isinstance(data, dict):
                return data.get("summary"), int(data.get("version", 0))
            return None
        except Exception as exc:
            logger.warning("Redis read error for summary (conv=%s): %s", conv_id, exc)
            return None

    async def set_summary(
        self,
        conv_id: str,
        summary: str,
        version: int,
        ttl: int = DEFAULT_CONV_TTL_SECONDS,
    ) -> None:
        """Cache conversation summary with version."""
        client = get_redis_client()
        if client is None:
            return

        try:
            payload = json.dumps({"summary": summary, "version": version})
            await client.setex(self._conv_summary_key(conv_id), ttl, payload)
        except Exception as exc:
            logger.warning("Redis write error for summary (conv=%s): %s", conv_id, exc)

    async def invalidate_summary(self, conv_id: str) -> None:
        """Invalidate cached summary when a new summary is compiled."""
        client = get_redis_client()
        if client is None:
            return

        try:
            await client.delete(self._conv_summary_key(conv_id))
        except Exception as exc:
            logger.warning("Redis delete error for summary (conv=%s): %s", conv_id, exc)

    async def get_user_memories(self, user_id: str) -> list[dict[str, Any]] | None:
        """
        Retrieve cached active long-term memories for a user.

        Returns None on cache miss or error.
        """
        client = get_redis_client()
        if client is None:
            return None

        try:
            raw = await client.get(self._user_memories_key(user_id))
            if not raw:
                return None
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            return None
        except Exception as exc:
            logger.warning("Redis read error for user memories (user=%s): %s", user_id, exc)
            return None

    async def set_user_memories(
        self,
        user_id: str,
        memories: list[dict[str, Any]],
        ttl: int = DEFAULT_MEMORY_TTL_SECONDS,
    ) -> None:
        """Cache active long-term memories for a user."""
        client = get_redis_client()
        if client is None:
            return

        try:
            serialized = json.dumps(memories)
            await client.setex(self._user_memories_key(user_id), ttl, serialized)
        except Exception as exc:
            logger.warning("Redis write error for user memories (user=%s): %s", user_id, exc)

    async def invalidate_user_memories(self, user_id: str) -> None:
        """Invalidate cached user memories when a memory is updated or added."""
        client = get_redis_client()
        if client is None:
            return

        try:
            await client.delete(self._user_memories_key(user_id))
        except Exception as exc:
            logger.warning("Redis delete error for user memories (user=%s): %s", user_id, exc)
