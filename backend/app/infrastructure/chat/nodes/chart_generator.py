"""
chart_generator_node
──────────────────────
Generates a ChartSpec from sql_results WITHOUT calling the LLM when possible.
Uses a heuristic chart-type selector first; falls back to LLM for ambiguous cases.

Chart spec format:
  { chart_type, x_col, y_col, title, subtitle, color_col, data }

Runs for: CHART_REQUEST, HYBRID, SQL_QUERY (auto-suggest), GET_INSIGHT (time-series).
Skipped for: TRAIN_MODEL, PREDICT, SCHEMA_EXPLORE with no data.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.infrastructure.chat.state import ChatState, ChatIntent, ChartSpec
from app.core.logging import get_logger

logger = get_logger(__name__)

_CHART_INTENTS = {
    ChatIntent.CHART_REQUEST,
    ChatIntent.HYBRID,
    ChatIntent.SQL_QUERY,
    ChatIntent.GET_INSIGHT,
    ChatIntent.FOLLOWUP,
}

_TIME_KEYWORDS = re.compile(
    r"(trend|over time|monthly|weekly|daily|yearly|by date|by month|by week|timeline|growth)",
    re.IGNORECASE,
)
_PIE_KEYWORDS  = re.compile(r"(share|proportion|breakdown|percentage|distribution|split)", re.IGNORECASE)
_SCATTER_KW    = re.compile(r"(correlation|scatter|vs\.?|versus|relationship)", re.IGNORECASE)


def chart_generator_node(state: ChatState) -> ChatState:
    node_name = "chart_generator"
    path = state.get("execution_path", []) + [node_name]

    intent = state.get("intent")
    if intent not in _CHART_INTENTS:
        return {**state, "execution_path": path}

    sql_results = state.get("sql_results")
    if not sql_results or not sql_results.get("rows") or len(sql_results["rows"]) < 1:
        return {**state, "execution_path": path}

    try:
        columns  = sql_results["columns"]
        rows     = sql_results["rows"]
        message  = state.get("message", "")
        stats    = state.get("sql_stats") or {}

        chart_type, x_col, y_col, color_col = _pick_chart_config(
            columns, rows, stats, message
        )

        if not x_col or not y_col:
            return {**state, "execution_path": path}

        title    = _generate_title(message, chart_type, x_col, y_col)
        subtitle = f"{sql_results['row_count']} rows · {sql_results['execution_time_ms']} ms"

        # Serialise data (cap at 500 pts for chart rendering)
        chart_data = _prepare_data(rows, x_col, y_col, color_col, max_pts=500)

        spec = ChartSpec(
            chart_type = chart_type,
            x_col      = x_col,
            y_col      = y_col,
            title      = title,
            subtitle   = subtitle,
            color_col  = color_col,
            data       = chart_data,
        )

        logger.info("chart_generated", chart_type=chart_type, points=len(chart_data))

        return {
            **state,
            "chart_spec":     spec,
            "execution_path": path,
        }

    except Exception as exc:
        logger.error("chart_generator_failed", error=str(exc))
        return {
            **state,
            "node_errors":    {**state.get("node_errors", {}), node_name: str(exc)},
            "execution_path": path,
        }


# ── heuristic chart selector ──────────────────────────────────────────────────

def _pick_chart_config(
    columns: List[str],
    rows: List[Dict],
    stats: Dict,
    message: str,
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """Returns (chart_type, x_col, y_col, color_col)."""

    if len(columns) < 2:
        return "bar", columns[0] if columns else None, None, None

    # Detect datetime column
    dt_cols = [
        c for c in columns
        if any(kw in c.lower() for kw in ("date", "month", "week", "year", "time", "day", "created", "at"))
    ]
    # Detect numeric columns
    num_cols = [c for c in columns if c in stats]
    # Detect categorical columns
    cat_cols = [c for c in columns if c not in stats and c not in dt_cols]

    # Time series → line chart
    if dt_cols and num_cols and _TIME_KEYWORDS.search(message):
        return "line", dt_cols[0], num_cols[0], cat_cols[0] if cat_cols else None

    # Explicit pie request
    if _PIE_KEYWORDS.search(message) and cat_cols and num_cols:
        return "pie", cat_cols[0], num_cols[0], None

    # Scatter
    if _SCATTER_KW.search(message) and len(num_cols) >= 2:
        return "scatter", num_cols[0], num_cols[1], cat_cols[0] if cat_cols else None

    # Date + numeric → line by default
    if dt_cols and num_cols:
        return "line", dt_cols[0], num_cols[0], cat_cols[0] if cat_cols else None

    # Categorical + numeric → bar
    if cat_cols and num_cols:
        return "bar", cat_cols[0], num_cols[0], None

    # Two numeric → scatter
    if len(num_cols) >= 2:
        return "scatter", num_cols[0], num_cols[1], None

    # Fallback: first two columns as bar
    return "bar", columns[0], columns[1], None


def _generate_title(message: str, chart_type: str, x_col: str, y_col: str) -> str:
    # Capitalise column names nicely
    x_nice = x_col.replace("_", " ").title()
    y_nice = y_col.replace("_", " ").title()
    type_label = {
        "line": "Trend of",
        "bar": "Distribution of",
        "pie": "Breakdown of",
        "scatter": "Correlation:",
        "area": "Area Chart:",
    }.get(chart_type, "")
    return f"{type_label} {y_nice} by {x_nice}".strip()


def _prepare_data(
    rows: List[Dict],
    x_col: str,
    y_col: str,
    color_col: Optional[str],
    max_pts: int,
) -> List[Dict]:
    out = []
    for row in rows[:max_pts]:
        pt: Dict[str, Any] = {
            "x": row.get(x_col),
            "y": row.get(y_col),
            x_col: row.get(x_col),
            y_col: row.get(y_col),
        }
        if color_col and color_col in row:
            pt[color_col] = row[color_col]
            pt["group"] = row[color_col]
        out.append(pt)
    return out
