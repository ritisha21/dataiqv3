from app.infrastructure.cache.celery_app import celery_app

connection_id = "f0ab1c5c-bb3d-4dbc-9e5e-732b4bc764de"
tenant_id = "00000000-0000-0000-0000-000000000001"

result = celery_app.send_task(
    "app.infrastructure.tasks.schema_tasks.introspect_schema_task",
    args=[connection_id, tenant_id],
    queue="schema"
)
print(f"Task dispatched: {result.id}")