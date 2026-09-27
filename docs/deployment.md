# Enterprise Agentic RAG Platform — Production Deployment Runbook

> **Scope**: Production deployment guide for the Enterprise Multi-Tenant Agentic RAG Platform.  
> **Philosophy**: 100% Free-Tier / Practical Low-Cost portable architecture with zero vendor lock-in.

---

## 1. System Architecture & Topology

The production platform separates interactive user workloads from asynchronous background ingestion tasks:

```
                          ┌────────────────────────┐
                          │    Browser Client      │
                          └───────────┬────────────┘
                                      │
                 ┌────────────────────┴────────────────────┐
                 │                                         │
                 ▼                                         ▼
      ┌──────────────────────┐                  ┌──────────────────────┐
      │   Frontend (Next.js) │                  │  Backend API (FastAPI)│
      │  Vercel (Hobby Tier) │                  │  Render / Railway    │
      └──────────┬───────────┘                  └──────────┬───────────┘
                 │                                         │
                 │ Authenticate (JWT)                      ├──────────────────────────┐
                 ▼                                         │                          │
      ┌──────────────────────┐                             ▼                          ▼
      │      Clerk Auth      │                  ┌──────────────────────┐   ┌──────────────────────┐
      │  (10k MAUs Free)     │                  │  Ingestion Worker    │   │  Upstash Redis       │
      └──────────────────────┘                  │ (Render Background)  │   │  (TLS / Queue)       │
                                                └──────────┬───────────┘   └──────────────────────┘
                                                           │
                                                           ▼
                                                ┌──────────────────────┐
                                                │  Supabase Managed    │
                                                │  PostgreSQL 15       │
                                                │  + pgvector (Port 6543)│
                                                │  + Document Storage  │
                                                └──────────────────────┘
```

| Component | Target Provider | Free / Low-Cost Tier | Responsibility |
| :--- | :--- | :--- | :--- |
| **Frontend** | **Vercel** | Free Hobby Tier | Next.js 15 SSR, Tailwind UI, Streaming Chat, Document Management |
| **Backend API** | **Render / Railway** | Free / Starter | FastAPI ASGI Cluster, SSE Token Streaming, LangGraph Agent |
| **Background Worker** | **Render / Railway** | Free / Starter | Async PDF Ingestion, Text Chunking, 7-Day TTL Database Purge |
| **Database & Vector** | **Supabase** | Free (500MB DB + pgvector) | Multi-tenant schema, Dense Vector Search, FTS, Storage |
| **Cache & Queue** | **Upstash Redis** | Free (10k commands/day) | Ephemeral queue, Rate-limiting sliding windows |
| **Identity & RBAC** | **Clerk** | Free (10,000 MAUs) | Multi-tenant organizations, JWT claims, role management |
| **Distributed Tracing** | **LangSmith** | Free Developer Tier | Multi-tenant execution trace trees, node latency profiling |
| **LLM Inference** | **OpenRouter** | BYOK (or Free Models) | Dual-route generation, cross-encoder reranking, web search |

---

## 2. Pre-Deployment Configuration Checklist

