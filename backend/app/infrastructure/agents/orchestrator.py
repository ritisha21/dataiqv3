from typing import TypedDict, Optional, Dict, Any, List, Annotated
from langgraph.graph import StateGraph, END
from app.infrastructure.llm.llm_service import llm_service
from app.infrastructure.llm.query_engine import query_engine, QuerySafetyError
import pandas as pd
import numpy as np
import structlog

logger = structlog.get_logger()


# ─── Centralized State ────────────────────────────────────────────────────────

class AgentState(TypedDict):
    # Input
    user_message: str
    tenant_id: str
    connection_id: str
    schema_context: str
    semantic_mappings: Dict[str, Any]

    # Routing
    intent: str
    confidence: float
    goal: Optional[str]

    # SQL path
    generated_sql: Optional[str]
    query_results: Optional[Dict[str, Any]]
    sql_error: Optional[str]

    # Insight path
    statistics: Optional[Dict[str, Any]]
    insight_text: Optional[str]

    # Chart path
    chart_spec: Optional[Dict[str, Any]]

    # Model path
    model_trigger: Optional[Dict[str, Any]]  # {goal, target_col, table}

    # Output
    response: Optional[str]
    error: Optional[str]
    retry_count: int

    # Runtime (injected, not serialized)
    db_engine: Optional[Any]


# ─── Node Functions (pure, stateless) ────────────────────────────────────────

def node_intent_classifier(state: AgentState) -> AgentState:
    try:
        result = llm_service.classify_intent(
            state["user_message"],
            state.get("schema_context", "")
        )
        return {
            **state,
            "intent": result.get("intent", "sql_query"),
            "confidence": result.get("confidence", 0.5),
            "goal": result.get("goal"),
        }
    except Exception as e:
        logger.error("intent_classifier_failed", error=str(e))
        return {**state, "intent": "sql_query", "confidence": 0.3, "goal": None}


def node_schema_retriever(state: AgentState) -> AgentState:
    # Schema context already injected - just pass through
    # In production this could fetch from cache/DB
    return state


def node_query_builder(state: AgentState) -> AgentState:
    if state["intent"] not in ("sql_query", "chart_request", "get_insight"):
        return state
    try:
        sql = llm_service.generate_sql(
            state["user_message"],
            state.get("schema_context", "")
        )
        return {**state, "generated_sql": sql, "sql_error": None}
    except Exception as e:
        logger.error("query_builder_failed", error=str(e))
        return {**state, "sql_error": str(e)}


def node_sql_executor(state: AgentState) -> AgentState:
    if not state.get("generated_sql") or not state.get("db_engine"):
        return state
    try:
        results = query_engine.execute(state["db_engine"], state["generated_sql"])
        return {**state, "query_results": results, "sql_error": None}
    except QuerySafetyError as e:
        return {**state, "query_results": None, "sql_error": f"Safety violation: {e}"}
    except Exception as e:
        retry = state.get("retry_count", 0)
        if retry < 1:
            # Retry with more context
            try:
                fixed_sql = llm_service.generate_sql(
                    f"{state['user_message']} (Previous SQL failed: {str(e)}. Fix it.)",
                    state.get("schema_context", "")
                )
                results = query_engine.execute(state["db_engine"], fixed_sql)
                return {**state, "query_results": results, "generated_sql": fixed_sql, "retry_count": retry + 1}
            except Exception as e2:
                return {**state, "query_results": None, "sql_error": str(e2)}
        return {**state, "query_results": None, "sql_error": str(e)}


def node_insight_generator(state: AgentState) -> AgentState:
    results = state.get("query_results")
    if not results or not results.get("rows"):
        return {**state, "insight_text": "No data returned for this query."}

    # Compute statistics
    try:
        df = pd.DataFrame(results["rows"])
        stats = {}
        for col in df.select_dtypes(include=[np.number]).columns:
            stats[col] = {
                "mean": round(float(df[col].mean()), 4),
                "std": round(float(df[col].std()), 4),
                "min": round(float(df[col].min()), 4),
                "max": round(float(df[col].max()), 4),
            }
        state = {**state, "statistics": stats}
    except Exception:
        state = {**state, "statistics": {}}

    if state["intent"] == "get_insight":
        try:
            insight = llm_service.generate_insight(
                results,
                state.get("statistics", {}),
                state["user_message"],
            )
            return {**state, "insight_text": insight}
        except Exception as e:
            return {**state, "insight_text": f"Could not generate insight: {e}"}

    return state


def node_chart_generator(state: AgentState) -> AgentState:
    results = state.get("query_results")
    if not results or state["intent"] not in ("chart_request", "sql_query", "get_insight"):
        return state
    try:
        spec = llm_service.generate_chart_spec(
            results.get("columns", []),
            results.get("rows", [])[:10],
            state["user_message"],
        )
        return {**state, "chart_spec": spec}
    except Exception as e:
        logger.warning("chart_generator_failed", error=str(e))
        return state


