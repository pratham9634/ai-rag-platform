"""
Documents API Router.

Handles document upload, validation, parsing, chunking, and metadata retrieval.
Enforces multi-tenant data isolation, SHA-256 idempotency, asynchronous background
worker ingestion, and automated 7-day TTL data retention cleanup.
"""

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.ratelimit import RateLimiter
from app.auth.security import get_current_tenant_id, require_role
from app.database.models import Document
from app.database.session import get_db
from app.services.parser import InvalidPDFError, PDFEncryptedError, PDFParser
from app.workers.cleanup_service import cleanup_expired_documents
from app.workers.ingestion_worker import process_document_ingestion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Strict Resource Constraints
MAX_DOCUMENTS_PER_TENANT = 10
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per PDF
MAX_VAULT_STORAGE_BYTES = 100 * 1024 * 1024  # 100 MB total vault storage
MAX_CHUNKS_PER_TENANT = 1000
DEFAULT_TTL_DAYS = 7


# ── Schemas ──────────────────────────────────────────────────────────
class TenantUsageResponse(BaseModel):
    """Tenant document quota, storage consumption, and chunk capacity."""

    tenant_id: str
    document_count: int
    max_documents: int = MAX_DOCUMENTS_PER_TENANT
    storage_bytes: int
    max_storage_bytes: int = MAX_VAULT_STORAGE_BYTES
    storage_mb: float
    max_storage_mb: float = 100.0
    chunk_count: int
    max_chunks: int = MAX_CHUNKS_PER_TENANT
    retention_days: int = DEFAULT_TTL_DAYS
    oldest_document_expires_at: datetime | None = None


class DocumentResponse(BaseModel):
    """Document metadata response model."""

    id: str
    tenant_id: str
    filename: str
    file_size: int
    status: str
    total_pages: int | None = None
    total_chunks: int | None = None
    error_message: str | None = None
    file_hash: str | None = None
    expires_at: datetime | None = None
    created_at: datetime


class DocumentUploadResponse(BaseModel):
    """Response returned upon document upload submission."""

    document_id: str
    filename: str
    status: str
    total_pages: int | None = None
    total_chunks: int | None = None
    is_duplicate: bool = False
    message: str


class DocumentStatusResponse(BaseModel):
    """Real-time status check response for asynchronous ingestion tracking."""

    document_id: str
    filename: str
    status: str
    total_pages: int | None = None
    total_chunks: int | None = None
    error_message: str | None = None
    created_at: datetime
    expires_at: datetime | None = None


class DocumentCleanupResponse(BaseModel):
    """Response returned by TTL expiration cleanup maintenance."""

    expired_documents: int
    deleted_chunks: int
    message: str


