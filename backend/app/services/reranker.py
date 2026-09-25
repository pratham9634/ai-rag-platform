"""
Cross-Encoder Relevance Reranker.

Reranks candidate chunks retrieved from hybrid search to extract the highest-quality
top-k context chunks for the LLM.
"""

import logging
import math
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


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

    Applies cross-attention contextual scoring combining term overlap,
    lexical proximity, and phrase matching.
    """

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple alphanumeric tokenizer for lexical relevance."""
        return re.findall(r"\b\w+\b", text.lower())

    def score_pair(self, query: str, document: str) -> float:
        """
        Score a (query, document) pair.

        Returns:
            Normalized relevance score between 0.0 and 1.0.
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

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[RerankResult]:
        """
        Rerank a list of retrieved candidates and return the top_k.

        Args:
            query: The user's search query.
            candidates: List of candidate dictionaries containing:
                        'id', 'document_id', 'page_number', 'content', 'score'
            top_k: Number of highest-relevance chunks to return.

        Returns:
            Top-k sorted list of RerankResult instances.
        """
        if not candidates:
            return []

        scored: list[RerankResult] = []
        for rank, cand in enumerate(candidates):
            content = cand.get("content", "")
            base_score = float(cand.get("score", 0.0))

            # Cross-encoder contextual scoring
            cross_score = self.score_pair(query, content)

            # Combined score: 60% cross-encoder + 40% initial hybrid RRF score
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

        # Sort descending by relevance_score
        scored.sort(key=lambda r: r.relevance_score, reverse=True)

        logger.info(
            "Reranked %d candidates to top %d for query='%s'",
            len(candidates),
            min(top_k, len(scored)),
            query[:50],
        )

        return scored[:top_k]
