"""
Unit and Integration Tests for Phase 8 Production Engineering & Workers.

Tests:
1. Multi-Tenant Idempotency: SHA-256 deduplication returns HTTP 200 with is_duplicate=True.
2. Cross-Tenant Isolation: Same file hash under Tenant B does NOT collide with Tenant A.
3. Document Status Polling: Status polling endpoint returns processing state and counts.
4. Asynchronous Ingestion State Transitions: PENDING -> PROCESSING -> READY.
5. Ingestion Worker Failure Handling: Malformed bytes transition status to FAILED with diagnostics.
6. Automated 7-Day TTL Cleanup: Expired documents and cascading chunks are purged.
7. Exponential Backoff & Jitter: Transient embedding errors retry gracefully.
"""

import hashlib
import io
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient

from app.database.models import Document, DocumentChunk
from app.database.session import get_db
from app.main import app
from app.workers.cleanup_service import cleanup_expired_documents
from app.workers.ingestion_worker import (
    generate_embeddings_with_retry,
    process_document_ingestion,
)


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provide a mock async database session for API and worker testing."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def make_dummy_pdf() -> bytes:
    """Generate minimal valid PDF byte string."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(
        fitz.Point(72, 72),
        "Enterprise RAG Policy Document Content For Worker Verification.",
    )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ── 1. Idempotency & SHA-256 Deduplication Tests ─────────────────────
def test_sha256_idempotency_detection(mock_db_session: AsyncMock) -> None:
    """Uploading an identical PDF under same tenant must return 200 with is_duplicate=True."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    pdf_bytes = make_dummy_pdf()
    file_hash = hashlib.sha256(pdf_bytes).hexdigest()
    doc_id = uuid.uuid4()
    existing_doc = Document(
        id=doc_id,
        tenant_id="tenant-alpha",
        filename="test.pdf",
        file_size=len(pdf_bytes),
        file_hash=file_hash,
        storage_path=f"tenant-alpha/{doc_id}.pdf",
        status="READY",
        page_count=1,
    )
    existing_doc.chunks = []

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_doc
    mock_db_session.execute.return_value = mock_result

    client = TestClient(app)
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        headers={"X-Tenant-ID": "tenant-alpha"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["is_duplicate"] is True
    assert data["document_id"] == str(doc_id)
    assert data["status"] == "READY"


def test_cross_tenant_deduplication_isolation(mock_db_session: AsyncMock) -> None:
    """Same file hash under Tenant B must NOT match Tenant A (strict isolation)."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    pdf_bytes = make_dummy_pdf()
    # Mocking DB query for Tenant B: no duplicate document found
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db_session.execute.return_value = mock_result

    with patch("app.api.documents.process_document_ingestion", new_callable=AsyncMock):
        client = TestClient(app)
        response = client.post(
            "/api/documents/upload",
            files={"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers={"X-Tenant-ID": "tenant-beta"},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 202
    data = response.json()
    assert data["is_duplicate"] is False
    assert data["status"] == "PENDING"


def test_document_status_polling_endpoint(mock_db_session: AsyncMock) -> None:
    """GET /api/documents/{id}/status should return real-time status and chunk count."""

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        tenant_id="tenant-alpha",
        filename="policy.pdf",
        file_size=2048,
        status="PROCESSING",
        page_count=3,
        error_message=None,
    )
    doc.created_at = datetime.now(UTC)
    doc.chunks = [MagicMock(), MagicMock(), MagicMock()]

    result_doc = MagicMock()
    result_doc.scalar_one_or_none.return_value = doc
    mock_db_session.execute.return_value = result_doc

    client = TestClient(app)
    response = client.get(
        f"/api/documents/{doc_id}/status",
        headers={"X-Tenant-ID": "tenant-alpha"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == str(doc_id)
    assert data["status"] == "PROCESSING"
    assert data["total_pages"] == 3
    assert data["total_chunks"] == 3


# ── 2. Asynchronous Ingestion Worker Tests ────────────────────────────
@pytest.mark.asyncio
async def test_ingestion_worker_success() -> None:
    """Worker should successfully process PDF, chunk text, and set READY status."""
    pdf_bytes = make_dummy_pdf()
    doc_id = uuid.uuid4()
    tenant_id = "tenant-worker-success"

    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        filename="handbook.pdf",
        file_size=len(pdf_bytes),
        storage_path=f"{tenant_id}/{doc_id}.pdf",
        status="PENDING",
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_result
    added_objects = []
    mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
    mock_db.commit = AsyncMock()

    class MockAsyncContextManager:
        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mgr = MockAsyncContextManager()
    with (
        patch("app.workers.ingestion_worker.async_session_factory", return_value=mgr),
        patch("app.workers.ingestion_worker.EmbeddingService") as mock_emb_cls,
    ):
        mock_emb_inst = AsyncMock()
        mock_emb_inst.generate_embeddings_batch.return_value = [[0.05] * 1536]
        mock_emb_cls.return_value = mock_emb_inst

        success = await process_document_ingestion(
            document_id=doc_id,
            tenant_id=tenant_id,
            file_bytes=pdf_bytes,
        )

    assert success is True
    assert doc.status == "READY"
    assert doc.page_count == 1
    assert doc.error_message is None
    assert len(added_objects) >= 1
    assert all(isinstance(obj, DocumentChunk) for obj in added_objects)
    assert added_objects[0].tenant_id == tenant_id


@pytest.mark.asyncio
async def test_ingestion_worker_failure_handling() -> None:
    """Worker should mark FAILED and record error_message on unparseable bytes."""
    corrupted_bytes = b"%PDF-1.4 Corrupted content that will fail parsing"
    doc_id = uuid.uuid4()
    tenant_id = "tenant-worker-failure"

    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        filename="corrupted.pdf",
        file_size=len(corrupted_bytes),
        storage_path=f"{tenant_id}/{doc_id}.pdf",
        status="PENDING",
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_result
    mock_db.commit = AsyncMock()

    class MockAsyncContextManager:
        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mgr = MockAsyncContextManager()
    with patch("app.workers.ingestion_worker.async_session_factory", return_value=mgr):
        success = await process_document_ingestion(
            document_id=doc_id,
            tenant_id=tenant_id,
            file_bytes=corrupted_bytes,
        )

    assert success is False
    assert doc.status == "FAILED"
    assert doc.error_message is not None


# ── 3. Automated 7-Day TTL Cleanup Tests ──────────────────────────────
@pytest.mark.asyncio
async def test_ttl_cleanup_purges_only_expired_records() -> None:
    """Cleanup service must query expires_at <= NOW() and delete matching records."""
    mock_db = AsyncMock()
    expired_doc_id = uuid.uuid4()

    # Step 1: Query for expired IDs
    result_expired = MagicMock()
    result_expired.scalars.return_value.all.return_value = [expired_doc_id]

    # Step 2: Count child chunks
    result_chunks = MagicMock()
    result_chunks.scalars.return_value.all.return_value = [uuid.uuid4(), uuid.uuid4()]

    # Step 3: Delete expired documents
    result_delete = MagicMock()

    mock_db.execute.side_effect = [result_expired, result_chunks, result_delete]
    mock_db.commit = AsyncMock()

    stats = await cleanup_expired_documents(mock_db)

    assert stats["expired_documents"] == 1
    assert stats["deleted_chunks"] == 2
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ttl_cleanup_noop_when_no_expired_records() -> None:
    """Cleanup service must gracefully return zeroes when no documents have expired."""
    mock_db = AsyncMock()
    result_empty = MagicMock()
    result_empty.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = result_empty

    stats = await cleanup_expired_documents(mock_db)

    assert stats["expired_documents"] == 0
    assert stats["deleted_chunks"] == 0
    mock_db.commit.assert_not_called()


# ── 4. Exponential Backoff Retry Tests ────────────────────────────────
@pytest.mark.asyncio
async def test_embedding_retry_recovers_after_transient_failure() -> None:
    """generate_embeddings_with_retry should retry and succeed when service recovers."""
    mock_service = AsyncMock()
    mock_service.generate_embeddings_batch.side_effect = [
        Exception("Rate limit 429"),
        [[0.1, 0.2, 0.3]],
    ]

    results = await generate_embeddings_with_retry(
        embedding_service=mock_service,
        texts=["test query"],
        max_retries=3,
        initial_backoff_sec=0.01,
    )

    assert results == [[0.1, 0.2, 0.3]]
    assert mock_service.generate_embeddings_batch.call_count == 2
