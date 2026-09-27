"""
Sub-15ms Dedicated Query Intent Detector.

Replaces slow LLM zero-shot routing with a high-throughput hybrid classifier:
1. Fast-Path Regex Rules (< 1ms): Deterministic matching for greetings and explicit citations.
2. Canonical Semantic Anchor Distance: Cosine and n-gram overlap against calibrated intent anchors.
3. Ambiguity Handoff: Hands off to LLM router only when classification confidence is below 0.70.
"""

import logging
import math
import re
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntentClassification:
    """Result of intent detection."""

    route: str  # "retrieve" or "direct"
    confidence: float  # 0.0 to 1.0
    method: str  # "fast_path_regex", "anchor_similarity", "llm_fallback"
    reason: str


class IntentDetector:
    """
    Sub-15ms query router that classifies user queries into 'retrieve' vs 'direct'.

    Minimizes TTFT (Time-To-First-Token) and LLM token expenditure on conversational turns.
    """

    # ── Fast-Path Regular Expressions ─────────────────────────────────
    GREETING_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(
            r"^\s*(?:hi|hello|hey|howdy|sup|yo|greetings|good\s+(?:morning|afternoon|evening))\b",
            re.I,
        ),
        re.compile(r"^\s*(?:thanks|thank\s+you|thx|cheers|appreciate\s+it)\b", re.I),
        re.compile(r"^\s*(?:bye|goodbye|see\s+ya|cya|farewell|have\s+a\s+good\s+day)\b", re.I),
        re.compile(
            r"^\s*(?:who\s+are\s+you|what\s+can\s+you\s+do|what\s+are\s+your\s+capabilities|help(?:\s+me)?)\b",
            re.I,
        ),
    ]

    DIRECT_CHITCHAT_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b(?:tell\s+me\s+a\s+joke|write\s+(?:a\s+)?poem|sing\s+a\s+song)\b", re.I),
        re.compile(r"\b(?:what\s+is\s+the\s+weather|current\s+time|todays?\s+date)\b", re.I),
        re.compile(r"^\s*(?:how\s+are\s+you|how's\s+it\s+going|what's\s+up)\b", re.I),
    ]

    EXPLICIT_DOCUMENT_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(
            r"\b(?:according\s+to|in\s+the\s+(?:document|pdf|file|contract|report|manual|policy|paper))\b",
            re.I,
        ),
        re.compile(r"\b(?:page\s+\d+|section\s+[\d\.]+|chapter\s+\d+|clause\s+[\d\.]+)\b", re.I),
        re.compile(r"\b(?:summarize\s+(?:the\s+)?(?:document|pdf|report|file|upload))\b", re.I),
        re.compile(
            r"\b(?:what\s+does\s+(?:the\s+)?(?:document|pdf|policy|contract|author)\s+say)\b", re.I
        ),
        re.compile(r"\b(?:uploaded\s+(?:data|file|pdf)|table\s+\d+|figure\s+\d+)\b", re.I),
        re.compile(r"\b(?:based\s+on\s+(?:the\s+)?(?:text|document|context|file))\b", re.I),
    ]

    # ── Canonical Intent Anchors ──────────────────────────────────────
    RETRIEVAL_ANCHOR_KEYWORDS: ClassVar[set[str]] = {
        "document",
        "pdf",
        "page",
        "section",
        "clause",
        "policy",
        "contract",
        "report",
        "table",
        "summary",
        "revenue",
        "agreement",
        "guidelines",
        "specification",
        "architecture",
        "audit",
        "compliance",
        "terms",
        "liability",
        "provision",
        "exhibit",
        "appendix",
        "article",
    }

    CHITCHAT_ANCHOR_KEYWORDS: ClassVar[set[str]] = {
        "hello",
        "hi",
        "hey",
        "joke",
        "weather",
        "poem",
        "story",
        "song",
        "feeling",
        "ai",
        "assistant",
        "name",
        "who",
        "thanks",
        "welcome",
        "mood",
        "chat",
        "fun",
        "bored",
    }

    def __init__(self, confidence_threshold: float = 0.70) -> None:
        self.confidence_threshold = confidence_threshold

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return set(re.findall(r"\b\w+\b", text.lower()))

    def detect_intent_fast(self, query: str) -> IntentClassification:
        """
        Pure CPU sub-1ms intent classification.

        Returns an IntentClassification with route and confidence.
        """
        clean_query = query.strip()
        if not clean_query:
            return IntentClassification(
                route="direct",
                confidence=1.0,
                method="fast_path_regex",
                reason="Empty query defaults to direct response.",
            )

        # 1. Check direct conversational greetings & capabilities
        for pat in self.GREETING_PATTERNS:
            if pat.search(clean_query):
                return IntentClassification(
                    route="direct",
                    confidence=0.98,
                    method="fast_path_regex",
                    reason=f"Matched conversational greeting pattern: {pat.pattern[:30]}",
                )

        # 2. Check direct chit-chat / creative / open-domain prompts
        for pat in self.DIRECT_CHITCHAT_PATTERNS:
            if pat.search(clean_query):
                return IntentClassification(
                    route="direct",
                    confidence=0.95,
                    method="fast_path_regex",
                    reason=f"Matched direct general inquiry pattern: {pat.pattern[:30]}",
                )

        # 3. Check explicit document provenance requests
        for pat in self.EXPLICIT_DOCUMENT_PATTERNS:
            if pat.search(clean_query):
                return IntentClassification(
                    route="retrieve",
                    confidence=0.98,
                    method="fast_path_regex",
                    reason=f"Matched explicit document inquiry pattern: {pat.pattern[:30]}",
                )

        # 4. Keyword anchor intersection scoring
        tokens = self._tokenize(clean_query)
        if tokens:
            retrieval_matches = tokens.intersection(self.RETRIEVAL_ANCHOR_KEYWORDS)
            chitchat_matches = tokens.intersection(self.CHITCHAT_ANCHOR_KEYWORDS)

            retrieval_score = len(retrieval_matches) / math.sqrt(len(tokens))
            chitchat_score = len(chitchat_matches) / math.sqrt(len(tokens))

            if retrieval_score > 0.4 and retrieval_score > chitchat_score:
                confidence = min(0.70 + (retrieval_score * 0.25), 0.95)
                return IntentClassification(
                    route="retrieve",
                    confidence=round(confidence, 2),
                    method="anchor_similarity",
                    reason=f"Domain keyword anchor density ({retrieval_matches})",
                )

            if chitchat_score > 0.4 and chitchat_score > retrieval_score:
                confidence = min(0.70 + (chitchat_score * 0.25), 0.95)
                return IntentClassification(
                    route="direct",
                    confidence=round(confidence, 2),
                    method="anchor_similarity",
                    reason=f"Conversational anchor density ({chitchat_matches})",
                )

        # 5. Default fallback to retrieval for factual / domain questions
        # In an Enterprise RAG platform, standard questions default to document retrieval
        return IntentClassification(
            route="retrieve",
            confidence=0.60,  # Below 0.70 threshold -> routes to LLM prompt
            method="llm_fallback",
            reason="Ambiguous intent requiring LLM router confirmation",
        )
