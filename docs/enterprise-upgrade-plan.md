# 🚀 Enterprise Architecture Upgrade Plan (Target: 94/100)

## Executive Summary
This document specifies the end-to-end implementation roadmap to upgrade the **Enterprise Agentic RAG Platform** from its current MVP rating (**76/100**) to a **Tier-1 Enterprise Grade Architecture (94/100)**. 

### Upgrade Scope
1. **Multi-Strategy Chunking by Document Type**: Markdown headers, Tabular CSV rows, Code AST, and Multi-Column PDF layout awareness.
2. **Jina AI Reranker (`jina-reranker-v2`)**: Long-context (8,192 tokens) multilingual neural cross-encoder.
3. **Sub-15ms Query Intent Detector**: Fast-path hybrid intent classifier eliminating slow LLM zero-shot routing.
4. **S3 Pre-Signed Direct Uploads + RabbitMQ + Celery Workers with Dead-Letter Queues (DLQ)**: Decoupling upload binaries and heavy CPU embedding jobs from the FastAPI web server.

---

## 🗺️ High-Level Target Architecture

```
                                  ┌─────────────────────────────┐
                                  │   Browser / Bento UI        │
                                  └──────────────┬──────────────┘
                                                 │
                        ┌────────────────────────┴────────────────────────┐
                        │ 1. Request Presigned URL                        │ 3. Confirm Upload (doc_id)
                        ▼                                                 ▼
             ┌─────────────────────┐                          ┌────────────────────────┐
             │   FastAPI Gateway   │                          │    FastAPI Gateway     │
             │   (Lightweight)     │                          │    (Producer)          │
             └──────────┬──────────┘                          └───────────┬────────────┘
                        │                                                 │
                        │ 2. Direct Binary PUT                            │ 4. Publish Job
                        ▼                                                 ▼
             ┌─────────────────────┐                          ┌────────────────────────┐
             │   AWS S3 / Supabase │                          │  RabbitMQ AMQP Broker  │
             │   Object Storage    │                          │  (Durable + DLQ)       │
             └──────────┬──────────┘                          └───────────┬────────────┘
                        │                                                 │
                        └──────────────────────┬──────────────────────────┘
                                               │ 5. Consume Task
                                               ▼
                                  ┌─────────────────────────────┐
                                  │    Celery / Worker Pool     │
                                  │  - Multi-Strategy Chunker   │
                                  │  - Batch Dense Embeddings   │
                                  │  - Atomic Postgres Upsert   │
                                  └──────────────┬──────────────┘
                                                 │
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │   Dead-Letter Queue (DLQ)   │
                                  │   (Corrupted/Failed Jobs)   │
                                  └─────────────────────────────┘
```

---

## 📋 Phase-by-Phase Implementation Plan

### Phase 1: Multi-Strategy Chunking by Document Type
**Target Files**: 
- `backend/app/services/chunker.py`
- `backend/app/services/parser.py`
- `backend/tests/test_chunker.py`

#### Implementation Details:
1. Define abstract base class `BaseChunker(ABC)` with method `chunk(text_or_pages, **kwargs) -> list[Chunk]`.
2. Implement 5 specialized chunking strategies:
   - **`MarkdownChunker`**: Parses header hierarchies (`#`, `##`, `###`), preserving section breadcrumbs (e.g., `Architecture > Ingress > Gateway`) in chunk metadata.
   - **`TabularChunker`**: Parses CSV and TSV files row-by-row, automatically prepending table column headers to every chunk to preserve semantic context for vector search.
   - **`PDFLayoutChunker`**: Preserves PyMuPDF layout blocks, strips redundant running headers/footers, and groups contiguous paragraphs.
   - **`CodeASTChunker`**: Splits Python/TypeScript/JSON files by function, class, or object scope rather than arbitrary token boundaries.
   - **`SemanticChunker`**: Enhanced token-sliding window for plain text with sentence-boundary detection.
3. Implement `ChunkerFactory.get_chunker(filename, mime_type)` to auto-detect and instantiate the optimal chunking engine.

---

### Phase 2: Jina AI Neural Reranker Integration
**Target Files**:
- `backend/app/services/reranker.py`
- `backend/app/config.py`
- `backend/tests/test_reranker.py`

#### Implementation Details:
1. Add `jina_api_key` and `jina_reranker_model` (`jina-reranker-v2-base-multilingual`) to `Settings`.
2. Update `RerankerService` to query `https://api.jina.ai/v1/rerank`:
   - Send candidate document texts and user query with `top_n=5`.
   - Support up to **8,192 tokens per candidate** (eliminating truncation of large tables or legal clauses).
