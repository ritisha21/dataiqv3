"""
schema_retriever_node
──────────────────────
Fetches schema_graph + semantic_mappings + schema_context_str from the
system DB (with Redis cache).  Populates state so every downstream node
has full schema access without hitting the DB again.
"""

from __future__ import annotations

from app.infrastructure.chat.state import ChatState
from app.infrastructure.chat.tools.schema_tools import get_schema
from app.core.logging import get_logger

logger = get_logger(__name__)


async def schema_retriever_node(state: ChatState, db) -> ChatState:
    """
    `db` is injected by the orchestrator (AsyncSession).
    This node is async because schema_tools does async DB + Redis calls.
    """
    node_name = "schema_retriever"
    path = state.get("execution_path", []) + [node_name]

    try:
        graph, mappings, context_str = await get_schema(
            tenant_id     = state["tenant_id"],
            connection_id = state["connection_id"],
            db            = db,
        )

        if not graph and not mappings:
            logger.warning("schema_not_found", tenant_id=state["tenant_id"])
            return {
                **state,
                "schema_graph":       None,
                "semantic_mappings":  None,
                "schema_context_str": "No schema available. Please connect a database first.",
                "node_errors":        {
                    **state.get("node_errors", {}),
                    node_name: "Schema not yet introspected",
                },
                "execution_path": path,
            }

        logger.info(
            "schema_retrieved",
            tables=len(graph.get("nodes", [])) if graph else 0,
        )

        return {
            **state,
            "schema_graph":       graph,
            "semantic_mappings":  mappings,
            "schema_context_str": context_str,
            "execution_path":     path,
        }

    except Exception as exc:
        logger.error("schema_retriever_failed", error=str(exc))
        return {
            **state,
            "schema_graph":       state.get("schema_graph"),
            "semantic_mappings":  state.get("semantic_mappings"),
            "schema_context_str": state.get("schema_context_str") or "",
            "node_errors":        {**state.get("node_errors", {}), node_name: str(exc)},
            "execution_path":     path,
        }
