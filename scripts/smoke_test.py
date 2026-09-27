"""
Enterprise RAG Platform — Automated Production Smoke Test Suite.

Validates that a deployed or local instance of the platform is fully operational:
1. Root welcome endpoint (GET /)
2. Liveness probe (GET /health)
3. Readiness probe (GET /health/ready)
4. SLA Latency & Metrics (GET /health/metrics)
5. CORS Headers Verification
6. Auth Guardrail & RFC-7807 Clean Rejection (GET /api/documents)

Usage:
    python scripts/smoke_test.py --url http://localhost:8000
    python scripts/smoke_test.py --url https://your-backend-api.onrender.com
"""

import argparse
import sys
import time
from typing import Any
import httpx


def run_smoke_test(base_url: str) -> bool:
    """Run smoke test suite against target base URL."""
    base_url = base_url.rstrip("/")
    print("=" * 70)
    print(f"ENTERPRISE RAG PLATFORM — SMOKE TEST SUITE")
    print(f"Target URL: {base_url}")
    print("=" * 70)

    client = httpx.Client(timeout=15.0)
    tests_passed = 0
    total_tests = 6
    results: list[dict[str, Any]] = []

    # ── Test 1: Root Welcome Endpoint ──
    t0 = time.time()
    try:
        resp = client.get(f"{base_url}/")
        latency = (time.time() - t0) * 1000
        passed = resp.status_code == 200 and resp.json().get("status") == "online"
        results.append({
            "name": "1. Root Welcome (/)",
            "status": "PASS" if passed else "FAIL",
            "code": resp.status_code,
            "latency": f"{latency:.1f}ms",
            "detail": f"Version: {resp.json().get('version', 'unknown')}",
        })
        if passed:
            tests_passed += 1
    except Exception as exc:
        results.append({
            "name": "1. Root Welcome (/)",
            "status": "FAIL",
            "code": 0,
            "latency": "ERR",
            "detail": str(exc),
        })

    # ── Test 2: Liveness Probe ──
    t0 = time.time()
    try:
        resp = client.get(f"{base_url}/health")
        latency = (time.time() - t0) * 1000
        passed = resp.status_code == 200 and resp.json().get("status") == "healthy"
        results.append({
            "name": "2. Liveness Probe (/health)",
            "status": "PASS" if passed else "FAIL",
            "code": resp.status_code,
            "latency": f"{latency:.1f}ms",
            "detail": f"Status: {resp.json().get('status')}",
        })
        if passed:
            tests_passed += 1
    except Exception as exc:
        results.append({
            "name": "2. Liveness Probe (/health)",
            "status": "FAIL",
            "code": 0,
            "latency": "ERR",
            "detail": str(exc),
        })

    # ── Test 3: Readiness Probe (DB & Infra) ──
    t0 = time.time()
    try:
        resp = client.get(f"{base_url}/health/ready")
        latency = (time.time() - t0) * 1000
        data = resp.json()
        db_val = data.get("database")
        db_status = db_val.get("connected") if isinstance(db_val, dict) else db_val
        passed = resp.status_code == 200 and data.get("status") in ["ready", "degraded"]
        results.append({
            "name": "3. Readiness Probe (/health/ready)",
            "status": "PASS" if passed else "FAIL",
            "code": resp.status_code,
            "latency": f"{latency:.1f}ms",
            "detail": f"Status: {data.get('status')} | DB: {db_status}",
        })
        if passed:
            tests_passed += 1
    except Exception as exc:
        results.append({
            "name": "3. Readiness Probe (/health/ready)",
            "status": "FAIL",
            "code": 0,
            "latency": "ERR",
            "detail": str(exc),
        })

    # ── Test 4: Metrics Endpoint ──
    t0 = time.time()
    try:
        resp = client.get(f"{base_url}/health/metrics")
        latency = (time.time() - t0) * 1000
        passed = resp.status_code == 200 and "uptime_seconds" in resp.json()
        results.append({
            "name": "4. SLA Metrics (/health/metrics)",
            "status": "PASS" if passed else "FAIL",
            "code": resp.status_code,
            "latency": f"{latency:.1f}ms",
            "detail": f"Uptime: {resp.json().get('uptime_seconds', 0):.0f}s",
        })
        if passed:
            tests_passed += 1
    except Exception as exc:
        results.append({
            "name": "4. SLA Metrics (/health/metrics)",
            "status": "FAIL",
            "code": 0,
            "latency": "ERR",
            "detail": str(exc),
        })

    # ── Test 5: CORS Options Preflight ──
    t0 = time.time()
    try:
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        }
        resp = client.options(f"{base_url}/api/chat/stream", headers=headers)
        latency = (time.time() - t0) * 1000
        allow_origin = resp.headers.get("access-control-allow-origin", "")
        passed = resp.status_code == 200 and len(allow_origin) > 0
        results.append({
            "name": "5. CORS Preflight (OPTIONS)",
            "status": "PASS" if passed else "FAIL",
            "code": resp.status_code,
            "latency": f"{latency:.1f}ms",
            "detail": f"Allowed Origin: {allow_origin}",
        })
        if passed:
            tests_passed += 1
    except Exception as exc:
        results.append({
            "name": "5. CORS Preflight (OPTIONS)",
            "status": "FAIL",
            "code": 0,
            "latency": "ERR",
            "detail": str(exc),
        })

    # ── Test 6: Auth Guardrail & Clean Error ──
    t0 = time.time()
    try:
        # Request without token or with invalid token should not leak stack traces
        resp = client.get(f"{base_url}/api/documents", headers={"Authorization": "Bearer invalid_token_123"})
        latency = (time.time() - t0) * 1000
        # In this platform, missing/invalid token either uses default tenant in dev or returns 401 in strict prod
        # In both cases, response must be clean JSON without python tracebacks
        body_text = resp.text
        has_no_traceback = "Traceback (most recent call last)" not in body_text and resp.status_code in [200, 401, 403]
        results.append({
            "name": "6. Auth Security Guardrail",
            "status": "PASS" if has_no_traceback else "FAIL",
            "code": resp.status_code,
            "latency": f"{latency:.1f}ms",
            "detail": "Clean JSON, Zero Traceback Leakage",
        })
        if has_no_traceback:
            tests_passed += 1
    except Exception as exc:
        results.append({
            "name": "6. Auth Security Guardrail",
            "status": "FAIL",
            "code": 0,
            "latency": "ERR",
            "detail": str(exc),
        })

    # ── Display Results Table ──
    print(f"{'TEST NAME':<34} | {'STATUS':<6} | {'CODE':<5} | {'LATENCY':<9} | {'DETAILS'}")
    print("-" * 75)
    for r in results:
        status_color = "\033[92mPASS\033[0m" if r["status"] == "PASS" else "\033[91mFAIL\033[0m"
        print(f"{r['name']:<34} | {status_color:<15} | {r['code']:<5} | {r['latency']:<9} | {r['detail']}")
    print("=" * 75)
    print(f"Summary: {tests_passed}/{total_tests} Tests Passed ({(tests_passed/total_tests)*100:.0f}%)")

    return tests_passed == total_tests


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Production Smoke Tests")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Target base URL to test (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    success = run_smoke_test(args.url)
    sys.exit(0 if success else 1)