3. Provide an automatic offline/local fallback when `JINA_API_KEY` is not configured (ensuring test suites and local dev run without external network dependencies).

---

### Phase 3: Sub-15ms Dedicated Query Intent Detector
**Target Files**:
- `backend/app/services/intent.py`
- `backend/app/agent/graph.py`
- `backend/tests/test_intent.py`

#### Implementation Details:
1. Create `IntentDetector` service combining:
   - **Fast-Path Regex & Exact Matchers**: Immediate `< 1ms` detection for conversational greetings (`hi`, `hello`, `thanks`, `bye`), system capability inquiries (`who are you`, `help`).
   - **Cosine Semantic Intent Anchors**: Encodes user query and measures cosine similarity against pre-computed canonical intent vectors:
     - `Document Inquiry Anchors`: "What does section 4 say?", "According to the contract...", "Summarize the revenue...".
     - `Chit-Chat Anchors`: "Tell me a joke", "How is the weather?", "Who was the 16th president?".
2. Refactor `AgentWorkflow.route_query` in `app/agent/graph.py`:
   - If confidence $\ge 0.70$, return deterministic classification instantly in $< 15\text{ms}$.
   - If ambiguous, fall back to LLM JSON prompt router.
   - Slashes TTFT (Time-To-First-Token) for chat queries by 500–800ms and reduces LLM token costs.

---

### Phase 4: S3 Presigned URLs + RabbitMQ + Celery Workers with DLQ
**Target Files**:
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `backend/app/config.py`
- `backend/app/services/storage.py`
- `backend/app/api/documents.py`
- `backend/app/workers/celery_app.py`
- `backend/app/workers/ingestion_tasks.py`
- `backend/requirements.txt`

#### Implementation Details:
1. **Infrastructure**:
   - Add `rabbitmq:3-management` service to `docker-compose.yml` (ports `5672` AMQP, `15672` UI).
   - Configure AMQP exchange `documents.exchange`, durable queue `documents.ingestion`, and Dead-Letter Queue `documents.dlq`.
2. **Object Storage Service (`app/services/storage.py`)**:
   - Implement S3/Supabase Storage signed URL generator using `boto3`.
   - Endpoint `POST /api/documents/upload-url`: Returns `{ document_id, presigned_url, storage_path, expires_in: 900 }`.
   - Client directly uploads binary to S3/Supabase (0 bytes pass through FastAPI RAM).
   - Endpoint `POST /api/documents/confirm-upload`: Validates file existence in storage and enqueues task to RabbitMQ.
3. **Celery Worker Architecture**:
   - Replace in-process `BackgroundTasks` with Celery tasks:
     ```python
     @celery_app.task(
         bind=True,
         max_retries=3,
         default_retry_delay=10,
         dead_letter_queue="documents.dlq"
     )
     def ingest_document_task(self, document_id: str, tenant_id: str, storage_path: str):
         ...
     ```
   - Auto-acknowledgement only after database commit.
   - Poisoned or unparseable files automatically route to `documents.dlq` with failure diagnostics.

---

## ⚙️ Configuration Guide

### 1. Environment Variables (`.env.example`)

Add the following environment variables:

```bash
# ============================================
# Jina AI Reranker
# ============================================
# Get free API key from https://jina.ai/reranker
JINA_API_KEY=jina_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
JINA_RERANKER_MODEL=jina-reranker-v2-base-multilingual

# ============================================
# RabbitMQ Message Broker
# ============================================
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672//
CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:5672//
CELERY_RESULT_BACKEND=redis://redis:6379/1

# ============================================
# Object Storage (AWS S3 or Supabase Storage)
# ============================================
STORAGE_BACKEND=supabase  # 's3' or 'supabase'
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
S3_BUCKET_NAME=enterprise-rag-documents
# For Supabase Storage S3-compatible credentials:
S3_ENDPOINT_URL=https://<project-ref>.supabase.co/storage/v1/s3
```

### 2. External Services Setup

1. **Jina AI**: Sign up at [jina.ai/reranker](https://jina.ai/reranker) to get a free API key (includes 1,000,000 tokens free).
2. **RabbitMQ**: Automatically spins up via `docker-compose up -d rabbitmq` with web dashboard at `http://localhost:15672` (default user: `guest` / `guest`).
3. **Storage**: Can use your existing Supabase Storage bucket (`documents`) or any standard AWS S3 bucket.
