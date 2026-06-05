"""
/api/v1/export/csv   POST  → run NL query, return CSV file download
/api/v1/export/query POST  → run raw SQL, return CSV file download
"""

from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.domain.models.models import DBConnection, SchemaSnapshot, SemanticMapping
from app.core.dependencies import get_tenant_context, TenantContext
from app.infrastructure.connectors.db_connector import connector_service
from app.infrastructure.connectors.semantic_layer import semantic_engine
from app.infrastructure.llm.llm_service import llm_service
from app.infrastructure.chat.tools.sql_tools import validate_sql, run_sql
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/export", tags=["export"])


class NLExportRequest(BaseModel):
    connection_id: str
    natural_language: str
    filename: Optional[str] = None


class SQLExportRequest(BaseModel):
    connection_id: str
    sql: str
    filename: Optional[str] = None


# ── NL → CSV ──────────────────────────────────────────────────────────────────

@router.post("/csv")
async def export_nl_to_csv(
    req: NLExportRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db:  AsyncSession  = Depends(get_db),
):
    """
    Takes a natural language question, converts to SQL,
    executes it, and returns the result as a downloadable CSV.
    """
    conn, schema_context = await _get_conn_and_schema(
        req.connection_id, ctx.tenant_id, db
    )

    # Generate SQL from NL
    try:
        raw_sql = llm_service.generate_sql(req.natural_language, schema_context)
    except Exception as exc:
        raise HTTPException(500, f"SQL generation failed: {exc}")

    return await _execute_and_stream_csv(
        conn     = conn,
        sql      = raw_sql,
        filename = req.filename or _make_filename(req.natural_language),
    )


# ── Raw SQL → CSV ─────────────────────────────────────────────────────────────

@router.post("/query-csv")
async def export_sql_to_csv(
    req: SQLExportRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db:  AsyncSession  = Depends(get_db),
):
    """
    Takes a raw SQL query, executes it,
    and returns the result as a downloadable CSV.
    """
    conn, _ = await _get_conn_and_schema(
        req.connection_id, ctx.tenant_id, db
    )

    return await _execute_and_stream_csv(
        conn     = conn,
        sql      = req.sql,
        filename = req.filename or "export.csv",
    )


# ── helpers ───────────────────────────────────────────────────────────────────

async def _get_conn_and_schema(
    connection_id: str,
    tenant_id:     str,
    db:            AsyncSession,
):
    conn_result = await db.execute(
        select(DBConnection).where(
            DBConnection.id        == connection_id,
            DBConnection.tenant_id == tenant_id,
            DBConnection.is_active == True,
        )
    )
    conn = conn_result.scalar_one_or_none()
    if not conn:
        raise HTTPException(404, "Connection not found")

    sem_result = await db.execute(
        select(SemanticMapping).where(
            SemanticMapping.connection_id == connection_id,
            SemanticMapping.tenant_id     == tenant_id,
        ).order_by(SemanticMapping.version.desc()).limit(1)
    )
    sem = sem_result.scalar_one_or_none()
    schema_context = semantic_engine.build_prompt_context(
        sem.mappings if sem else {}
    )

    return conn, schema_context


async def _execute_and_stream_csv(
    conn:     DBConnection,
    sql:      str,
    filename: str,
) -> StreamingResponse:
    # Validate SQL safety
    clean_sql, err = validate_sql(sql)
    if err:
        raise HTTPException(400, f"Unsafe SQL: {err}")

    # Execute
    db_engine = connector_service.get_engine_for_query(conn)
    try:
        result = run_sql(db_engine, clean_sql)
    except Exception as exc:
        raise HTTPException(500, f"Query failed: {exc}")
    finally:
        db_engine.dispose()

    if not result["rows"]:
        raise HTTPException(404, "Query returned no data")

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames = result["columns"],
        extrasaction = "ignore",
    )
    writer.writeheader()
    writer.writerows(result["rows"])
    output.seek(0)

    safe_filename = filename if filename.endswith(".csv") else f"{filename}.csv"

    logger.info(
        "csv_export",
        rows    = result["row_count"],
        columns = len(result["columns"]),
        file    = safe_filename,
    )

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type = "text/csv",
        headers    = {
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "X-Row-Count":         str(result["row_count"]),
        },
    )


def _make_filename(question: str) -> str:
    """Turn a NL question into a safe filename."""
    import re
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", question.lower())[:40].strip("_")
    return f"{safe}.csv"
