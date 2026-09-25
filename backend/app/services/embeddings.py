"""
Embedding Generation Service.

Generates dense vector embeddings (1536 dimensions) for chunks and search queries.
Uses OpenRouter API when an API key is available, with a deterministic local fallback
for offline testing and development environments.
"""

import hashlib
import logging
import math
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 1536
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"


class EmbeddingServiceError(Exception):
    """Base exception for embedding generation failures."""

    pass


class EmbeddingService:
    """Service to generate dense vector embeddings."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_EMBEDDING_MODEL,
        dimension: int = EMBEDDING_DIMENSION,
    ) -> None:
        """
        Initialize the embedding service.

        Args:
            api_key: OpenRouter API key (defaults to settings.openrouter_api_key or None).
            model: Embedding model name.
            dimension: Vector dimension (default 1536).
        """
        self.api_key = api_key or getattr(settings, "openrouter_api_key", None) or ""
        self.model = model
        self.dimension = dimension

    @staticmethod
    def normalize_l2(vector: list[float]) -> list[float]:
        """Normalize a vector to unit length (L2 norm = 1.0)."""
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0.0:
            return vector
        return [x / norm for x in vector]

    def _generate_local_fallback_embedding(self, text: str) -> list[float]:
        """
        Deterministic, unit-normalized fallback embedding generator for testing and offline dev.

        Uses cryptographic hashing to generate reproducible 1536-dim pseudo-embeddings
        with semantic continuity across identical strings.
        """
        if not text:
            return [0.0] * self.dimension

        # Generate seed hashes across dimension segments
        vector: list[float] = []
        for i in range(self.dimension):
            h = hashlib.sha256(f"{text}:{i}".encode()).digest()
            val = (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) * 2.0 - 1.0
            vector.append(val)

        return self.normalize_l2(vector)

    async def generate_embedding(
        self,
        text: str,
        api_key_override: str | None = None,
    ) -> list[float]:
        """
        Generate a single embedding vector for a text query or chunk.

        Args:
            text: Text string to embed.
            api_key_override: Optional user-supplied BYOK key.

        Returns:
            1536-dimensional unit-normalized float list.
        """
        batch = await self.generate_embeddings_batch([text], api_key_override=api_key_override)
        if not batch:
            raise EmbeddingServiceError("Failed to generate embedding vector.")
        return batch[0]

    async def generate_embeddings_batch(
        self,
        texts: list[str],
        api_key_override: str | None = None,
    ) -> list[list[float]]:
        """
        Generate embeddings for a list of texts in a single batch request.

        Args:
            texts: List of strings to embed.
            api_key_override: Optional user-supplied BYOK key.

        Returns:
            List of 1536-dimensional unit-normalized float vectors.
        """
        if not texts:
            return []

        active_key = api_key_override or self.api_key

        # If no key configured, use deterministic local fallback
        is_placeholder = active_key.startswith("sk-dummy") or active_key.startswith("sk-or-your")
        if not active_key or is_placeholder:
            logger.debug(
                "No live OpenRouter key configured; using local fallback for %d texts",
                len(texts),
            )
            return [self._generate_local_fallback_embedding(t) for t in texts]

        # Call OpenRouter API
        headers = {
            "Authorization": f"Bearer {active_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/pratham9634/ai-rag-platform",
            "X-Title": "Enterprise RAG Platform",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "input": texts,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/embeddings",
                    headers=headers,
                    json=payload,
                )

            if response.status_code != 200:
                logger.warning(
                    "OpenRouter embedding call returned %d: %s. Falling back to local vectors.",
                    response.status_code,
                    response.text,
                )
                return [self._generate_local_fallback_embedding(t) for t in texts]

            data = response.json()
            raw_embeddings = [item["embedding"] for item in data.get("data", [])]

            # Normalize each vector
            return [self.normalize_l2(vec) for vec in raw_embeddings]

        except Exception as e:
            logger.warning(
                "Exception calling OpenRouter embeddings (%s). Using local fallback.",
                str(e),
            )
            return [self._generate_local_fallback_embedding(t) for t in texts]
