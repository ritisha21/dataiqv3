"""
ml_trigger_node
─────────────────
Handles two sub-intents:
  TRAIN_MODEL  → resolves target column from semantic mappings, dispatches
                 Celery task, returns ml_task_status
  PREDICT      → finds the latest READY model for this tenant+connection,
                 runs synchronous inference via ml_pipeline.predict()

Zero LLM calls here. Pure deterministic logic.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from app.infrastructure.chat.state import ChatState, ChatIntent, MLTaskStatus
from app.core.logging import get_logger

logger = get_logger(__name__)

# goal → semantic tag used to auto-detect target column
_GOAL_TARGET_TAGS: Dict[str, list[str]] = {
    "churn":            ["target_churn"],
    "revenue_forecast": ["target_revenue", "numeric"],
    "classification":   ["target_churn", "categorical"],
    "regression":       ["target_revenue", "numeric"],
}


def ml_trigger_node(state: ChatState) -> ChatState:
    node_name = "ml_trigger"
    path = state.get("execution_path", []) + [node_name]

    intent = state.get("intent")

    if intent == ChatIntent.TRAIN_MODEL:
        return _handle_train(state, path, node_name)
    elif intent == ChatIntent.PREDICT:
        return _handle_predict(state, path, node_name)
    else:
        return {**state, "execution_path": path}


# ── training dispatch ─────────────────────────────────────────────────────────

def _handle_train(state: ChatState, path: list, node_name: str) -> ChatState:
    goal     = state.get("goal") or "classification"
    mappings = state.get("semantic_mappings") or {}

    target_col, source_table = _resolve_target(mappings, goal)

    if not target_col or not source_table:
        return {
            **state,
            "ml_task_status": MLTaskStatus(
                triggered    = False,
                task_id      = None,
                model_id     = None,
                goal         = goal,
                target_col   = None,
                source_table = None,
                status       = "failed",
                metrics      = None,
            ),
            "node_errors":    {
                **state.get("node_errors", {}),
                node_name: f"Could not auto-resolve target column for goal={goal}",
            },
            "execution_path": path,
        }

    try:
        from app.infrastructure.tasks.ml_tasks import train_model_task
        import uuid, json

        model_id = str(uuid.uuid4())

        # We need connection credentials — pull from DB synchronously
        conn_cfg = _fetch_connection_config_sync(
            state["connection_id"], state["tenant_id"]
        )
        if not conn_cfg:
            raise RuntimeError("DB connection record not found")

        training_cfg = {
            "goal":              goal,
            "target_col":        target_col,
            "source_table":      source_table,
            "hyperparameters":   {},
            "semantic_mappings": mappings,
        }

        task = train_model_task.delay(
            model_id, state["tenant_id"], conn_cfg, training_cfg
        )

        logger.info("ml_train_dispatched", model_id=model_id, goal=goal, target=target_col)

        return {
            **state,
            "ml_task_status": MLTaskStatus(
                triggered    = True,
                task_id      = task.id,
                model_id     = model_id,
                goal         = goal,
                target_col   = target_col,
                source_table = source_table,
                status       = "pending",
                metrics      = None,
            ),
            "execution_path": path,
        }

    except Exception as exc:
        logger.error("ml_train_dispatch_failed", error=str(exc))
        return {
            **state,
            "ml_task_status": MLTaskStatus(
                triggered=False, task_id=None, model_id=None,
                goal=goal, target_col=target_col, source_table=source_table,
                status="failed", metrics=None,
            ),
            "node_errors":    {**state.get("node_errors", {}), node_name: str(exc)},
            "execution_path": path,
        }


# ── prediction dispatch ───────────────────────────────────────────────────────

def _handle_predict(state: ChatState, path: list, node_name: str) -> ChatState:
    try:
        # Find latest ready model for this tenant+connection
        model = _fetch_latest_ready_model(state["tenant_id"], state["connection_id"])
        if not model:
            return {
                **state,
                "model_output": {"error": "No trained model available for this connection."},
                "execution_path": path,
            }

        # Parse input features from user message (best-effort JSON extraction)
        import json, re
        input_data: Dict[str, Any] = {}
        json_match = re.search(r"\{.*?\}", state["message"], re.DOTALL)
        if json_match:
            try:
                input_data = json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        from app.infrastructure.ml_pipeline.pipeline import ml_pipeline
        prediction = ml_pipeline.predict(model["artifact_path"], input_data)

        logger.info("ml_predict_ok", model_id=model["id"])

        return {
            **state,
            "model_output":  {
                "model_id":   model["id"],
                "model_name": model["name"],
                "goal":       model["goal"],
                **prediction,
            },
            "execution_path": path,
        }

    except Exception as exc:
        logger.error("ml_predict_failed", error=str(exc))
        return {
            **state,
            "model_output": {"error": str(exc)},
            "node_errors":  {**state.get("node_errors", {}), node_name: str(exc)},
            "execution_path": path,
        }


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_target(
    mappings: Dict, goal: str
) -> tuple[Optional[str], Optional[str]]:
    target_tags = _GOAL_TARGET_TAGS.get(goal, ["target_churn", "target_revenue"])

    for table_name, tinfo in mappings.get("tables", {}).items():
        for col_name, col_info in tinfo.get("columns", {}).items():
            if col_info.get("tag") in target_tags:
                return col_name, table_name

    # Fallback: pick last column of first table
    tables = list(mappings.get("tables", {}).items())
    if tables:
        tname, tinfo = tables[0]
        cols = list(tinfo.get("columns", {}).keys())
        return (cols[-1] if cols else None), tname

    return None, None


def _fetch_connection_config_sync(
    connection_id: str, tenant_id: str
) -> Optional[Dict]:
    from sqlalchemy import create_engine, text
    from app.core.config import settings

    engine = create_engine(settings.SYNC_DATABASE_URL)
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT db_type, host, port, database, username, encrypted_password
                FROM db_connections
                WHERE id = :cid AND tenant_id = :tid AND is_active = true
            """), {"cid": connection_id, "tid": tenant_id}).fetchone()
        return {
            "db_type":            row[0],
            "host":               row[1],
            "port":               row[2],
            "database":           row[3],
            "username":           row[4],
            "encrypted_password": row[5],
        } if row else None
    finally:
        engine.dispose()


def _fetch_latest_ready_model(
    tenant_id: str, connection_id: str
) -> Optional[Dict]:
    from sqlalchemy import create_engine, text
    from app.core.config import settings

    engine = create_engine(settings.SYNC_DATABASE_URL)
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT id, name, goal, artifact_path
                FROM ml_models
                WHERE tenant_id = :tid
                  AND connection_id = :cid
                  AND status = 'ready'
                ORDER BY trained_at DESC
                LIMIT 1
            """), {"tid": tenant_id, "cid": connection_id}).fetchone()
        return {"id": str(row[0]), "name": row[1], "goal": row[2], "artifact_path": row[3]} if row else None
    finally:
        engine.dispose()
