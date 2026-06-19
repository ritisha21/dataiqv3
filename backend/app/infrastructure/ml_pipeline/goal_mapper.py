"""
Business Goal → CRM Model → ML Model recommendation engine.
Maps high-level business goals to appropriate CRM predictive models
based on available columns in the connected database.
"""

from typing import Dict, List, Optional, Any

# Full catalogue: business goal → CRM model → ML config
GOAL_CATALOGUE = {
    "reduce_churn": {
        "label": "Reduce churn rate",
        "crm_model": "Churn Prediction",
        "crm_model_key": "churn_prediction",
        "description": "Predict which customers are likely to leave so you can intervene early.",
        "business_value": "Retention of customer base, win-back campaigns, proactive support",
        "ml_goal": "classification",
        "required_cols": [],
        "preferred_cols": ["login_freq", "purchase_freq", "support_tickets", "payment_failures", "subscription_status"],
        "fallback_cols": ["close_value", "deal_stage", "sales_agent", "product", "created_date"],
        "target_col": "deal_stage",
        "ml_model": "XGBoost",
        "source_table_hints": ["sales_pipeline", "customers", "accounts", "subscriptions"],
    },
    "improve_sales_conversion": {
        "label": "Improve sales conversion",
        "crm_model": "Lead Scoring",
        "crm_model_key": "lead_scoring",
        "description": "Score and rank leads by their likelihood to convert so sales focuses on the right prospects.",
        "business_value": "Sales prioritization, higher win rates, shorter sales cycles",
        "ml_goal": "classification",
        "required_cols": [],
        "preferred_cols": ["source_channel", "company_size", "industry", "website_visits", "email_opens", "demo_booked", "time_in_funnel"],
        "fallback_cols": ["sales_agent", "product", "created_date", "close_value"],
        "target_col": "deal_stage",
        "ml_model": "XGBoost",
        "source_table_hints": ["sales_pipeline", "leads", "opportunities"],
    },
    "improve_lead_quality": {
        "label": "Improve lead quality",
        "crm_model": "Lead Qualification",
        "crm_model_key": "lead_qualification",
        "description": "Qualify leads automatically based on fit signals before they enter the pipeline.",
        "business_value": "Better pipeline quality, reduced wasted sales effort",
        "ml_goal": "classification",
        "required_cols": [],
        "preferred_cols": ["industry", "company_size", "source_channel", "sales_touchpoints"],
        "fallback_cols": ["sales_agent", "product", "created_date"],
        "target_col": "deal_stage",
        "ml_model": "XGBoost",
        "source_table_hints": ["sales_pipeline", "leads", "accounts"],
    },
    "improve_retention": {
        "label": "Improve customer retention",
        "crm_model": "Retention Risk",
        "crm_model_key": "retention_risk",
        "description": "Identify at-risk customers before they churn so retention teams can act.",
        "business_value": "Proactive retention, reduced churn, improved LTV",
        "ml_goal": "classification",
        "required_cols": [],
        "preferred_cols": ["login_freq", "purchase_freq", "support_complaints", "payment_failures", "subscription_downgrade"],
        "fallback_cols": ["sales_agent", "product", "created_date", "close_value"],
        "target_col": "deal_stage",
        "ml_model": "XGBoost",
        "source_table_hints": ["sales_pipeline", "customers", "accounts"],
    },
    "increase_upsell": {
        "label": "Increase upsell / cross-sell",
        "crm_model": "Upsell Propensity",
        "crm_model_key": "upsell_propensity",
        "description": "Identify which customers are most likely to buy additional products or upgrade.",
        "business_value": "Revenue expansion without new customer acquisition cost",
        "ml_goal": "classification",
        "required_cols": [],
        "preferred_cols": ["purchase_history", "product", "account_age", "feature_adoption", "support_interactions"],
        "fallback_cols": ["sales_agent", "product", "created_date", "close_value"],
        "target_col": "deal_stage",
        "ml_model": "LightGBM/XGBoost",
        "source_table_hints": ["sales_pipeline", "orders", "accounts"],
    },
    "forecast_revenue": {
        "label": "Forecast revenue",
        "crm_model": "Sales Forecasting",
        "crm_model_key": "sales_forecasting",
        "description": "Predict future revenue based on pipeline and historical sales patterns.",
        "business_value": "Budget planning, resource allocation, investor reporting",
        "ml_goal": "regression",
        "required_cols": [],
        "preferred_cols": ["close_value", "deal_stage", "sales_agent", "product", "created_date"],
        "fallback_cols": ["close_value", "sales_agent", "product"],
        "target_col": "close_value",
        "ml_model": "XGBoost Regressor",
        "source_table_hints": ["sales_pipeline", "orders", "revenue"],
    },
    "segment_customers": {
        "label": "Segment customers",
        "crm_model": "Customer Segmentation",
        "crm_model_key": "customer_segmentation",
        "description": "Group customers into actionable clusters: Loyal, At Risk, High Value, Low Engagement.",
        "business_value": "Personalized campaigns, targeted outreach, resource prioritization",
        "ml_goal": "clustering",
        "required_cols": [],
        "preferred_cols": ["purchase_freq", "close_value", "account_age", "product", "sales_agent"],
        "fallback_cols": ["close_value", "sales_agent", "product", "created_date"],
        "target_col": None,
        "ml_model": "K-Means",
        "source_table_hints": ["sales_pipeline", "customers", "accounts", "orders"],
    },
    "improve_onboarding": {
        "label": "Improve onboarding",
        "crm_model": "Activation Prediction",
        "crm_model_key": "activation_prediction",
        "description": "Predict which new users will successfully activate and which need intervention.",
        "business_value": "Better onboarding ROI, reduced early churn",
        "ml_goal": "classification",
        "required_cols": [],
        "preferred_cols": ["login_freq", "feature_adoption", "support_interactions", "created_date"],
        "fallback_cols": ["sales_agent", "product", "created_date"],
        "target_col": "deal_stage",
        "ml_model": "XGBoost",
        "source_table_hints": ["customers", "accounts", "sales_pipeline"],
    },
    "improve_engagement": {
        "label": "Improve customer engagement",
        "crm_model": "Position-Based Login Prediction",
        "crm_model_key": "position_login",
        "description": "Analyze login activity relative to user lifecycle stage to generate behavioral insights.",
        "business_value": "Engagement optimization, lifecycle marketing, product adoption",
        "ml_goal": "classification",
        "required_cols": [],
        "preferred_cols": ["login_freq", "feature_adoption", "account_age", "support_interactions"],
        "fallback_cols": ["sales_agent", "product", "created_date"],
        "target_col": "deal_stage",
        "ml_model": "XGBoost",
        "source_table_hints": ["customers", "accounts", "sales_pipeline"],
    },
}


