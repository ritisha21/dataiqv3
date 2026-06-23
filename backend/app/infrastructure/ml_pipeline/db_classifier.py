"""
db_classifier.py
Auto-classifies a database schema as CRM, ERP, or Hybrid based on
table names and column names, then surfaces appropriate prediction models.

Usage:
    from db_classifier import classify_schema, get_available_models_for_type

    db_type, confidence, breakdown = classify_schema(tables_dict)
    models = get_available_models_for_type(db_type)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import re

# ─────────────────────────────────────────────────────────────────────────────
# Signal tables: CRM vs ERP keyword sets
# ─────────────────────────────────────────────────────────────────────────────

CRM_TABLE_SIGNALS = {
    # Customer / contact entities
    "contact", "contacts", "customer", "customers", "client", "clients",
    "lead", "leads", "prospect", "prospects", "account", "accounts",
    # Sales pipeline
    "opportunity", "opportunities", "deal", "deals", "pipeline",
    "quote", "quotes", "proposal", "proposals",
    # Engagement / activity
    "activity", "activities", "interaction", "interactions", "note", "notes",
    "call", "calls", "email", "emails", "campaign", "campaigns",
    "segment", "segments", "subscription", "subscriptions",
    # Support
    "ticket", "tickets", "case", "cases", "support_request",
    # Revenue
    "order", "orders", "invoice", "invoices", "payment", "payments",
    "transaction", "transactions", "revenue",
    # CRM metadata
    "crm_model", "crm_config", "funnel", "stage", "stages",
}

ERP_TABLE_SIGNALS = {
    # Finance / accounting
    "ledger", "general_ledger", "journal", "journal_entry", "account_payable",
    "account_receivable", "balance_sheet", "trial_balance", "fiscal_period",
    "budget", "budgets", "cost_center", "cost_centres",
    # Inventory / supply chain
    "inventory", "stock", "warehouse", "warehouses", "bin", "bins",
    "purchase_order", "po", "supplier", "suppliers", "vendor", "vendors",
    "material", "materials", "bom", "bill_of_materials", "routing",
    # Manufacturing
    "production", "work_order", "work_orders", "shop_floor", "mrp",
    "quality", "quality_control", "batch", "batches", "shift",
    # HR / Payroll
    "employee", "employees", "payroll", "payslip", "attendance",
    "leave", "department", "departments", "position", "positions",
    # Asset management
    "asset", "assets", "depreciation", "maintenance", "asset_category",
    # ERP metadata
    "erp_config", "company", "companies", "branch", "branches",
}

CRM_COLUMN_SIGNALS = {
    "customer_id", "client_id", "contact_id", "lead_id", "account_id",
    "opportunity_id", "deal_id", "stage", "pipeline_stage", "lead_score",
    "churn_risk", "ltv", "clv", "lifetime_value", "nps_score",
    "last_contact_date", "next_followup", "conversion_date",
    "acquisition_source", "utm_source", "utm_campaign",
    "subscription_status", "plan_type", "mrr", "arr",
    "days_since_last_purchase", "purchase_frequency", "recency",
}

ERP_COLUMN_SIGNALS = {
    "gl_account", "cost_center_id", "profit_center", "fiscal_year",
    "fiscal_period", "debit", "credit", "journal_ref",
    "po_number", "grn_number", "material_code", "batch_number",
    "warehouse_id", "bin_location", "reorder_point", "safety_stock",
    "work_order_id", "bom_version", "routing_id", "machine_id",
    "employee_id", "paygrade", "tax_code", "asset_id",
}


# ─────────────────────────────────────────────────────────────────────────────
# Model registry: which models are valid per DB type
# ─────────────────────────────────────────────────────────────────────────────

MODEL_REGISTRY: Dict[str, List[Dict]] = {
    "CRM": [
        {
            "id": "churn_prediction",
            "name": "Churn Prediction",
            "description": "Predicts which customers are likely to churn in the next 30/60/90 days.",
            "required_signals": ["customer_id", "last_purchase", "frequency"],
            "target_column_hints": ["churn", "is_churned", "active"],
        },
        {
            "id": "clv_prediction",
            "name": "Customer Lifetime Value",
            "description": "Estimates total revenue a customer will generate over their lifetime.",
            "required_signals": ["order_value", "frequency", "tenure"],
            "target_column_hints": ["clv", "ltv", "lifetime_value"],
        },
        {
            "id": "lead_scoring",
            "name": "Lead Scoring",
            "description": "Scores leads by conversion probability using engagement and firmographic signals.",
            "required_signals": ["lead_id", "source", "engagement_score"],
            "target_column_hints": ["converted", "is_qualified", "lead_score"],
        },
        {
            "id": "upsell_propensity",
            "name": "Upsell Propensity",
            "description": "Identifies customers most likely to upgrade or add products.",
            "required_signals": ["current_plan", "usage", "tenure"],
            "target_column_hints": ["upgraded", "plan_change", "upsell_flag"],
        },
        {
            "id": "nps_prediction",
            "name": "NPS / CSAT Prediction",
            "description": "Predicts customer satisfaction scores before surveys are sent.",
            "required_signals": ["ticket_count", "resolution_time", "tenure"],
            "target_column_hints": ["nps_score", "csat_score", "rating"],
        },
        {
            "id": "next_best_action",
            "name": "Next Best Action",
            "description": "Recommends the optimal next engagement action per customer.",
            "required_signals": ["interaction_history", "segment", "stage"],
            "target_column_hints": ["action_taken", "outcome", "campaign_response"],
        },
    ],
    "ERP": [
        {
            "id": "demand_forecasting",
            "name": "Demand Forecasting",
            "description": "Forecasts product/material demand to optimise inventory levels.",
            "required_signals": ["date", "quantity", "product_id"],
            "target_column_hints": ["quantity_sold", "units_moved", "demand"],
        },
        {
            "id": "inventory_optimisation",
            "name": "Inventory Optimisation",
            "description": "Recommends reorder points and safety stock levels.",
            "required_signals": ["stock_level", "lead_time", "demand_rate"],
            "target_column_hints": ["reorder_point", "safety_stock", "shortage"],
        },
        {
            "id": "supplier_risk",
            "name": "Supplier Risk Score",
            "description": "Scores suppliers by delivery reliability and quality risk.",
            "required_signals": ["supplier_id", "delivery_date", "quality_flag"],
            "target_column_hints": ["on_time", "defect_rate", "supplier_score"],
        },
        {
            "id": "cost_variance",
            "name": "Cost Variance Prediction",
            "description": "Predicts budget vs actual cost overruns before period close.",
            "required_signals": ["budget", "actual_spend", "cost_center"],
            "target_column_hints": ["variance", "over_budget", "cost_deviation"],
        },
        {
            "id": "maintenance_prediction",
            "name": "Predictive Maintenance",
            "description": "Flags assets likely to fail before next scheduled maintenance.",
            "required_signals": ["asset_id", "last_maintenance", "usage_hours"],
            "target_column_hints": ["failure_date", "downtime", "maintenance_flag"],
        },
    ],
    "Hybrid": [],  # dynamically filled — union of CRM + ERP subsets
}

# Hybrid gets top-3 CRM + top-3 ERP models
MODEL_REGISTRY["Hybrid"] = MODEL_REGISTRY["CRM"][:3] + MODEL_REGISTRY["ERP"][:3]


# ─────────────────────────────────────────────────────────────────────────────
# Classifier
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    db_type: str                    # "CRM" | "ERP" | "Hybrid" | "Unknown"
    confidence: float               # 0.0 – 1.0
    crm_score: int
    erp_score: int
    matched_crm_tables: List[str]
    matched_erp_tables: List[str]
    matched_crm_columns: List[str]
    matched_erp_columns: List[str]
    available_models: List[Dict] = field(default_factory=list)
    reasoning: str = ""


def _normalise(name: str) -> str:
    """Strip schema prefix, lower-case, replace separators with underscore."""
    name = name.lower().split(".")[-1]  # strip schema prefix like public.
    name = re.sub(r"[\s\-]+", "_", name)
    return name


def classify_schema(
    tables: Dict[str, List[str]],
    *,
    hybrid_threshold: float = 0.30,
) -> ClassificationResult:
    """
    Classify a database schema.

    Parameters
    ----------
    tables : dict
        Mapping of table_name → [list of column names].
        e.g. {"customers": ["id", "email", "created_at"], "orders": [...]}
    hybrid_threshold : float
        If the minority score is at least this fraction of the total, label Hybrid.

    Returns
    -------
    ClassificationResult
    """
    crm_score = 0
    erp_score = 0
    matched_crm_tables: List[str] = []
    matched_erp_tables: List[str] = []
    matched_crm_cols: List[str] = []
    matched_erp_cols: List[str] = []

    for raw_table, columns in tables.items():
        tbl = _normalise(raw_table)

        # Table-level signals (weight 3 each)
        if tbl in CRM_TABLE_SIGNALS:
            crm_score += 3
            matched_crm_tables.append(raw_table)
        elif tbl in ERP_TABLE_SIGNALS:
            erp_score += 3
            matched_erp_tables.append(raw_table)
        else:
            # Partial substring match (weight 1)
            for sig in CRM_TABLE_SIGNALS:
                if sig in tbl or tbl in sig:
                    crm_score += 1
                    matched_crm_tables.append(raw_table)
                    break
            for sig in ERP_TABLE_SIGNALS:
                if sig in tbl or tbl in sig:
                    erp_score += 1
                    matched_erp_tables.append(raw_table)
                    break

        # Column-level signals (weight 1 each)
        for raw_col in columns:
            col = _normalise(raw_col)
            if col in CRM_COLUMN_SIGNALS:
                crm_score += 1
                matched_crm_cols.append(f"{raw_table}.{raw_col}")
            elif col in ERP_COLUMN_SIGNALS:
                erp_score += 1
                matched_erp_cols.append(f"{raw_table}.{raw_col}")

    total = crm_score + erp_score

    # ── Determine type ──────────────────────────────────────────────────────
    if total == 0:
        db_type = "Unknown"
        confidence = 0.0
        reasoning = "No recognisable CRM or ERP signals found in schema."
    else:
        crm_ratio = crm_score / total
        erp_ratio = erp_score / total

        minority_ratio = min(crm_ratio, erp_ratio)

        if minority_ratio >= hybrid_threshold:
            db_type = "Hybrid"
            confidence = round(1.0 - abs(crm_ratio - erp_ratio), 2)
            reasoning = (
                f"Schema contains both CRM signals ({crm_score} pts) "
                f"and ERP signals ({erp_score} pts). "
                f"Minority side is {minority_ratio:.0%} → Hybrid."
            )
        elif crm_ratio >= erp_ratio:
            db_type = "CRM"
            confidence = round(crm_ratio, 2)
            reasoning = (
                f"CRM signals dominate ({crm_score} pts vs {erp_score} ERP pts). "
                f"Matched tables: {', '.join(matched_crm_tables[:5]) or 'none'}."
            )
        else:
            db_type = "ERP"
            confidence = round(erp_ratio, 2)
            reasoning = (
                f"ERP signals dominate ({erp_score} pts vs {crm_score} CRM pts). "
                f"Matched tables: {', '.join(matched_erp_tables[:5]) or 'none'}."
            )

    available_models = get_available_models_for_type(db_type)

    return ClassificationResult(
        db_type=db_type,
        confidence=confidence,
        crm_score=crm_score,
        erp_score=erp_score,
        matched_crm_tables=matched_crm_tables,
        matched_erp_tables=matched_erp_tables,
        matched_crm_columns=matched_crm_cols,
        matched_erp_columns=matched_erp_cols,
        available_models=available_models,
        reasoning=reasoning,
    )


def get_available_models_for_type(db_type: str) -> List[Dict]:
    """Return model configs for a given DB type."""
    return MODEL_REGISTRY.get(db_type, [])


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: build tables dict from SQLAlchemy inspector (call from router)
# ─────────────────────────────────────────────────────────────────────────────

def schema_to_tables_dict(inspector) -> Dict[str, List[str]]:
    """
    Convert a SQLAlchemy Inspector to the {table: [columns]} dict
    that classify_schema() expects.

    Usage in router:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = schema_to_tables_dict(inspector)
        result = classify_schema(tables)
    """
    result: Dict[str, List[str]] = {}
    for table_name in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns(table_name)]
        result[table_name] = cols
    return result