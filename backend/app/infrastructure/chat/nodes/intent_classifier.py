"""
intent_classifier_node
────────────────────────
Calls the LLM once with a tight prompt to classify intent.
Falls back to sql_query on any failure.
Detects FOLLOWUP intent by checking memory turns for previous SQL/insight.
"""

from __future__ import annotations

import json
from app.infrastructure.chat.state import ChatState, ChatIntent
from app.infrastructure.llm.llm_service import llm_service
from app.core.logging import get_logger

logger = get_logger(__name__)

_INTENT_PROMPT = """You are an intent classifier for a business intelligence platform.

Classify the user message into exactly ONE intent:

- sql_query        : retrieve / filter / aggregate raw data
- get_insight      : explain trends, root cause, "why did X happen?"
- train_model      : build/train ML model, "predict churn", "forecast revenue"
- chart_request    : explicit request for a chart or graph
- predict          : run inference on existing model ("predict for customer X")
- schema_explore   : ask about tables, columns, data structure
- hybrid           : needs both SQL + chart OR insight + chart together
- followup         : refers to a previous answer ("why further?", "break it down")

Rules:
- If message contains "why", "explain", "reason", "cause" → lean get_insight or hybrid
- If message contains "chart", "graph", "visualize", "plot" → lean chart_request or hybrid
- If message references "last result", "it", "that", "further" and history exists → followup
- For train / predict, also extract the business goal: churn | revenue_forecast | classification | regression

Respond ONLY with compact JSON, no markdown:
{"intent":"<intent>","confidence":<0.0-1.0>,"goal":"<or null>"}
"""


def intent_classifier_node(state: ChatState) -> ChatState:
    node_name = "intent_classifier"
    path = state.get("execution_path", []) + [node_name]

    try:
        # Build context — include memory summary so FOLLOWUP can be detected
        memory_block = ""
        if state.get("memory_turns"):
            last = state["memory_turns"][-2:]          # last 2 turns
            snippets = [f"{t['role'].upper()}: {t['content'][:80]}" for t in last]
            memory_block = "\n\nRecent history:\n" + "\n".join(snippets)

        raw = llm_service.classify_intent(
            user_message   = state["message"],
            schema_context = (state.get("schema_context_str") or "")[:400] + memory_block,
        )

        intent_str  = raw.get("intent", "sql_query")
        confidence  = float(raw.get("confidence", 0.5))
        goal        = raw.get("goal")

        # Validate enum
        try:
            intent = ChatIntent(intent_str)
        except ValueError:
            intent = ChatIntent.SQL_QUERY
            confidence = 0.4

        # If no memory exists, FOLLOWUP is impossible
        if intent == ChatIntent.FOLLOWUP and not state.get("memory_turns"):
            intent     = ChatIntent.SQL_QUERY
            confidence = 0.5

        logger.info("intent_classified", intent=intent.value, confidence=confidence)

        return {
            **state,
            "intent":         intent,
            "confidence":     confidence,
            "goal":           goal,
            "execution_path": path,
        }

    except Exception as exc:
        logger.error("intent_classifier_failed", error=str(exc))
        return {
            **state,
            "intent":         ChatIntent.SQL_QUERY,
            "confidence":     0.3,
            "goal":           None,
            "node_errors":    {**state.get("node_errors", {}), node_name: str(exc)},
            "execution_path": path,
        }
