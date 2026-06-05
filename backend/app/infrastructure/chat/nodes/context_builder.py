"""
context_builder_node
──────────────────────
Merges:
  1. schema_context_str  (already in state from schema_retriever)
  2. Redis memory summary (last N turns)
  3. FOLLOWUP resolution  – if intent is FOLLOWUP, rewrite message
     to include the SQL / result from the last turn so downstream nodes
     don't need to know about history.

This node is the only one that touches memory; all other nodes work
purely from ChatState fields.
"""

from __future__ import annotations

from app.infrastructure.chat.state import ChatState, ChatIntent
from app.infrastructure.chat.tools.memory_tools import (
    fetch_chat_memory,
    build_memory_context,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

_MAX_CONTEXT_CHARS = 3_000   # hard cap on combined context fed into LLM prompts


async def context_builder_node(state: ChatState) -> ChatState:
    node_name = "context_builder"
    path = state.get("execution_path", []) + [node_name]

    try:
        # ── 1. fetch memory turns ─────────────────────────────────────────────
        turns = await fetch_chat_memory(
            tenant_id     = state["tenant_id"],
            connection_id = state["connection_id"],
        )
        memory_summary = await build_memory_context(
            tenant_id     = state["tenant_id"],
            connection_id = state["connection_id"],
        )

        # ── 2. FOLLOWUP resolution ────────────────────────────────────────────
        effective_message = state["message"]
        if state.get("intent") == ChatIntent.FOLLOWUP and turns:
            # find the last assistant turn that has SQL or insight
            last_sql     = None
            last_content = None
            for t in reversed(turns):
                if t["role"] == "assistant":
                    last_content = t["content"]
                    last_sql     = t.get("sql")
                    break

            # rewrite message to include prior context
            ctx_parts = []
            if last_sql:
                ctx_parts.append(f"[Previous SQL: {last_sql[:300]}]")
            if last_content:
                ctx_parts.append(f"[Previous answer: {last_content[:200]}]")
            if ctx_parts:
                effective_message = (
                    " ".join(ctx_parts) + "\n\nFollow-up question: " + state["message"]
                )
                logger.info("followup_resolved", effective_len=len(effective_message))

        # ── 3. build combined prompt context ──────────────────────────────────
        schema_part  = state.get("schema_context_str") or ""
        memory_part  = memory_summary or ""

        combined = _truncate(
            schema_part  + "\n\n" + memory_part,
            _MAX_CONTEXT_CHARS,
        )

        return {
            **state,
            "memory_turns":      turns,
            "message":           effective_message,   # may be rewritten for FOLLOWUP
            "schema_context_str": combined,
            "execution_path":    path,
        }

    except Exception as exc:
        logger.error("context_builder_failed", error=str(exc))
        return {
            **state,
            "node_errors":    {**state.get("node_errors", {}), node_name: str(exc)},
            "execution_path": path,
        }


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[context truncated]"
