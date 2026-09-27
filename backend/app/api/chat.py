"""
Chat and Agentic RAG API Router with Persistent Memory.

Provides endpoints for:
1. Multi-tenant and user-isolated conversation management
2. ContextManager-driven RAG with recent window, summary, and semantic memories
3. Real-time Server-Sent Events (SSE) token streaming
4. Async non-blocking memory extraction and incremental summarization
5. User memory inspection and deactivation
"""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated, Any

import tiktoken
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.graph import AgentWorkflow
from app.api.ratelimit import RateLimiter
from app.auth.security import AuthenticatedUser, get_current_user
from app.database.models import Conversation, Message, UserMemory
from app.database.session import async_session_factory, get_db
from app.services.context_manager import ContextManager
from app.services.memory_cache import MemoryCacheService
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

_tokenizer = None
try:
    _tokenizer = tiktoken.get_encoding("cl100k_base")
except Exception as exc:
    logger.debug("Tiktoken encoding not initialized: %s", exc)

_background_tasks: set[asyncio.Task[Any]] = set()


def _schedule_background_task(coro: Any) -> None:
    """Schedule async task and retain reference to prevent GC premature cleanup (RUF006)."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    if _tokenizer:
        try:
            return len(_tokenizer.encode(text))
        except Exception as exc:
            logger.debug("Token count estimation error: %s", exc)
    return len(text) // 4


# ── Schemas ──────────────────────────────────────────────────────────
class CreateConversationRequest(BaseModel):
    """Payload to initiate a new chat thread."""

    title: str = Field(default="New Conversation", max_length=255)


class ConversationResponse(BaseModel):
    """Conversation summary metadata."""

    id: str
    tenant_id: str
    user_id: str = "unknown_user"
    title: str
    summary: str | None = None
    summary_version: int = 0
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class CitationResponse(BaseModel):
    """Grounded citation source reference."""

    chunk_id: str
    document_id: str
    page_number: int
    relevance_score: float | None = None


class MessageResponse(BaseModel):
    """Individual conversation message."""

    id: str
    conversation_id: str
    user_id: str = "unknown_user"
    role: str
    content: str
    citations: list[CitationResponse] | None = None
    created_at: datetime


class ChatQueryRequest(BaseModel):
    """Request payload for an agentic RAG query."""

    conversation_id: str | None = None
    query: str = Field(..., min_length=1, max_length=4000)
    model: str | None = None
    top_k: int | None = None
    enable_web_search: bool | None = None
    history: list[dict[str, str]] | None = None


class ChatQueryResponse(BaseModel):
    """Full synchronous response from the agentic RAG state machine."""

    conversation_id: str
    query: str
    answer: str
    citations: list[CitationResponse]
    route_taken: str


class UserMemoryResponse(BaseModel):
    """Declarative user memory item."""

    id: str
    user_id: str
    memory_type: str
    content: str
    importance: float
    confidence: float
    is_active: bool
    created_at: datetime


# ── Background Post-Processing ───────────────────────────────────────
async def _async_memory_post_processing(
    tenant_id: str,
    user_id: str,
    conv_id: uuid.UUID,
    user_msg_id: uuid.UUID,
    user_query: str,
    assistant_answer: str,
    api_key_override: str | None = None,
) -> None:
    """
    Non-blocking async task executed after the response is returned.

    1. Analyzes latest turn with LLM to extract durable facts/preferences.
    2. Semantically deduplicates and supersedes older conflicting memories.
    3. Increments and updates conversation summary if message count >= threshold.
    """
    if async_session_factory is None:
        return

    try:
        memory_service = MemoryService()

        # 1. Extract candidate durable memories
        candidates = await memory_service.extract_memories_from_turn(
            user_content=user_query,
            assistant_content=assistant_answer,
            api_key_override=api_key_override,
        )

        async with async_session_factory() as bg_db:
            if candidates:
                await memory_service.save_or_update_memories(
                    db=bg_db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    memories=candidates,
                    source_conv_id=conv_id,
                    source_msg_id=user_msg_id,
                    api_key_override=api_key_override,
                )

            # 2. Check if running summary needs update
            await memory_service.summarize_conversation_if_needed(
                db=bg_db,
                conv_id=conv_id,
                tenant_id=tenant_id,
                user_id=user_id,
                api_key_override=api_key_override,
            )

    except Exception as exc:
        logger.warning(
            "Background memory extraction/summarization error (conv=%s, user=%s): %s",
            conv_id,
            user_id,
            exc,
        )


# ── Conversation Management Endpoints ────────────────────────────────
@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation thread",
)
async def create_conversation(
    payload: CreateConversationRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """Create a new conversation thread isolated to tenant and user."""
    conv_id = uuid.uuid4()
    now = datetime.now(UTC)
    conversation = Conversation(
        id=conv_id,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        title=payload.title,
        summary=None,
        summary_version=0,
        created_at=now,
        updated_at=now,
    )
    db.add(conversation)
    await db.flush()

    return ConversationResponse(
        id=str(conversation.id),
        tenant_id=conversation.tenant_id,
        user_id=conversation.user_id,
        title=conversation.title,
        summary=conversation.summary,
        summary_version=conversation.summary_version,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=0,
    )


@router.get(
    "/conversations",
    response_model=list[ConversationResponse],
    summary="List all conversations for the authenticated user",
)
async def list_conversations(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """Retrieve all conversations belonging to the current tenant and user."""
    query = (
        select(Conversation)
        .where(
            Conversation.tenant_id == user.tenant_id,
            Conversation.user_id == user.user_id,
        )
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.updated_at.desc())
    )
    result = await db.execute(query)
    convs = result.scalars().all()

    return [
        ConversationResponse(
            id=str(c.id),
            tenant_id=c.tenant_id,
            user_id=c.user_id,
            title=c.title,
            summary=c.summary,
            summary_version=c.summary_version,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=len(c.messages),
        )
        for c in convs
    ]


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
    summary="Get conversation message history",
)
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """Retrieve chronologically ordered messages for a verified conversation."""
    conv_query = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.tenant_id == user.tenant_id,
        Conversation.user_id == user.user_id,
    )
    conv_result = await db.execute(conv_query)
    if not conv_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    msg_query = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.tenant_id == user.tenant_id,
        )
        .order_by(Message.created_at.asc())
    )
    msg_result = await db.execute(msg_query)
    messages = msg_result.scalars().all()

    return [
        MessageResponse(
            id=str(m.id),
            conversation_id=str(m.conversation_id),
            user_id=m.user_id,
            role=m.role,
            content=m.content,
            citations=[CitationResponse(**c) for c in (m.citations or [])],
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation and all its messages",
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a conversation thread and all associated messages."""
    conv_query = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.tenant_id == user.tenant_id,
        Conversation.user_id == user.user_id,
    )
    conv_result = await db.execute(conv_query)
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    # Delete all associated messages
    await db.execute(
        delete(Message).where(
            Message.conversation_id == conversation_id,
            Message.tenant_id == user.tenant_id,
        )
    )
    await db.delete(conv)
    await db.flush()

    # Invalidate Redis cache
    cache = MemoryCacheService()
    await cache.invalidate_recent_messages(str(conversation_id))
    await cache.invalidate_summary(str(conversation_id))


