# Enterprise Agentic RAG Platform

[![CI Pipeline](https://github.com/pratham9634/ai-rag-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/pratham9634/ai-rag-platform/actions/workflows/ci.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16+-black.svg?logo=next.js&logoColor=white)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+--pgvector-336791.svg?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Docker](https://img.shields.io/badge/Docker-Production--Ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com)
[![Tests](https://img.shields.io/badge/pytest-83%20passed-success.svg)](backend/tests)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An enterprise-grade, multi-tenant, agentic Retrieval-Augmented Generation (RAG) platform. Features **hybrid retrieval** (dense vector embeddings + full-text BM25 search), **Reciprocal Rank Fusion (RRF)**, **Cross-Encoder reranking**, **LangGraph self-correcting agentic loops**, **Row-Level Security (RLS) multi-tenancy**, **Bring-Your-Own-Key (BYOK) model routing**, **7-day automated document TTL retention**, and a **Linear App-inspired Bento UI** with real-time P50/P90/P99 telemetry.

---

## 1. 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph Clients["Frontend Clients"]
        UI["Linear/Bento Dark UI (Next.js 16)"]
        Admin["Admin Telemetry Dashboard"]
        Settings["BYOK & Model Settings Modal"]
    end

    subgraph AuthTier["Identity & Access Control"]
        Clerk["Clerk Multi-Tenant Auth\n(JWT Claims: org_id / user_id)"]
    end

    subgraph Gateway["API & Routing Tier (FastAPI)"]
        Ingress["FastAPI Gateway (:8000)"]
        RL["Distributed Token-Bucket Rate Limiter"]
        Telemetry["Prometheus Metrics Exporter\n(/health/metrics: P50/P90/P99)"]
    end

    subgraph AgenticPipeline["LangGraph Self-Correcting State Machine"]
        Router{"Query Intent Router"}
        Retriever["Hybrid Retrieval Engine\n(pgvector Cosine + Keyword BM25)"]
        Grader{"Relevance Grader\n(Cross-Encoder ms-marco)"}
        Rewriter["Query Reformulator\n(Self-Correction)"]
        Generator["Grounded Answer Synthesizer\n(Strict Citations Grounding)"]
        Direct["Conversational Fast-Path"]
    end

    subgraph StorageTier["Database & Caching Tier"]
        Supavisor["Supavisor / PgBouncer\nTransaction Pooler (Port 6543)"]
        PG[("PostgreSQL 15 + pgvector\n(Tenant Row-Level Security)")]
        Redis[("Redis 7 Cache & Queue")]
    end

    subgraph Workers["Background Services"]
        Worker["Async Ingestion Worker\n(PyMuPDF + Chunking + all-MiniLM-L6-v2)"]
        TTL["Automated 7-Day TTL Cleanup Daemon"]
    end

    subgraph Inference["LLM Inference Providers"]
        OpenRouter["OpenRouter Gateway\n(Claude 3.5 Sonnet / GPT-4o Mini / Llama 3.1 8B Free)"]
    end

    UI --> Clerk
    Clerk --> Ingress
    Ingress --> RL
    RL --> Router
    Router -- "Direct Chat" --> Direct
    Router -- "Document Query" --> Retriever
    Retriever --> Grader
    Grader -- "Low Relevance" --> Rewriter
    Rewriter --> Retriever
    Grader -- "Relevant" --> Generator
    Generator --> OpenRouter
    Direct --> OpenRouter

    Ingress --> Supavisor
    Supavisor --> PG
    Ingress --> Redis
    Worker --> Supavisor
    TTL --> Supavisor
    Ingress --> Telemetry
    Admin --> Telemetry
```

---

## 2. ⚡ Core Capabilities

- **Cyclic Agentic RAG (LangGraph)**: Bounded self-correcting workflow with deterministic intent routing, document relevance grading, automatic query rewriting, and strict citation grounding.
- **Hybrid Search Engine**: Fuses dense semantic vector embeddings (`all-MiniLM-L6-v2` via pgvector `<->` cosine distance) with PostgreSQL full-text keyword indexing (`tsvector @@ plainto_tsquery`) using Reciprocal Rank Fusion (RRF, $k=60$).
- **Cross-Encoder Reranking**: Scores top-20 retrieved candidates with `cross-encoder/ms-marco-MiniLM-L-6-v2` to filter false-positive context and feed high-precision passages to the LLM.
- **Strict Multi-Tenant Isolation**: Derives `tenant_id` from cryptographically signed Clerk JWTs. Enforces PostgreSQL Row-Level Security (RLS) across all documents, chunks, conversations, and vector indices.
- **Bring Your Own Key (BYOK)**: Supports Claude 3.5 Sonnet, GPT-4o Mini, Llama 3.1 8B Free, and Mistral 7B Free. Custom API keys are stored ephemerally in browser `sessionStorage` and transmitted via `X-BYOK-API-Key` headers without database persistence.
- **Automated 7-Day Document TTL**: Non-blocking background worker automatically purges expired documents, chunks, and storage binaries after 7 days, satisfying SOC2/GDPR compliance.
- **Production Observability**: Real-time sliding-window P50, P90, and P99 latency tracking, error-rate gauges, and LangSmith distributed tracing with sensitive header masking.

---

## 3. 🛠️ Tech Stack & Zero-Cost Architecture

Designed to run completely on **100% free-tier services** without proprietary vendor lock-in:

| Layer | Technology | Production Choice | Rationale |
|---|---|---|---|
| **Frontend** | Next.js 16 (App Router), TypeScript, Tailwind CSS | Vercel Free Tier | Zero-config edge hosting, sub-second TTFB |
| **Backend API** | FastAPI, Python 3.11, Pydantic v2, Uvicorn | Render / Railway Free Tier | High-throughput asynchronous ASGI streaming |
| **Authentication** | Clerk Auth (`@clerk/nextjs`) | Clerk Free Tier (10,000 MAU) | Decoupled identity, multi-tenant org claims |
| **Database & Vectors** | PostgreSQL 15 + `pgvector` | Supabase Free Tier (500MB) | Native ACID relational models + vector similarity |
| **Connection Pooling**| Supavisor (Port 6543) | Supabase Managed Pooler | Prevents connection exhaustion under load |
| **Cache & Rate Limiting**| Redis 7 | Upstash Redis Free Tier | Serverless low-latency queue & distributed token bucket |
| **Embeddings & LLMs**| `all-MiniLM-L6-v2` / OpenRouter | OpenRouter Free Pool | Open-weights inference with zero base cost |
| **CI/CD** | GitHub Actions | GitHub Free Runners | Automated linting, 83 pytest tests & Docker builds |

---

## 4. 🔬 In-Depth RAG Pipeline

```
PDF Upload (max 10MB)
    │
    ▼
SHA-256 Checksum Validation (Idempotent Duplicate Prevention)
    │
    ▼
PyMuPDF (`fitz`) Text Extraction (Multi-Column Layout Preservation)
    │
    ▼
Semantic Chunking (500-token chunks, 100-token overlap, page-numbered)
    │
    ▼
Dense Embedding (all-MiniLM-L6-v2, 384 dimensions)
    │
    ▼
Supabase PostgreSQL Bulk Upsert (Atomic transaction with pgvector & FTS)
```

```
User Query
    │
    ├── 1. Vector Search (HNSW Cosine Similarity, Top 20)
    └── 2. Lexical Search (Postgres tsvector/tsquery BM25, Top 20)
            │
            ▼
    Reciprocal Rank Fusion: RRF_score(d) = Σ 1 / (60 + rank(d))
            │
            ▼
    Cross-Encoder Reranker (ms-marco-MiniLM-L-6-v2, Top 5)
            │
            ▼
    Relevance Grader Gate (LangGraph) ───[Low Score]──► Query Rewriter ──► Re-retrieval
            │
            ▼ [Passed]
    Grounded Generator (Prompt Injection Guarded XML delimiters)
            │
            ▼
    Server-Sent Events (SSE) Token Stream + Verified Page Citations
```

---

## 5. 🎨 UI/UX Design System (Linear App + Bento)

The user interface follows the official **Linear App** and **Bento Grid** design system guidelines:
- **Canvas**: Pure deep dark canvas (`#030712` / `#010102`).
- **Surface Steps**: Four-tier elevation ladder (`#0b0f17` → `#121826` → `#1a2234`) with hairline borders (`#23252a` / `border-white/[0.08]`).
- **Chromatic Accent**: Linear signature lavender-blue (`#5e6ad2`), hover (`#828fff`), focus (`#5e69d1`).
- **Interactive Citation Inspector Drawer**: Clicking any `[Page X • 98%]` citation badge triggers an animated slide-in drawer displaying document ID, chunk ID, confidence scores, and provenance context.
- **Admin Telemetry Bento**: Real-time system health grid displaying P50/P90/P99 latency percentiles, 7-day TTL monitor, storage quota gauges, and Phase 7 benchmark results.

---

## 6. 🚀 Quickstart & Local Setup

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (v24+)
- [Node.js](https://nodejs.org/) (v20+ or v22+)
- [Python](https://www.python.org/) (3.11+)

### 1. Clone & Setup Environment
```bash
git clone https://github.com/pratham9634/ai-rag-platform.git
cd ai-rag-platform

# Copy template and configure credentials
cp .env.example .env
```

Ensure `.env` contains:
```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_db
REDIS_URL=redis://localhost:6379/0
OPENROUTER_API_KEY=your_key_here
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
```

### 2. Run with Docker Compose
```bash
docker compose up --build
```
- **Web UI:** [http://localhost:3000](http://localhost:3000)
- **FastAPI API:** [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Live Metrics Endpoint:** [http://localhost:8000/health/metrics](http://localhost:8000/health/metrics)

### 3. Local Development (Without Docker)

**Backend:**
```bash
cd backend
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

---

## 7. 🧪 Testing & Verification

The platform features an automated test suite with **83 unit, integration, and security tests** that run in both local environments and CI/CD runners:

```bash
# Run backend test suite (83 tests)
cd backend
python -m pytest tests/ -v

# Run smoke test against running instance
python scripts/smoke_test.py --url http://localhost:8000

# Verify frontend types and linting
cd ../frontend
node ./node_modules/typescript/bin/tsc --noEmit
npm run lint
```

### Test Suite Breakdown
- `tests/test_health.py`: Liveness, readiness, and metric histogram verification.
- `tests/test_auth.py`: JWT claims verification, tenant context extraction, and unauthorized 401 gates.
- `tests/test_documents.py`: PyMuPDF parsing, SHA-256 duplicate rejection, and asynchronous ingestion.
- `tests/test_retrieval.py`: Hybrid pgvector + BM25 search, Reciprocal Rank Fusion, and Cross-Encoder ranking.
- `tests/test_agent.py`: LangGraph state machine, query rewriter, and citation grounding.
- `tests/test_security.py`: Prompt injection sanitization, delimiter escaping, and SQL injection prevention.
- `tests/test_eval.py`: Faithfulness, answer relevance, and context recall benchmark harness.

---

## 8. 📦 Production Docker Images

Multi-stage, unprivileged, minimal production Dockerfiles:

```bash
# Build backend production image
docker build -f backend/Dockerfile.prod -t rag-backend:prod ./backend

# Build frontend production image
docker build -f frontend/Dockerfile.prod -t rag-frontend:prod ./frontend
```

---

## 9. 🌐 Scaling to 100k DAU

For detailed system scaling projections, capacity planning, distributed Celery worker architectures, and HNSW partitioning strategies, consult:
📄 [docs/scaling.md](docs/scaling.md)

---

## 10. 📚 Architectural Decisions & Interview Q&A

- **Architecture Decisions Log:** [decision.md](decision.md) (Detailed trade-offs and rationale for all 10 project phases)
- **Interview Preparation Guide:** [questions.txt](questions.txt) (70 production-grade AI/RAG system design questions & detailed technical answers)
- **Security & Threat Model:** [docs/security.md](docs/security.md) and [docs/threat-model.md](docs/threat-model.md)
- **Benchmark Evaluation Report:** [docs/evaluation-report.md](docs/evaluation-report.md)

---

## 11. 📅 10-Day Implementation Roadmap

- [x] **Day 1: Platform Scaffolding & Core Architecture** (FastAPI, Docker, Health Probes)
- [x] **Day 2: Document Ingestion & PyMuPDF Chunking** (SHA-256 deduplication, atomic database transactions)
- [x] **Day 3: Hybrid Retrieval & Cross-Encoder Reranking** (pgvector + BM25, RRF fusion)
- [x] **Day 4: Self-Correcting Agentic RAG** (LangGraph state machine, cyclic retry, SSE streaming)
- [x] **Day 5: Multi-Tenancy & Security** (Clerk JWT claims, Postgres Row-Level Security)
- [x] **Day 6: Adversarial Security & Prompt Injection** (XML delimiter escaping, BYOK ephemeral memory)
- [x] **Day 7: Evaluation Benchmark Harness** (Golden dataset, Faithfulness & Relevance metrics)
- [x] **Day 8: Production Engineering** (Async background ingestion, Redis rate limiting, 7-day TTL daemon)
- [x] **Day 9: CI/CD & Cloud Deployment** (GitHub Actions, Multi-stage Docker, `render.yaml` IaC)
- [x] **Day 10: Linear/Bento UI Redesign, Admin Telemetry & Scaling** (Linear App theme, Citation Inspector, `docs/scaling.md`)
