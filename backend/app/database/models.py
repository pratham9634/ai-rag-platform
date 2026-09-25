"""
Database Models for Enterprise RAG Platform.

Defines SQLAlchemy ORM models with strict multi-tenancy enforcement.
Every data entity contains a tenant_id to guarantee data isolation.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy database models."""

    pass


class Document(Base):
    """
    Uploaded Document record.

    Represents an original document uploaded by a tenant.
    Tracks ingestion lifecycle status from PENDING to READY or FAILED.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Organization ID derived server-side from JWT claims",
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="File size in bytes",
    )
    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        doc="Private Supabase Storage path: {tenant_id}/{doc_id}.pdf",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="PENDING",
        doc="Ingestion state: PENDING, PROCESSING, READY, FAILED",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Error details if ingestion failed",
    )
    file_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="SHA-256 hex digest of original file for idempotency and deduplication",
    )
    page_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Total number of pages extracted from document",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Automated 7-day TTL expiration timestamp for automated data retention",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Cascading delete: deleting a document removes all its chunks atomically
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )

    __table_args__ = (
        Index("ix_documents_tenant_status", "tenant_id", "status"),
        Index("ix_documents_tenant_created", "tenant_id", "created_at"),
        Index("ix_documents_tenant_file_hash", "tenant_id", "file_hash"),
        Index("ix_documents_expires_at", "expires_at"),
    )


class DocumentChunk(Base):
    """
    Extracted text chunk from a document.

    Stores the chunk text, source page number for citations,
    token count, and will host the vector embedding (pgvector).
    """

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Denormalized tenant_id for high-speed tenant-filtered vector search",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Zero-based ordering index within the document",
    )
    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="1-based source page number in the original PDF for grounding citations",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Extracted chunk text",
    )
    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Number of BPE tokens in this chunk",
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536),
        nullable=True,
        doc="1536-dimensional dense embedding vector for semantic search",
    )
    tsv: Mapped[Any | None] = mapped_column(
        TSVECTOR,
        nullable=True,
        doc="PostgreSQL tsvector for sparse lexical full-text search",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="chunks",
    )

    __table_args__ = (
        Index("ix_chunks_tenant_doc", "tenant_id", "document_id"),
        Index("ix_chunks_tenant_page", "tenant_id", "page_number"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Conversation(Base):
    """
    Multi-tenant chat conversation thread.

    Groups multi-turn messages and preserves context under a specific tenant.
    """

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Organization ID derived server-side from JWT claims",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="New Conversation",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    __table_args__ = (Index("ix_conversations_tenant_updated", "tenant_id", "updated_at"),)


class Message(Base):
    """
    A single turn within a multi-tenant conversation thread.

    Stores role (user/assistant), message text, and grounded citations list.
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Denormalized tenant_id for high-speed tenant-filtered message queries",
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Message sender role: user, assistant, system",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Grounding citations list: doc_id, filename, page_number, chunk_id",
    )
    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
    )

    __table_args__ = (
        Index("ix_messages_tenant_conv", "tenant_id", "conversation_id"),
        Index("ix_messages_tenant_created", "tenant_id", "created_at"),
    )
