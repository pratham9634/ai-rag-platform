"""
Evaluation CLI Runner.

Executes the automated benchmark evaluation suite across the 10-page handbook
and 30-question golden dataset, outputting quantitative metrics and the formal report.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.database.session import async_session_factory

from evaluation.evaluator import EvaluationEngine, format_markdown_report
from evaluation.models import EvaluationConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("eval_runner")

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_REPORT_PATH = PROJECT_ROOT / "docs" / "evaluation-report.md"
DEFAULT_JSON_PATH = Path(__file__).parent / "results.json"
DEFAULT_DATASET = Path(__file__).parent / "datasets" / "golden_dataset.json"
DEFAULT_DOCUMENT = Path(__file__).parent / "datasets" / "acme_employee_handbook.pdf"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Enterprise RAG Evaluation Runner")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of evaluation questions (default: all 30 questions)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of concurrent evaluation queries (default: 1)",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to golden dataset JSON",
    )
    parser.add_argument(
        "--document",
        type=Path,
        default=DEFAULT_DOCUMENT,
        help="Path to benchmark PDF document",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Destination path for Markdown evaluation report",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help="Destination path for JSON benchmark results",
    )
    parser.add_argument(
        "--tenant",
        type=str,
        default="eval-tenant",
        help="Tenant ID for benchmark data isolation",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Optional OpenRouter API key override",
    )

    args = parser.parse_args()

    if not async_session_factory:
        logger.error("DATABASE_URL is not configured. Evaluation cannot proceed.")
        return

    logger.info("Initializing Enterprise RAG Evaluation...")
    logger.info("Target Document: %s", args.document.name)
    logger.info("Target Dataset: %s", args.dataset.name)
    logger.info("Tenant ID: %s", args.tenant)
    logger.info("Concurrency: %d", args.concurrency)

    config = EvaluationConfig(
        tenant_id=args.tenant,
        limit=args.limit,
        concurrency=args.concurrency,
        report_output_path=str(args.report_out),
        json_output_path=str(args.json_out),
    )

    async with async_session_factory() as db:
        engine = EvaluationEngine(
            db=db,
            tenant_id=args.tenant,
            dataset_path=args.dataset,
            document_path=args.document,
            config=config,
        )
        summary = await engine.run_full_suite(
            limit=args.limit,
            api_key_override=args.api_key,
        )

    # 1. Save JSON raw results
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(mode="json"), f, indent=2)
    logger.info("Raw benchmark results saved to: %s", args.json_out)

    # 2. Generate and save Markdown Report
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    report_md = format_markdown_report(summary)
    with open(args.report_out, "w", encoding="utf-8") as f:
        f.write(report_md)

    logger.info("Markdown evaluation report saved to: %s", args.report_out)

    # 3. Print high-level summary
    rc = summary.retrieval_comparison
    gs = summary.generation_summary
    ls = summary.latency_summary

    print("\n" + "=" * 60)
    print("      ENTERPRISE AGENTIC RAG EVALUATION RESULTS")
    print("=" * 60)
    print(f"Total Evaluated Questions: {summary.total_questions}")
    print("\n[RETRIEVAL PERFORMANCE]")
    print(
        f"  Dense Vector Only:        Recall@5={rc['dense_vector']['recall@5']:.4f} | MRR={rc['dense_vector']['mrr']:.4f}"
    )
    print(
        f"  Hybrid (Dense+FTS+RRF):   Recall@5={rc['hybrid_rrf']['recall@5']:.4f} | MRR={rc['hybrid_rrf']['mrr']:.4f}"
    )
    print(
        f"  Hybrid + Reranker:        Recall@5={rc['hybrid_reranked']['recall@5']:.4f} | MRR={rc['hybrid_reranked']['mrr']:.4f}"
    )
    print("\n[GENERATION & RAG TRIAD]")
    print(f"  Faithfulness:             {gs['faithfulness'] * 100:.1f}%")
    print(f"  Answer Relevance:         {gs['answer_relevance'] * 100:.1f}%")
    print(f"  Citation Precision:       {gs['citation_accuracy'] * 100:.1f}%")
    print(f"  Unanswerable Rejection:   {gs['unanswerable_rejection_rate'] * 100:.1f}%")
    print(f"  Adversarial Defense:      {gs['adversarial_defense_rate'] * 100:.1f}%")
    print("\n[LATENCY PROFILE]")
    print(f"  P50: {ls.p50_ms:.1f}ms | P90: {ls.p90_ms:.1f}ms | P99: {ls.p99_ms:.1f}ms")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
