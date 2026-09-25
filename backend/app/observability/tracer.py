"""
Enterprise Observability, Distributed Tracing & Production Metrics Engine.

Provides:
1. LangSmith Tracing Configuration with Tenant Scoping.
2. Production JSON Structured Log Formatting.
3. Thread-Safe Query Latency & Token Usage Accounting.
4. Percentile (P50, P90, P99) Metric Aggregations.
"""

import json
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def configure_langsmith_tracing() -> bool:
    """
    Safely configure LangSmith tracing environment variables based on application settings.

    Returns:
        bool: True if LangSmith tracing is actively enabled, False otherwise.
    """
    if settings.langchain_tracing_v2 and settings.langchain_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project or "enterprise-rag"
        logger.info(
            "LangSmith distributed tracing enabled (Project: %s).",
            settings.langchain_project,
        )
        return True
    return False


def get_tracer_run_config(
    tenant_id: str,
    run_name: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Generate LangGraph/LangChain execution configuration with multi-tenant tagging.

    Enforces that tenant identity is indexed in trace metadata for quota tracking
    and audit trails without leaking secrets.
    """
    metadata: dict[str, Any] = {"tenant_id": tenant_id}
    if extra_metadata:
        metadata.update(extra_metadata)

    return {
        "run_name": run_name or f"rag_query_{tenant_id}",
        "tags": [f"tenant:{tenant_id}", "enterprise-rag"],
        "metadata": metadata,
    }


class MetricsTracker:
    """Thread-safe in-memory metric collector for production monitoring and SLAs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._query_latencies_ms: list[float] = []
        self._tenant_request_counts: dict[str, int] = defaultdict(int)
        self._tenant_token_counts: dict[str, int] = defaultdict(int)
        self._error_counts: dict[str, int] = defaultdict(int)

    def record_query(
        self,
        tenant_id: str,
        latency_ms: float,
        tokens_used: int = 0,
        is_error: bool = False,
    ) -> None:
        """Record latency, token usage, and status for a completed user query."""
        with self._lock:
            self._query_latencies_ms.append(latency_ms)
            # Keep sliding window of latest 5000 queries to bound memory
            if len(self._query_latencies_ms) > 5000:
                self._query_latencies_ms = self._query_latencies_ms[-5000:]

            self._tenant_request_counts[tenant_id] += 1
            if tokens_used > 0:
                self._tenant_token_counts[tenant_id] += tokens_used
            if is_error:
                self._error_counts[tenant_id] += 1

    def get_summary(self) -> dict[str, Any]:
        """Compute aggregated operational metrics, percentiles, and uptime."""
        with self._lock:
            uptime_seconds = int(time.time() - self._start_time)
            latencies = sorted(self._query_latencies_ms)
            count = len(latencies)

            def get_percentile(p: float) -> float:
                if not latencies:
                    return 0.0
                idx = min(round(p * (count - 1)), count - 1)
                return round(latencies[idx], 2)

            total_requests = sum(self._tenant_request_counts.values())
            total_tokens = sum(self._tenant_token_counts.values())
            total_errors = sum(self._error_counts.values())
            error_rate = round(total_errors / total_requests, 4) if total_requests > 0 else 0.0

            return {
                "uptime_seconds": uptime_seconds,
                "total_queries": total_requests,
                "total_tokens_consumed": total_tokens,
                "total_errors": total_errors,
                "error_rate": error_rate,
                "latency_percentiles_ms": {
                    "p50": get_percentile(0.50),
                    "p90": get_percentile(0.90),
                    "p99": get_percentile(0.99),
                    "avg": round(sum(latencies) / count, 2) if count > 0 else 0.0,
                },
                "active_tenants_count": len(self._tenant_request_counts),
            }

    def reset(self) -> None:
        """Reset internal metrics (useful between test runs)."""
        with self._lock:
            self._start_time = time.time()
            self._query_latencies_ms.clear()
            self._tenant_request_counts.clear()
            self._tenant_token_counts.clear()
            self._error_counts.clear()


class StructuredJsonFormatter(logging.Formatter):
    """Production JSON log formatter for cloud log aggregators (ELK, CloudWatch, Datadog)."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if hasattr(record, "tenant_id"):
            log_entry["tenant_id"] = record.tenant_id
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


# Global singleton instance
metrics_tracker = MetricsTracker()
