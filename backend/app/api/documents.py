"""
Documents API Router.

Handles document upload, validation, parsing, chunking, and metadata retrieval.
Enforces multi-tenant data isolation on all operations.
"""

import logging
import uuid
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Document, DocumentChunk
from app.database.session import get_db
from app.services.chunker import SemanticChunker
from app.services.parser import InvalidPDFError, PDFEncryptedError, PDFParser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# 10 MB upload limit
MAX_FILE_SIZE = 10 * 1024 * 1024


# ── Schemas ──────────────────────────────────────────────────────────
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


class DocumentUploadResponse(BaseModel):
    """Response returned upon successful document upload and chunking."""

    document_id: str
    filename: str
    status: str
    total_pages: int
    total_chunks: int
    message: str


# ── Tenant Resolution Helper ─────────────────────────────────────────
def get_current_tenant_id(
    x_tenant_id: Annotated[
        str | None,
        Header(description="Tenant identifier (Derived from JWT in production)"),
    ] = None,
) -> str:
    """
    Extract active tenant_id.

    In Day 2-4, accepts the X-Tenant-ID header (fallback 'default-tenant').
    In Day 5, this will be replaced with verified Clerk JWT claims.
    """
    if not x_tenant_id or not x_tenant_id.strip():
        return "default-tenant"
    return x_tenant_id.strip()


# ── Endpoints ────────────────────────────────────────────────────────
@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a PDF document",
)
async def upload_document(
    file: Annotated[UploadFile, File(description="PDF document (max 10MB)")],
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """
    Upload a PDF document, validate magic bytes, parse pages, and chunk text.

    - Validates file type is PDF
    - Validates file size is <= 10MB
    - Parses text and preserves page citations
    - Chunks text using structure-aware semantic chunking
    - Inserts Document and Chunks in a single atomic transaction
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

    # 3. Validate magic bytes and parse PDF
    try:
        parsed_doc = PDFParser.parse_bytes(content)
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
    except Exception as e:
        logger.exception("Unexpected error while parsing PDF")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process PDF: {e}",
        ) from e

    # 4. Chunk document preserving page numbers
    chunker = SemanticChunker(chunk_size=500, chunk_overlap=50)
    pages_input = [(p.page_number, p.text) for p in parsed_doc.pages]
    chunks = chunker.chunk_document(pages_input)

    # 5. Persist to database in atomic transaction
    doc_id = uuid.uuid4()
    storage_path = f"{tenant_id}/{doc_id}.pdf"

    document = Document(
        id=doc_id,
        tenant_id=tenant_id,
        filename=filename,
        file_size=file_size,
        storage_path=storage_path,
        status="READY",
    )
    db.add(document)

    for c in chunks:
        db_chunk = DocumentChunk(
            document_id=doc_id,
            tenant_id=tenant_id,
            chunk_index=c.chunk_index,
            page_number=c.page_number,
            content=c.content,
            token_count=c.token_count,
        )
        db.add(db_chunk)

    await db.flush()

    logger.info(
        "Ingested document: id=%s, tenant=%s, pages=%d, chunks=%d",
        str(doc_id),
        tenant_id,
        parsed_doc.total_pages,
        len(chunks),
    )

    return DocumentUploadResponse(
        document_id=str(doc_id),
        filename=filename,
        status="READY",
        total_pages=parsed_doc.total_pages,
        total_chunks=len(chunks),
        message="Document uploaded and chunked successfully.",
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
            total_chunks=len(d.chunks),
            error_message=d.error_message,
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
        total_chunks=len(doc.chunks),
        error_message=doc.error_message,
    )
