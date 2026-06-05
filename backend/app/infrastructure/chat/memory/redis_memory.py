"""
Redis memory layer for the chat pipeline.

Key schema:
  chat:memory:{tenant_id}:{connection_id}  →  List<JSON(MemoryTurn)>
  (capped at MAX_TURNS, stored as a Redis List with LPUSH + LTRIM)

Serialisation: JSON.  Each entry is a MemoryTurn TypedDict.
TTL: 24 h rolling window (reset on every write).
"""

from __future__ import annotations

import json
from typing import List, Optional
import redis.asyncio as aioredis

from app.core.config import settings
from app.infrastructure.chat.state import MemoryTurn
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_TURNS   = 20          # how many past turns to retain
MEMORY_TTL  = 86_400      # 24 h in seconds
_KEY_PREFIX = "chat:memory"


def _key(tenant_id: str, connection_id: str) -> str:
    return f"{_KEY_PREFIX}:{tenant_id}:{connection_id}"


def _redis() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


# ── public API ────────────────────────────────────────────────────────────────

async def fetch_memory(tenant_id: str, connection_id: str) -> List[MemoryTurn]:
    """Return up to MAX_TURNS prior turns (oldest → newest)."""
    try:
        r = _redis()
        raw_items: List[str] = await r.lrange(_key(tenant_id, connection_id), 0, MAX_TURNS - 1)
        await r.aclose()
        # lrange returns newest first (LPUSH); reverse so oldest → newest
        turns: List[MemoryTurn] = []
        for item in reversed(raw_items):
            try:
                turns.append(json.loads(item))
            except json.JSONDecodeError:
                pass
        return turns
    except Exception as exc:
        logger.warning("redis_memory_fetch_failed", error=str(exc))
        return []


async def store_memory(
    tenant_id:     str,
    connection_id: str,
    user_message:  str,
    assistant_reply: str,
    sql:           Optional[str] = None,
    intent:        Optional[str] = None,
) -> None:
    """Append a user + assistant turn pair and trim to MAX_TURNS."""
    try:
        r = _redis()
        k = _key(tenant_id, connection_id)
        pipe = r.pipeline()

        user_turn: MemoryTurn = {
            "role":    "user",
            "content": user_message,
            "sql":     None,
            "intent":  intent,
        }
        asst_turn: MemoryTurn = {
            "role":    "assistant",
            "content": assistant_reply,
            "sql":     sql,
            "intent":  intent,
        }

        # LPUSH keeps newest at index-0 so LTRIM keeps the MAX_TURNS most recent
        pipe.lpush(k, json.dumps(asst_turn))
        pipe.lpush(k, json.dumps(user_turn))
        pipe.ltrim(k, 0, (MAX_TURNS * 2) - 1)   # *2 because user+assistant pairs
        pipe.expire(k, MEMORY_TTL)
        await pipe.execute()
        await r.aclose()
    except Exception as exc:
        logger.warning("redis_memory_store_failed", error=str(exc))


async def clear_memory(tenant_id: str, connection_id: str) -> None:
    try:
        r = _redis()
        await r.delete(_key(tenant_id, connection_id))
        await r.aclose()
    except Exception as exc:
        logger.warning("redis_memory_clear_failed", error=str(exc))


async def get_memory_summary(tenant_id: str, connection_id: str) -> str:
    """
    Returns a plain-text condensed summary of memory turns for LLM context injection.
    E.g.
      [Turn 1] User: show revenue by region  → SQL executed, 12 rows
      [Turn 2] User: why did it drop?        → insight generated
    """
    turns = await fetch_memory(tenant_id, connection_id)
    if not turns:
        return ""

    lines = ["=== Conversation history (recent first) ==="]
    for i, t in enumerate(turns[-10:], 1):          # last 10 turns max
        role    = t["role"].upper()
        content = t["content"][:120].replace("\n", " ")
        extra   = ""
        if t.get("sql"):
            extra = f"  [SQL: {t['sql'][:60]}...]"
        lines.append(f"[{i}] {role}: {content}{extra}")

    return "\n".join(lines)
