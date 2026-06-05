"""
Schema Tool Layer
──────────────────
get_schema(tenant_id, connection_id, db_session)
  → (schema_graph, semantic_mappings, schema_context_str)

Fetches the latest SchemaSnapshot + SemanticMapping from the system DB,
then builds a condensed LLM-prompt string (no full dump).

Cache: Redis  key=schema:ctx:{tenant_id}:{connection_id}  TTL=5 min
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domain.models.models import SchemaSnapshot, SemanticMapping
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE_TTL    = 300      # 5 minutes
_MAX_TABLES   = 15       # max tables in LLM context string
_MAX_COLS     = 20       # max columns per table in LLM context string
_CACHE_PREFIX = "schema:ctx"


# ── main entry ────────────────────────────────────────────────────────────────

async def get_schema(
    tenant_id:     str,
    connection_id: str,
    db:            AsyncSession,
) -> Tuple[Optional[Dict], Optional[Dict], str]:
    """
    Returns:
        schema_graph       – raw graph dict (nodes + edges) or None
        semantic_mappings  – mapping dict or None
        schema_context_str – condensed string for LLM
    """
    # ── Redis cache hit? ──────────────────────────────────────────────────────
    cached = await _cache_get(tenant_id, connection_id)
    if cached:
        return cached["graph"], cached["mappings"], cached["context_str"]

    # ── load from system DB ───────────────────────────────────────────────────
    snap_result = await db.execute(
        select(SchemaSnapshot)
        .where(
            SchemaSnapshot.connection_id == connection_id,
            SchemaSnapshot.tenant_id == tenant_id,
        )
        .order_by(SchemaSnapshot.version.desc())
        .limit(1)
    )
    snapshot = snap_result.scalar_one_or_none()

    sem_result = await db.execute(
        select(SemanticMapping)
        .where(
            SemanticMapping.connection_id == connection_id,
            SemanticMapping.tenant_id == tenant_id,
        )
        .order_by(SemanticMapping.version.desc())
        .limit(1)
    )
    sem = sem_result.scalar_one_or_none()

    schema_graph      = snapshot.schema_graph      if snapshot else None
    semantic_mappings = sem.mappings               if sem       else None

    context_str = _build_context_string(schema_graph, semantic_mappings)

    # ── populate cache ────────────────────────────────────────────────────────
    await _cache_set(tenant_id, connection_id, schema_graph, semantic_mappings, context_str)

    return schema_graph, semantic_mappings, context_str


# ── context string builder (schema-aware, no full dump) ──────────────────────

def _build_context_string(
    schema_graph:      Optional[Dict],
    semantic_mappings: Optional[Dict],
) -> str:
    if not schema_graph and not semantic_mappings:
        return "No schema available."

    lines: list[str] = ["-- Database schema --"]
    tables_done = 0

    # Prefer semantic_mappings (richer) over raw graph
    if semantic_mappings and semantic_mappings.get("tables"):
        for table_name, tinfo in list(semantic_mappings["tables"].items())[:_MAX_TABLES]:
            purpose = tinfo.get("purpose", "general")
            lines.append(f"\nTABLE {table_name}  (purpose: {purpose})")
            cols = list(tinfo.get("columns", {}).items())[:_MAX_COLS]
            for col_name, cinfo in cols:
                pk  = " [PK]"  if cinfo.get("primary_key") else ""
                tag = cinfo.get("tag", "feature")
                dt  = cinfo.get("dtype", "unknown")
                lines.append(f"  {col_name}: {dt} [{tag}]{pk}")
            tables_done += 1

    elif schema_graph and schema_graph.get("nodes"):
        for node in schema_graph["nodes"][:_MAX_TABLES]:
            lines.append(f"\nTABLE {node['id']}")
            for col in node.get("columns", [])[:_MAX_COLS]:
                pk = " [PK]" if col.get("primary_key") else ""
                lines.append(f"  {col['name']}: {col.get('type','?')}{pk}")
            tables_done += 1

    # FK edges (optional, keep concise)
    if schema_graph and schema_graph.get("edges"):
        lines.append("\n-- Foreign keys --")
        for edge in schema_graph["edges"][:20]:
            src_cols = ", ".join(edge.get("source_columns", []))
            tgt_cols = ", ".join(edge.get("target_columns", []))
            lines.append(
                f"  {edge['source']}({src_cols}) → {edge['target']}({tgt_cols})"
            )

    return "\n".join(lines)


# ── Redis cache helpers ───────────────────────────────────────────────────────

async def _cache_get(tenant_id: str, connection_id: str) -> Optional[Dict]:
    key = f"{_CACHE_PREFIX}:{tenant_id}:{connection_id}"
    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        raw = await r.get(key)
        await r.aclose()
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.debug("schema_cache_miss", error=str(exc))
        return None


async def _cache_set(
    tenant_id:     str,
    connection_id: str,
    graph:         Optional[Dict],
    mappings:      Optional[Dict],
    context_str:   str,
) -> None:
    key = f"{_CACHE_PREFIX}:{tenant_id}:{connection_id}"
    payload = {
        "graph":       graph,
        "mappings":    mappings,
        "context_str": context_str,
    }
    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.setex(key, _CACHE_TTL, json.dumps(payload))
        await r.aclose()
    except Exception as exc:
        logger.debug("schema_cache_write_failed", error=str(exc))
