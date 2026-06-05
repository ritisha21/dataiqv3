"""
/api/v1/chat  — unified chat endpoint
/api/v1/chat/stream — SSE streaming variant
/api/v1/chat/history — last N turns
/api/v1/chat/clear — clear memory
"""

from __future__ import annotations

import json
import asyncio
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.domain.models.models import DBConnection
from app.core.dependencies import get_tenant_context, TenantContext
from app.infrastructure.chat.orchestrator import run_chat
from app.infrastructure.chat.tools.memory_tools import (
    fetch_chat_memory,
    clear_chat_memory,
)
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


# ── request / response schemas ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    connection_id: str = Field(..., description="UUID of the connected DB")
    message:       str = Field(..., min_length=1, max_length=4_000)

    class Config:
        str_strip_whitespace = True


class ChatResponse(BaseModel):
    response_type: str            # sql | ml | insight | chart | hybrid | error
    text:          str
    sql:           Optional[str]  = None
    data:          list           = []
    columns:       list           = []
    chart:         Optional[dict] = None
    insight:       Optional[str]  = None
    ml_task:       Optional[dict] = None
    model_output:  Optional[dict] = None
    stats:         Optional[dict] = None
    confidence:    float          = 0.0
    execution_path: list          = []


# ── helpers ───────────────────────────────────────────────────────────────────

async def _resolve_connection(
    connection_id: str, tenant_id: str, db: AsyncSession
) -> DBConnection:
    result = await db.execute(
        select(DBConnection).where(
            DBConnection.id == connection_id,
            DBConnection.tenant_id == tenant_id,
            DBConnection.is_active == True,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(404, "Connection not found or inactive")
    return conn


# ── main chat endpoint (non-streaming) ───────────────────────────────────────

@router.post("/", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db:  AsyncSession  = Depends(get_db),
):
    """
    Synchronous chat endpoint.
    Runs the full LangGraph pipeline and returns a structured JSON response.
    """
    conn = await _resolve_connection(req.connection_id, ctx.tenant_id, db)

    logger.info(
        "chat_request",
        tenant_id     = ctx.tenant_id,
        connection_id = req.connection_id,
        message_len   = len(req.message),
    )

    result = await run_chat(
        message         = req.message,
        tenant_id       = ctx.tenant_id,
        user_id         = ctx.user_id,
        connection_id   = req.connection_id,
        db_conn_record  = conn,
        db_session      = db,
        stream          = False,
    )

    return ChatResponse(**result)


# ── SSE streaming endpoint ────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db:  AsyncSession  = Depends(get_db),
):
    """
    Server-Sent Events streaming endpoint.
    Emits progress events as the pipeline executes, then the final result.

    SSE event format:
      data: {"event": "progress", "node": "sql_generator", "message": "Generating SQL..."}
      data: {"event": "done", "payload": <ChatResponse JSON>}
      data: {"event": "error", "message": "..."}
    """
    conn = await _resolve_connection(req.connection_id, ctx.tenant_id, db)

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            # ── progress events ───────────────────────────────────────────────
            progress_nodes = [
                ("intent_classifier",  "Classifying your question…"),
                ("schema_retriever",   "Loading database schema…"),
                ("context_builder",    "Building context…"),
                ("sql_generator",      "Generating SQL query…"),
                ("sql_validator",      "Validating query safety…"),
                ("sql_executor",       "Executing query…"),
                ("insight_generator",  "Generating insights…"),
                ("chart_generator",    "Preparing chart…"),
                ("response_formatter", "Formatting response…"),
            ]

            # Emit first 3 progress events immediately (they feel fast)
            for node, msg in progress_nodes[:3]:
                yield _sse({"event": "progress", "node": node, "message": msg})
                await asyncio.sleep(0.05)

            # Run the actual pipeline
            result = await run_chat(
                message         = req.message,
                tenant_id       = ctx.tenant_id,
                user_id         = ctx.user_id,
                connection_id   = req.connection_id,
                db_conn_record  = conn,
                db_session      = db,
                stream          = True,
            )

            # Emit progress events for nodes that were actually visited
            visited = result.get("execution_path", [])
            for node, msg in progress_nodes[3:]:
                if node in visited:
                    yield _sse({"event": "progress", "node": node, "message": msg})
                    await asyncio.sleep(0.03)

            # Final payload
            yield _sse({"event": "done", "payload": result})

        except Exception as exc:
            logger.error("sse_stream_error", error=str(exc))
            yield _sse({"event": "error", "message": str(exc)})
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type = "text/event-stream",
        headers    = {
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",    # disable nginx buffering
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── memory endpoints ──────────────────────────────────────────────────────────

@router.get("/history")
async def get_history(
    connection_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Return last N conversation turns for a given connection."""
    turns = await fetch_chat_memory(ctx.tenant_id, connection_id)
    return {"connection_id": connection_id, "turns": turns, "count": len(turns)}


@router.delete("/history")
async def clear_history(
    connection_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Clear conversation memory for a connection."""
    await clear_chat_memory(ctx.tenant_id, connection_id)
    return {"status": "cleared", "connection_id": connection_id}


# ── helpers ───────────────────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"
