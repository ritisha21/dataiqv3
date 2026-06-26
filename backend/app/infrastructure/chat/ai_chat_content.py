"""
ai_chat_context.py
──────────────────
Builds the system prompt for the AI chat so it:
  1. NEVER queries crm_model (the table doesn't exist)
  2. Knows about available models via the /api/classify/models/type/{db_type} endpoint
  3. Knows the actual tables in the connected DB (from schema scan)
  4. Understands what model types exist and what they predict

Wire into your LangGraph / chat handler like:
    from ai_chat_context import build_system_prompt
    system = build_system_prompt(db_type="CRM", available_tables=tables_list)
"""

from __future__ import annotations
from typing import List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Model descriptions (mirrors db_classifier.py, kept here for prompt building)
# ─────────────────────────────────────────────────────────────────────────────

MODEL_DESCRIPTIONS = {
    "CRM": [
        "churn_prediction — predicts which customers are at risk of leaving",
        "clv_prediction — estimates total lifetime revenue per customer",
        "lead_scoring — scores leads by probability of conversion",
        "upsell_propensity — identifies customers ready to upgrade",
        "nps_prediction — predicts satisfaction score before surveying",
        "next_best_action — recommends optimal engagement action",
    ],
    "ERP": [
        "demand_forecasting — forecasts product/material demand",
        "inventory_optimisation — recommends reorder points and safety stock",
        "supplier_risk — scores suppliers by reliability and quality",
        "cost_variance — predicts budget overruns before period close",
        "maintenance_prediction — flags assets likely to fail",
    ],
    "Hybrid": [
        "churn_prediction", "clv_prediction", "lead_scoring",
        "demand_forecasting", "inventory_optimisation", "supplier_risk",
    ],
}


def build_system_prompt(
    db_type: str = "Unknown",
    available_tables: Optional[List[str]] = None,
    connection_name: Optional[str] = None,
) -> str:
    """
    Build a system prompt for the AI chat that is grounded in the actual
    connected DB schema and available prediction models.

    Parameters
    ----------
    db_type         : "CRM" | "ERP" | "Hybrid" | "Unknown"
    available_tables: List of actual table names from schema scan.
    connection_name : Human-readable name of the connection, for context.

    Returns
    -------
    System prompt string to pass as the 'system' field to the LLM.
    """
    tables_str = (
        "\n".join(f"  - {t}" for t in (available_tables or []))
        or "  (no tables scanned yet — ask the user to run a schema scan first)"
    )

    models_list = MODEL_DESCRIPTIONS.get(db_type, ["(unknown — run /api/scan/classify first)"])
    models_str = "\n".join(f"  - {m}" for m in models_list)

    conn_label = f'"{connection_name}"' if connection_name else "the connected database"

    return f"""You are DataIQ's AI assistant. You help users understand and analyse {conn_label}.

## What you know about this database
- **Database type detected:** {db_type}
- **Available tables** (from last schema scan):
{tables_str}

## Available prediction models for this database
These are the models DataIQ can train on this schema:
{models_str}

## CRITICAL RULES — you must follow these without exception

### Never query tables that don't exist
The following tables do NOT exist in this database and must NEVER appear in SQL:
  - crm_model
  - erp_model
  - model_registry
  - available_models

If you need to list available models, describe them from the list above — do NOT write SQL to query a models table.

### Only query tables from the available tables list
Before writing any SQL, check that every table name you use appears in the "Available tables" list above.
If a user asks about a concept that would require a non-existent table, explain what tables you CAN use instead.

### How to answer "what models are available?"
Answer from the list above. Do NOT attempt:
  SELECT name FROM crm_model ...
  SELECT * FROM available_models ...
  SELECT model_name FROM models ...

Instead say: "Based on your {db_type} database, DataIQ can train: [list the models]"

### SQL guidelines
- Use only SELECT statements (read-only)
- Always include LIMIT clauses (default LIMIT 100, max LIMIT 10000)
- Use table aliases for readability
- Handle NULLs with COALESCE where relevant

## Your role
1. Answer questions about the data in the connected tables
2. Explain what each prediction model does and what columns it needs
3. Help users understand their schema and spot data quality issues
4. Suggest which model fits their business goal

Be concise, specific, and always ground your answers in the actual schema.
"""


def get_tool_schema_for_models(db_type: str) -> dict:
    """
    Returns a tool definition that the AI can call instead of querying crm_model.
    Add this to your LangGraph tool list.

    The AI will call get_available_models() → returns list from db_classifier,
    not from a non-existent DB table.
    """
    return {
        "name": "get_available_models",
        "description": (
            "Returns the list of prediction models available for the connected database. "
            "Use this instead of any SQL query to a models table."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    }


def available_models_tool_handler(db_type: str) -> dict:
    """
    Handles the get_available_models tool call.
    Returns structured model list for the given db_type.
    """
    from backend.app.infrastructure.ml_pipeline.db_classifier import get_available_models_for_type
    models = get_available_models_for_type(db_type)
    return {
        "db_type": db_type,
        "models": models,
        "note": "These models are built into DataIQ — no database table required.",
    }