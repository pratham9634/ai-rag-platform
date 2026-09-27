# Enterprise Scaling Architecture: 100k Daily Active Users (DAU)

This document outlines the architectural roadmap and system scaling strategy for the Enterprise Agentic RAG Platform, detailing how the system transitions from the Day 1–9 single-node containerized deployment to a resilient, multi-region, distributed architecture capable of handling **100,000 Daily Active Users (DAU)**.

---

## 1. Workload Projections & Capacity Model (100k DAU)

| Metric | Day 1–9 Baseline (Single Node) | 100k DAU Production Target | Scaling Strategy |
|---|---|---|---|
| **Daily Active Users (DAU)** | ~50 concurrent test users | 100,000 active enterprise users | Multi-tenant horizontal scaling |
| **Queries per Second (QPS)** | 1–5 QPS | **350 QPS average, 1,200 QPS peak** | Horizontally scaled FastAPI pods |
| **Document Ingestion** | 50 PDFs/day (~500 MB) | **15,000 PDFs/day (~150 GB/day)** | Distributed Celery worker pool |
| **pgvector Embeddings Stored** | ~50,000 chunks (~75 MB) | **45,000,000 chunks (~68 GB vectors)** | HNSW index partitioning & sharding |
| **P95 Latency Target** | < 2,500 ms | **< 1,200 ms (hybrid search + stream)** | Redis semantic cache + Read replicas |
| **Database Connections** | Max 20 concurrent | **2,500+ concurrent connections** | Supavisor / PgBouncer connection pooling |
| **Storage Retention** | 7-day automated TTL | Multi-tier retention (Hot 30d, Cold S3) | S3 Glacier archival + pgvector partition drops |

---

## 2. High-Level Distributed Architecture (100k DAU)

```mermaid
flowchart TD
    subgraph Client Tier
        Web[Web Browsers / Linear UI]
        Mobile[Mobile & Native Clients]
        API[Enterprise REST / SDK Clients]
    end

    subgraph Edge & Ingress Tier
        CF[Cloudflare Edge CDN / WAF]
        ALB[AWS Application Load Balancer / Nginx Ingress]
    end

    subgraph Compute Tier (Kubernetes EKS)
        subgraph FastAPI Ingress Cluster (Autoscaled 8-32 Pods)
            API1[FastAPI Pod 1]
            API2[FastAPI Pod 2]
            APIN[FastAPI Pod N]
        end

        subgraph Asynchronous Ingestion Cluster (KEDA Autoscaled)
            W1[Celery Worker 1 (PDF Parsing)]
            W2[Celery Worker 2 (Embedding)]
            WN[Celery Worker N (pgvector Bulk)]
        end
    end

    subgraph Caching & Messaging Tier
        RedisQ[(Redis Queue / Celery Broker)]
        RedisCache[(Redis Cluster: Semantic Cache & Rate Limits)]
    end

    subgraph Database Tier (PostgreSQL + pgvector)
        Supavisor[Supavisor / PgBouncer Connection Pooler]
        DB_Primary[(Postgres Primary: Writes & RLS)]
        DB_Replica1[(Read Replica 1: pgvector Search)]
        DB_Replica2[(Read Replica 2: Keyword BM25 Search)]
    end

    subgraph Storage Tier
        S3Hot[(AWS S3 / Supabase Storage: Hot PDFs)]
        S3Cold[(S3 Glacier: Compliance Archival)]
    end

    subgraph Inference & Observability
        OpenRouter[OpenRouter / Self-Hosted vLLM Cluster]
        Otel[OpenTelemetry Collector]
        Grafana[Prometheus + Grafana + LangSmith]
    end

    Web --> CF
    Mobile --> CF
    API --> CF
    CF --> ALB
    ALB --> API1 & API2 & APIN

    API1 & API2 & APIN --> RedisCache
    API1 & API2 & APIN --> RedisQ
    RedisQ --> W1 & W2 & WN

    API1 & API2 & APIN --> Supavisor
    W1 & W2 & WN --> Supavisor
    Supavisor --> DB_Primary
    DB_Primary -. Replication .-> DB_Replica1 & DB_Replica2

    W1 & W2 & WN --> S3Hot
    S3Hot -. 30-Day Lifecycle .-> S3Cold

    API1 & API2 & APIN --> OpenRouter
    API1 & API2 & APIN --> Otel
    Otel --> Grafana
```

---

## 3. Tier-by-Tier Scaling Strategies

### 3.1 Edge & Ingress Tier
- **Cloudflare Edge CDN & WAF**:
  - Global SSL termination and DDoS mitigation.
  - Edge caching of Next.js frontend static assets (HTML/CSS/JS/images) with 100% cache hit ratio for non-dynamic assets.
  - JWT token pre-validation using Cloudflare Workers to filter out unauthenticated requests before hitting backend pods.
