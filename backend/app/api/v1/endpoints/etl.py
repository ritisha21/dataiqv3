"""
/api/v1/etl/scan          POST  → scan DB, return suggestions
/api/v1/etl/train         POST  → kick off training for selected suggestions
/api/v1/etl/status/{tid}  GET   → task status
/api/v1/etl/results       GET   → all ETL-trained models for this tenant
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.domain.models.models import DBConnection, MLModel
from app.core.dependencies import get_tenant_context, TenantContext, require_analyst_or_admin
from app.infrastructure.etl.scanner import etl_scanner
from app.infrastructure.tasks.etl_tasks import run_etl_task
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/etl", tags=["etl"])


# ── request/response models ───────────────────────────────────────────────────

class ScanRequest(BaseModel):
    connection_id: str


class TrainRequest(BaseModel):
    connection_id: str
    selected_ids: List[str]          # list of suggestion IDs user picked
    suggestions: List[Dict[str, Any]] # full suggestion objects (sent back from /scan)


class ScanResponse(BaseModel):
    connection_id: str
    tables: List[Dict[str, Any]]
    suggestions: List[Dict[str, Any]]
    total_tables: int
    total_suggestions: int


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/scan", response_model=ScanResponse)
async def scan_database(
    req: ScanRequest,
    ctx: TenantContext = Depends(require_analyst_or_admin),
    db:  AsyncSession  = Depends(get_db),
):
    """
    Scans the connected database, profiles all tables,
    and returns a list of possible ML features/goals the user can pick.
    """
    conn = await _get_conn(req.connection_id, ctx.tenant_id, db)

    try:
        result = await _run_sync_scan(conn)
    except Exception as exc:
        logger.error("etl_scan_failed", error=str(exc))
        raise HTTPException(500, f"Scan failed: {exc}")

    return ScanResponse(
        connection_id      = req.connection_id,
        tables             = result["tables"],
        suggestions        = result["suggestions"],
        total_tables       = len(result["tables"]),
        total_suggestions  = len(result["suggestions"]),
    )


@router.post("/train")
async def train_selected(
    req: TrainRequest,
    ctx: TenantContext = Depends(require_analyst_or_admin),
    db:  AsyncSession  = Depends(get_db),
):
    """
    User picks 1+ suggestions from /scan results.
    Kicks off async ETL pipeline for each.
    """
    conn = await _get_conn(req.connection_id, ctx.tenant_id, db)

    # Filter to only selected suggestions
    selected = [
        s for s in req.suggestions
        if s["id"] in req.selected_ids
    ]

    if not selected:
        raise HTTPException(400, "No valid suggestions selected")

    # Build connection config for Celery (no ORM objects cross process boundary)
    connection_config = {
        "db_type":            conn.db_type.value,
        "host":               conn.host,
        "port":               conn.port,
        "database":           conn.database,
        "username":           conn.username,
        "encrypted_password": conn.encrypted_password,
    }

    task = run_etl_task.delay(
        tenant_id         = ctx.tenant_id,
        connection_id     = req.connection_id,
        suggestions       = selected,
        connection_config = connection_config,
    )

    logger.info(
        "etl_train_dispatched",
        task_id=task.id,
        count=len(selected),
        tenant=ctx.tenant_id,
    )

    return {
        "task_id":   task.id,
        "status":    "queued",
        "count":     len(selected),
        "models":    [s["id"] for s in selected],
        "message":   f"Training {len(selected)} model(s). Check /etl/results for progress.",
    }


@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Poll Celery task status."""
    from celery.result import AsyncResult
    from app.infrastructure.cache.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)
    payload: Dict[str, Any] = {
        "task_id": task_id,
        "state":   result.state,
    }
    if result.state == "SUCCESS":
        payload["result"] = result.result
    elif result.state == "FAILURE":
        payload["error"] = str(result.result)
    elif result.state == "PROGRESS":
        payload["meta"] = result.info

    return payload


@router.get("/results")
async def get_etl_results(
    connection_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db:  AsyncSession  = Depends(get_db),
):
    """Returns all models trained via ETL for this connection."""
    result = await db.execute(
        select(MLModel).where(
            MLModel.tenant_id     == ctx.tenant_id,
            MLModel.connection_id == connection_id,
        ).order_by(MLModel.created_at.desc())
    )
    models = result.scalars().all()

    return {
        "models": [
            {
                "id":            str(m.id),
                "name":          m.name,
                "goal":          m.goal.value,
                "status":        m.status.value,
                "target_column": m.target_column,
                "source_table":  m.source_table,
                "metrics":       m.metrics,
                "trained_at":    m.trained_at.isoformat() if m.trained_at else None,
            }
            for m in models
        ]
    }


# ── helpers ───────────────────────────────────────────────────────────────────

async def _get_conn(
    connection_id: str, tenant_id: str, db: AsyncSession
) -> DBConnection:
    result = await db.execute(
        select(DBConnection).where(
            DBConnection.id        == connection_id,
            DBConnection.tenant_id == tenant_id,
            DBConnection.is_active == True,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(404, "Connection not found")
    return conn


async def _run_sync_scan(conn: DBConnection) -> Dict[str, Any]:
    """Run the synchronous scanner in a thread so it doesn't block the event loop."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        etl_scanner.scan_and_suggest,
        conn,
    )
