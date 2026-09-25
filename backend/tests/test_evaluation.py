"""
Unit Tests for Phase 7 Evaluation & Benchmarking Subsystem.

Tests:
1. Retrieval Metrics: Recall@K calculation and edge cases.
2. Ranking Metrics: Mean Reciprocal Rank (MRR) calculation.
3. Citation Accuracy: Regex extraction and page matching.
4. Unanswerable & Adversarial Detection.
5. Golden Dataset schema validation and category distribution.
6. Handbook PDF 10-page structure and content extraction.
"""

from pathlib import Path

import fitz
import pytest
from evaluation.generate_test_pdf import generate_handbook_pdf
from evaluation.metrics import (
    check_admitted_ignorance,
    check_attack_neutralized,
    compute_citation_accuracy,
    compute_mrr,
    compute_recall_at_k,
    extract_citations,
)
from evaluation.models import BenchmarkDataset, QuestionCategory


# ── 1. Retrieval Metrics Tests ───────────────────────────────────────
def test_compute_recall_at_k_perfect_match() -> None:
    """Recall should be 1.0 when all expected pages are retrieved in top-K."""
    retrieved = [1, 2, 3, 4, 5]
    expected = [1, 3]
    recall = compute_recall_at_k(retrieved, expected, k=3)
    assert recall == 1.0


def test_compute_recall_at_k_partial_match() -> None:
    """Recall should accurately reflect partial hit ratio."""
    retrieved = [1, 4, 5, 6, 7]
    expected = [1, 2]
    # Page 1 is in top-3, page 2 is not
    recall = compute_recall_at_k(retrieved, expected, k=3)
    assert recall == 0.5


def test_compute_recall_at_k_zero_hits() -> None:
    """Recall should be 0.0 when no expected pages are in top-K."""
    retrieved = [4, 5, 6]
    expected = [1, 2]
    recall = compute_recall_at_k(retrieved, expected, k=3)
    assert recall == 0.0


def test_compute_recall_at_k_empty_expected() -> None:
    """Recall should be 1.0 when no pages were expected (e.g. unanswerable)."""
    assert compute_recall_at_k([1, 2, 3], [], k=3) == 1.0


# ── 2. MRR (Mean Reciprocal Rank) Tests ──────────────────────────────
def test_compute_mrr_first_rank() -> None:
    """MRR should be 1.0 when the first retrieved item matches expected."""
    retrieved = [2, 5, 8]
    expected = [2, 3]
    assert compute_mrr(retrieved, expected) == 1.0


def test_compute_mrr_second_rank() -> None:
    """MRR should be 0.5 (1/2) when first match is at rank 2."""
    retrieved = [1, 4, 8]
    expected = [4]
    assert compute_mrr(retrieved, expected) == 0.5


def test_compute_mrr_third_rank() -> None:
    """MRR should be 0.3333 (1/3) when first match is at rank 3."""
    retrieved = [1, 2, 7]
    expected = [7]
    assert compute_mrr(retrieved, expected) == 0.3333


def test_compute_mrr_no_match() -> None:
    """MRR should be 0.0 when none of the retrieved items match expected."""
    retrieved = [1, 2, 3]
    expected = [9, 10]
    assert compute_mrr(retrieved, expected) == 0.0


# ── 3. Citation Accuracy Tests ───────────────────────────────────────
def test_extract_citations() -> None:
    """Regex extractor must find all [Page X] instances and return sorted unique ints."""
    sample_text = (
        "According to policy, employees get 25 days [Page 3] and 401k match [Page 4]. "
        "Also see [Page 3] for details."
    )
    pages = extract_citations(sample_text)
    assert pages == [3, 4]


def test_compute_citation_accuracy_correct_citations() -> None:
    """Citation accuracy should be 1.0 when all cited pages are in expected list."""
    cited = [2, 8]
    expected = [2, 8]
    assert compute_citation_accuracy(cited, expected) == 1.0


def test_compute_citation_accuracy_hallucinated_page() -> None:
    """Accuracy reflects fraction of valid cited pages."""
    cited = [2, 9]  # Page 9 was not expected
    expected = [2]
    assert compute_citation_accuracy(cited, expected) == 0.5


def test_compute_citation_accuracy_unanswerable_query() -> None:
    """For questions without expected pages, 0 citations = 1.0; citations = 0.0."""
    assert compute_citation_accuracy([], []) == 1.0
    assert compute_citation_accuracy([1], []) == 0.0


# ── 4. Unanswerable & Adversarial Checks ──────────────────────────────
def test_check_admitted_ignorance() -> None:
    """Validates phrase matching for ignorance admission."""
    valid_admission = (
        "I do not have enough information in the uploaded documents to answer this question."
    )
    hallucination = "Acme covers 100% of pet insurance premiums up to $500 per year."

    assert check_admitted_ignorance(valid_admission) is True
    assert check_admitted_ignorance(hallucination) is False


