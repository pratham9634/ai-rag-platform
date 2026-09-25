# Enterprise Agentic RAG Platform — System Architecture

## 1. System Overview

The Enterprise Agentic RAG Platform is a multi-tenant, security-hardened, production-grade retrieval-augmented generation platform. It allows organizations to upload private documents, index them with hybrid search (dense semantic embeddings + sparse lexical keyword search), and query them via an agentic retrieval pipeline with reranking and citation grounding.

```
┌─────────────────────────────────────────────────────────────┐
│                          USER                               │
│                            │                                │
│                            ▼                                │
│                    ┌──────────────┐                         │
│                    │    CLERK     │  Identity Provider      │
│                    │   (hosted)   │  Auth, Orgs, Sessions   │
│                    └──────┬───────┘                         │
│                           │                                 │
│                           ▼                                 │
│                  ┌────────────────┐                         │
│                  │    NEXT.JS     │  Frontend (React / SSR) │
│                  │  (Docker:3000) │  Clerk SDK, UI          │
│                  └────────┬───────┘                         │
│                           │ HTTP Bearer JWT                 │
│                           ▼                                 │
│                  ┌────────────────┐                         │
│                  │    FASTAPI     │  API Gateway / Backend  │
│                  │  (Docker:8000) │  AuthN/AuthZ, RAG Logic │
│                  └───┬────┬───┬───┘                         │
│                      │    │   │                             │
│              ┌───────┘    │   └──────────┐                  │
│              ▼            ▼              ▼                  │
│        ┌──────────┐ ┌──────────┐  ┌──────────────┐          │
│        │ SUPABASE │ │  REDIS   │  │  OPENROUTER  │          │
│        │ (Cloud)  │ │ (Docker: │  │   (Cloud)    │          │
│        │•Postgres │ │   6379)  │  │•LLM Gateway  │          │
│        │•pgvector │ │•Queue    │  │•BYOK Keys    │          │
│        │•Storage  │ │•Cache    │  │•Model Route  │          │
│        └──────────┘ │•RateLim  │  └──────────────┘          │
│                     └─────┬────┘                            │
│                           │                                 │
│                     ┌─────▼──────┐                          │
│                     │   WORKER   │ Background Processing    │
│                     │  (Docker)  │ PDF Ingest, Chunk, Embed │
│                     └────────────┘                          │
│                                                             │
│                     ┌────────────┐                          │
│                     │ LANGSMITH  │ LLM Observability        │
│                     │  (Cloud)   │ Traces, Latency, Evals   │
│                     └────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Core Components & Responsibilities

| Component | Technology | Responsibility | Hosting Model |
| :--- | :--- | :--- | :--- |
| **Identity Provider** | Clerk | Authentication, passwordless/OAuth, MFA, session management, organization memberships. | Cloud (SaaS) |
| **Frontend** | Next.js 15+ (App Router), TypeScript, Tailwind CSS | UI, client routing, Clerk auth state, document management views, chat with citations. | Container (Port 3000) |
| **Backend API** | FastAPI, Pydantic v2, Python 3.11 | JWT verification, RBAC enforcement, query orchestration, REST endpoints, structured logging. | Container (Port 8000) |
| **Database & Vectors** | Supabase (PostgreSQL 15+ with `pgvector`) | Relational metadata (orgs, users, documents, conversations), dense embeddings, Full-Text Search (tsvector). | Cloud (Supabase Managed) |
| **Object Storage** | Supabase Storage (S3-compatible) | Secure, private storage for original uploaded PDF files. | Cloud (Supabase Managed) |
| **Cache & Queue** | Redis 7 | Asynchronous job queues, sliding-window rate limiting, session cache. | Container (Port 6379) |
| **Background Worker** | Python 3.11 (Arq / Redis worker) | Asynchronous PDF extraction, structure-aware chunking, embedding generation, batch vector inserts. | Container |
| **LLM Gateway** | OpenRouter | Multi-model access (OpenAI, Anthropic, Google, DeepSeek) with BYOK (Bring Your Own Key) & fallback. | Cloud (API) |
| **Observability** | LangSmith | LLM tracing, retrieval scoring, agent tool call inspection, latency breakdowns. | Cloud (API) |

---

## 3. Security Architecture & Threat Model

### 3.1 Strict Multi-Tenant Isolation
- Every core database table includes a `tenant_id` (organization ID) column.
- The `tenant_id` is **never accepted from client request bodies or query parameters**.
- The backend derives the `tenant_id` server-side from the verified Clerk JWT session token.
- Every database query without exception includes `WHERE tenant_id = :current_tenant_id`.

### 3.2 Authentication vs. Authorization
- **Authentication (AuthN - "Who are you?"):** Delegated entirely to Clerk. Clerk issues cryptographically signed JWTs verifying the user identity and active organization.
- **Authorization (AuthZ - "What can you do?"):** Enforced strictly by FastAPI dependency injection. Roles (`Owner`, `Admin`, `Member`, `Viewer`) determine permission to upload, delete, view, or manage API keys.

### 3.3 BYOK (Bring Your Own Key) Security
- Users supply their own OpenRouter API key.
- Keys are passed via encrypted headers or encrypted at rest with AES-256-GCM.
- Keys are used ephemerally in-memory and **never logged, never output to traces, and never sent to LangSmith**.

### 3.4 Storage Privacy
- The Supabase Storage bucket `documents` is configured as **private**.
- Documents are never accessible via public URLs.
- Document access requires backend mediation with tenant verification before generating short-lived signed URLs.

---

## 4. Ingestion & Retrieval Pipeline

### Ingestion Flow
1. **Upload:** User posts PDF via Next.js to `/api/documents/upload`.
2. **Acceptance:** FastAPI validates file type/size, stores raw PDF in Supabase Storage, creates a `PENDING` document record, pushes job to Redis queue, and returns `202 Accepted`.
3. **Worker Processing:**
   - Worker picks up job from Redis.
   - Extracts text and page coordinates using PyMuPDF.
   - Applies structure-aware chunking (~500 tokens with 10% overlap).
   - Generates vector embeddings for each chunk.
   - Inserts chunks and vectors into Supabase pgvector in a single database transaction.
   - Marks document status as `READY`.

### Retrieval Flow (Hybrid Search + Reranking)
1. **Query:** User submits natural language question.
2. **Dual-Route Retrieval:**
   - **Dense Semantic Search:** Query is embedded and matched via pgvector cosine distance (`<=>`).
   - **Sparse Lexical Search:** Query matches full-text keywords using PostgreSQL `tsvector` / `websearch_to_tsquery`.
3. **Reciprocal Rank Fusion (RRF):** Merges top semantic and lexical candidates into unified pool.
4. **Cross-Encoder Reranking:** Reranks candidates for contextual relevance to produce the final top-k chunks.
5. **Generation & Grounding:** LLM generates answer strictly citing retrieved chunk sources `[Document, Page X]`.

---

## 5. Architectural Tradeoffs & Decisions

### Why Supabase pgvector over Dedicated Vector DBs (e.g., Pinecone, Qdrant)?
- **Atomic Transactions:** Document metadata and vector chunks are deleted or updated within the same ACID transaction.
- **Unified Filtering:** Pre-filtering by `tenant_id` and metadata uses native SQL indexes without cross-system synchronizations.
- **Operational Simplicity:** Avoids managing multiple database vendors during development and deployment.

### Why Clerk over Supabase Auth?
- **Separation of Concerns:** Auth logic and database storage are decoupled. Switching or modifying the database layer will not compromise or interrupt identity management.
- **Enterprise Ready:** Clerk provides first-class organization switching, multi-factor authentication, and user impersonation for customer support.

### Why Redis for Queues over PostgreSQL Polling?
- Polling PostgreSQL tables at high frequency introduces unnecessary read lock contention and disk I/O.
- Redis provides sub-millisecond in-memory queueing, atomic counters for rate limiting, and pub/sub capabilities.
