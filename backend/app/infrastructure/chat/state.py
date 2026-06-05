"""
ChatState — Single source of truth for the entire chat pipeline.
Every node reads from and writes to this object.
Immutable pattern: nodes return {**state, key: new_value}.
"""

from typing import TypedDict, Optional, List, Dict, Any, Literal
from dataclasses import dataclass, field
from enum import Enum


class ChatIntent(str, Enum):
    SQL_QUERY      = "sql_query"       # direct data retrieval
    GET_INSIGHT    = "get_insight"     # analytical explanation (why/how)
    TRAIN_MODEL    = "train_model"     # trigger ML pipeline
    CHART_REQUEST  = "chart_request"   # explicit visualisation request
    PREDICT        = "predict"         # run inference on existing model
    SCHEMA_EXPLORE = "schema_explore"  # "what tables do I have?"
    FOLLOWUP       = "followup"        # references previous turn ("why further?")
    HYBRID         = "hybrid"          # insight + chart together


class ResponseType(str, Enum):
    SQL     = "sql"
    ML      = "ml"
    INSIGHT = "insight"
    CHART   = "chart"
    HYBRID  = "hybrid"
    ERROR   = "error"


# ── per-column stat record ────────────────────────────────────────────────────
class ColumnStats(TypedDict):
    mean:   Optional[float]
    std:    Optional[float]
    min:    Optional[float]
    max:    Optional[float]
    median: Optional[float]
    trend:  Optional[str]      # "up" | "down" | "flat"
    pct_change: Optional[float]


# ── SQL execution result ──────────────────────────────────────────────────────
class SQLResult(TypedDict):
    columns:          List[str]
    rows:             List[Dict[str, Any]]
    row_count:        int
    execution_time_ms: float
    sql:              str
    truncated:        bool          # True if row_count == MAX_QUERY_ROWS


# ── chart specification ───────────────────────────────────────────────────────
class ChartSpec(TypedDict):
    chart_type: str           # bar | line | pie | scatter | area | heatmap
    x_col:      str
    y_col:      str
    title:      str
    subtitle:   Optional[str]
    color_col:  Optional[str]  # for grouped charts
    data:       List[Dict[str, Any]]


# ── ML task descriptor ────────────────────────────────────────────────────────
class MLTaskStatus(TypedDict):
    triggered:   bool
    task_id:     Optional[str]
    model_id:    Optional[str]
    goal:        Optional[str]
    target_col:  Optional[str]
    source_table: Optional[str]
    status:      Optional[str]   # pending | training | ready | failed
    metrics:     Optional[Dict[str, Any]]


# ── memory turn record ────────────────────────────────────────────────────────
class MemoryTurn(TypedDict):
    role:    Literal["user", "assistant"]
    content: str
    sql:     Optional[str]
    intent:  Optional[str]


# ── main state ────────────────────────────────────────────────────────────────
class ChatState(TypedDict):
    # ── identity ──────────────────────────────────────────────────────────────
    tenant_id:     str
    user_id:       str
    connection_id: str
    request_id:    str

    # ── input ─────────────────────────────────────────────────────────────────
    message:       str
    stream:        bool

    # ── memory ────────────────────────────────────────────────────────────────
    memory_turns:  List[MemoryTurn]     # last N prior turns, injected by context_builder

    # ── intent ────────────────────────────────────────────────────────────────
    intent:        Optional[ChatIntent]
    confidence:    float
    goal:          Optional[str]         # churn | revenue_forecast | etc. (for train_model)

    # ── schema layer ──────────────────────────────────────────────────────────
    schema_graph:       Optional[Dict[str, Any]]   # full graph from snapshot
    semantic_mappings:  Optional[Dict[str, Any]]   # table -> {purpose, columns}
    schema_context_str: Optional[str]              # condensed string for LLM prompt

    # ── sql path ──────────────────────────────────────────────────────────────
    generated_sql:  Optional[str]
    validated_sql:  Optional[str]
    sql_error:      Optional[str]
    sql_results:    Optional[SQLResult]
    sql_stats:      Optional[Dict[str, ColumnStats]]  # computed after execution
    retry_count:    int

    # ── ml path ───────────────────────────────────────────────────────────────
    ml_task_status: Optional[MLTaskStatus]
    model_output:   Optional[Dict[str, Any]]    # prediction result if predict intent

    # ── insight path ──────────────────────────────────────────────────────────
    insights:       Optional[str]

    # ── chart path ────────────────────────────────────────────────────────────
    chart_spec:     Optional[ChartSpec]

    # ── output ────────────────────────────────────────────────────────────────
    response_type:   Optional[ResponseType]
    final_response:  Optional[str]
    error:           Optional[str]

    # ── runtime (not serialised to client) ───────────────────────────────────
    db_engine:       Optional[Any]
    node_errors:     Dict[str, str]          # node_name -> error message
    execution_path:  List[str]               # ordered list of nodes visited
