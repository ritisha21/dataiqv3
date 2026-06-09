path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\chat\nodes\ml_trigger.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Extract target_col and source_table from the user message directly
old = "    goal     = state.get(\"goal\") or \"classification\"\n    mappings = state.get(\"semantic_mappings\") or {}\n\n    target_col, source_table = _resolve_target(mappings, goal)"

new = """    goal     = state.get("goal") or "classification"
    mappings = state.get("semantic_mappings") or {}

    # Try to extract table and target from the message directly
    message = state.get("message", "").lower()
    target_col, source_table = _resolve_target(mappings, goal)

    # Parse from message if not resolved from mappings
    import re
    table_match = re.search(r'(?:on|from|table)[\\s]+([\\w]+)[\\s]+table|([\\w]+)[\\s]+table', message)
    target_match = re.search(r'(?:using|target|predict)[\\s]+([\\w_]+)[\\s]+(?:as|column|field)?', message)

    if table_match:
        source_table = table_match.group(1) or table_match.group(2)
    if target_match:
        target_col = target_match.group(1)

    # Final fallback for churn on sales_pipeline
    if not source_table:
        source_table = "sales_pipeline"
    if not target_col:
        target_col = "deal_stage" """

if old in content:
    content = content.replace(old, new)
    print("Patched successfully")
else:
    print("ERROR: block not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)