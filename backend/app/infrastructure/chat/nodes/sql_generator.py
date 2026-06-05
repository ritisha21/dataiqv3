"""
sql_generator_node
────────────────────
Uses LLM ONLY for SQL text generation.
Builds a schema-aware, memory-aware prompt.
Never executes SQL itself.
"""

from __future__ import annotations

import re
from app.infrastructure.chat.state import ChatState, ChatIntent
from app.infrastructure.llm.llm_service import llm_service
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── SQL generation prompt ─────────────────────────────────────────────────────
_SQL_SYSTEM = """You are an expert SQL analyst working with a business database.

Generate a single, correct SELECT SQL query that answers the user's question.

Rules:
- ONLY SELECT statements
- Never use: INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, GRANT
- Use proper JOIN syntax when tables need to be combined
- Use aliases for clarity: SELECT t.name AS customer_name
- For trend/time analysis: GROUP BY a datetime column and ORDER BY it ASC
- For revenue/amount analysis: use SUM(), AVG(), COUNT() as appropriate
- Always LIMIT results to 1000 rows maximum
- Quote column/table names with double-quotes if they contain spaces or are reserved words
- For "last month": use WHERE date_col >= DATE_TRUNC('month', NOW() - INTERVAL '1 month')
  AND date_col < DATE_TRUNC('month', NOW())
- For "drop" or trend questions: include time series data ordered by date

Output ONLY the raw SQL, no explanation, no markdown fences, no semicolon at end.
"""


def sql_generator_node(state: ChatState) -> ChatState:
    node_name = "sql_generator"
    path = state.get("execution_path", []) + [node_name]

    # Only generate SQL when intent requires it
    skip_intents = {ChatIntent.TRAIN_MODEL, ChatIntent.PREDICT, ChatIntent.SCHEMA_EXPLORE}
    if state.get("intent") in skip_intents:
        return {**state, "execution_path": path}

    try:
        context = state.get("schema_context_str") or ""

        # For FOLLOWUP: carry previous SQL as hint
        prior_sql = ""
        if state.get("intent") == ChatIntent.FOLLOWUP:
            for t in reversed(state.get("memory_turns") or []):
                if t.get("sql"):
                    prior_sql = f"\n\nPrevious SQL for context:\n{t['sql']}"
                    break

        full_context = context + prior_sql

        raw_sql = llm_service.generate_sql(
            user_question  = state["message"],
            schema_context = full_context,
        )

        # Strip any stray markdown the LLM might have added
        cleaned = _strip_markdown(raw_sql)

        logger.info("sql_generated", sql_preview=cleaned[:120])

        return {
            **state,
            "generated_sql": cleaned,
            "sql_error":     None,
            "execution_path": path,
        }

    except Exception as exc:
        logger.error("sql_generator_failed", error=str(exc))
        return {
            **state,
            "generated_sql": None,
            "sql_error":     f"SQL generation failed: {exc}",
            "node_errors":   {**state.get("node_errors", {}), node_name: str(exc)},
            "execution_path": path,
        }


def _strip_markdown(sql: str) -> str:
    sql = re.sub(r"```sql\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```\s*",    "", sql)
    return sql.strip().rstrip(";")
