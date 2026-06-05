"""
response_formatter_node
─────────────────────────
Final node. Assembles ALL pipeline outputs into the structured API response.
Also persists the turn to Redis memory.

Output schema:
  {
    "response_type": "sql|ml|insight|chart|hybrid|error",
    "text":          "...",
    "sql":           "...",
    "data":          [...],
    "chart":         {...},
    "insight":       "...",
    "confidence":    0.0-1.0,
  }
"""

from __future__ import annotations

from app.infrastructure.chat.state import ChatState, ChatIntent, ResponseType
from app.infrastructure.chat.tools.memory_tools import store_chat_memory
from app.core.logging import get_logger

logger = get_logger(__name__)


async def response_formatter_node(state: ChatState) -> ChatState:
    node_name = "response_formatter"
    path = state.get("execution_path", []) + [node_name]

    # ── determine response_type ───────────────────────────────────────────────
    response_type = _resolve_response_type(state)

    # ── build text summary ────────────────────────────────────────────────────
    text_parts: list[str] = []
    sql_used: str | None  = None

    if state.get("sql_error"):
        text_parts.append(f"⚠️  Query error: {state['sql_error']}")
        response_type = ResponseType.ERROR

    elif state.get("sql_results"):
        rc  = state["sql_results"]["row_count"]
        ms  = state["sql_results"]["execution_time_ms"]
        sql_used = state.get("validated_sql") or state.get("generated_sql")
        text_parts.append(f"Query returned **{rc} row{'s' if rc != 1 else ''}** in {ms} ms.")
        if state["sql_results"].get("truncated"):
            text_parts.append(f"_(Results capped at {rc} rows.)_")

    if state.get("insights"):
        text_parts.append(state["insights"])

    if state.get("ml_task_status"):
        mts = state["ml_task_status"]
        if mts.get("triggered"):
            text_parts.append(
                f"🤖 Model training queued — goal: **{mts['goal']}**, "
                f"target: **{mts['target_col']}** on table **{mts['source_table']}**. "
                f"Task ID: `{mts['task_id']}`"
            )
        else:
            text_parts.append("⚠️  Could not start model training — check logs.")

    if state.get("model_output"):
        mo = state["model_output"]
        if "error" in mo:
            text_parts.append(f"⚠️  Prediction error: {mo['error']}")
        else:
            pred  = mo.get("prediction", "N/A")
            conf  = mo.get("confidence", "")
            conf_str = f" (confidence: {conf:.0%})" if conf else ""
            text_parts.append(f"🔮 Prediction: **{pred}**{conf_str}")

    if state.get("chart_spec"):
        ct = state["chart_spec"].get("chart_type", "chart")
        text_parts.append(f"📊 {ct.title()} chart generated.")

    if not text_parts:
        text_parts.append("I processed your request but found no data to display.")

    final_text = "\n\n".join(text_parts)

    # ── build structured response ─────────────────────────────────────────────
    structured: dict = {
        "response_type": response_type.value,
        "text":          final_text,
        "sql":           sql_used,
        "data":          (state.get("sql_results") or {}).get("rows", []),
        "columns":       (state.get("sql_results") or {}).get("columns", []),
        "chart":         state.get("chart_spec"),
        "insight":       state.get("insights"),
        "ml_task":       state.get("ml_task_status"),
        "model_output":  state.get("model_output"),
        "stats":         state.get("sql_stats"),
        "confidence":    round(state.get("confidence", 0.0), 3),
        "execution_path": state.get("execution_path", []),
    }

    # ── persist to memory (best-effort) ──────────────────────────────────────
    try:
        await store_chat_memory(
            tenant_id       = state["tenant_id"],
            connection_id   = state["connection_id"],
            user_message    = state["message"],
            assistant_reply = final_text,
            sql             = sql_used,
            intent          = state.get("intent", {}).value
                              if hasattr(state.get("intent"), "value") else str(state.get("intent")),
        )
    except Exception as exc:
        logger.warning("memory_store_failed", error=str(exc))

    logger.info(
        "response_formatted",
        response_type=response_type.value,
        text_len=len(final_text),
    )

    return {
        **state,
        "response_type":  response_type,
        "final_response": structured,
        "execution_path": path,
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_response_type(state: ChatState) -> ResponseType:
    intent      = state.get("intent")
    has_sql     = bool(state.get("sql_results"))
    has_chart   = bool(state.get("chart_spec"))
    has_insight = bool(state.get("insights"))
    has_ml      = bool(state.get("ml_task_status") or state.get("model_output"))

    if state.get("sql_error"):
        return ResponseType.ERROR

    if intent in (ChatIntent.TRAIN_MODEL, ChatIntent.PREDICT):
        return ResponseType.ML

    if has_insight and has_chart:
        return ResponseType.HYBRID

    if has_insight:
        return ResponseType.INSIGHT

    if has_chart:
        return ResponseType.CHART

    if has_sql:
        return ResponseType.SQL

    if has_ml:
        return ResponseType.ML

    return ResponseType.SQL
