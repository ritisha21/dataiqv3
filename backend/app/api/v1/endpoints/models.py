from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uuid

from app.db.database import get_db
from app.domain.models.models import (
    MLModel, ModelGoal, ModelStatus, DBConnection,
    SchemaSnapshot, SemanticMapping, MLExperiment
)
from app.core.dependencies import get_tenant_context, TenantContext, require_analyst_or_admin
from app.infrastructure.tasks.ml_tasks import train_model_task

router = APIRouter(prefix="/models", tags=["models"])


class TrainModelRequest(BaseModel):
    connection_id: str
    name: str
    goal: ModelGoal
    target_column: str
    source_table: str
    hyperparameters: Optional[Dict[str, Any]] = {}


class PredictRequest(BaseModel):
    model_id: str
    input_data: Dict[str, Any]


class ModelResponse(BaseModel):
    id: str
    name: str
    goal: str
    status: str
    target_column: str
    source_table: str
    metrics: Optional[Dict]
    version: int
    created_at: str
    trained_at: Optional[str]


@router.post("/train-model", status_code=202)
async def train_model(
    req: TrainModelRequest,
    ctx: TenantContext = Depends(require_analyst_or_admin),
    db: AsyncSession = Depends(get_db),
):
    # Verify connection belongs to tenant
    conn_result = await db.execute(
        select(DBConnection).where(
            DBConnection.id == req.connection_id,
            DBConnection.tenant_id == ctx.tenant_id,
        )
    )
    conn = conn_result.scalar_one_or_none()
    if not conn:
        raise HTTPException(404, "Connection not found")

    # Load semantic mappings
    sem_result = await db.execute(
        select(SemanticMapping).where(
            SemanticMapping.connection_id == req.connection_id,
            SemanticMapping.tenant_id == ctx.tenant_id,
        ).order_by(SemanticMapping.version.desc()).limit(1)
    )
    sem = sem_result.scalar_one_or_none()

    # Create model record
    model = MLModel(
        tenant_id=ctx.tenant_id,
        connection_id=req.connection_id,
        name=req.name,
        goal=req.goal,
        status=ModelStatus.pending,
        target_column=req.target_column,
        source_table=req.source_table,
        hyperparameters=req.hyperparameters,
    )
    db.add(model)
    await db.flush()
    model_id = str(model.id)
    await db.commit()

    # Dispatch async task
    connection_config = {
        "db_type": conn.db_type.value,
        "host": conn.host,
        "port": conn.port,
        "database": conn.database,
        "username": conn.username,
        "encrypted_password": conn.encrypted_password,
    }
    training_config = {
        "goal": req.goal.value,
        "target_col": req.target_column,
        "source_table": req.source_table,
        "hyperparameters": req.hyperparameters,
        "semantic_mappings": sem.mappings if sem else {},
    }

    task = train_model_task.delay(model_id, ctx.tenant_id, connection_config, training_config)

    return {
        "model_id": model_id,
        "task_id": task.id,
        "status": "training_queued",
        "message": f"Model '{req.name}' training started",
    }


@router.get("/", response_model=List[ModelResponse])
async def list_models(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MLModel).where(MLModel.tenant_id == ctx.tenant_id).order_by(MLModel.created_at.desc())
    )
    models = result.scalars().all()
    return [
        ModelResponse(
            id=str(m.id),
            name=m.name,
            goal=m.goal.value,
            status=m.status.value,
            target_column=m.target_column,
            source_table=m.source_table,
            metrics=m.metrics,
            version=m.version,
            created_at=m.created_at.isoformat(),
            trained_at=m.trained_at.isoformat() if m.trained_at else None,
        )
        for m in models
    ]


@router.get("/{model_id}")
async def get_model(
    model_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MLModel).where(MLModel.id == model_id, MLModel.tenant_id == ctx.tenant_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "Model not found")

    # Load experiments
    exp_result = await db.execute(
        select(MLExperiment).where(MLExperiment.model_id == model_id).order_by(MLExperiment.run_number)
    )
    experiments = exp_result.scalars().all()

    return {
        "id": str(model.id),
        "name": model.name,
        "goal": model.goal.value,
        "status": model.status.value,
        "target_column": model.target_column,
        "source_table": model.source_table,
        "feature_columns": model.feature_columns,
        "metrics": model.metrics,
        "hyperparameters": model.hyperparameters,
        "dataset_hash": model.dataset_hash,
        "version": model.version,
        "error_message": model.error_message,
        "created_at": model.created_at.isoformat(),
        "trained_at": model.trained_at.isoformat() if model.trained_at else None,
        "experiments": [
            {"run": e.run_number, "metrics": e.metrics, "params": e.params}
            for e in experiments
        ],
    }


@router.post("/predict")
async def predict(
    req: PredictRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MLModel).where(
            MLModel.id == req.model_id,
            MLModel.tenant_id == ctx.tenant_id,
            MLModel.status == ModelStatus.ready,
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "Model not found or not ready")

    if not model.artifact_path:
        raise HTTPException(400, "Model artifact not available")

    from app.infrastructure.ml_pipeline.pipeline import ml_pipeline
    try:
        prediction = ml_pipeline.predict(model.artifact_path, req.input_data)
        return {
            "model_id": req.model_id,
            "model_name": model.name,
            "goal": model.goal.value,
            "prediction": prediction,
        }
    except Exception as e:
        raise HTTPException(500, f"Prediction failed: {e}")