def detect_available_models(schema_tables: List[Dict]) -> List[str]:
    """
    Given a list of schema table nodes, detect which business goals
    are feasible based on available columns.
    Returns list of goal keys that are possible.
    """
    # Flatten all column names across all tables
    all_cols = set()
    table_names = set()
    for table in schema_tables:
        table_names.add(table.get("id", "").lower())
        for col in table.get("columns", []):
            all_cols.add(col.get("name", "").lower())

    available_goals = []
    for goal_key, config in GOAL_CATALOGUE.items():
        # Check if any source table hint matches
        table_match = any(
            hint in table_names
            for hint in config["source_table_hints"]
        )
        # Always include if we have any data tables
        if table_match or len(table_names) > 0:
            available_goals.append(goal_key)

    return available_goals


def recommend_model(
    goal_key: str,
    schema_tables: List[Dict],
) -> Optional[Dict[str, Any]]:
    """
    Given a business goal and schema, return a full recommendation
    including which table, target column, features, and ML model to use.
    """
    if goal_key not in GOAL_CATALOGUE:
        return None

    config = GOAL_CATALOGUE[goal_key]

    # Find best matching table
    all_tables = {t.get("id", "").lower(): t for t in schema_tables}
    best_table = None
    best_table_cols = []

    for hint in config["source_table_hints"]:
        if hint in all_tables:
            best_table = hint
            best_table_cols = [c.get("name", "") for c in all_tables[hint].get("columns", [])]
            break

    # Fall back to first available table
    if not best_table and schema_tables:
        first = schema_tables[0]
        best_table = first.get("id", "")
        best_table_cols = [c.get("name", "") for c in first.get("columns", [])]

    if not best_table:
        return None

    # Determine which preferred cols are actually available
    available_preferred = [c for c in config["preferred_cols"] if c in best_table_cols]
    available_fallback = [c for c in config["fallback_cols"] if c in best_table_cols]

    # Use preferred if available, otherwise fallback
    feature_cols = available_preferred if available_preferred else available_fallback

    # Determine target column
    target_col = config["target_col"]
    if target_col and target_col not in best_table_cols:
        # Try to find a suitable target
        for candidate in ["deal_stage", "status", "stage", "outcome", "converted"]:
            if candidate in best_table_cols:
                target_col = candidate
                break

    return {
        "goal_key": goal_key,
        "goal_label": config["label"],
        "crm_model": config["crm_model"],
        "crm_model_key": config["crm_model_key"],
        "description": config["description"],
        "business_value": config["business_value"],
        "ml_model": config["ml_model"],
        "ml_goal": config["ml_goal"],
        "source_table": best_table,
        "target_col": target_col,
        "feature_cols": feature_cols,
        "available_cols": best_table_cols,
        "data_quality": "good" if available_preferred else "limited",
        "data_quality_note": (
            f"Found {len(available_preferred)} ideal features for this model."
            if available_preferred
            else f"Ideal features not found. Using {len(available_fallback)} available columns as proxy."
        ),
    }


