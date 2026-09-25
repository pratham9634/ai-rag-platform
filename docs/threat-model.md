# Enterprise Agentic RAG Platform — STRIDE Threat Model

## 1. System Assets & Security Objectives

| Asset | Confidentiality | Integrity | Availability | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Enterprise Documents (PDFs)** | **Critical** | **High** | **High** | Proprietary corporate policies, employee data, financial reports stored in Supabase Storage. |
| **Document Vectors & Chunks** | **Critical** | **High** | **High** | 384-dimensional embeddings and text chunks in PostgreSQL `pgvector`. |
| **BYOK User API Keys** | **Critical** | **Critical** | **Medium** | Tenant OpenRouter credentials passed for LLM generation. |
| **Chat History & Citations** | **High** | **Medium** | **High** | Conversation threads and citations recorded in PostgreSQL. |
| **System Prompts & Agent Logic** | **Medium** | **Critical** | **High** | Routing prompts, relevance evaluators, and system instructions. |

---

## 2. Threat Actors & Capabilities

1. **External Anonymous Attacker:** Unauthenticated internet user attempting to bypass CORS, execute denial-of-service attacks, or probe API endpoints for unauthenticated access.
2. **Malicious Tenant User (Tenant A):** Authenticated user belonging to Organization A attempting to read, search, or delete Organization B's confidential documents (BOLA / IDOR).
3. **Prompt Injection Adversary:** User uploading malicious PDFs or submitting crafted chat prompts designed to hijack LLM behavior, extract system prompts, or exfiltrate BYOK keys.
4. **Insider / Infrastructure Observer:** System administrators, cloud APM tools (e.g. LangSmith), or log collectors inspecting raw HTTP requests or application output.

---

## 3. STRIDE Threat Analysis & Mitigation Matrix

### 3.1 Spoofing (Identity & Tenant Spoofing)
* **Threat:** An attacker sends `X-Tenant-ID: tenant-victim` in headers to impersonate another organization.
* **Impact:** Unauthorized access to victim tenant's documents and chat threads.
* **Mitigation:** In production, `tenant_id` is derived exclusively from cryptographically verified Clerk JWT session tokens (`org_id` claim). Client-provided tenant headers are disregarded.

### 3.2 Tampering (Data & Prompt Tampering)
* **Threat 1:** An attacker uploads a modified executable disguised as a `.pdf` file.
  - *Mitigation:* The API reads the file header and strictly validates the `%PDF-` magic-byte signature before passing the byte buffer to PyMuPDF.
* **Threat 2 (Indirect Prompt Injection):** A malicious document contains commands instructing the agent to ignore grounding rules and fabricate answers.
  - *Mitigation:* All chunk context is enclosed in `<untrusted_document_context>` XML tags with closing tags neutralized (`&lt;/untrusted_document_context&gt;`). The system prompt explicitly commands the model to treat all enclosed text as untrusted passive data.

### 3.3 Repudiation (Auditability)
* **Threat:** A tenant administrator deletes an enterprise document and denies performing the action.
* **Impact:** Loss of audit trail and forensic accountability.
* **Mitigation:** Every document upload, deletion, and chat query logs structured metadata containing `tenant_id`, `user_id`, document UUID, and timestamp (with sensitive credentials scrubbed).

### 3.4 Information Disclosure (Secret & Cross-Tenant Leakage)
* **Threat 1 (BYOK Leakage):** User OpenRouter keys (`sk-or-v1-...`) leak into application logs, error messages, or LangSmith traces.
  - *Mitigation:* In-memory ephemeral key handling; custom regex `SensitiveDataFilter` installed on root/Uvicorn loggers; keys omitted from trace payloads.
* **Threat 2 (Cross-Tenant Retrieval):** A semantic search query from Tenant A returns vector chunks owned by Tenant B.
  - *Mitigation:* Mathematical tenant isolation enforced in SQLAlchemy: `WHERE tenant_id = :tenant_id` is mandatory on all pgvector similarity queries and PostgreSQL FTS lookups.
* **Threat 3 (Stack Trace Leakage):** A 500 error exposes database credentials or internal file paths to the client.
  - *Mitigation:* Global FastAPI exception handlers suppress raw tracebacks and return sanitized RFC 7807 JSON error responses.

### 3.5 Denial of Service (Resource Exhaustion)
* **Threat 1:** An attacker floods the `/api/chat/stream` endpoint with thousands of concurrent requests, burning LLM tokens and exhausting backend connections.
  - *Mitigation:* Sliding-window rate limiter restricts requests to 30 req/min per tenant.
* **Threat 2 (Decompression Bomb):** An attacker uploads a tiny PDF that decompresses into gigabytes of RAM during parsing.
  - *Mitigation:* 10 MB maximum upload file size; PyMuPDF stream parsing enforces page-level memory limits.

### 3.6 Elevation of Privilege (RBAC Bypass)
* **Threat:** A user with role `org:viewer` attempts to call `POST /api/documents/upload` or `DELETE /api/documents/{id}`.
* **Impact:** Unauthorized modification or deletion of corporate knowledge bases.
* **Mitigation:** FastAPI dependency `require_role(["admin", "org:admin"])` strictly verifies the user's Clerk role before endpoint logic executes, returning `HTTP 403 Forbidden` if unauthorized.
