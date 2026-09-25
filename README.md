# Enterprise Agentic RAG Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-15+-black.svg?logo=next.js&logoColor=white)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An enterprise-grade, multi-tenant, agentic Retrieval-Augmented Generation (RAG) platform. Features hybrid retrieval (dense vector embeddings + sparse lexical search), reciprocal rank fusion, cross-encoder reranking, multi-tenant RBAC isolation, BYOK (Bring Your Own Key) model routing, and asynchronous background document ingestion.

---

## 🏗️ Architecture

```
User (Browser)
     │
     ▼
[ Clerk Hosted Auth ] ──── (Identity / Session / MFA)
     │
     ▼
[ Next.js 15+ Frontend ] (:3000)
     │ HTTP + Bearer JWT
     ▼
[ FastAPI Backend API ] (:8000)
     ├── Supabase PostgreSQL + pgvector (Documents, Metadata, Chunks)
     ├── Supabase Storage (Private raw PDFs)
     ├── Redis 7 (Job Queue, Rate Limiting, Ephemeral State)
     ├── Background Worker (Asynchronous parsing, chunking, embedding)
     ├── OpenRouter Gateway (BYOK LLM routing)
     └── LangSmith (Observability & Tracing)
```

---

## ⚡ Tech Stack

- **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS, `@clerk/nextjs`
- **Backend:** FastAPI, Python 3.11, Pydantic v2, Uvicorn
- **Database & Storage:** Supabase PostgreSQL with `pgvector`, Supabase Storage (S3-compatible)
- **Caching & Queues:** Redis 7
- **AI & RAG:** PyMuPDF, Sentence-Transformers / OpenRouter Embeddings, Reciprocal Rank Fusion, Cross-Encoder Reranking
- **Auth & Multi-Tenancy:** Clerk (Identity Provider) + FastAPI (Server-side RBAC enforcement)
- **DevOps & Containers:** Docker, Docker Compose, GitHub Actions

---

## 🚀 Getting Started

### 1. Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Node.js 20+](https://nodejs.org/)
- [Python 3.11+](https://www.python.org/)
- A free [Clerk](https://clerk.com) account and [Supabase](https://supabase.com) project

### 2. Clone and Setup Environment Variables
```bash
git clone https://github.com/pratham9634/ai-rag-platform.git
cd ai-rag-platform

# Copy environment variable template
cp .env.example .env
```
Fill in your credentials in `.env` (Clerk keys, Supabase credentials, Redis URL).

### 3. Run with Docker Compose
```bash
docker compose up --build
```
- **Frontend:** `http://localhost:3000`
- **Backend API:** `http://localhost:8000`
- **API Health Check:** `http://localhost:8000/health`
- **API Docs (Development only):** `http://localhost:8000/docs`

### 4. Running Locally for Development

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

## 📁 Repository Structure

```text
ai-rag-platform/
├── backend/
│   ├── app/
│   │   ├── api/             # API routes (health, docs, etc.)
│   │   ├── auth/            # Clerk JWT verification & tenant context
│   │   ├── database/        # Database models & connections
│   │   ├── services/        # Business logic & RAG pipeline
│   │   ├── workers/         # Background queue workers
│   │   ├── config.py        # Pydantic Settings
│   │   └── main.py          # FastAPI application factory
│   ├── tests/               # Backend pytest test suite
│   ├── Dockerfile
│   ├── pyproject.toml       # Ruff, MyPy, and Pytest configuration
│   └── requirements.txt
├── frontend/
│   ├── app/                 # Next.js App Router (dashboard, auth pages)
│   ├── middleware.ts        # Clerk route protection middleware
│   ├── Dockerfile
│   └── package.json
├── docs/
│   └── architecture.md      # Detailed system architecture & security spec
├── evaluation/
│   └── datasets/            # Evaluation benchmarks
├── docker-compose.yml       # Multi-service container orchestration
├── .env.example             # Documented environment variable template
├── questions.txt            # Architectural & AI interview preparation guide
└── README.md
```

---

## 🛡️ Security Features

- **Strict Multi-Tenancy:** `tenant_id` is derived from cryptographic JWT claims and enforced on every database query.
- **BYOK (Bring Your Own Key):** User LLM keys are held ephemerally in memory or encrypted at rest; never exposed in logs or observability pipelines.
- **Private Document Store:** Direct public access to uploaded files is forbidden; access is governed by backend authorization and short-lived signed URLs.
- **Strict CORS & Headers:** Non-permissive CORS in production; security headers enabled.

---

## 📖 Roadmap (10-Day Plan)

- [x] **Day 1:** Foundation, Architecture, Scaffolding, Health Check & Docker
- [ ] **Day 2:** Document Ingestion Pipeline, PDF Parsing & Chunking
- [ ] **Day 3:** Hybrid Retrieval (Vector + Full-Text Search) & Reranking
- [ ] **Day 4:** Agentic Workflows & Tool Calling
- [ ] **Day 5:** Multi-Tenancy & Role-Based Access Control (RBAC)
- [ ] **Day 6:** Security Hardening & Prompt Injection Defense
- [ ] **Day 7:** Comprehensive Evaluation Benchmark Suite
- [ ] **Day 8:** Production Engineering (Workers, Rate Limiting, LangSmith)
- [ ] **Day 9:** CI/CD & Cloud Deployment
- [ ] **Day 10:** UI Polish, Admin Console & Interview Prep