def get_all_goals() -> List[Dict]:
    """Return all goals with labels for the UI dropdown."""
    return [
        {"key": k, "label": v["label"], "crm_model": v["crm_model"], "ml_model": v["ml_model"]}
        for k, v in GOAL_CATALOGUE.items()
    ]

# ── DB Classification ─────────────────────────────────────────────────────────

CRM_TABLE_SIGNALS = {
    "leads", "opportunities", "deals", "contacts", "accounts", "customers",
    "sales_pipeline", "pipeline", "prospects", "campaigns", "activities",
    "subscriptions", "churn", "retention", "support_tickets", "tickets"
}

ERP_TABLE_SIGNALS = {
    "invoices", "purchase_orders", "inventory", "warehouse", "shipments",
    "suppliers", "vendors", "general_ledger", "payroll", "assets",
    "cost_centers", "budgets", "procurement"
}


def classify_db(schema_tables: List[Dict]) -> Dict[str, Any]:
    """
    Classify a database as CRM, ERP, or Hybrid based on table names.
    Returns classification + confidence + matched signals.
    """
    table_names = {t.get("id", "").lower() for t in schema_tables}
    crm_hits = table_names & CRM_TABLE_SIGNALS
    erp_hits = table_names & ERP_TABLE_SIGNALS

    if crm_hits and erp_hits:
        db_type = "Hybrid"
        confidence = 0.75
    elif crm_hits:
        db_type = "CRM"
        confidence = min(0.6 + len(crm_hits) * 0.1, 0.99)
    elif erp_hits:
        db_type = "ERP"
        confidence = min(0.6 + len(erp_hits) * 0.1, 0.99)
    else:
        db_type = "Unknown"
        confidence = 0.3

    return {
        "db_type": db_type,
        "confidence": round(confidence, 2),
        "crm_signals": list(crm_hits),
        "erp_signals": list(erp_hits),
        "suitable_for": "CRM predictive models" if db_type in ("CRM", "Hybrid") else "ERP analytics",
    }
