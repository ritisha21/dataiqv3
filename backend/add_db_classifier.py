import re

# 1. Add classifier to goal_mapper.py
goal_mapper_path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\goal_mapper.py"

classifier_code = '''

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
'''

with open(goal_mapper_path, "r", encoding="utf-8") as f:
    content = f.read()

if "classify_db" not in content:
    content = content.rstrip() + classifier_code
    with open(goal_mapper_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Added classify_db to goal_mapper.py")
else:
    print("Already exists")

# 2. Patch schema_tasks.py to call classify_db and store in schema_graph
tasks_path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\tasks\schema_tasks.py"

with open(tasks_path, "r", encoding="utf-8") as f:
    content = f.read()

old = "        # Introspect\n        graph = connector_service.introspect_schema(mock)"
new = """        # Introspect
        graph = connector_service.introspect_schema(mock)"""

# Add import and classification after graph is built
old2 = "        semantic_mappings = semantic_engine.classify_schema(graph.to_dict(), connection_id)"
new2 = """        semantic_mappings = semantic_engine.classify_schema(graph.to_dict(), connection_id)
        # Classify DB type (CRM/ERP/Hybrid)
        from app.infrastructure.ml_pipeline.goal_mapper import classify_db
        graph_dict = graph.to_dict()
        graph_dict["db_classification"] = classify_db(graph_dict.get("nodes", []))"""

if "db_classification" not in content:
    content = content.replace(old2, new2)
    # Also update the INSERT to use graph_dict instead of graph.to_dict()
    content = content.replace(
        '"schema_graph": json.dumps(graph.to_dict()),',
        '"schema_graph": json.dumps(graph_dict),'
    )
    with open(tasks_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Patched schema_tasks.py")
else:
    print("Already patched")

# 3. Patch available_goals endpoint to return db_classification too
models_path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\api\v1\endpoints\models.py"

with open(models_path, "r", encoding="utf-8") as f:
    content = f.read()

old3 = "    schema_tables = snapshot.schema_graph.get(\"nodes\", [])\n    available = detect_available_models(schema_tables)\n    all_goals = {g[\"key\"]: g for g in get_all_goals()}\n    return [all_goals[k] for k in available if k in all_goals]"
new3 = """    schema_tables = snapshot.schema_graph.get("nodes", [])
    db_classification = snapshot.schema_graph.get("db_classification", {})
    available = detect_available_models(schema_tables)
    all_goals = {g["key"]: g for g in get_all_goals()}
    return {
        "db_classification": db_classification,
        "available_goals": [all_goals[k] for k in available if k in all_goals],
    }"""

if '"db_classification": db_classification' not in content:
    content = content.replace(old3, new3)
    with open(models_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Patched available_goals endpoint")
else:
    print("Already patched")

print("\nAll done! Restart uvicorn, rescan schema, then test:")
print("GET /api/v1/models/goals/available/<connection_id>")