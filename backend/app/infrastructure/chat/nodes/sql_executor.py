"""
sql_executor_node
───────────────────
Executes validated_sql against the user's read-only DB engine.
On failure (first attempt):
  - asks LLM to fix the SQL with the error message appended
  - re-validates and retries ONCE
  - if second attempt fails → sets sql_error, does not raise

After execution:
  - computes column statistics (compute_column_stats)
  - populates sql_results + sql_stats in state
"""

from __future__ import annotations

from app.infrastructure.chat.state import ChatState
from app.infrastructure.chat.tools.sql_tools import run_sql, validate_sql, compute_column_stats
from app.infrastructure.llm.llm_service import llm_service
from app.core.logging import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 1


def sql_executor_node(state: ChatState) -> ChatState:
    node_name = "sql_executor"
    path = state.get("execution_path", []) + [node_name]

    # Nothing to execute
    if not state.get("validated_sql") or not state.get("db_engine"):
        return {**state, "execution_path": path}

    # Upstream error already present — skip
    if state.get("sql_error"):
        return {**state, "execution_path": path}

    sql_to_run  = state["validated_sql"]
    retry_count = state.get("retry_count", 0)

    try:
        result = run_sql(state["db_engine"], sql_to_run)
        stats  = compute_column_stats(result)

        logger.info(
            "sql_executed_ok",
            rows=result["row_count"],
            ms=result["execution_time_ms"],
        )

        return {
            **state,
            "sql_results":   result,
            "sql_stats":     stats,
            "sql_error":     None,
            "retry_count":   retry_count,
            "execution_path": path,
        }

    except Exception as exc:
        err_str = str(exc)
        logger.warning("sql_execution_failed", error=err_str, retry=retry_count)

        if retry_count < _MAX_RETRIES:
            # Ask LLM to fix
            try:
                fixed_sql_raw = llm_service.generate_sql(
                    user_question  = (
                        f"{state['message']}\n\n"
                        f"[Previous SQL failed with: {err_str}. "
                        f"Generate a corrected SQL query.]"
                    ),
                    schema_context = state.get("schema_context_str") or "",
                )
                clean_fixed, val_err = validate_sql(fixed_sql_raw)
                if val_err:
                    raise RuntimeError(val_err)

                result = run_sql(state["db_engine"], clean_fixed)
                stats  = compute_column_stats(result)

                logger.info("sql_retry_succeeded", rows=result["row_count"])

                return {
                    **state,
                    "generated_sql":  fixed_sql_raw,
                    "validated_sql":  clean_fixed,
                    "sql_results":    result,
                    "sql_stats":      stats,
                    "sql_error":      None,
                    "retry_count":    retry_count + 1,
                    "execution_path": path,
                }

            except Exception as retry_exc:
                logger.error("sql_retry_failed", error=str(retry_exc))
                return {
                    **state,
                    "sql_results":    None,
                    "sql_error":      f"Query failed after retry: {retry_exc}",
                    "retry_count":    retry_count + 1,
                    "node_errors":    {**state.get("node_errors", {}), node_name: str(retry_exc)},
                    "execution_path": path,
                }

        return {
            **state,
            "sql_results":    None,
            "sql_error":      err_str,
            "node_errors":    {**state.get("node_errors", {}), node_name: err_str},
            "execution_path": path,
        }
