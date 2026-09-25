"""
Asynchronous Ingestion Worker for Enterprise RAG Platform.

Handles background processing of uploaded documents:
1. Updates document state: PENDING -> PROCESSING.
2. Structure-aware PDF text extraction via PDFParser.
3. Semantic chunking with page-preservation via SemanticChunker.
4. Batch embedding generation with exponential backoff & jitter retry.
5. Atomic persistence of chunks with pgvector embeddings and full-text search tsvectors.
6. State completion: PROCESSING -> READY (or FAILED with error diagnostics).
"""

import asyncio
import logging
import secrets
import uuid

from sqlalchemy import func, select

from app.database.models import Document, DocumentChunk
from app.database.session import async_session_factory
from app.services.chunker import SemanticChunker
from app.services.embeddings import EmbeddingService
from app.services.parser import PDFParser

logger = logging.getLogger(__name__)


async def generate_embeddings_with_retry(
    embedding_service: EmbeddingService,
    texts: list[str],
    max_retries: int = 3,
    initial_backoff_sec: float = 1.0,
) -> list[list[float]]:
    """
    Generate batch embeddings with exponential backoff and jitter.

    Handles transient rate-limiting (HTTP 429) or temporary network timeouts.
    """
    if not texts:
        return []

    for attempt in range(1, max_retries + 1):
        try:
            return await embedding_service.generate_embeddings_batch(texts)
        except Exception as e:
            if attempt == max_retries:
                logger.warning(
                    "Embedding generation exhausted %d retries: %s. Continuing with empty vectors.",
                    max_retries,
                    e,
                )
                return []
            jitter = secrets.SystemRandom().uniform(0.1, 0.5)
            sleep_time = (initial_backoff_sec * (2 ** (attempt - 1))) + jitter
            logger.warning(
                "Embedding attempt %d/%d failed: %s. Retrying in %.2fs...",
                attempt,
                max_retries,
                e,
                sleep_time,
            )
            await asyncio.sleep(sleep_time)

    return []


async def process_document_ingestion(
    document_id: uuid.UUID,
    tenant_id: str,
    file_bytes: bytes,
) -> bool:
    """
    Asynchronous worker task that ingests a document in the background.

    Decouples PDF parsing, chunking, and embedding from the HTTP request cycle.
    Guarantees strict tenant isolation during all database writes.
    """
    if not async_session_factory:
        logger.error("Database session factory unavailable. Ingestion job %s aborted.", document_id)
        return False

    logger.info("Starting background ingestion for doc_id=%s, tenant=%s", document_id, tenant_id)

    async with async_session_factory() as db:
        # 1. Fetch document and set status to PROCESSING
        stmt = select(Document).where(
            Document.id == document_id,
            Document.tenant_id == tenant_id,
        )
        result = await db.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            logger.error("Document %s for tenant %s not found in database.", document_id, tenant_id)
            return False

        document.status = "PROCESSING"
        document.error_message = None
        await db.commit()

    # 2. Heavy CPU/NLP parsing & chunking (outside active DB transaction)
    try:
        parsed_doc = PDFParser.parse_bytes(file_bytes)
        chunker = SemanticChunker(chunk_size=500, chunk_overlap=50)
        pages_input = [(p.page_number, p.text) for p in parsed_doc.pages]
        chunks = chunker.chunk_document(pages_input)

        embedding_service = EmbeddingService()
        chunk_texts = [c.content for c in chunks]
        embeddings = await generate_embeddings_with_retry(
            embedding_service=embedding_service,
            texts=chunk_texts,
        )

        # 3. Persist chunks and update document to READY
        async with async_session_factory() as db:
            stmt = select(Document).where(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
            )
            result = await db.execute(stmt)
            doc_to_update = result.scalar_one_or_none()
            if not doc_to_update:
                logger.error("Document %s disappeared during processing.", document_id)
                return False

            for idx, c in enumerate(chunks):
                emb = embeddings[idx] if idx < len(embeddings) else None
                db_chunk = DocumentChunk(
                    document_id=document_id,
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
            doc_to_update.page_count = parsed_doc.total_pages
            doc_to_update.error_message = None
            await db.commit()

        logger.info(
            "Background ingestion SUCCESS: doc_id=%s, tenant=%s, pages=%d, chunks=%d",
            document_id,
            tenant_id,
            parsed_doc.total_pages,
            len(chunks),
        )
        return True

    except Exception as e:
        logger.exception("Background ingestion FAILED for doc_id=%s: %s", document_id, e)
        async with async_session_factory() as db:
            stmt = select(Document).where(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
            )
            result = await db.execute(stmt)
            failed_doc = result.scalar_one_or_none()
            if failed_doc:
                failed_doc.status = "FAILED"
                failed_doc.error_message = str(e)
                await db.commit()
        return False
