"""
SQL Tool Layer
──────────────
run_sql(engine, sql)   → SQLResult
validate_sql(sql)      → (clean_sql, error_or_None)

Safety contract:
  • SELECT-only at AST level (sqlglot parse tree walk)
  • No stacked statements
  • Row cap: MAX_QUERY_ROWS (env-configurable)
  • Statement timeout injected via SET LOCAL (Postgres) / MAX_EXECUTION_TIME (MySQL)
  • All column values serialised to JSON-safe types
"""

from __future__ import annotations

import time
import json
from typing import Any, Dict, List, Optional, Tuple

import sqlglot
import sqlglot.expressions as exp
from sqlalchemy import text

from app.core.config import settings
from app.infrastructure.chat.state import SQLResult
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── safety constants ──────────────────────────────────────────────────────────
_BANNED_NODE_TYPES: set[str] = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "REPLACE", "MERGE", "GRANT", "REVOKE",
    "EXECUTE", "CALL", "COPY", "LOAD", "SET",
    "CREATE TABLE", "CREATE INDEX", "CREATE VIEW",
}


class SQLSafetyError(ValueError):
    """Raised when a query violates safety policy."""


# ── validation ────────────────────────────────────────────────────────────────

def validate_sql(raw_sql: str) -> Tuple[str, Optional[str]]:
    """
    Returns (cleaned_sql, None) on success.
    Returns ("", error_message) on failure.
    """
    sql = raw_sql.strip().rstrip(";")

    if not sql:
        return "", "Empty SQL"

    try:
        statements = sqlglot.parse(sql)
    except Exception as exc:
        return "", f"SQL parse error: {exc}"

    if len(statements) == 0:
        return "", "No statements found"

    if len(statements) > 1:
        return "", "Multiple statements are not allowed"

    stmt = statements[0]

    # ── must be a SELECT ──────────────────────────────────────────────────────
    if not isinstance(stmt, exp.Select):
        kind = type(stmt).__name__
        return "", f"Only SELECT statements are permitted. Got: {kind}"

    # ── AST walk: ban any mutation node ───────────────────────────────────────
    for node in stmt.walk():
        node_type = type(node).__name__.upper()
        if node_type in _BANNED_NODE_TYPES:
            return "", f"Forbidden operation in query: {node_type}"

    # ── enforce or inject LIMIT ───────────────────────────────────────────────
    limit_node = stmt.args.get("limit")
    if limit_node is None:
        sql = f"{sql}\nLIMIT {settings.MAX_QUERY_ROWS}"
    else:
        try:
            existing_limit = int(str(limit_node.this))
            if existing_limit > settings.MAX_QUERY_ROWS:
                # Replace the limit
                sql = (
                    sqlglot.parse_one(sql)
                    .limit(settings.MAX_QUERY_ROWS)
                    .sql(dialect="postgres")
                )
        except Exception:
            pass  # leave as-is; runtime will truncate via fetchmany

    return sql, None


# ── execution ─────────────────────────────────────────────────────────────────

def run_sql(engine: Any, sql: str) -> SQLResult:
    """
    Execute *already-validated* SQL on a read-only engine connection.

    Returns SQLResult TypedDict.
    Raises RuntimeError on execution failure.
    """
    start = time.perf_counter()

    with engine.connect() as conn:
        # ── statement timeout (best-effort; dialect-specific) ─────────────────
        try:
            timeout_ms = settings.QUERY_TIMEOUT_SECONDS * 1_000
            conn.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
        except Exception:
            try:
                # MySQL
                conn.execute(text(
                    f"SET SESSION MAX_EXECUTION_TIME = {int(timeout_ms)}"
                ))
            except Exception:
                pass

        try:
            result = conn.execute(text(sql))
        except Exception as exc:
            raise RuntimeError(str(exc))

        columns: List[str] = list(result.keys())
        raw_rows           = result.fetchmany(settings.MAX_QUERY_ROWS)
        truncated          = len(raw_rows) == settings.MAX_QUERY_ROWS

    elapsed_ms = round((time.perf_counter() - start) * 1_000, 2)

    # ── serialise rows to JSON-safe dicts ─────────────────────────────────────
    serialised: List[Dict[str, Any]] = []
    for raw_row in raw_rows:
        row_dict: Dict[str, Any] = {}
        for col, val in zip(columns, raw_row):
            row_dict[col] = _json_safe(val)
        serialised.append(row_dict)

    logger.info(
        "sql_executed",
        row_count=len(serialised),
        elapsed_ms=elapsed_ms,
        truncated=truncated,
    )

    return SQLResult(
        columns          = columns,
        rows             = serialised,
        row_count        = len(serialised),
        execution_time_ms= elapsed_ms,
        sql              = sql,
        truncated        = truncated,
    )


# ── helpers ───────────────────────────────────────────────────────────────────

def _json_safe(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (int, float, str, bool)):
        return val
    if hasattr(val, "isoformat"):          # date / datetime / time
        return val.isoformat()
    try:
        json.dumps(val)
        return val
    except (TypeError, ValueError):
        return str(val)


def compute_column_stats(sql_result: SQLResult) -> Dict[str, Any]:
    """
    Compute per-column descriptive statistics for numeric columns.
    Returns {col: ColumnStats}.  Non-numeric columns are skipped.
    """
    import numpy as np

    stats: Dict[str, Any] = {}
    rows = sql_result["rows"]
    if not rows:
        return stats

    for col in sql_result["columns"]:
        values = []
        for row in rows:
            v = row.get(col)
            if v is not None:
                try:
                    values.append(float(v))
                except (TypeError, ValueError):
                    pass

        if len(values) < 2:
            continue

        arr = np.array(values)
        # simple linear trend
        if len(arr) >= 3:
            xs      = np.arange(len(arr))
            coeffs  = np.polyfit(xs, arr, 1)
            trend   = "up" if coeffs[0] > 0.01 else ("down" if coeffs[0] < -0.01 else "flat")
            pct_chg = round(float((arr[-1] - arr[0]) / (abs(arr[0]) + 1e-9) * 100), 2)
        else:
            trend   = "flat"
            pct_chg = 0.0

        stats[col] = {
            "mean":       round(float(arr.mean()), 4),
            "std":        round(float(arr.std()),  4),
            "min":        round(float(arr.min()),  4),
            "max":        round(float(arr.max()),  4),
            "median":     round(float(np.median(arr)), 4),
            "trend":      trend,
            "pct_change": pct_chg,
        }

    return stats
