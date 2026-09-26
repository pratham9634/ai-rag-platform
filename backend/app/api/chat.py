"""
Chat and Agentic RAG API Router.

Provides endpoints for conversation management, agentic question answering,
and Server-Sent Events (SSE) token streaming with citation grounding.
Enforces multi-tenant data isolation on all operations.
"""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.graph import AgentWorkflow
from app.api.ratelimit import RateLimiter
from app.auth.security import get_current_tenant_id
from app.database.models import Conversation, Message
from app.database.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Schemas ──────────────────────────────────────────────────────────
class CreateConversationRequest(BaseModel):
    """Payload to initiate a new chat thread."""

    title: str = Field(default="New Conversation", max_length=255)


class ConversationResponse(BaseModel):
    """Conversation summary metadata."""

    id: str
    tenant_id: str
    title: str
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


class ChatQueryResponse(BaseModel):
    """Full synchronous response from the agentic RAG state machine."""

    conversation_id: str
    query: str
    answer: str
    citations: list[CitationResponse]
    route_taken: str


# ── Conversation Management Endpoints ────────────────────────────────
@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation thread",
)
async def create_conversation(
    payload: CreateConversationRequest,
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """Create a new conversation thread for the active tenant."""
    conv_id = uuid.uuid4()
    now = datetime.now(UTC)
    conversation = Conversation(
        id=conv_id,
        tenant_id=tenant_id,
        title=payload.title,
        created_at=now,
        updated_at=now,
    )
    db.add(conversation)
    await db.flush()

    return ConversationResponse(
        id=str(conversation.id),
        tenant_id=conversation.tenant_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=0,
    )


@router.get(
    "/conversations",
    response_model=list[ConversationResponse],
    summary="List all conversations for the tenant",
)
async def list_conversations(
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """Retrieve all conversations belonging to the current tenant."""
    query = (
        select(Conversation)
        .where(Conversation.tenant_id == tenant_id)
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.updated_at.desc())
    )
    result = await db.execute(query)
    convs = result.scalars().all()

    return [
        ConversationResponse(
            id=str(c.id),
            tenant_id=c.tenant_id,
            title=c.title,
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
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """Retrieve chronologically ordered messages for a conversation."""
    # Verify tenant owns conversation
    conv_query = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.tenant_id == tenant_id,
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
            Message.tenant_id == tenant_id,
        )
        .order_by(Message.created_at.asc())
    )
    msg_result = await db.execute(msg_query)
    messages = msg_result.scalars().all()

    return [
        MessageResponse(
            id=str(m.id),
            conversation_id=str(m.conversation_id),
            role=m.role,
            content=m.content,
            citations=[CitationResponse(**c) for c in (m.citations or [])],
            created_at=m.created_at,
        )
        for m in messages
    ]


# ── Agentic Query & Streaming Endpoints ──────────────────────────────
@router.post(
    "/query",
    response_model=ChatQueryResponse,
    summary="Execute agentic RAG query (synchronous)",
    dependencies=[Depends(RateLimiter(requests_per_minute=30, scope="chat"))],
)
async def chat_query(
    payload: ChatQueryRequest,
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
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
    Execute full agentic RAG workflow:
    1. Resolve or create conversation thread.
    2. Route query (direct response vs retrieval).
    3. If retrieve: fetch candidates, grade relevance, rewrite if needed, and synthesize answer.
    4. Save user prompt and assistant response to database.
    5. Return grounded response with citations.
    """
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

        # Verify conversation belongs to tenant
        cq = select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.tenant_id == tenant_id,
        )
        cr = await db.execute(cq)
        if not cr.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            )
    else:
        # Create a new conversation automatically with query snippet as title
        conv_id = uuid.uuid4()
        title_snippet = payload.query[:40] + ("..." if len(payload.query) > 40 else "")
        now = datetime.now(UTC)
        new_conv = Conversation(
            id=conv_id,
            tenant_id=tenant_id,
            title=title_snippet,
            created_at=now,
            updated_at=now,
        )
        db.add(new_conv)
        await db.flush()

    # 2. Record user message
    now = datetime.now(UTC)
    user_msg = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        tenant_id=tenant_id,
        role="user",
        content=payload.query,
        created_at=now,
    )
    db.add(user_msg)

    effective_api_key = x_byok_api_key or x_openrouter_api_key

    # 3. Run Agent Workflow
    workflow = AgentWorkflow(db=db)
    final_state = await workflow.run(
        tenant_id=tenant_id,
        query=payload.query,
        api_key_override=effective_api_key,
        model_override=payload.model,
        top_k=payload.top_k,
    )

    answer = final_state.get("generation", "No response generated.")
    citations = final_state.get("citations", [])
    route = final_state.get("route", "retrieve")

    # 4. Record assistant message with citations
    assistant_msg = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        tenant_id=tenant_id,
        role="assistant",
        content=answer,
        citations=citations,
        created_at=datetime.now(UTC),
    )
    db.add(assistant_msg)
    await db.flush()

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
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
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
    Stream tokens in real-time using Server-Sent Events (SSE).

    SSE Events:
    - `data: {"type": "route", "route": "retrieve"}`
    - `data: {"type": "citations", "citations": [...]}`
    - `data: {"type": "token", "content": "..."}`
    - `data: {"type": "done", "conversation_id": "..."}`
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # 1. Immediate initial feedback to client
            status_init = {
                "type": "status",
                "stage": "routing",
                "message": "Analyzing query intent & routing...",
            }
            yield f"data: {json.dumps(status_init)}\n\n"
            await asyncio.sleep(0.04)

            # 2. Status update for retrieval
            status_retrieval = {
                "type": "status",
                "stage": "retrieving",
                "message": "Searching knowledge base with hybrid vectors & keywords...",
            }
            yield f"data: {json.dumps(status_retrieval)}\n\n"

            effective_api_key = x_byok_api_key or x_openrouter_api_key

            # 3. Execute LangGraph agentic workflow
            workflow = AgentWorkflow(db=db)
            final_state = await workflow.run(
                tenant_id=tenant_id,
                query=payload.query,
                api_key_override=effective_api_key,
                model_override=payload.model,
                top_k=payload.top_k,
            )

            answer = final_state.get("generation", "")
            citations = final_state.get("citations", [])
            route = final_state.get("route", "retrieve")

            # 4. Status update for generation
            status_gen = {
                "type": "status",
                "stage": "generating",
                "message": "Synthesizing grounded answer with citations...",
            }
            yield f"data: {json.dumps(status_gen)}\n\n"
            await asyncio.sleep(0.04)

            # 5. Resolve or create persistent conversation
            conv_id: uuid.UUID
            is_new_conv = True
            if payload.conversation_id:
                try:
                    conv_id = uuid.UUID(payload.conversation_id)
                    conv_check = await db.execute(
                        select(Conversation).where(
                            Conversation.id == conv_id,
                            Conversation.tenant_id == tenant_id,
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

            now = datetime.now(UTC)
            if is_new_conv:
                new_conv = Conversation(
                    id=conv_id,
                    tenant_id=tenant_id,
                    title=payload.query[:60] + ("..." if len(payload.query) > 60 else ""),
                    created_at=now,
                    updated_at=now,
                )
                db.add(new_conv)
            else:
                conv_obj = await db.get(Conversation, conv_id)
                if conv_obj:
                    conv_obj.updated_at = now

            # Save user message
            user_msg = Message(
                id=uuid.uuid4(),
                conversation_id=conv_id,
                tenant_id=tenant_id,
                role="user",
                content=payload.query,
                created_at=now,
            )
            db.add(user_msg)

            # Save assistant message with citations
            assistant_msg = Message(
                id=uuid.uuid4(),
                conversation_id=conv_id,
                tenant_id=tenant_id,
                role="assistant",
                content=answer,
                citations=citations,
                created_at=now,
            )
            db.add(assistant_msg)
            await db.flush()

            # 6. Send route and citations metadata
            yield f"data: {json.dumps({'type': 'route', 'route': route})}\n\n"
            if citations:
                yield f"data: {json.dumps({'type': 'citations', 'citations': citations})}\n\n"

            # 7. Stream generation tokens word by word with human-like micro-pacing
            words = answer.split(" ")
            for i, word in enumerate(words):
                token = word if i == len(words) - 1 else word + " "
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                await asyncio.sleep(0.02)

            # 8. Send completion event
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': str(conv_id)})}\n\n"

        except Exception as err:
            logger.error(f"Error in chat_stream event_generator: {err}", exc_info=True)
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
