# Enterprise RAG Platform: Failure Modes & Disaster Recovery (DR)

This document provides a comprehensive operational analysis of critical infrastructure failure scenarios, blast radius assessments, automated failover mechanisms, and runbooks for the Enterprise Agentic RAG Platform.

---

## 1. System Resilience Overview & DR Objectives

| Metric | Target Objective | Implementation Strategy |
| :--- | :--- | :--- |
| **Recovery Point Objective (RPO)** | **< 1 minute** | PostgreSQL WAL replication (Supabase) + Write-Through DB session management. |
| **Recovery Time Objective (RTO)** | **< 30 seconds** | Stateless backend containers + Asynchronous worker retries + Health check probes. |
| **Data Retention Compliance** | **7-Day Automated TTL** | Background cleanup worker running scheduled vacuum purges on `expires_at <= NOW()`. |
| **Ingestion Idempotency** | **100% Deterministic** | Tenant-scoped SHA-256 payload digest preventing redundant chunking/embedding. |

---

## 2. Failure Matrix & Blast Radius

| Failure Scenario | Detection Mechanism | Blast Radius | Automated Fallback / Self-Healing | Operator Runbook |
| :--- | :--- | :--- | :--- | :--- |
| **Redis Outage / Unavailability** | Redis connection heartbeat failure (`ConnectionRefusedError`) | Minor: L1 query caching disabled; rate limiter degrades to in-memory sliding window. | In-memory token bucket rate limiting activates transparently; LLM pipeline continues without cache hits. | 1. Check Redis process / ElastiCache cluster.<br>2. Restart container: `docker restart redis`. |
| **OpenRouter 429 / Down** | HTTP 429 / 5xx from OpenRouter upstream client. | Moderate: Query generation delayed; worker embedding jobs paused. | Exponential backoff with cryptographic jitter ($1.0 \times 2^{n} + \text{jitter}$); fallback to secondary LLM model. | 1. Verify API credit quota on OpenRouter dashboard.<br>2. Rotate BYOK key if quota breached. |
| **PostgreSQL / Pgvector Unavailable** | SQLAlchemy pool timeout / `OperationalError` / `asyncpg` disconnect. | Critical: Document uploads, user queries, and auth status checks fail (HTTP 503). | Connection pool pre-ping rejects dead sockets; FastAPI returns clean RFC-7807 error without leaking internals. | 1. Check Supabase database compute status.<br>2. Verify DB connection pooler (PgBouncer port 6543 vs Direct 5432). |
| **Worker Crashes Mid-Ingestion** | Document remains in `PROCESSING` state past worker heartbeat timeout. | Isolated: Only the currently processing document is affected. | Document transitions to `FAILED` with diagnostics; on re-upload or manual retry, idempotent handler resumes. | 1. Inspect worker logs via `docker logs backend`.<br>2. Inspect `Document.error_message` via GET `/api/documents/{id}/status`. |
| **Ingestion Retried Mid-Stream** | Worker receives duplicate job ID or client re-submits file. | Zero: Multi-tenant SHA-256 idempotency check activates. | SHA-256 index query finds existing `READY` document, returns HTTP 200 without creating duplicate chunks. | No manual action required. |

---

## 3. Deep-Dive Failure Scenarios & Self-Healing Workflows

### Scenario A: What Happens If Redis Dies?
- **Immediate Impact**:
  - Semantic query caching is temporarily bypassed.
  - Rate limiting switches automatically to the in-memory fallback sliding-window registry (`app/api/ratelimit.py`).
- **Data Integrity**:
  - Zero data loss. No persistent application data (documents, chunks, vectors, conversation messages) is stored exclusively in Redis.
- **Recovery Behavior**:
  - The Redis client continuously attempts reconnection on subsequent HTTP requests.
  - When Redis becomes available again, query caching and distributed rate limiting resume immediately with zero service restarts required.

---

