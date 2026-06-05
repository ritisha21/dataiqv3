"""
Memory tools — thin wrappers called by nodes inside the LangGraph pipeline.
All state-free; all async.
"""

from app.infrastructure.chat.memory.redis_memory import (
    fetch_memory,
    store_memory,
    clear_memory,
    get_memory_summary,
)

__all__ = [
    "fetch_chat_memory",
    "store_chat_memory",
    "clear_chat_memory",
    "build_memory_context",
]


async def fetch_chat_memory(tenant_id: str, connection_id: str):
    """Retrieve last N turns as List[MemoryTurn]."""
    return await fetch_memory(tenant_id, connection_id)


async def store_chat_memory(
    tenant_id:       str,
    connection_id:   str,
    user_message:    str,
    assistant_reply: str,
    sql:             str | None = None,
    intent:          str | None = None,
) -> None:
    """Persist one user+assistant turn pair."""
    await store_memory(
        tenant_id        = tenant_id,
        connection_id    = connection_id,
        user_message     = user_message,
        assistant_reply  = assistant_reply,
        sql              = sql,
        intent           = intent,
    )


async def clear_chat_memory(tenant_id: str, connection_id: str) -> None:
    await clear_memory(tenant_id, connection_id)


async def build_memory_context(tenant_id: str, connection_id: str) -> str:
    """Return a plain-text block for injection into LLM prompts."""
    return await get_memory_summary(tenant_id, connection_id)
