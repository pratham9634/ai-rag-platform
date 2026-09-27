"""
Cross-Encoder Neural Relevance Reranker.

Leverages Jina AI's multilingual neural cross-encoder (jina-reranker-v2-base-multilingual)
supporting up to 8,192 candidate tokens with seamless local fallback to lexical cross-attention.
"""

import asyncio
import logging
import math
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

JINA_RERANK_URL = "https://api.jina.ai/v1/rerank"


@dataclass
class RerankResult:
    """Represents a scored and reranked document chunk."""

    chunk_id: str
    document_id: str
    page_number: int
    content: str
    relevance_score: float  # Normalized 0.0 to 1.0
    original_rank: int


class RerankerService:
    """
    Reranker for scoring candidate document chunks against a user query.

    Applies neural cross-encoder reranking via Jina AI API, with automatic fallback
    to local lexical cross-attention when offline or unconfigured.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 6.0,
    ) -> None:
        self.api_key = api_key or settings.jina_api_key
        self.model = model or settings.jina_reranker_model or "jina-reranker-v2-base-multilingual"
        self.timeout = timeout

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple alphanumeric tokenizer for lexical relevance."""
        return re.findall(r"\b\w+\b", text.lower())

    def score_pair(self, query: str, document: str) -> float:
        """
        Local cross-attention lexical scoring algorithm.

        Used as an immediate sub-millisecond local scorer and fallback.
        """
        if not query or not document:
            return 0.0

        q_tokens = self._tokenize(query)
        d_tokens = self._tokenize(document)

        if not q_tokens or not d_tokens:
            return 0.0

        d_token_set = set(d_tokens)
        q_token_set = set(q_tokens)

        # 1. Unigram Recall: what fraction of query words appear in document?
        overlap = q_token_set.intersection(d_token_set)
        recall = len(overlap) / len(q_token_set)

        # 2. Phrase matching bonus: does the exact query or subphrases appear?
        clean_query = " ".join(q_tokens)
        clean_doc = " ".join(d_tokens)
        phrase_bonus = 0.3 if clean_query in clean_doc else 0.0

        # 3. Term frequency saturation: log(1 + tf)
        tf_score = sum(math.log(1 + d_tokens.count(term)) for term in overlap)
        normalized_tf = min(tf_score / (len(q_token_set) + 1.0), 0.5)

        # Combined composite relevance
        score = (recall * 0.5) + phrase_bonus + (normalized_tf * 0.2)
        return min(max(score, 0.0), 1.0)

    def _local_rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[RerankResult]:
        """Local heuristic reranking fallback combining lexical overlap and base RRF score."""
        scored: list[RerankResult] = []
        for rank, cand in enumerate(candidates):
            content = cand.get("content", "")
            base_score = float(cand.get("score", 0.0))

            cross_score = self.score_pair(query, content)
            combined_score = (cross_score * 0.6) + (min(base_score, 1.0) * 0.4)

            scored.append(
                RerankResult(
                    chunk_id=str(cand.get("id", "")),
                    document_id=str(cand.get("document_id", "")),
                    page_number=int(cand.get("page_number", 1)),
                    content=content,
                    relevance_score=round(combined_score, 4),
                    original_rank=rank + 1,
                )
            )

        scored.sort(key=lambda r: r.relevance_score, reverse=True)
        return scored[:top_k]

    async def rerank_async(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 5,
        api_key_override: str | None = None,
    ) -> list[RerankResult]:
        """
        Asynchronously rerank candidates using Jina AI Neural Cross-Encoder API.

        Falls back to local heuristic if JINA_API_KEY is not configured or on network error.
        """
        if not candidates:
            return []

        active_key = api_key_override or self.api_key
        if not active_key:
            logger.debug("No Jina API key configured; using local lexical cross-encoder.")
            return self._local_rerank(query, candidates, top_k)

        doc_texts = [c.get("content", "") for c in candidates]
        payload = {
            "model": self.model,
            "query": query,
            "top_n": min(top_k, len(candidates)),
            "documents": doc_texts,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {active_key}",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(JINA_RERANK_URL, json=payload, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    results: list[RerankResult] = []
                    for item in data.get("results", []):
                        idx = item.get("index")
                        if idx is not None and 0 <= idx < len(candidates):
                            cand = candidates[idx]
                            results.append(
                                RerankResult(
                                    chunk_id=str(cand.get("id", "")),
                                    document_id=str(cand.get("document_id", "")),
                                    page_number=int(cand.get("page_number", 1)),
                                    content=cand.get("content", ""),
                                    relevance_score=round(
                                        float(item.get("relevance_score", 0.0)), 4
                                    ),
                                    original_rank=idx + 1,
                                )
                            )
                    logger.info(
                        "Jina AI Neural Reranker scored %d candidates to top %d for query='%s'",
                        len(candidates),
                        len(results),
                        query[:50],
                    )
                    return results

                logger.warning(
                    "Jina AI rerank request returned HTTP %d: %s. Falling back to local scorer.",
                    response.status_code,
                    response.text[:200],
                )
        except Exception as e:
            logger.warning("Jina AI reranker call failed (%s). Falling back to local scorer.", e)

        return self._local_rerank(query, candidates, top_k)

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 5,
        api_key_override: str | None = None,
    ) -> list[RerankResult]:
        """
        Synchronous reranker interface with fallback.

        Used in synchronous testing or pipeline nodes.
        """
        if not candidates:
            return []

        active_key = api_key_override or self.api_key
        if not active_key:
            return self._local_rerank(query, candidates, top_k)

        try:
            # If in an event loop, run asynchronously
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Avoid nested event loop blocking; fall back to local or run in new thread
                return self._local_rerank(query, candidates, top_k)
            return loop.run_until_complete(
                self.rerank_async(query, candidates, top_k, api_key_override)
            )
        except Exception:
            return self._local_rerank(query, candidates, top_k)