### Scenario B: What Happens If OpenRouter Dies or Rate Limits?
- **Immediate Impact**:
  - Embedding generation or generative answer synthesis fails if OpenRouter returns HTTP 429 (Rate Limit Exceeded) or HTTP 502/503.
- **Ingestion Worker Resilience**:
  - `generate_embeddings_with_retry` intercepts upstream failures.
  - Implements **Exponential Backoff with Cryptographic Jitter**:
    $$\text{Sleep Time} = \left(\text{initial\_backoff} \times 2^{\text{attempt} - 1}\right) + \text{SystemRandom}(0.1, 0.5)$$
  - Retries up to 3 times before graceful degradation.
- **User Query Resilience**:
  - The LangGraph agentic router captures generator exceptions and returns a gracefully degraded notification to the client without exposing API keys or stack traces.

---

### Scenario C: What Happens If Supabase / PostgreSQL Is Unavailable?
- **Immediate Impact**:
  - Incoming HTTP requests requiring DB interaction fail fast.
- **Circuit Protection**:
  - SQLAlchemy `pool_pre_ping=True` proactively validates connections before dispensing them from the pool. Dead sockets are immediately discarded and re-established rather than causing cryptic query failures.
  - Global FastAPI exception handler (`app/main.py`) intercepts `OperationalError` and returns structured JSON `HTTP 500/503` with a sanitized reference ID, preventing internal schema or credential leakage.

---

### Scenario D: What Happens If a Background Worker Crashes Mid-Ingestion?
- **Failure State Tracking**:
  - The document state machine follows:
    $$\text{PENDING} \longrightarrow \text{PROCESSING} \longrightarrow \text{READY} \quad \text{or} \quad \text{FAILED}$$
  - CPU-heavy parsing and chunking occur **outside** active database transaction blocks.
  - If PyMuPDF or the worker process encounters an unhandled exception or SIGKILL mid-flight:
    1. The exception is trapped in `process_document_ingestion`.
    2. The document record is atomically marked `status = "FAILED"` and `error_message = str(e)`.
    3. No orphaned partial chunks are persisted because chunk insertion and `READY` status update are wrapped in an atomic database commit block.

---

### Scenario E: What Happens If an Ingestion Job Is Retried?
- **Multi-Tenant SHA-256 Idempotency Engine**:
  - When a file upload request is received, the server computes:
    $$\text{file\_hash} = \text{SHA-256}(\text{file\_bytes})$$
  - The server queries the compound index `(tenant_id, file_hash, status)`:
    ```sql
    SELECT * FROM documents
    WHERE tenant_id = :tenant_id
      AND file_hash = :file_hash
      AND status = 'READY'
    LIMIT 1;
    ```
  - **If Found**: Returns `HTTP 200 OK` with `is_duplicate: true` and the existing `document_id`. Redundant PyMuPDF parsing, semantic chunking, and embedding generation are completely skipped.
  - **Tenant Isolation**: If Tenant B uploads the exact same physical PDF as Tenant A, the query for Tenant B returns `None`. Deduplication is **strictly tenant-scoped**, preventing cross-tenant information leakage or authorization bypass.

---

## 4. Automated 7-Day TTL Retention & Cleanup Routine

To ensure compliance with GDPR, SOC 2, and data retention policies, all uploaded documents carry an automated 7-day expiration timestamp:
$$\text{expires\_at} = \text{created\_at} + 7\text{ days}$$

### Execution Model
1. **Scheduled Daemon**: `start_periodic_cleanup_loop` runs every 3600 seconds (1 hour).
2. **Atomic Cascading Deletion**:
   ```sql
   DELETE FROM documents WHERE expires_at <= NOW();
   ```
   PostgreSQL `ON DELETE CASCADE` foreign keys automatically purge all associated `document_chunks` and their 1536-dimensional vector embeddings, reclaiming storage space and maintaining indexing speed.
3. **Manual Trigger**: Authorized administrators (`org:admin`) can invoke `POST /api/documents/cleanup` at any time to run on-demand maintenance.
