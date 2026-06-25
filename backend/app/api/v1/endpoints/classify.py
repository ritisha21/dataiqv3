"""
backend/app/api/v1/endpoints/classify.py
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from sqlalchemy import create_engine, inspect as sa_inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ml_pipeline.db_classifier import (
    classify_schema,
    schema_to_tables_dict,
    get_available_models_for_type,
)
from app.db.database import get_db
from app.domain.models.models import DBConnection

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
    if direct:
        return direct

    result = await db.execute(
        select(DBConnection).where(DBConnection.id == connection_id)
    )
    conn = result.scalar_one_or_none()

    if not conn:
        raise HTTPException(
            status_code=404,
            detail=f"Connection {connection_id!r} not found.",
        )

    # Build connection string from stored fields
    # encrypted_password is used as-is here — if your app decrypts it elsewhere,
    # swap conn.encrypted_password for the decrypted value
    db_type_str = conn.db_type.value if hasattr(conn.db_type, "value") else str(conn.db_type)
    dialect = "postgresql" if db_type_str == "postgres" else db_type_str

    return (
        f"{dialect}://{conn.username}:{conn.encrypted_password}"
        f"@{conn.host}:{conn.port}/{conn.database}"
    )


# ─── POST /scan/classify ──────────────────────────────────────────────────────

@router.post("/scan/classify", response_model=ClassificationResponse)
async def classify_connection(
    req: ClassifyRequest,
    db: AsyncSession = Depends(get_db),
) -> ClassificationResponse:
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
    allowed = {"CRM", "ERP", "Hybrid", "Unknown"}
    if db_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid db_type {db_type!r}. Must be one of {allowed}.",
        )
    models = get_available_models_for_type(db_type)
    return ModelListResponse(db_type=db_type, models=models)