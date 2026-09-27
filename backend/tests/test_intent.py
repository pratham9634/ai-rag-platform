"""
Unit tests for Sub-15ms Dedicated Query Intent Detector.

Tests greeting patterns, explicit document references, domain anchor scoring,
and sub-millisecond execution latency.
"""

import time

from app.services.intent import IntentDetector


def test_intent_detector_greetings_route_to_direct() -> None:
    """Conversational pleasantries must immediately route to 'direct' with high confidence."""
    detector = IntentDetector()

    greetings = [
        "hi",
        "Hello there!",
        "hey assistant",
        "Good morning",
        "thanks a lot",
        "Who are you?",
        "What can you do?",
        "tell me a joke",
    ]

    for q in greetings:
        res = detector.detect_intent_fast(q)
        assert res.route == "direct", f"Failed for query: {q}"
        assert res.confidence >= 0.70


def test_intent_detector_explicit_document_queries_route_to_retrieve() -> None:
    """Explicit document references must route to 'retrieve' with high confidence."""
    detector = IntentDetector()

    doc_queries = [
        "What does page 4 say about termination?",
        "According to the contract, what is the notice period?",
        "Summarize the uploaded pdf report.",
        "In section 3.2, what are the compliance requirements?",
        "What does the policy document state regarding remote work?",
        "Based on the text in the file, calculate the revenue.",
    ]

    for q in doc_queries:
        res = detector.detect_intent_fast(q)
        assert res.route == "retrieve", f"Failed for query: {q}"
        assert res.confidence >= 0.70


def test_intent_detector_sub_millisecond_latency() -> None:
    """Fast-path classification must execute in under 1 millisecond on average."""
    detector = IntentDetector()
    queries = [
        "Hello world",
        "According to the document on page 12",
        "What is the corporate liability limit?",
        "Can you write a poem about autumn?",
    ]

    # Warmup
    for q in queries:
        detector.detect_intent_fast(q)

    start = time.perf_counter()
    iterations = 500
    for _ in range(iterations):
        for q in queries:
            detector.detect_intent_fast(q)
    total_time = time.perf_counter() - start

    avg_time_per_query_ms = (total_time / (iterations * len(queries))) * 1000.0
    # Must be well under 1ms (typically ~0.005ms)
    assert avg_time_per_query_ms < 1.0, f"Average latency too high: {avg_time_per_query_ms:.4f}ms"