def node_model_selector(state: AgentState) -> AgentState:
    if state["intent"] != "train_model":
        return state

    goal = state.get("goal", "classification")
    mappings = state.get("semantic_mappings", {})

    # Heuristically find target column and table
    target_col = None
    source_table = None

    for table_name, table_info in mappings.get("tables", {}).items():
        for col_name, col_info in table_info.get("columns", {}).items():
            if goal in ("churn",) and col_info["tag"] == "target_churn":
                target_col = col_name
                source_table = table_name
                break
            elif goal in ("revenue_forecast",) and col_info["tag"] == "target_revenue":
                target_col = col_name
                source_table = table_name
                break
        if target_col:
            break

    if not target_col and mappings.get("tables"):
        # Fallback: first table, first non-id col
        first_table = list(mappings["tables"].keys())[0]
        source_table = first_table
        cols = list(mappings["tables"][first_table]["columns"].keys())
        target_col = cols[-1] if cols else None

    return {
        **state,
        "model_trigger": {
            "goal": goal,
            "target_col": target_col,
            "source_table": source_table,
        },
    }


def node_response_builder(state: AgentState) -> AgentState:
    intent = state.get("intent")
    parts = []

    if state.get("sql_error"):
        parts.append(f"❌ Query error: {state['sql_error']}")
    elif state.get("query_results"):
        rc = state["query_results"].get("row_count", 0)
        parts.append(f"✅ Query returned {rc} rows in {state['query_results'].get('execution_time_ms', 0)}ms")

    if state.get("insight_text"):
        parts.append(state["insight_text"])

    if state.get("model_trigger"):
        mt = state["model_trigger"]
        parts.append(f"🤖 Model training triggered for goal='{mt['goal']}' on table='{mt['source_table']}', target='{mt['target_col']}'")

    if not parts:
        parts.append("I processed your request.")

    return {**state, "response": "\n\n".join(parts)}


# ─── Routing Logic ────────────────────────────────────────────────────────────

def route_after_intent(state: AgentState) -> str:
    intent = state.get("intent", "sql_query")
    if intent == "train_model":
        return "model_selector"
    elif intent == "schema_explore":
        return "response_builder"
    else:
        return "schema_retriever"


def route_after_executor(state: AgentState) -> str:
    if state.get("sql_error") and state.get("retry_count", 0) >= 1:
        return "response_builder"
    if state.get("intent") in ("get_insight",):
        return "insight_generator"
    return "chart_generator"


# ─── Build Graph ──────────────────────────────────────────────────────────────

def build_agent_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("intent_classifier", node_intent_classifier)
    workflow.add_node("schema_retriever", node_schema_retriever)
    workflow.add_node("query_builder", node_query_builder)
    workflow.add_node("sql_executor", node_sql_executor)
    workflow.add_node("insight_generator", node_insight_generator)
    workflow.add_node("chart_generator", node_chart_generator)
    workflow.add_node("model_selector", node_model_selector)
    workflow.add_node("response_builder", node_response_builder)

    workflow.set_entry_point("intent_classifier")

    workflow.add_conditional_edges("intent_classifier", route_after_intent, {
        "schema_retriever": "schema_retriever",
        "model_selector": "model_selector",
        "response_builder": "response_builder",
    })

    workflow.add_edge("schema_retriever", "query_builder")
    workflow.add_edge("query_builder", "sql_executor")

    workflow.add_conditional_edges("sql_executor", route_after_executor, {
        "insight_generator": "insight_generator",
        "chart_generator": "chart_generator",
        "response_builder": "response_builder",
    })

    workflow.add_edge("insight_generator", "chart_generator")
    workflow.add_edge("chart_generator", "response_builder")
    workflow.add_edge("model_selector", "response_builder")
    workflow.add_edge("response_builder", END)

    return workflow.compile()


# Singleton
agent_graph = build_agent_graph()


async def run_agent(
    user_message: str,
    tenant_id: str,
    connection_id: str,
    schema_context: str,
    semantic_mappings: Dict[str, Any],
    db_engine: Any,
) -> AgentState:
    initial_state: AgentState = {
        "user_message": user_message,
        "tenant_id": tenant_id,
        "connection_id": connection_id,
        "schema_context": schema_context,
        "semantic_mappings": semantic_mappings,
        "intent": "",
        "confidence": 0.0,
        "goal": None,
        "generated_sql": None,
        "query_results": None,
        "sql_error": None,
        "statistics": None,
        "insight_text": None,
        "chart_spec": None,
        "model_trigger": None,
        "response": None,
        "error": None,
        "retry_count": 0,
        "db_engine": db_engine,
    }

    result = await agent_graph.ainvoke(initial_state)
    return result
