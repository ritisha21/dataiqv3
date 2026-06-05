"""
Chat Orchestrator — LangGraph implementation
──────────────────────────────────────────────
Full directed graph:

  intent_classifier
        │
        ├─ train_model / predict ──────────────→ ml_trigger ──────────→ response_formatter
        ├─ schema_explore ─────────────────────────────────────────────→ response_formatter
        └─ sql_query / insight / chart / hybrid / followup
                 │
           schema_retriever
                 │
           context_builder
                 │
           sql_generator
                 │
           sql_validator
                 │
           sql_executor
                 │
          ┌──────┴──────┐
          │             │
   insight_generator  (skipped if not insight/hybrid)
          │
   chart_generator
          │
   response_formatter → END

All nodes are pure functions or async functions.
The orchestrator owns:
  - db_engine injection (read-only SQLAlchemy engine)
  - AsyncSession injection for schema_retriever
  - node error accumulation
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, END

from app.infrastructure.chat.state import ChatState, ChatIntent
from app.infrastructure.chat.nodes.intent_classifier  import intent_classifier_node
from app.infrastructure.chat.nodes.schema_retriever   import schema_retriever_node
from app.infrastructure.chat.nodes.context_builder    import context_builder_node
from app.infrastructure.chat.nodes.sql_generator      import sql_generator_node
from app.infrastructure.chat.nodes.sql_validator      import sql_validator_node
from app.infrastructure.chat.nodes.sql_executor       import sql_executor_node
from app.infrastructure.chat.nodes.ml_trigger         import ml_trigger_node
from app.infrastructure.chat.nodes.insight_generator  import insight_generator_node
from app.infrastructure.chat.nodes.chart_generator    import chart_generator_node
from app.infrastructure.chat.nodes.response_formatter import response_formatter_node
from app.infrastructure.chat.tools.memory_tools       import fetch_chat_memory
from app.infrastructure.connectors.db_connector       import connector_service
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── routing functions (pure) ──────────────────────────────────────────────────

def _route_after_intent(state: ChatState) -> str:
    intent = state.get("intent")
    if intent in (ChatIntent.TRAIN_MODEL, ChatIntent.PREDICT):
        return "ml_trigger"
    if intent == ChatIntent.SCHEMA_EXPLORE:
        return "response_formatter"
    return "schema_retriever"


def _route_after_executor(state: ChatState) -> str:
    """After SQL execution, decide whether to generate insights."""
    intent = state.get("intent")
    if state.get("sql_error") and state.get("retry_count", 0) >= 1:
        return "response_formatter"
    if intent in (ChatIntent.GET_INSIGHT, ChatIntent.HYBRID, ChatIntent.FOLLOWUP):
        return "insight_generator"
    return "chart_generator"


def _route_after_validator(state: ChatState) -> str:
    """Skip execution if validation failed."""
    if state.get("sql_error"):
        return "response_formatter"
    return "sql_executor"


# ── wrapper: make async schema_retriever work as a sync node ─────────────────
# LangGraph supports async nodes natively when graph is invoked with ainvoke()

async def _schema_retriever_wrapper(state: ChatState) -> ChatState:
    # db session injected via state["_db"] by the runner
    db = state.get("_db")
    return await schema_retriever_node(state, db)


# ── graph builder ─────────────────────────────────────────────────────────────

def build_chat_graph() -> Any:
    g = StateGraph(ChatState)

    g.add_node("intent_classifier",  intent_classifier_node)
    g.add_node("schema_retriever",   _schema_retriever_wrapper)
    g.add_node("context_builder",    context_builder_node)
    g.add_node("sql_generator",      sql_generator_node)
    g.add_node("sql_validator",      sql_validator_node)
    g.add_node("sql_executor",       sql_executor_node)
    g.add_node("ml_trigger",         ml_trigger_node)
    g.add_node("insight_generator",  insight_generator_node)
    g.add_node("chart_generator",    chart_generator_node)
    g.add_node("response_formatter", response_formatter_node)

    g.set_entry_point("intent_classifier")

    # intent → branch
    g.add_conditional_edges(
        "intent_classifier",
        _route_after_intent,
        {
            "schema_retriever":   "schema_retriever",
            "ml_trigger":         "ml_trigger",
            "response_formatter": "response_formatter",
        },
    )

    # schema → context → sql gen → validator
    g.add_edge("schema_retriever",  "context_builder")
    g.add_edge("context_builder",   "sql_generator")
    g.add_edge("sql_generator",     "sql_validator")

    # validator → branch (skip exec if safety failed)
    g.add_conditional_edges(
        "sql_validator",
        _route_after_validator,
        {
            "sql_executor":       "sql_executor",
            "response_formatter": "response_formatter",
        },
    )

    # executor → branch (insight vs chart)
    g.add_conditional_edges(
        "sql_executor",
        _route_after_executor,
        {
            "insight_generator":  "insight_generator",
            "chart_generator":    "chart_generator",
            "response_formatter": "response_formatter",
        },
    )

    g.add_edge("insight_generator",  "chart_generator")
    g.add_edge("chart_generator",    "response_formatter")
    g.add_edge("ml_trigger",         "response_formatter")
    g.add_edge("response_formatter", END)

    return g.compile()


# singleton
_chat_graph = build_chat_graph()


# ── public entry point ────────────────────────────────────────────────────────

async def run_chat(
    *,
    message:       str,
    tenant_id:     str,
    user_id:       str,
    connection_id: str,
    db_conn_record: Any,      # DBConnection ORM object
    db_session:    Any,        # AsyncSession (for schema retrieval)
    stream:        bool = False,
) -> Dict[str, Any]:
    """
    Builds initial state, runs the compiled LangGraph, returns final_response dict.
    """
    request_id = str(uuid.uuid4())[:8]

    # Build read-only engine from connection record
    db_engine = connector_service.get_engine_for_query(db_conn_record)

    # Pre-fetch memory (async, outside graph)
    memory_turns = await fetch_chat_memory(tenant_id, connection_id)

    initial_state: ChatState = {
        # identity
        "tenant_id":          tenant_id,
        "user_id":            user_id,
        "connection_id":      connection_id,
        "request_id":         request_id,
        # input
        "message":            message,
        "stream":             stream,
        # memory (pre-loaded)
        "memory_turns":       memory_turns,
        # intent (will be filled)
        "intent":             None,
        "confidence":         0.0,
        "goal":               None,
        # schema (will be filled)
        "schema_graph":       None,
        "semantic_mappings":  None,
        "schema_context_str": None,
        # sql path
        "generated_sql":      None,
        "validated_sql":      None,
        "sql_error":          None,
        "sql_results":        None,
        "sql_stats":          None,
        "retry_count":        0,
        # ml path
        "ml_task_status":     None,
        "model_output":       None,
        # insight / chart
        "insights":           None,
        "chart_spec":         None,
        # output
        "response_type":      None,
        "final_response":     None,
        "error":              None,
        # runtime (injected, not returned to client)
        "db_engine":          db_engine,
        "_db":                db_session,    # for schema_retriever
        "node_errors":        {},
        "execution_path":     [],
    }

    try:
        result: ChatState = await _chat_graph.ainvoke(initial_state)
        return result.get("final_response") or _error_response("Pipeline produced no output")
    except Exception as exc:
        logger.error("chat_graph_failed", error=str(exc), request_id=request_id)
        return _error_response(str(exc))
    finally:
        try:
            db_engine.dispose()
        except Exception:
            pass


def _error_response(msg: str) -> Dict[str, Any]:
    return {
        "response_type": "error",
        "text":          f"Sorry, something went wrong: {msg}",
        "sql":           None,
        "data":          [],
        "columns":       [],
        "chart":         None,
        "insight":       None,
        "ml_task":       None,
        "model_output":  None,
        "stats":         None,
        "confidence":    0.0,
        "execution_path": [],
    }