### Step 1: Clerk Authentication Setup
1. Log into [Clerk Dashboard](https://dashboard.clerk.com) and create an application.
2. In **Organizations Settings**, enable **Allow users to create organizations**.
3. Under **API Keys**, collect:
   * `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (starts with `pk_live_` or `pk_test_`)
   * `CLERK_SECRET_KEY` (starts with `sk_live_` or `sk_test_`)

### Step 2: Supabase Database & Storage Setup
1. Log into [Supabase Dashboard](https://supabase.com/dashboard) and create a project.
2. Navigate to **SQL Editor** and execute the database migration:
   ```sql
   -- Enable pgvector extension
   CREATE EXTENSION IF NOT EXISTS vector;

   -- Create documents and document_chunks tables
   -- (Execute backend/app/database/init_db.py or schema definitions)
   ```
3. Navigate to **Storage** → Create a **Private** bucket named `documents`.
4. In **Project Settings** → **Database**:
   * Use **Connection Pooling (Supavisor)** on port **6543** (Transaction Mode).
   * Format: `postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres`

### Step 3: Upstash Redis (Managed Cloud TLS) Setup
1. Log into [Upstash Console](https://console.upstash.com) and create a Redis database.
2. Select your nearest cloud region.
3. Under **Connect**, copy the **UPSTASH_REDIS_REST_URL** or standard TLS connection string:
   * Format: `rediss://default:[password]@[endpoint].upstash.io:6379`
   * *Note: Notice the double `s` in `rediss://`, indicating secure TLS.*

---

## 3. Backend & Worker Deployment (Render Blueprint)

The repository provides [render.yaml](file:///c:/Users/prath/OneDrive/Desktop/project2/ai-rag-platform/render.yaml) for automated Infrastructure-as-Code deployment.

### Method A: Deploy via Render Blueprints (Recommended)
1. Fork or push this repository to GitHub.
2. In [Render Dashboard](https://dashboard.render.com), click **New +** → **Blueprint**.
3. Connect your repository. Render automatically reads `render.yaml` and provisions:
   * Web Service: `enterprise-rag-api`
   * Worker Service: `enterprise-rag-worker`
   * Redis Instance: `enterprise-rag-redis`
4. In the Render Dashboard, fill in the required environment variables:
   * `CLERK_SECRET_KEY`
   * `SUPABASE_URL`
   * `SUPABASE_SERVICE_ROLE_KEY`
   * `DATABASE_URL` (Supabase port 6543 connection pool string)
   * `BACKEND_CORS_ORIGINS` (Set to your Vercel frontend URL, e.g. `https://your-frontend.vercel.app`)

### Method B: Self-Hosted Production via Docker Compose
For VPS or dedicated server deployment (Ubuntu / Debian / EC2):
```bash
# 1. Clone repository
git clone https://github.com/pratham9634/ai-rag-platform.git
cd ai-rag-platform

# 2. Configure production secrets
cp .env.example .env
nano .env

# 3. Launch hardened containers
docker compose -f docker-compose.prod.yml up -d --build

# 4. Verify running health checks
docker compose -f docker-compose.prod.yml ps
```

---

## 4. Frontend Deployment (Vercel)

1. Log into [Vercel](https://vercel.com) and click **Add New** → **Project**.
2. Import the `ai-rag-platform` repository.
3. In **Root Directory**, select `frontend`.
4. Configure the **Environment Variables**:
   ```ini
   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
   NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
   NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
   NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/dashboard
   NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/dashboard
   NEXT_PUBLIC_API_URL=https://your-backend-api.onrender.com
   ```
5. Click **Deploy**. Vercel will build and deploy the Next.js standalone application.
6. Once deployed, copy your assigned Vercel URL (e.g. `https://enterprise-rag.vercel.app`) and add it to `BACKEND_CORS_ORIGINS` in your backend environment variables.

---

## 5. Post-Deployment Verification (Smoke Testing)

Run the automated smoke test suite against your live deployed backend:

```bash
python scripts/smoke_test.py --url https://your-backend-api.onrender.com
```

Expected output:
```text
======================================================================
ENTERPRISE RAG PLATFORM — SMOKE TEST SUITE
Target URL: https://your-backend-api.onrender.com
======================================================================
TEST NAME                          | STATUS | CODE  | LATENCY   | DETAILS
---------------------------------------------------------------------------
1. Root Welcome (/)                | PASS   | 200   | 180.2ms   | Version: 0.1.0
2. Liveness Probe (/health)        | PASS   | 200   | 45.1ms    | Status: healthy
3. Readiness Probe (/health/ready) | PASS   | 200   | 82.4ms    | Status: ready | DB: connected
4. SLA Metrics (/health/metrics)   | PASS   | 200   | 42.8ms    | Uptime: 360s
5. CORS Preflight (OPTIONS)        | PASS   | 200   | 50.1ms    | Allowed Origin: https://your-frontend.vercel.app
6. Auth Security Guardrail         | PASS   | 401   | 44.7ms    | Clean JSON, Zero Traceback Leakage
===========================================================================
Summary: 6/6 Tests Passed (100%)
```

---

## 6. Critical Scaling & Production Guardrails

### 1. Connection Pool Sizing (Supavisor Port 6543)
* **The Pitfall**: Direct connection to PostgreSQL port `5432` creates a persistent backend connection per ASGI worker. In a serverless or autoscaling cluster with 10 instances × 4 Uvicorn workers = 40 connections, exceeding Supabase's free tier max connections limit (typically 15–20).
* **The Solution**: Always route `DATABASE_URL` through port `6543` with `?sslmode=require`. Supavisor manages transaction-scoped multiplexing, allowing 500+ client requests to share 5–10 real PostgreSQL connections.

### 2. Zero-Downtime Rolling Deployments
* The API cluster uses health checks at `/health/ready`.
* During a rolling deployment:
  1. The new container is started in parallel.
  2. Orchestrator polls `/health/ready`. Traffic is NOT routed until database pools are warm and ready.
  3. Once healthy, traffic switches seamlessly.
  4. The old container receives `SIGTERM`, drains active SSE connections, and stops cleanly.

### 3. Asynchronous Worker Graceful Shutdown
* The ingestion worker handles `SIGINT` and `SIGTERM` signals via Python's `asyncio.Event`.
* When a worker is stopped or scaled down:
  1. It halts accepting new PDF ingestion tasks.
  2. In-flight database transactions finish committing.
  3. The 7-day TTL cleanup daemon is cancelled gracefully.
  4. The worker exits cleanly without leaving documents stuck in `PROCESSING` state.

---

## 7. Disaster Recovery & Rollback Playbook

1. **Stale/Failed Ingestion Cleanup**:
   If an unexpected infrastructure crash causes documents to remain in `PROCESSING` state:
   ```sql
   UPDATE documents
   SET status = 'FAILED', error_message = 'Worker node restart during ingestion'
   WHERE status = 'PROCESSING' AND updated_at < NOW() - INTERVAL '15 minutes';
   ```
2. **Instant Rollback**:
   * On Vercel: Click **Deployments** → Select prior healthy build → Click **Redeploy / Instant Rollback**.
   * On Render: Click **History** → Select previous commit → Click **Rollback**.
