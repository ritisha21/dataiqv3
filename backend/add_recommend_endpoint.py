path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\api\v1\endpoints\models.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Add import at top
if "goal_mapper" not in content:
    content = content.replace(
        "from app.domain.models.models import",
        "from app.infrastructure.ml_pipeline.goal_mapper import detect_available_models, recommend_model, get_all_goals\nfrom app.domain.models.models import"
    )

# Add endpoints before last line
new_endpoints = '''

@router.get("/goals")
async def list_goals():
    """Return all available business goals."""
    return get_all_goals()


@router.post("/recommend")
async def recommend(
    req: dict,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Given a business goal and connection, recommend a CRM model."""
    from sqlalchemy import select
    from app.domain.models.models import SchemaSnapshot, DBConnection
    import json

    connection_id = req.get("connection_id")
    goal_key = req.get("goal_key")

    if not connection_id or not goal_key:
        raise HTTPException(400, "connection_id and goal_key are required")

    # Get latest schema snapshot
    result = await db.execute(
        select(SchemaSnapshot)
        .where(SchemaSnapshot.connection_id == connection_id)
        .where(SchemaSnapshot.tenant_id == ctx.tenant_id)
        .order_by(SchemaSnapshot.version.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(404, "No schema found for this connection. Run a schema scan first.")

    schema_tables = snapshot.schema_graph.get("nodes", [])
    recommendation = recommend_model(goal_key, schema_tables)

    if not recommendation:
        raise HTTPException(400, "Could not generate recommendation for this goal and schema.")

    return recommendation


@router.get("/available-goals/{connection_id}")
async def available_goals(
    connection_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Return which business goals are feasible given the connected schema."""
    from sqlalchemy import select
    from app.domain.models.models import SchemaSnapshot

    result = await db.execute(
        select(SchemaSnapshot)
        .where(SchemaSnapshot.connection_id == connection_id)
        .where(SchemaSnapshot.tenant_id == ctx.tenant_id)
        .order_by(SchemaSnapshot.version.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        return []

    schema_tables = snapshot.schema_graph.get("nodes", [])
    available = detect_available_models(schema_tables)
    all_goals = {g["key"]: g for g in get_all_goals()}
    return [all_goals[k] for k in available if k in all_goals]
'''

if "/recommend" not in content:
    content = content.rstrip() + new_endpoints
    print("Added recommend endpoints")
else:
    print("Already exists")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)