# ── User Memory Endpoints ────────────────────────────────────────────
@router.get(
    "/memories",
    response_model=list[UserMemoryResponse],
    summary="List active long-term memories for the user",
)
async def list_user_memories(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """List all active durable memories stored for the authenticated user."""
    stmt = (
        select(UserMemory)
        .where(
            UserMemory.tenant_id == user.tenant_id,
            UserMemory.user_id == user.user_id,
            UserMemory.is_active.is_(True),
        )
        .order_by(UserMemory.updated_at.desc())
    )
    res = await db.execute(stmt)
    memories = res.scalars().all()

    return [
        UserMemoryResponse(
            id=str(m.id),
            user_id=m.user_id,
            memory_type=m.memory_type,
            content=m.content,
            importance=m.importance,
            confidence=m.confidence,
            is_active=m.is_active,
            created_at=m.created_at,
        )
        for m in memories
    ]


@router.delete(
    "/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate or remove a user memory",
)
async def delete_user_memory(
    memory_id: uuid.UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Mark a user memory as inactive/superseded."""
    stmt = select(UserMemory).where(
        UserMemory.id == memory_id,
        UserMemory.tenant_id == user.tenant_id,
        UserMemory.user_id == user.user_id,
    )
    res = await db.execute(stmt)
    memory = res.scalar_one_or_none()
    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found.",
        )

    memory.is_active = False
    memory.updated_at = datetime.now(UTC)
    await db.commit()

    cache = MemoryCacheService()
    await cache.invalidate_user_memories(user.user_id)


# ── Agentic Query & Streaming Endpoints ──────────────────────────────
@router.post(
    "/query",
    response_model=ChatQueryResponse,
    summary="Execute agentic RAG query (synchronous)",
    dependencies=[Depends(RateLimiter(requests_per_minute=30, scope="chat"))],
)
async def chat_query(
    payload: ChatQueryRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_openrouter_api_key: Annotated[
        str | None,
        Header(alias="X-OpenRouter-API-Key", description="Optional BYOK OpenRouter API key"),
    ] = None,
    x_byok_api_key: Annotated[
        str | None,
        Header(alias="X-BYOK-API-Key", description="Optional BYOK OpenRouter API key from UI"),
    ] = None,
) -> Any:
    """
    Execute full agentic RAG workflow with persistent memory:
    1. Authenticate user and validate conversation ownership.
    2. Record user prompt.
    3. Concurrently retrieve recent messages, summary, long-term memory, history, and RAG.
    4. Compile token-budgeted context.
    5. Run LangGraph workflow.
    6. Persist assistant response.
    7. Trigger background memory extraction & summarization.
    """
    effective_api_key = x_byok_api_key or x_openrouter_api_key

    # 1. Resolve conversation
    conv_id: uuid.UUID
    if payload.conversation_id:
        try:
            conv_id = uuid.UUID(payload.conversation_id)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid conversation_id UUID format.",
            ) from err

        cq = select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.tenant_id == user.tenant_id,
            Conversation.user_id == user.user_id,
        )
        cr = await db.execute(cq)
        if not cr.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            )
    else:
        conv_id = uuid.uuid4()
        title_snippet = payload.query[:40] + ("..." if len(payload.query) > 40 else "")
        now = datetime.now(UTC)
        new_conv = Conversation(
            id=conv_id,
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            title=title_snippet,
            summary=None,
            summary_version=0,
            created_at=now,
            updated_at=now,
        )
        db.add(new_conv)
        await db.flush()

    # 2. Record user message
    now = datetime.now(UTC)
    user_msg_id = uuid.uuid4()
    user_tokens = _estimate_tokens(payload.query)
    user_msg = Message(
        id=user_msg_id,
        conversation_id=conv_id,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        role="user",
        content=payload.query,
        token_count=user_tokens,
        created_at=now,
    )
    db.add(user_msg)

    # 3. Assemble compiled context via ContextManager
    context_mgr = ContextManager()
    compiled_ctx = await context_mgr.build_context(
        db=db,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        conv_id=conv_id if payload.conversation_id else None,
        query=payload.query,
        top_k=payload.top_k,
        api_key_override=effective_api_key,
    )

    # Use client-provided history override if supplied, else context manager history
    chat_history = payload.history or compiled_ctx.recent_messages

    # 4. Run Agent Workflow
    workflow = AgentWorkflow(db=db)
    final_state = await workflow.run(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        query=payload.query,
        api_key_override=effective_api_key,
        model_override=payload.model,
        top_k=payload.top_k,
        chat_history=chat_history,
        memory_context=compiled_ctx.formatted_context,
    )

    answer = final_state.get("generation", "No response generated.")
    citations = final_state.get("citations", compiled_ctx.citations)
    route = final_state.get("route", "retrieve")

    # 5. Record assistant message with citations
    assistant_tokens = _estimate_tokens(answer)
    assistant_msg = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        role="assistant",
        content=answer,
        citations=citations,
        token_count=assistant_tokens,
        created_at=datetime.now(UTC),
    )
    db.add(assistant_msg)
    await db.commit()

    # 6. Invalidate recent messages cache for next turn
    cache = MemoryCacheService()
    await cache.invalidate_recent_messages(str(conv_id))

    # 7. Asynchronously trigger long-term memory extraction & summary updates
    _schedule_background_task(
        _async_memory_post_processing(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            conv_id=conv_id,
            user_msg_id=user_msg_id,
            user_query=payload.query,
            assistant_answer=answer,
            api_key_override=effective_api_key,
        )
    )

    return ChatQueryResponse(
        conversation_id=str(conv_id),
        query=payload.query,
        answer=answer,
        citations=[CitationResponse(**c) for c in citations],
        route_taken=route,
    )


@router.post(
    "/stream",
    summary="Stream agentic RAG response tokens via Server-Sent Events (SSE)",
    dependencies=[Depends(RateLimiter(requests_per_minute=30, scope="chat"))],
)
async def chat_stream(
    payload: ChatQueryRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_openrouter_api_key: Annotated[
        str | None,
        Header(alias="X-OpenRouter-API-Key"),
    ] = None,
    x_byok_api_key: Annotated[
        str | None,
        Header(alias="X-BYOK-API-Key"),
    ] = None,
) -> StreamingResponse:
    """
    Stream tokens in real-time using Server-Sent Events (SSE) with persistent memory:
    - Recent conversation window
    - Running conversation summary
    - Semantic user memories
    - Historical conversation recall
    - Grounded RAG citations
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # 1. Status: Routing
            routing_status = {
                "type": "status",
                "stage": "routing",
                "message": "Analyzing query intent & routing...",
            }
            yield f"data: {json.dumps(routing_status)}\n\n"
            await asyncio.sleep(0.04)

            # 2. Status: Context & Retrieval
            retrieval_status = {
                "type": "status",
                "stage": "retrieving",
                "message": "Searching knowledge base & recalling memories...",
            }
            yield f"data: {json.dumps(retrieval_status)}\n\n"

            # 3. Resolve conversation
            conv_id: uuid.UUID
            is_new_conv = True

            if payload.conversation_id:
                try:
                    conv_id = uuid.UUID(payload.conversation_id)
                    conv_check = await db.execute(
                        select(Conversation).where(
                            Conversation.id == conv_id,
                            Conversation.tenant_id == user.tenant_id,
                            Conversation.user_id == user.user_id,
                        )
                    )
                    if conv_check.scalar_one_or_none():
                        is_new_conv = False
                    else:
                        conv_id = uuid.uuid4()
                except ValueError:
                    conv_id = uuid.uuid4()
            else:
                conv_id = uuid.uuid4()

            effective_api_key = x_byok_api_key or x_openrouter_api_key

            # 4. ContextManager concurrent retrieval
            context_mgr = ContextManager()
            compiled_ctx = await context_mgr.build_context(
                db=db,
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                conv_id=conv_id if not is_new_conv else None,
                query=payload.query,
                top_k=payload.top_k,
                api_key_override=effective_api_key,
            )

            chat_history = payload.history or compiled_ctx.recent_messages

            # 5. Execute LangGraph agentic workflow
            workflow = AgentWorkflow(db=db)
            final_state = await workflow.run(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                query=payload.query,
                api_key_override=effective_api_key,
                model_override=payload.model,
                top_k=payload.top_k,
                chat_history=chat_history,
                memory_context=compiled_ctx.formatted_context,
            )

            answer = final_state.get("generation", "")
            citations = final_state.get("citations", compiled_ctx.citations)
            route = final_state.get("route", "retrieve")

            # 6. Status: Generating
            gen_status = {
                "type": "status",
                "stage": "generating",
                "message": "Synthesizing grounded answer with citations...",
            }
            yield f"data: {json.dumps(gen_status)}\n\n"
            await asyncio.sleep(0.04)

            # 7. Persist messages and conversation
            now = datetime.now(UTC)
            user_msg_id = uuid.uuid4()
            if async_session_factory is not None:
                try:
                    async with async_session_factory() as persist_db:
                        if is_new_conv:
                            new_conv = Conversation(
                                id=conv_id,
                                tenant_id=user.tenant_id,
                                user_id=user.user_id,
                                title=payload.query[:60]
                                + ("..." if len(payload.query) > 60 else ""),
                                summary=None,
                                summary_version=0,
                                created_at=now,
                                updated_at=now,
                            )
                            persist_db.add(new_conv)
                        else:
                            conv_obj = await persist_db.get(Conversation, conv_id)
                            if conv_obj:
                                conv_obj.updated_at = now

                        # Save user message
                        user_msg = Message(
                            id=user_msg_id,
                            conversation_id=conv_id,
                            tenant_id=user.tenant_id,
                            user_id=user.user_id,
                            role="user",
                            content=payload.query,
                            token_count=_estimate_tokens(payload.query),
                            created_at=now,
                        )
                        persist_db.add(user_msg)

                        # Save assistant message with citations
                        assistant_msg = Message(
                            id=uuid.uuid4(),
                            conversation_id=conv_id,
                            tenant_id=user.tenant_id,
                            user_id=user.user_id,
                            role="assistant",
                            content=answer,
                            citations=citations,
                            token_count=_estimate_tokens(answer),
                            created_at=now,
                        )
                        persist_db.add(assistant_msg)
                        await persist_db.commit()

                        # Invalidate recent cache
                        cache = MemoryCacheService()
                        await cache.invalidate_recent_messages(str(conv_id))

                        # Schedule async memory extraction and summarization
                        _schedule_background_task(
                            _async_memory_post_processing(
                                tenant_id=user.tenant_id,
                                user_id=user.user_id,
                                conv_id=conv_id,
                                user_msg_id=user_msg_id,
                                user_query=payload.query,
                                assistant_answer=answer,
                                api_key_override=effective_api_key,
                            )
                        )
                except Exception as persist_err:
                    logger.error(
                        "Failed to persist chat message in stream: %s",
                        persist_err,
                        exc_info=True,
                    )

            # 8. Send route and citations metadata
            yield f"data: {json.dumps({'type': 'route', 'route': route})}\n\n"
            if citations:
                yield f"data: {json.dumps({'type': 'citations', 'citations': citations})}\n\n"

            # 9. Stream tokens with micro-pacing
            words = answer.split(" ")
            for i, word in enumerate(words):
                token = word if i == len(words) - 1 else word + " "
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                await asyncio.sleep(0.02)

            # 10. Send completion event
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': str(conv_id)})}\n\n"

        except Exception as err:
            logger.error("Error in chat_stream event_generator: %s", err, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(err)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
