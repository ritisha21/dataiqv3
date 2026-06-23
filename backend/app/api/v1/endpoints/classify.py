"""
routers/classify.py
───────────────────
New endpoints to hook the DB auto-classifier into the existing scan flow.

Mount in main.py:
    from routers.classify import router as classify_router
    app.include_router(classify_router, prefix="/api", tags=["classify"])

Endpoints
---------
POST /api/scan/classify
    Body: { connection_id: str }
    Scans schema and returns db_type, confidence, and available models.
    Also persists result to the connection's metadata in the DB.

GET  /api/classify/models/{connection_id}
    Returns last-stored classification + available models for a connection.

GET  /api/classify/models/type/{db_type}
    Returns available models for a given type directly (no DB needed).
    Used by AI chat to avoid querying crm_model table.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.exc import SQLAlchemyError

# ── adjust these imports to match your project structure ──
from db_classifier import classify_schema, schema_to_tables_dict, get_available_models_for_type
# from database import get_db           # your async session factory
# from models import Connection         # your ORM model for stored connections
# from crud import get_connection_by_id # your CRUD helper

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class ClassifyRequest(BaseModel):
    connection_id: str
    connection_string: Optional[str] = None   # pass directly if not stored


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


# ─────────────────────────────────────────────────────────────────────────────
# Helper: get connection string from your connection store
# Replace the body of this function with your actual lookup logic.
# ─────────────────────────────────────────────────────────────────────────────

async def _resolve_connection_string(connection_id: str, direct: Optional[str]) -> str:
    """
    Return a SQLAlchemy connection string for the given connection_id.

    Priority:
      1. direct  — caller passed it explicitly (e.g. from Zustand store)
      2. DB lookup — fetch stored connection by ID

    Raises HTTPException(404) if not found.
    """
    if direct:
        return direct

    # ── TODO: replace with your actual DB/CRUD lookup ──────────────────────
    # Example (synchronous SQLite/Postgres lookup):
    #
    #   conn = await crud.get_connection_by_id(connection_id)
    #   if not conn:
    #       raise HTTPException(status_code=404, detail=f"Connection {connection_id!r} not found")
    #   return conn.connection_string
    #
    # For now we raise so the missing lookup is obvious in logs:
    raise HTTPException(
        status_code=422,
        detail=(
            "connection_string not provided and DB lookup not yet wired. "
            "Pass connection_string directly or implement _resolve_connection_string()."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/scan/classify
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/scan/classify", response_model=ClassificationResponse)
async def classify_connection(req: ClassifyRequest) -> ClassificationResponse:
    """
    Scan the schema for a stored connection and auto-classify it as
    CRM, ERP, Hybrid, or Unknown.

    This endpoint is called automatically after a successful schema scan
    so the frontend can immediately surface the right prediction models.
    """
    conn_str = await _resolve_connection_string(req.connection_id, req.connection_string)

    # ── Connect and inspect ────────────────────────────────────────────────
    try:
        engine = create_engine(conn_str, pool_pre_ping=True, connect_args={"connect_timeout": 10})
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
            detail="Schema is empty — no tables found. Ensure the database contains data.",
        )

    # ── Classify ────────────────────────────────────────────────────────────
    result = classify_schema(tables_dict)

    # ── Persist to your connection metadata (optional but recommended) ──────
    # await crud.update_connection_metadata(
    #     req.connection_id,
    #     db_type=result.db_type,
    #     db_type_confidence=result.confidence,
    # )

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


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/classify/models/{connection_id}
# Used by the Models page to reload the classification without re-scanning
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/classify/models/{connection_id}", response_model=ModelListResponse)
async def get_models_for_connection(connection_id: str) -> ModelListResponse:
    """
    Returns available models for a connection using its stored db_type.
    Does NOT re-scan the schema — just reads the last stored classification.

    If not yet classified, returns empty list with db_type='Unknown'.
    """
    # ── TODO: replace with your actual lookup ──────────────────────────────
    # conn = await crud.get_connection_by_id(connection_id)
    # if not conn:
    #     raise HTTPException(status_code=404, detail="Connection not found")
    # db_type = conn.metadata.get("db_type", "Unknown")

    # Placeholder until lookup is wired:
    db_type = "Unknown"
    models = get_available_models_for_type(db_type)

    return ModelListResponse(db_type=db_type, models=models)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/classify/models/type/{db_type}
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/classify/models/type/{db_type}", response_model=ModelListResponse)
async def get_models_by_type(db_type: str) -> ModelListResponse:
    """
    Returns available models for a given db_type directly.

    This is the endpoint the AI chat should call instead of
    SELECT name FROM crm_model — it avoids the undefined table error.

    Valid db_type values: CRM, ERP, Hybrid, Unknown
    """
    allowed = {"CRM", "ERP", "Hybrid", "Unknown"}
    if db_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid db_type {db_type!r}. Must be one of {allowed}.",
        )
    models = get_available_models_for_type(db_type)
    return ModelListResponse(db_type=db_type, models=models)