- **Application Load Balancer (ALB)**:
  - Round-robin HTTP/2 and WebSocket/SSE streaming proxying.
  - Real-time health check probes pointing to `/health/live` and `/health/ready`.
  - Automatic cross-zone load balancing across 3 Availability Zones (AZs).

### 3.2 Compute Cluster (Kubernetes EKS / GKE)
- **FastAPI Horizontal Pod Autoscaler (HPA)**:
  - Base: 8 pods (2 vCPU, 4GB RAM each).
  - Peak autoscale: Up to 32 pods triggered when CPU utilization exceeds 70% or average latency exceeds 800ms.
  - Stateless architecture: No session affinity required; all conversation state is stored in Postgres with tenant isolation.
- **Asynchronous Ingestion Workers (Celery + KEDA)**:
  - Heavy PyMuPDF document parsing, semantic chunking, and embedding generation are completely decoupled from FastAPI request threads.
  - **KEDA (Kubernetes Event-driven Autoscaling)** monitors Redis queue length:
    - 0–50 documents queued: 4 workers.
    - 50–500 documents queued: 16 workers.
    - > 500 documents queued: 32 workers with GPU-assisted inference for local embedding models.

### 3.3 Database Tier (PostgreSQL + pgvector + Supavisor)
- **Supavisor / PgBouncer Connection Pooling**:
  - Eliminates Postgres connection exhaustion by pooling up to 10,000 client connections into a manageable pool of 150 persistent server connections in transaction mode (`pool_mode = transaction`).
- **Read Replicas & Read/Write Splitting**:
  - **Primary Node**: Handles document uploads, conversation creation, and message inserts.
  - **Read Replica 1 & 2**: Handles hybrid pgvector semantic search (`<->` cosine distance) and full-text keyword searches (`tsvector @@ plainto_tsquery`).
  - Read queries are automatically routed to replicas using SQLAlchemy's asynchronous read-write session routing engine.
- **HNSW Index Sharding & Partitioning**:
  - Chunks table is partitioned by `tenant_id` (Hash partitioning across 16 database partitions).
  - HNSW index build settings optimized for high recall:
    ```sql
    CREATE INDEX CONCURRENTLY idx_chunks_embedding_hnsw
    ON document_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 24, ef_construction = 128);
    ```

### 3.4 Distributed Semantic Caching (Redis Cluster)
- **Semantic Query Deduplication**:
  - Embeddings of incoming user queries are compared against recently asked queries in Redis.
  - If cosine similarity between a new query and a cached query within the same tenant is `> 0.98` and the document catalog has not changed, the cached synthesized response is returned in **< 45ms** without invoking the LLM.
- **Token Bucket Rate Limiting**:
  - Distributed Redis-backed rate limiting per tenant (e.g., 60 req/min for free tier, 600 req/min for enterprise tier).

### 3.5 Storage & Document Lifecycle Tier
- **Object Storage**:
  - Uploaded PDFs are stored in S3/Supabase Storage with bucket-level server-side encryption (AES-256).
- **Automated Lifecycle Policy**:
  - Hot tier: 0–7 days (fast retrieval, immediate re-indexing).
  - Warm tier: 8–30 days (infrequent access).
  - Cold tier: 30+ days (archived to S3 Glacier, vector embeddings pruned to maintain high HNSW index memory residency).

---

## 4. Cost Optimization Strategy (Enterprise Scale)

| Layer | Optimization Technique | Expected Monthly Savings |
|---|---|---|
| **LLM Inference** | Routing simple queries to free/open-source models (Llama 3.1 8B) and caching repetitive queries | ~65% reduction in API spend |
| **Embeddings** | Ingesting with `all-MiniLM-L6-v2` locally on worker nodes rather than external proprietary APIs | 100% free vector embeddings |
| **Compute** | Spot instances on AWS EKS for Celery ingestion workers with auto-termination | ~70% compute cost savings |
| **Postgres** | Partitioned drop of expired vectors vs individual DELETE rows (zero vacuum bloat) | 40% IOPS reduction |

---

## 5. Disaster Recovery & High Availability (HA)

- **Target RPO (Recovery Point Objective)**: < 1 minute (continuous WAL streaming to S3).
- **Target RTO (Recovery Time Objective)**: < 5 minutes (automated failover to secondary replica via Patroni / AWS Aurora Multi-AZ).
- **Chaos Engineering**: Automated weekly node termination in staging to verify LangGraph workflow resilience and graceful reconnection.