# ── Endpoints ────────────────────────────────────────────────────────
@router.get(
    "/usage",
    response_model=TenantUsageResponse,
    summary="Get tenant document quota, vault storage, and chunk capacity",
)
async def get_tenant_usage(
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """Retrieve document count, vault storage bytes, and pgvector chunk counts for tenant."""
    docs_query = (
        select(Document)
        .where(Document.tenant_id == tenant_id, Document.status != "FAILED")
        .options(selectinload(Document.chunks))
        .order_by(Document.expires_at.asc())
    )
    res = await db.execute(docs_query)
    docs = res.scalars().all()

    doc_count = len(docs)
    total_bytes = sum(d.file_size for d in docs)
    total_chunks = sum(len(d.chunks) for d in docs)
    oldest_expiry = docs[0].expires_at if (docs and docs[0].expires_at) else None

    return TenantUsageResponse(
        tenant_id=tenant_id,
        document_count=doc_count,
        max_documents=MAX_DOCUMENTS_PER_TENANT,
        storage_bytes=total_bytes,
        max_storage_bytes=MAX_VAULT_STORAGE_BYTES,
        storage_mb=round(total_bytes / (1024 * 1024), 2),
        max_storage_mb=100.0,
        chunk_count=total_chunks,
        max_chunks=MAX_CHUNKS_PER_TENANT,
        retention_days=DEFAULT_TTL_DAYS,
        oldest_document_expires_at=oldest_expiry,
    )


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload and asynchronously ingest a PDF document",
    dependencies=[Depends(RateLimiter(requests_per_minute=20, scope="upload"))],
)
async def upload_document(
    file: Annotated[UploadFile, File(description="PDF document (max 10MB)")],
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    response: Response,
) -> Any:
    """
    Upload a PDF document for asynchronous background ingestion.

    - Validates magic bytes (%PDF-) and file size <= 10MB
    - Enforces tenant limits: max 10 PDFs, max 100MB vault storage
    - Computes SHA-256 digest for multi-tenant idempotency and deduplication
    - If already ingested for this tenant, skips redundant processing (HTTP 200)
    - If new, creates PENDING document record with 7-day TTL and dispatches worker (HTTP 202)
    """
    # 1. Validate file extension
    filename = file.filename or "unknown.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported.",
        )

    # 2. Read bytes and enforce size constraint
    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if file_size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed limit of {max_mb}MB.",
        )

    # 3. Magic-byte verification and encryption check
    try:
        PDFParser.validate_pdf_bytes(content)
    except PDFEncryptedError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e
    except InvalidPDFError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # 4. Check tenant document quota (max 10 PDFs)
    count_stmt = select(func.count(Document.id)).where(
        Document.tenant_id == tenant_id,
        Document.status != "FAILED",
    )
    count_res = await db.execute(count_stmt)
    raw_count = count_res.scalar()
    try:
        current_doc_count = int(raw_count) if raw_count is not None else 0
    except (TypeError, ValueError):
        current_doc_count = 0

    if current_doc_count >= MAX_DOCUMENTS_PER_TENANT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Workspace document quota reached: Maximum {MAX_DOCUMENTS_PER_TENANT} "
                "PDFs allowed. Please delete an older document to continue."
            ),
        )

    # 5. Check vault storage quota (max 100 MB)
    storage_stmt = select(func.coalesce(func.sum(Document.file_size), 0)).where(
        Document.tenant_id == tenant_id,
        Document.status != "FAILED",
    )
    storage_res = await db.execute(storage_stmt)
    raw_storage = storage_res.scalar()
    try:
        current_storage = int(raw_storage) if raw_storage is not None else 0
    except (TypeError, ValueError):
        current_storage = 0

    if current_storage + file_size > MAX_VAULT_STORAGE_BYTES:
        max_mb = MAX_VAULT_STORAGE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Vault storage quota exceeded: Maximum {max_mb}MB "
                "total allowed across all documents."
            ),
        )

    # 4. SHA-256 Digest for Idempotency & Deduplication
    file_hash = hashlib.sha256(content).hexdigest()

    # Check if exact file was already processed for this tenant
    dup_stmt = (
        select(Document)
        .where(
            Document.tenant_id == tenant_id,
            Document.file_hash == file_hash,
            Document.status == "READY",
        )
        .options(selectinload(Document.chunks))
    )
    dup_res = await db.execute(dup_stmt)
    existing_doc = dup_res.scalar_one_or_none()

    if existing_doc:
        logger.info(
            "Idempotency hit: tenant=%s already has READY document %s (hash=%s)",
            tenant_id,
            existing_doc.id,
            file_hash[:12],
        )
        response.status_code = status.HTTP_200_OK
        return DocumentUploadResponse(
            document_id=str(existing_doc.id),
            filename=existing_doc.filename,
            status="READY",
            total_pages=existing_doc.page_count,
            total_chunks=len(existing_doc.chunks),
            is_duplicate=True,
            message="Document already ingested for this tenant (idempotent duplicate skipped).",
        )

    # 5. Create PENDING document record with 7-day automated retention TTL
    doc_id = uuid.uuid4()
    storage_path = f"{tenant_id}/{doc_id}.pdf"
    expires_at = datetime.now(UTC) + timedelta(days=DEFAULT_TTL_DAYS)

    document = Document(
        id=doc_id,
        tenant_id=tenant_id,
        filename=filename,
        file_size=file_size,
        file_hash=file_hash,
        storage_path=storage_path,
        status="PENDING",
        expires_at=expires_at,
    )
    db.add(document)
    await db.commit()

    # 6. Dispatch asynchronous background worker
    background_tasks.add_task(
        process_document_ingestion,
        document_id=doc_id,
        tenant_id=tenant_id,
        file_bytes=content,
    )

    logger.info(
        "Accepted document for async ingestion: id=%s, tenant=%s, file_hash=%s",
        doc_id,
        tenant_id,
        file_hash[:12],
    )

    return DocumentUploadResponse(
        document_id=str(doc_id),
        filename=filename,
        status="PENDING",
        total_pages=None,
        total_chunks=None,
        is_duplicate=False,
        message="Document accepted for asynchronous background processing.",
    )


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="Check real-time processing status of a document",
)
async def get_document_status(
    document_id: uuid.UUID,
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """
    Check processing status of an asynchronously ingested document.

    Enforces strict multi-tenant isolation.
    """
    query = (
        select(Document)
        .where(Document.id == document_id, Document.tenant_id == tenant_id)
        .options(selectinload(Document.chunks))
    )
    result = await db.execute(query)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return DocumentStatusResponse(
        document_id=str(doc.id),
        filename=doc.filename,
        status=doc.status,
        total_pages=doc.page_count,
        total_chunks=len(doc.chunks),
        error_message=doc.error_message,
        created_at=doc.created_at,
        expires_at=doc.expires_at,
    )


@router.post(
    "/cleanup",
    response_model=DocumentCleanupResponse,
    summary="Purge expired documents past 7-day TTL (Admin only)",
)
async def trigger_document_cleanup(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[Any, Depends(require_role(["admin", "org:admin"]))],
) -> Any:
    """
    Manually trigger data retention TTL cleanup.

    Purges all documents and cascading chunk vectors where expires_at <= NOW().
    Restricted to Administrator role.
    """
    stats = await cleanup_expired_documents(db)
    return DocumentCleanupResponse(
        expired_documents=stats["expired_documents"],
        deleted_chunks=stats["deleted_chunks"],
        message=(
            f"Cleaned up {stats['expired_documents']} expired documents and "
            f"{stats['deleted_chunks']} vector chunks."
        ),
    )


@router.get(
    "",
    response_model=list[DocumentResponse],
    summary="List all documents for active tenant",
)
async def list_documents(
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """
    List all documents for the current tenant.

    Strict multi-tenant filter: WHERE tenant_id = :tenant_id.
    """
    query = (
        select(Document)
        .where(Document.tenant_id == tenant_id)
        .options(selectinload(Document.chunks))
        .order_by(Document.created_at.desc())
    )
    result = await db.execute(query)
    docs = result.scalars().all()

    return [
        DocumentResponse(
            id=str(d.id),
            tenant_id=d.tenant_id,
            filename=d.filename,
            file_size=d.file_size,
            status=d.status,
            total_pages=d.page_count,
            total_chunks=len(d.chunks),
            error_message=d.error_message,
            file_hash=d.file_hash,
            expires_at=d.expires_at,
            created_at=d.created_at,
        )
        for d in docs
    ]


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details by ID",
)
async def get_document(
    document_id: uuid.UUID,
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """
    Get a single document by ID, enforcing tenant isolation.

    Returns 404 if the document does not exist OR belongs to another tenant.
    """
    query = (
        select(Document)
        .where(Document.id == document_id, Document.tenant_id == tenant_id)
        .options(selectinload(Document.chunks))
    )
    result = await db.execute(query)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return DocumentResponse(
        id=str(doc.id),
        tenant_id=doc.tenant_id,
        filename=doc.filename,
        file_size=doc.file_size,
        status=doc.status,
        total_pages=doc.page_count,
        total_chunks=len(doc.chunks),
        error_message=doc.error_message,
        file_hash=doc.file_hash,
        expires_at=doc.expires_at,
        created_at=doc.created_at,
    )


@router.delete(
    "/{document_id}",
    summary="Delete document and remove all vector chunks (Admin only)",
)
async def delete_document(
    document_id: uuid.UUID,
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[Any, Depends(require_role(["admin", "org:admin"]))],
) -> dict[str, str]:
    """
    Delete a document and cascade remove all its chunk vectors.

    Strict multi-tenant isolation: WHERE id = :id AND tenant_id = :tenant_id.
    Enforces Role-Based Access Control (RBAC): Only Admin role permitted.
    """
    query = select(Document).where(
        Document.id == document_id,
        Document.tenant_id == tenant_id,
    )
    result = await db.execute(query)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    await db.delete(doc)
    await db.flush()

    return {"message": "Document and all chunks deleted successfully."}
