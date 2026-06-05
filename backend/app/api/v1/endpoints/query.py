from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, Dict, Any, AsyncGenerator
import json
import asyncio

from app.db.database import get_db
from app.domain.models.models import DBConnection, SchemaSnapshot, SemanticMapping, QueryHistory
from app.core.dependencies import get_tenant_context, TenantContext
from app.infrastructure.connectors.db_connector import connector_service
from app.infrastructure.connectors.semantic_layer import semantic_engine
from app.infrastructure.agents.orchestrator import run_agent

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    connection_id: str
    natural_language: str


class ChatRequest(BaseModel):
    connection_id: str
    message: str
    stream: bool = False


async def _get_connection_and_schema(
    connection_id: str, tenant_id: str, db: AsyncSession
):
    conn_result = await db.execute(
        select(DBConnection).where(
            DBConnection.id == connection_id,
            DBConnection.tenant_id == tenant_id,
            DBConnection.is_active == True,
        )
    )
    conn = conn_result.scalar_one_or_none()
    if not conn:
        raise HTTPException(404, "Connection not found")

    schema_result = await db.execute(
        select(SchemaSnapshot).where(
            SchemaSnapshot.connection_id == connection_id,
            SchemaSnapshot.tenant_id == tenant_id,
        ).order_by(SchemaSnapshot.version.desc()).limit(1)
    )
    snapshot = schema_result.scalar_one_or_none()

    sem_result = await db.execute(
        select(SemanticMapping).where(
            SemanticMapping.connection_id == connection_id,
            SemanticMapping.tenant_id == tenant_id,
        ).order_by(SemanticMapping.version.desc()).limit(1)
    )
    sem_mapping = sem_result.scalar_one_or_none()

    return conn, snapshot, sem_mapping


@router.post("/query")
async def run_query(
    req: QueryRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    conn, snapshot, sem_mapping = await _get_connection_and_schema(
        req.connection_id, ctx.tenant_id, db
    )

    if not snapshot:
        raise HTTPException(400, "Schema not introspected yet")

    schema_context = semantic_engine.build_prompt_context(
        sem_mapping.mappings if sem_mapping else {}
    )

    db_engine = connector_service.get_engine_for_query(conn)

    try:
        result = await run_agent(
            user_message=req.natural_language,
            tenant_id=ctx.tenant_id,
            connection_id=req.connection_id,
            schema_context=schema_context,
            semantic_mappings=sem_mapping.mappings if sem_mapping else {},
            db_engine=db_engine,
        )
    finally:
        db_engine.dispose()

    # Log query
    qh = QueryHistory(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        connection_id=req.connection_id,
        natural_language=req.natural_language,
        generated_sql=result.get("generated_sql"),
        row_count=result.get("query_results", {}).get("row_count") if result.get("query_results") else None,
        execution_time_ms=result.get("query_results", {}).get("execution_time_ms") if result.get("query_results") else None,
        success=result.get("sql_error") is None,
        error_message=result.get("sql_error"),
    )
    db.add(qh)
    await db.commit()

    return {
        "intent": result.get("intent"),
        "sql": result.get("generated_sql"),
        "results": result.get("query_results"),
        "insight": result.get("insight_text"),
        "chart_spec": result.get("chart_spec"),
        "model_trigger": result.get("model_trigger"),
        "response": result.get("response"),
    }


@router.post("/chat")
async def chat(
    req: ChatRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Chat endpoint - same as query but returns streamed text for UI."""
    if req.stream:
        conn, snapshot, sem_mapping = await _get_connection_and_schema(
            req.connection_id, ctx.tenant_id, db
        )
        schema_context = semantic_engine.build_prompt_context(
            sem_mapping.mappings if sem_mapping else {}
        )
        db_engine = connector_service.get_engine_for_query(conn)

        async def stream_response() -> AsyncGenerator[str, None]:
            try:
                result = await run_agent(
                    user_message=req.message,
                    tenant_id=ctx.tenant_id,
                    connection_id=req.connection_id,
                    schema_context=schema_context,
                    semantic_mappings=sem_mapping.mappings if sem_mapping else {},
                    db_engine=db_engine,
                )
                payload = json.dumps({
                    "intent": result.get("intent"),
                    "sql": result.get("generated_sql"),
                    "results": result.get("query_results"),
                    "insight": result.get("insight_text"),
                    "chart_spec": result.get("chart_spec"),
                    "model_trigger": result.get("model_trigger"),
                    "response": result.get("response"),
                    "done": True,
                })
                yield f"data: {payload}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
            finally:
                db_engine.dispose()

        return StreamingResponse(stream_response(), media_type="text/event-stream")

    # Non-streaming: delegate to query endpoint
    query_req = QueryRequest(connection_id=req.connection_id, natural_language=req.message)
    return await run_query(query_req, ctx, db)
