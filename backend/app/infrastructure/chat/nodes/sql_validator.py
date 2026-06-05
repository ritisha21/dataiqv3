"""
sql_validator_node
────────────────────
Runs the generated SQL through the safety layer (AST validation).
Populates validated_sql on success, sql_error on failure.
Does NOT execute — that is sql_executor_node's responsibility.
"""

from __future__ import annotations

from app.infrastructure.chat.state import ChatState
from app.infrastructure.chat.tools.sql_tools import validate_sql
from app.core.logging import get_logger

logger = get_logger(__name__)


def sql_validator_node(state: ChatState) -> ChatState:
    node_name = "sql_validator"
    path = state.get("execution_path", []) + [node_name]

    raw_sql = state.get("generated_sql")

    # Nothing to validate
    if not raw_sql:
        return {
            **state,
            "validated_sql":  None,
            "execution_path": path,
        }

    # If already errored upstream, propagate
    if state.get("sql_error"):
        return {**state, "execution_path": path}

    clean_sql, error = validate_sql(raw_sql)

    if error:
        logger.warning("sql_validation_failed", reason=error, sql=raw_sql[:200])
        return {
            **state,
            "validated_sql":  None,
            "sql_error":      f"SQL safety check failed: {error}",
            "node_errors":    {**state.get("node_errors", {}), node_name: error},
            "execution_path": path,
        }

    logger.info("sql_validated_ok", sql_preview=clean_sql[:120])

    return {
        **state,
        "validated_sql":  clean_sql,
        "sql_error":      None,
        "execution_path": path,
    }
