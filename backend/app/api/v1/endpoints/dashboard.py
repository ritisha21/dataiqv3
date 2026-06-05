from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio

from app.db.database import get_db
from app.domain.models.models import DBConnection, SchemaSnapshot, SemanticMapping, QueryHistory, MLModel, ModelStatus
from app.core.dependencies import get_tenant_context, TenantContext
from app.infrastructure.connectors.db_connector import connector_service
from app.infrastructure.llm.query_engine import query_engine
from sqlalchemy import text

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/widgets")
async def get_dashboard_widgets(
    connection_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Returns KPI widgets and chart data for dashboard."""
    conn_result = await db.execute(
        select(DBConnection).where(
            DBConnection.id == connection_id,
            DBConnection.tenant_id == ctx.tenant_id,
        )
    )
    conn = conn_result.scalar_one_or_none()
    if not conn:
        raise HTTPException(404, "Connection not found")

    sem_result = await db.execute(
        select(SemanticMapping).where(
            SemanticMapping.connection_id == connection_id,
            SemanticMapping.tenant_id == ctx.tenant_id,
        ).order_by(SemanticMapping.version.desc()).limit(1)
    )
    sem = sem_result.scalar_one_or_none()
    if not sem:
        raise HTTPException(400, "Schema not introspected yet")

    db_engine = connector_service.get_engine_for_query(conn)
    widgets = []

    try:
        # Auto-generate KPI widgets from semantic mappings
        for table_name, table_info in list(sem.mappings.get("tables", {}).items())[:5]:
            table_widgets = _generate_table_widgets(db_engine, table_name, table_info)
            widgets.extend(table_widgets)
    finally:
        db_engine.dispose()

    # Query history stats
    qh_result = await db.execute(
        select(QueryHistory).where(
            QueryHistory.tenant_id == ctx.tenant_id,
            QueryHistory.connection_id == connection_id,
        ).order_by(QueryHistory.created_at.desc()).limit(10)
    )
    recent_queries = qh_result.scalars().all()

    # Model summary
    model_result = await db.execute(
        select(MLModel).where(
            MLModel.tenant_id == ctx.tenant_id,
            MLModel.connection_id == connection_id,
        ).order_by(MLModel.created_at.desc()).limit(5)
    )
    models = model_result.scalars().all()

    return {
        "widgets": widgets,
        "recent_queries": [
            {
                "id": str(q.id),
                "question": q.natural_language,
                "row_count": q.row_count,
                "success": q.success,
                "created_at": q.created_at.isoformat(),
            }
            for q in recent_queries
        ],
        "models": [
            {
                "id": str(m.id),
                "name": m.name,
                "goal": m.goal.value,
                "status": m.status.value,
                "metrics": m.metrics,
            }
            for m in models
        ],
    }


def _generate_table_widgets(db_engine, table_name: str, table_info: Dict) -> List[Dict]:
    widgets = []
    try:
        # Row count widget
        with db_engine.connect() as conn:
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
        widgets.append({
            "type": "kpi",
            "title": f"Total {table_name.replace('_', ' ').title()}",
            "value": count,
            "table": table_name,
        })

        # Numeric column distribution
        numeric_cols = [
            col for col, info in table_info.get("columns", {}).items()
            if info.get("tag") in ("numeric", "target_revenue")
        ][:2]

        for col in numeric_cols:
            try:
                with db_engine.connect() as conn:
                    row = conn.execute(text(
                        f'SELECT AVG("{col}"), MIN("{col}"), MAX("{col}") FROM "{table_name}"'
                    )).fetchone()
                if row and row[0] is not None:
                    widgets.append({
                        "type": "stat",
                        "title": f"Avg {col.replace('_', ' ').title()}",
                        "value": round(float(row[0]), 2),
                        "min": round(float(row[1]), 2) if row[1] else None,
                        "max": round(float(row[2]), 2) if row[2] else None,
                        "table": table_name,
                        "column": col,
                    })
            except Exception:
                pass

        # Categorical distribution (for bar charts)
        cat_cols = [
            col for col, info in table_info.get("columns", {}).items()
            if info.get("tag") in ("categorical", "target_churn")
        ][:1]

        for col in cat_cols:
            try:
                with db_engine.connect() as conn:
                    rows = conn.execute(text(
                        f'SELECT "{col}", COUNT(*) as cnt FROM "{table_name}" GROUP BY "{col}" ORDER BY cnt DESC LIMIT 10'
                    )).fetchall()
                if rows:
                    widgets.append({
                        "type": "chart",
                        "chart_type": "bar",
                        "title": f"{col.replace('_', ' ').title()} Distribution",
                        "data": [{"label": str(r[0]), "value": r[1]} for r in rows],
                        "table": table_name,
                        "column": col,
                    })
            except Exception:
                pass

    except Exception:
        pass

    return widgets
