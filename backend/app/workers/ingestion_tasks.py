"""
Celery Asynchronous Ingestion Tasks for Enterprise RAG Platform.

Processes uploaded documents out-of-process via RabbitMQ worker pool:
1. Updates document state: PENDING -> PROCESSING.
2. Fetches binary directly from Object Storage (Supabase / S3).
3. Parses structure (PDFParser / Text / Markdown / CSV / Code).
4. Multi-Strategy chunking via ChunkerFactory.
5. Batch dense embedding generation with exponential backoff & jitter.
6. Atomic database persistence with pgvector embeddings and full-text search tsvectors.
7. Updates document state: PROCESSING -> READY (or routes to DLQ on terminal failure).
"""

import asyncio
import logging
import uuid
from typing import Any

from sqlalchemy import func, select

from app.database.models import Document, DocumentChunk
from app.database.session import async_session_factory
from app.services.chunker import ChunkerFactory
from app.services.embeddings import EmbeddingService
from app.services.parser import PDFParser
from app.services.storage import StorageService
from app.workers.celery_app import celery_app
from app.workers.ingestion_worker import generate_embeddings_with_retry

logger = logging.getLogger(__name__)


async def _execute_ingestion_pipeline(
    doc_id: uuid.UUID,
    tenant_id: str,
    storage_path: str,
    filename: str,
    raw_bytes: bytes | None = None,
) -> bool:
    """Internal asynchronous worker pipeline implementation."""
    if not async_session_factory:
        logger.error("Database session factory unavailable. Ingestion job %s aborted.", doc_id)
        return False

    logger.info(
        "Executing Celery ingestion pipeline: doc_id=%s, tenant=%s, path=%s",
        doc_id,
        tenant_id,
        storage_path,
    )

    # 1. Update Document status -> PROCESSING
    async with async_session_factory() as db:
        stmt = select(Document).where(Document.id == doc_id, Document.tenant_id == tenant_id)
        res = await db.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            logger.error("Document %s for tenant %s not found in DB.", doc_id, tenant_id)
            return False
        doc.status = "PROCESSING"
        doc.error_message = None
        await db.commit()

    # 2. Acquire file bytes from Storage or memory
    file_bytes = raw_bytes
    if not file_bytes:
        try:
            storage = StorageService()
            file_bytes = await storage.download_file_bytes(storage_path)
        except Exception as e:
            logger.error("Failed to download file from storage for doc_id=%s: %s", doc_id, e)
            async with async_session_factory() as db:
                stmt = select(Document).where(
                    Document.id == doc_id, Document.tenant_id == tenant_id
                )
                res = await db.execute(stmt)
                doc = res.scalar_one_or_none()
                if doc:
                    doc.status = "FAILED"
                    doc.error_message = f"Storage download error: {e}"
                    await db.commit()
            return False

    # 3. Parse & Chunk with Multi-Strategy ChunkerFactory
    try:
        pages_input: list[tuple[int, str]] = []
        total_pages = 1

        is_pdf = filename.lower().endswith(".pdf") or file_bytes.startswith(b"%PDF-")
        if is_pdf:
            parsed = PDFParser.parse_bytes(file_bytes)
            total_pages = parsed.total_pages
            pages_input = [(p.page_number, p.text) for p in parsed.pages]
        else:
            # Plain text, Markdown, CSV, or Source Code
            try:
                decoded_text = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                decoded_text = file_bytes.decode("latin-1")
            pages_input = [(1, decoded_text)]

        chunker = ChunkerFactory.get_chunker(filename=filename, chunk_size=500, chunk_overlap=50)
        chunks = chunker.chunk_document(pages_input)

        if not chunks:
            logger.warning("No chunks generated for doc_id=%s (file empty or non-text)", doc_id)

        # 4. Generate batch embeddings with retry
        embedding_service = EmbeddingService()
        chunk_texts = [c.content for c in chunks]
        embeddings = await generate_embeddings_with_retry(
            embedding_service=embedding_service,
            texts=chunk_texts,
        )

        # 5. Persist chunks and update document to READY
        async with async_session_factory() as db:
            stmt = select(Document).where(Document.id == doc_id, Document.tenant_id == tenant_id)
            res = await db.execute(stmt)
            doc_to_update = res.scalar_one_or_none()
            if not doc_to_update:
                logger.error("Document %s disappeared during processing.", doc_id)
                return False

            for idx, c in enumerate(chunks):
                emb = embeddings[idx] if idx < len(embeddings) else None
                db_chunk = DocumentChunk(
                    document_id=doc_id,
                    tenant_id=tenant_id,
                    chunk_index=c.chunk_index,
                    page_number=c.page_number,
                    content=c.content,
                    token_count=c.token_count,
                    embedding=emb,
                    tsv=func.to_tsvector("english", c.content),
                )
                db.add(db_chunk)

            doc_to_update.status = "READY"
            doc_to_update.page_count = total_pages
            doc_to_update.error_message = None
            await db.commit()

        logger.info(
            "Celery ingestion SUCCESS: doc_id=%s, pages=%d, chunks=%d, strategy=%s",
            doc_id,
            total_pages,
            len(chunks),
            chunker.__class__.__name__,
        )
        return True

    except Exception as e:
        logger.exception("Ingestion pipeline failed for doc_id=%s: %s", doc_id, e)
        async with async_session_factory() as db:
            stmt = select(Document).where(Document.id == doc_id, Document.tenant_id == tenant_id)
            res = await db.execute(stmt)
            doc = res.scalar_one_or_none()
            if doc:
                doc.status = "FAILED"
                doc.error_message = str(e)
                await db.commit()
        raise


@celery_app.task(  # type: ignore[misc]
    bind=True,
    name="tasks.ingest_document",
    max_retries=3,
    default_retry_delay=15,
)
def ingest_document_task(
    self: Any,
    document_id: str,
    tenant_id: str,
    storage_path: str,
    filename: str,
) -> bool:
    """
    Celery background worker entrypoint.

    Executes document ingestion with automatic retries and DLQ routing.
    """
    doc_uuid = uuid.UUID(document_id)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                _execute_ingestion_pipeline(doc_uuid, tenant_id, storage_path, filename),
                loop,
            )
            return future.result()
        return loop.run_until_complete(
            _execute_ingestion_pipeline(doc_uuid, tenant_id, storage_path, filename)
        )
    except Exception as exc:
        logger.warning(
            "Celery task failed for document_id=%s (attempt %d/%d): %s",
            document_id,
            self.request.retries + 1,
            self.max_retries,
            exc,
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=15 * (2**self.request.retries)) from exc
        # Terminal failure: re-raise so message routes to dead-letter queue (DLQ)
        raise exc from exc
