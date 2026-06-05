"""
insight_generator_node
────────────────────────
Calls LLM ONLY to generate a plain-English business narrative.
All statistical computation happens deterministically BEFORE the LLM call.

The insight prompt receives:
  - condensed sql_stats (mean / trend / pct_change per column)
  - sample rows (≤ 10)
  - user question
  - memory context (for follow-up continuity)

Only runs for intents: GET_INSIGHT, HYBRID, FOLLOWUP (when SQL has data).
"""

from __future__ import annotations

import json
from typing import Any, Dict

from app.infrastructure.chat.state import ChatState, ChatIntent
from app.infrastructure.llm.llm_service import llm_service
from app.core.logging import get_logger

logger = get_logger(__name__)

_INSIGHT_INTENTS = {
    ChatIntent.GET_INSIGHT,
    ChatIntent.HYBRID,
    ChatIntent.FOLLOWUP,
}

_INSIGHT_SYSTEM = """You are a senior business analyst reviewing data query results.

Write 2–3 concise paragraphs with:
1. Key finding — what does the data show?
2. Notable patterns or anomalies — any trend, spike, or drop?
3. Actionable recommendation — what should the business do?

Be specific with numbers. Avoid generic filler phrases.
Do NOT include SQL, code, or markdown.
"""


def insight_generator_node(state: ChatState) -> ChatState:
    node_name = "insight_generator"
    path = state.get("execution_path", []) + [node_name]

    intent = state.get("intent")

    # Skip if intent doesn't need insight, or if there's no data to analyse
    if intent not in _INSIGHT_INTENTS:
        return {**state, "execution_path": path}

    sql_results = state.get("sql_results")
    if not sql_results or not sql_results.get("rows"):
        return {
            **state,
            "insights":       "No data was returned to generate insights.",
            "execution_path": path,
        }

    try:
        # Build a compact payload for the LLM — no full row dump
        stats    = state.get("sql_stats") or {}
        sample   = sql_results["rows"][:10]
        columns  = sql_results["columns"]

        payload: Dict[str, Any] = {
            "question":    state["message"],
            "row_count":   sql_results["row_count"],
            "columns":     columns,
            "sample_rows": sample,
            "statistics":  stats,
        }

        # Inject memory snippet for follow-up continuity
        memory_turns = state.get("memory_turns") or []
        if memory_turns:
            prev = [
                f"{t['role'].upper()}: {t['content'][:80]}"
                for t in memory_turns[-4:]
            ]
            payload["conversation_history"] = prev

        prompt_content = json.dumps(payload, indent=2, default=str)[:4_000]

        insight_text = llm_service.generate_insight(
            query_results = sql_results,
            statistics    = stats,
            user_question = state["message"],
        )

        logger.info("insight_generated", chars=len(insight_text))

        return {
            **state,
            "insights":       insight_text,
            "execution_path": path,
        }

    except Exception as exc:
        logger.error("insight_generator_failed", error=str(exc))
        return {
            **state,
            "insights":       f"Could not generate insight: {exc}",
            "node_errors":    {**state.get("node_errors", {}), node_name: str(exc)},
            "execution_path": path,
        }
