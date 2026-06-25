"""
backend/app/api/v1/endpoints/classify.py
─────────────────────────────────────────
Endpoints:
  POST /api/v1/scan/classify          — scan + classify a connection's schema
  GET  /api/v1/classify/models/type/{db_type}  — list models for a db type
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from sqlalchemy import create_engine, inspect as sa_inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ml_pipeline.db_classifier import (
    classify_schema,
    schema_to_tables_dict,
    get_available_models_for_type,
)
from app.db.database import get_db
from app.domain.models.models import Connection

router = APIRouter()


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class ClassifyRequest(BaseModel):
    connection_id: str
    connection_string: Optional[str] = None


class ClassificationResponse(BaseModel):
    connection_id: str
    db_type: str
    confidence: float
    crm_score: int
    erp_score: int
    reasoning: str
    available_models: List[Dict[str, Any]]
    matched_crm_tables: List[str]
    matched_erp_tables: List[str]
    matched_crm_columns: List[str]
    matched_erp_columns: List[str]


class ModelListResponse(BaseModel):
    db_type: str
    models: List[Dict[str, Any]]


# ─── Helper: resolve connection string ────────────────────────────────────────

async def _resolve_connection_string(
    connection_id: str,
    direct: Optional[str],
    db: AsyncSession,
) -> str:
    """
    1. If the caller passed connection_string directly, use it.
    2. Otherwise look up the Connection row by ID.
    """
    if direct:
        return direct

    result = await db.execute(
        Connection.__table__.select().where(
            Connection.id == connection_id
        )
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Connection {connection_id!r} not found.",
        )

    # Build the connection string from stored fields
    # Adjust field names to match your Connection model columns
    conn_str = row.connection_string if hasattr(row, "connection_string") else None

    if not conn_str:
        # Fallback: build from individual fields if you store host/port/db separately
        try:
            conn_str = (
                f"{row.db_type}://{row.username}:{row.password}"
                f"@{row.host}:{row.port}/{row.database}"
            )
        except AttributeError:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Cannot resolve connection string. "
                    "Pass connection_string directly in the request body."
                ),
            )

    return conn_str


# ─── POST /scan/classify ──────────────────────────────────────────────────────

@router.post("/scan/classify", response_model=ClassificationResponse)
async def classify_connection(
    req: ClassifyRequest,
    db: AsyncSession = Depends(get_db),
) -> ClassificationResponse:
    """
    Inspects the schema of a stored connection and classifies it as
    CRM, ERP, Hybrid, or Unknown. Returns the matching prediction models.

    Call this automatically after every schema scan so the Models page
    and AI chat always know what type of database is connected.
    """
    conn_str = await _resolve_connection_string(req.connection_id, req.connection_string, db)

    try:
        engine = create_engine(
            conn_str,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10},
        )
        inspector = sa_inspect(engine)
        tables_dict = schema_to_tables_dict(inspector)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=400, detail=f"Could not inspect schema: {exc}")
    finally:
        try:
            engine.dispose()
        except Exception:
            pass

    if not tables_dict:
        raise HTTPException(
            status_code=404,
            detail="Schema is empty — no tables found.",
        )

    result = classify_schema(tables_dict)

    return ClassificationResponse(
        connection_id=req.connection_id,
        db_type=result.db_type,
        confidence=result.confidence,
        crm_score=result.crm_score,
        erp_score=result.erp_score,
        reasoning=result.reasoning,
        available_models=result.available_models,
        matched_crm_tables=result.matched_crm_tables,
        matched_erp_tables=result.matched_erp_tables,
        matched_crm_columns=result.matched_crm_columns,
        matched_erp_columns=result.matched_erp_columns,
    )


# ─── GET /classify/models/type/{db_type} ─────────────────────────────────────

@router.get("/classify/models/type/{db_type}", response_model=ModelListResponse)
async def get_models_by_type(db_type: str) -> ModelListResponse:
    """
    Returns DataIQ's built-in prediction models for a given DB type.
    No DB query needed — answers from the model registry in db_classifier.py.

    Valid values: CRM, ERP, Hybrid, Unknown
    """
    allowed = {"CRM", "ERP", "Hybrid", "Unknown"}
    if db_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid db_type {db_type!r}. Must be one of {allowed}.",
        )
    models = get_available_models_for_type(db_type)
    return ModelListResponse(db_type=db_type, models=models)