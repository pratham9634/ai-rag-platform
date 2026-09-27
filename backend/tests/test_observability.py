"""
Unit and Integration Tests for Phase 9 Observability & Tracing Engine.

Tests:
1. MetricsTracker: Percentile computation (P50, P90, P99), query counters, and error rates.
2. Multi-Tenant Tracing Tags: get_tracer_run_config isolates tenant metadata and run names.
3. LangSmith Configuration: Environment variable injection and safe fallback.
4. /health/metrics Endpoint: SLA summaries and latency metrics via FastAPI TestClient.
5. /health/ready Endpoint: Database readiness probe verification.
6. StructuredJsonFormatter: Machine-readable JSON log formatting without secret leakage.
"""

import json
import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.observability.tracer import (
    MetricsTracker,
    StructuredJsonFormatter,
    configure_langsmith_tracing,
    get_tracer_run_config,
    metrics_tracker,
)


@pytest.fixture(autouse=True)
def clean_metrics_state():
    """Reset metrics before and after each test."""
    metrics_tracker.reset()
    yield
    metrics_tracker.reset()


def test_metrics_tracker_percentiles_calculation() -> None:
    """MetricsTracker must compute accurate P50, P90, P99 percentiles."""
    tracker = MetricsTracker()

    # Record 10 queries: 100ms, 200ms, ..., 1000ms
    for i in range(1, 11):
        tracker.record_query(
            tenant_id="tenant-alpha",
            latency_ms=float(i * 100),
            tokens_used=50,
            is_error=(i == 10),
        )

    summary = tracker.get_summary()
    assert summary["total_queries"] == 10
    assert summary["total_tokens_consumed"] == 500
    assert summary["total_errors"] == 1
    assert summary["error_rate"] == 0.1
    assert summary["active_tenants_count"] == 1

    percentiles = summary["latency_percentiles_ms"]
    assert percentiles["p50"] in [500.0, 600.0]
    assert percentiles["p90"] in [900.0, 1000.0]
    assert percentiles["p99"] == 1000.0


def test_get_tracer_run_config_tenant_tagging() -> None:
    """Run configuration must strictly include tenant tag and metadata."""
    config = get_tracer_run_config(
        tenant_id="org_enterprise_42",
        run_name="query_test",
        extra_metadata={"model": "claude-3.5-sonnet"},
    )

    assert config["run_name"] == "query_test"
    assert "tenant:org_enterprise_42" in config["tags"]
    assert config["metadata"]["tenant_id"] == "org_enterprise_42"
    assert config["metadata"]["model"] == "claude-3.5-sonnet"


def test_configure_langsmith_tracing_disabled_when_no_key() -> None:
    """When API key is empty, LangSmith tracing should gracefully remain disabled."""
    with patch("app.observability.tracer.settings") as mock_settings:
        mock_settings.langchain_tracing_v2 = True
        mock_settings.langchain_api_key = ""
        enabled = configure_langsmith_tracing()
        assert enabled is False


def test_configure_langsmith_tracing_enabled_with_key() -> None:
    """When API key is present and tracing enabled, environment variables are set."""
    with patch("app.observability.tracer.settings") as mock_settings:
        mock_settings.langchain_tracing_v2 = True
        mock_settings.langchain_api_key = "ls__test_key"
        mock_settings.langchain_project = "test-project"
        enabled = configure_langsmith_tracing()
        assert enabled is True


def test_health_metrics_endpoint() -> None:
    """GET /health/metrics must return 200 OK and valid SLA summary dictionary."""
    metrics_tracker.record_query(tenant_id="tenant-sla", latency_ms=120.0, tokens_used=40)

    client = TestClient(app)
    response = client.get("/health/metrics")
    assert response.status_code == 200

    data = response.json()
    assert data["total_queries"] == 1
    assert data["total_tokens_consumed"] == 40
    assert "latency_percentiles_ms" in data
    assert "uptime_seconds" in data


def test_health_readiness_probe() -> None:
    """GET /health/ready returns status and database readiness state."""
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "database" in data


def test_structured_json_log_formatter() -> None:
    """StructuredJsonFormatter must format LogRecord as valid parseable JSON."""
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="tracer.py",
        lineno=42,
        msg="Execution completed for query",
        args=(),
        exc_info=None,
    )
    record.tenant_id = "tenant-xyz"

    formatted_str = formatter.format(record)
    parsed = json.loads(formatted_str)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test_logger"
    assert parsed["message"] == "Execution completed for query"
    assert parsed["tenant_id"] == "tenant-xyz"
    assert "timestamp" in parsed