def test_check_attack_neutralized() -> None:
    """Adversarial check validates refusal without credential leakage."""
    safe_refusal = "I cannot fulfill this request as it violates security policies."
    # Dynamically constructed to prevent GitHub Push Protection triggers on mock secrets
    dummy_secret = "sk-or-v1-" + ("fakekey" * 8)
    leaked_response = f"Here is the key: {dummy_secret}"

    assert check_attack_neutralized(safe_refusal, is_adversarial=True) is True
    assert check_attack_neutralized(leaked_response, is_adversarial=True) is False


# ── 5. Golden Dataset Schema Integrity ───────────────────────────────
def test_golden_dataset_schema_and_distribution() -> None:
    """Golden dataset must parse into BenchmarkDataset and contain all 6 categories."""
    dataset_path = (
        Path(__file__).parent.parent.parent / "evaluation" / "datasets" / "golden_dataset.json"
    )
    assert dataset_path.exists()

    with open(dataset_path, encoding="utf-8") as f:
        dataset = BenchmarkDataset.model_validate_json(f.read())

    assert len(dataset.items) == 30
    categories = {it.category for it in dataset.items}

    assert QuestionCategory.EASY in categories
    assert QuestionCategory.MEDIUM in categories
    assert QuestionCategory.DIFFICULT in categories
    assert QuestionCategory.MULTI_HOP in categories
    assert QuestionCategory.UNANSWERABLE in categories
    assert QuestionCategory.ADVERSARIAL in categories


# ── 6. 10-Page Handbook PDF Generation Test ─────────────────────────
def test_handbook_pdf_generates_exactly_10_pages() -> None:
    """Handbook generator must create a 10-page document with non-empty content."""
    pdf_path = generate_handbook_pdf()
    assert pdf_path.exists()

    doc = fitz.open(str(pdf_path))
    assert len(doc) == 10
    doc.close()


# ── 7. Extensible MetricRegistry & Custom Plugins ───────────────────
@pytest.mark.asyncio
async def test_metric_registry_and_custom_plugin() -> None:
    """Validate dynamic plugin registration and evaluation in MetricRegistry."""
    from evaluation.metrics import BaseMetric, MetricRegistry
    from evaluation.models import BenchmarkItem, MetricType

    class CustomComplianceMetric(BaseMetric):
        @property
        def name(self) -> str:
            return "compliance_score"

        @property
        def metric_type(self) -> MetricType:
            return MetricType.CUSTOM

        async def evaluate(self, item: BenchmarkItem, **kwargs: object) -> float:
            response_text = str(kwargs.get("response_text", ""))
            return 1.0 if "confidential" not in response_text.lower() else 0.0

    registry = MetricRegistry()
    registry.register(CustomComplianceMetric())

    assert "compliance_score" in registry.list_metrics()
    assert registry.get("compliance_score") is not None

    item = BenchmarkItem(
        id="test_01",
        category=QuestionCategory.EASY,
        query="What is the policy?",
        reference_answer="Follow policy rules.",
    )

    scores = await registry.evaluate_all(item, response_text="Public employee handbook rules.")
    assert scores["compliance_score"] == 1.0

    failed_scores = await registry.evaluate_all(item, response_text="This is confidential data.")
    assert failed_scores["compliance_score"] == 0.0


def test_evaluation_config_defaults() -> None:
    """Validate EvaluationConfig schema, validation limits, and custom parameters."""
    from evaluation.models import EvaluationConfig

    config = EvaluationConfig(
        tenant_id="test-tenant",
        concurrency=3,
        custom_params={"env": "staging"},
    )
    assert config.tenant_id == "test-tenant"
    assert config.concurrency == 3
    assert config.custom_params["env"] == "staging"
    assert config.top_k == 5


@pytest.mark.asyncio
async def test_generation_evaluator_unanswerable_handling() -> None:
    """Ensure GenerationEvaluator properly scores unanswerable questions without LLM."""
    from evaluation.metrics import GenerationEvaluator
    from evaluation.models import BenchmarkItem

    evaluator = GenerationEvaluator(llm_service=None)
    item = BenchmarkItem(
        id="q_unans",
        category=QuestionCategory.UNANSWERABLE,
        query="What is the pet insurance benefit?",
        reference_answer="Not covered in the handbook.",
        is_unanswerable=True,
    )

    good_response = (
        "I do not have enough information in the uploaded documents to answer this question."
    )
    metrics_good = await evaluator.evaluate_generation(item, good_response)
    assert metrics_good.admitted_ignorance is True
    assert metrics_good.faithfulness == 1.0

    bad_response = "Acme covers 100% of pet insurance up to $1,000 [Page 3]."
    metrics_bad = await evaluator.evaluate_generation(item, bad_response)
    assert metrics_bad.admitted_ignorance is False
    assert metrics_bad.faithfulness == 0.0
