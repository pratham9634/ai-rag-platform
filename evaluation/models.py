"""
Evaluation Domain Models & Schemas.

Defines extensible Pydantic v2 schemas for benchmark items, datasets,
metric evaluation outputs, latency distributions, and evaluation summaries.
Designed for clean extensibility to support custom metrics and benchmarks.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class QuestionCategory(StrEnum):
    """Categorization of evaluation benchmark questions."""

    EASY = "easy"
    MEDIUM = "medium"
    DIFFICULT = "difficult"
    MULTI_HOP = "multi_hop"
    UNANSWERABLE = "unanswerable"
    ADVERSARIAL = "adversarial"
    CUSTOM = "custom"


class MetricType(StrEnum):
    """Classification of benchmark metric types."""

    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    SECURITY = "security"
    LATENCY = "latency"
    CUSTOM = "custom"


class BenchmarkItem(BaseModel):
    """Individual golden evaluation test case."""

    id: str = Field(..., description="Unique test case identifier (e.g. 'q01')")
    category: QuestionCategory = Field(..., description="Difficulty/type category")
    query: str = Field(..., description="Natural language user query")
    expected_pages: list[int] = Field(
        default_factory=list,
        description="Ground-truth page numbers containing the facts",
    )
    expected_keywords: list[str] = Field(
        default_factory=list,
        description="Essential keywords/terms expected in the answer",
    )
    reference_answer: str = Field(
        ...,
        description="Authoritative reference ground-truth answer",
    )
    is_unanswerable: bool = Field(
        default=False,
        description="True if the question cannot be answered from the document",
    )
    is_adversarial: bool = Field(
        default=False,
        description="True if query is a prompt injection or credential attack",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata for domain-specific attributes",
    )


class BenchmarkDataset(BaseModel):
    """Collection of benchmark evaluation items."""

    version: str = "1.0.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    description: str
    document_name: str
    items: list[BenchmarkItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalMetrics(BaseModel):
    """Quantitative retrieval effectiveness scores."""

    recall_at_3: float = Field(0.0, ge=0.0, le=1.0)
    recall_at_5: float = Field(0.0, ge=0.0, le=1.0)
    mrr: float = Field(0.0, ge=0.0, le=1.0, description="Mean Reciprocal Rank")
    retrieved_pages: list[int] = Field(default_factory=list)
    custom_scores: dict[str, float] = Field(default_factory=dict)


class GenerationMetrics(BaseModel):
    """Qualitative and quantitative generation scores."""

    faithfulness: float = Field(0.0, ge=0.0, le=1.0, description="Groundedness in context")
    answer_relevance: float = Field(
        0.0, ge=0.0, le=1.0, description="Semantic alignment with query"
    )
    citation_accuracy: float = Field(
        0.0, ge=0.0, le=1.0, description="Precision of cited page numbers"
    )
    cited_pages: list[int] = Field(default_factory=list)
    admitted_ignorance: bool = Field(False, description="Properly admitted lack of context")
    attack_neutralized: bool = Field(False, description="Safely rejected prompt injection")
    explanation: str = Field("", description="LLM judge reasoning")
    custom_scores: dict[str, float] = Field(default_factory=dict)


class LatencyStats(BaseModel):
    """Latency distribution percentiles in milliseconds."""

    p50_ms: float = 0.0
    p90_ms: float = 0.0
    p99_ms: float = 0.0
    mean_ms: float = 0.0


class BenchmarkItemResult(BaseModel):
    """Evaluation outcome for a single benchmark question."""

    item: BenchmarkItem
    dense_retrieval: RetrievalMetrics
    hybrid_retrieval: RetrievalMetrics
    reranked_retrieval: RetrievalMetrics
    generation: GenerationMetrics
    response_text: str
    total_latency_ms: float
    custom_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Dynamic scores computed by extensible custom metric plugins",
    )


class EvaluationReportSummary(BaseModel):
    """Consolidated summary of an entire benchmark evaluation run."""

    run_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_questions: int
    categories: dict[str, int]
    retrieval_comparison: dict[str, dict[str, float]]
    generation_summary: dict[str, float]
    latency_summary: LatencyStats
    details: list[BenchmarkItemResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationConfig(BaseModel):
    """Declarative runtime configuration for evaluation runs."""

    tenant_id: str = "eval-tenant"
    limit: int | None = None
    concurrency: int = Field(1, ge=1, le=10, description="Max parallel evaluation tasks")
    top_k: int = 5
    enable_llm_judge: bool = True
    report_output_path: str = "docs/evaluation-report.md"
    json_output_path: str = "evaluation/results.json"
    custom_params: dict[str, Any] = Field(default_factory=dict)
