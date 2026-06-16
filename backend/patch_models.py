path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\api\v1\endpoints\models.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Add import after existing imports
old_import = "from app.infrastructure.tasks.ml_tasks import train_model_task"
new_import = (
    "from app.infrastructure.tasks.ml_tasks import train_model_task\n"
    "from app.infrastructure.ml_pipeline.goal_mapper import detect_available_models, recommend_model, get_all_goals"
)

if "goal_mapper" not in content:
    content = content.replace(old_import, new_import)
    print("Added import")
else:
    print("Import already exists")

# Add SchemaSnapshot to domain imports
if "SchemaSnapshot" not in content:
    content = content.replace(
        "from app.domain.models.models import (",
        "from app.domain.models.models import (\n    SchemaSnapshot,"
    )
    print("Added SchemaSnapshot import")

# Add endpoints at end of file
new_endpoints = (
    "\n\n"
    "@router.get(\"/goals/all\")\n"
    "async def list_goals():\n"
    "    \"\"\"Return all available business goals.\"\"\"\n"
    "    return get_all_goals()\n"
    "\n\n"
    "@router.get(\"/goals/available/{connection_id}\")\n"
    "async def available_goals(\n"
    "    connection_id: str,\n"
    "    ctx: TenantContext = Depends(get_tenant_context),\n"
    "    db: AsyncSession = Depends(get_db),\n"
    "):\n"
    "    \"\"\"Return which business goals are feasible given the connected schema.\"\"\"\n"
    "    result = await db.execute(\n"
    "        select(SchemaSnapshot)\n"
    "        .where(SchemaSnapshot.connection_id == connection_id)\n"
    "        .where(SchemaSnapshot.tenant_id == ctx.tenant_id)\n"
    "        .order_by(SchemaSnapshot.version.desc())\n"
    "        .limit(1)\n"
    "    )\n"
    "    snapshot = result.scalar_one_or_none()\n"
    "    if not snapshot:\n"
    "        return []\n"
    "    schema_tables = snapshot.schema_graph.get(\"nodes\", [])\n"
    "    available = detect_available_models(schema_tables)\n"
    "    all_goals = {g[\"key\"]: g for g in get_all_goals()}\n"
    "    return [all_goals[k] for k in available if k in all_goals]\n"
    "\n\n"
    "@router.post(\"/goals/recommend\")\n"
    "async def recommend(\n"
    "    req: Dict[str, Any],\n"
    "    ctx: TenantContext = Depends(get_tenant_context),\n"
    "    db: AsyncSession = Depends(get_db),\n"
    "):\n"
    "    \"\"\"Given a business goal and connection, recommend a CRM model + training config.\"\"\"\n"
    "    connection_id = req.get(\"connection_id\")\n"
    "    goal_key = req.get(\"goal_key\")\n"
    "\n"
    "    if not connection_id or not goal_key:\n"
    "        raise HTTPException(400, \"connection_id and goal_key are required\")\n"
    "\n"
    "    result = await db.execute(\n"
    "        select(SchemaSnapshot)\n"
    "        .where(SchemaSnapshot.connection_id == connection_id)\n"
    "        .where(SchemaSnapshot.tenant_id == ctx.tenant_id)\n"
    "        .order_by(SchemaSnapshot.version.desc())\n"
    "        .limit(1)\n"
    "    )\n"
    "    snapshot = result.scalar_one_or_none()\n"
    "    if not snapshot:\n"
    "        raise HTTPException(404, \"No schema found. Run a schema scan first.\")\n"
    "\n"
    "    schema_tables = snapshot.schema_graph.get(\"nodes\", [])\n"
    "    recommendation = recommend_model(goal_key, schema_tables)\n"
    "\n"
    "    if not recommendation:\n"
    "        raise HTTPException(400, \"Could not generate recommendation for this goal and schema.\")\n"
    "\n"
    "    return recommendation\n"
)

if "goals/all" not in content:
    content = content.rstrip() + new_endpoints
    print("Added 3 new endpoints")
else:
    print("Endpoints already exist")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Done! Verify with: GET /api/v1/models/goals/all")
