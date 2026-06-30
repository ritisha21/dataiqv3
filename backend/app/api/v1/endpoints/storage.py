"""
backend/app/api/v1/endpoints/storage.py
─────────────────────────────────────────
Endpoints for triggering CSV extraction to MinIO and listing snapshots.

POST /api/v1/storage/extract        — trigger extraction (async, returns task_id)
GET  /api/v1/storage/snapshots/{connection_id}/{table_name}  — list snapshot history
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional

from app.db.database import get_db
from app.domain.models.models import DBConnection
from app.core.dependencies import get_tenant_context, TenantContext
from app.infrastructure.tasks.storage_tasks import extract_to_minio_task
from app.infrastructure.storage.minio_client import minio_storage

router = APIRouter(prefix="/storage", tags=["storage"])


class ExtractRequest(BaseModel):
    connection_id: str
    tables: List[str]   # which tables to extract; pass all known table names


class SnapshotResponse(BaseModel):
    object_key: str
    size_bytes: int
    last_modified: str


@router.post("/extract", status_code=202)
async def trigger_extraction(
    req: ExtractRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger CSV extraction of one or more tables to MinIO."""
    conn_result = await db.execute(
        select(DBConnection).where(
            DBConnection.id == req.connection_id,
            DBConnection.tenant_id == ctx.tenant_id,
        )
    )
    conn = conn_result.scalar_one_or_none()
    if not conn:
        raise HTTPException(404, "Connection not found")

    if not req.tables:
        raise HTTPException(400, "At least one table must be specified")

    connection_config = {
        "db_type": conn.db_type.value,
        "host": conn.host,
        "port": conn.port,
        "database": conn.database,
        "username": conn.username,
        "encrypted_password": conn.encrypted_password,
    }

    task = extract_to_minio_task.delay(
        ctx.tenant_id, req.connection_id, req.tables, connection_config
    )

    return {
        "task_id": task.id,
        "status": "extraction_queued",
        "tables": req.tables,
    }


@router.get("/snapshots/{connection_id}/{table_name}", response_model=List[SnapshotResponse])
async def list_snapshots(
    connection_id: str,
    table_name: str,
    limit: int = 10,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List CSV snapshot history for a table, most recent first."""
    snapshots = minio_storage.list_snapshots(
        tenant_id=ctx.tenant_id,
        connection_id=connection_id,
        table_name=table_name,
        limit=limit,
    )
    return snapshots