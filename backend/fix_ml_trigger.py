import re

path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\chat\nodes\ml_trigger.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = '''    try:
        from app.infrastructure.tasks.ml_tasks import train_model_task
        import uuid, json

        model_id = str(uuid.uuid4())

        # We need connection credentials — pull from DB synchronously
        conn_cfg = _fetch_connection_config_sync(
            state["connection_id"], state["tenant_id"]
        )
        if not conn_cfg:
            raise RuntimeError("DB connection record not found")

        training_cfg = {
            "goal":              goal,
            "target_col":        target_col,
            "source_table":      source_table,
            "hyperparameters":   {},
            "semantic_mappings": mappings,
        }

        task = train_model_task.delay(
            model_id, state["tenant_id"], conn_cfg, training_cfg
        )'''

new = '''    try:
        from app.infrastructure.tasks.ml_tasks import train_model_task
        import uuid, json

        # We need connection credentials — pull from DB synchronously
        conn_cfg = _fetch_connection_config_sync(
            state["connection_id"], state["tenant_id"]
        )
        if not conn_cfg:
            raise RuntimeError("DB connection record not found")

        # Create the ml_models record FIRST so the worker can update it
        model_id = _create_model_record_sync(
            tenant_id=state["tenant_id"],
            connection_id=state["connection_id"],
            goal=goal,
            target_col=target_col,
            source_table=source_table,
        )

        training_cfg = {
            "goal":              goal,
            "target_col":        target_col,
            "source_table":      source_table,
            "hyperparameters":   {},
            "semantic_mappings": mappings,
        }

        task = train_model_task.delay(
            model_id, state["tenant_id"], conn_cfg, training_cfg
        )'''

if old in content:
    content = content.replace(old, new)
    print("Replaced train dispatch block OK")
else:
    print("ERROR: could not find block to replace — check whitespace/encoding")

# Add the helper function before the last line
helper = '''

def _create_model_record_sync(
    tenant_id: str, connection_id: str, goal: str,
    target_col: str, source_table: str
) -> str:
    from sqlalchemy import create_engine, text
    from app.core.config import settings
    import uuid

    model_id = str(uuid.uuid4())
    engine = create_engine(settings.SYNC_DATABASE_URL)
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO ml_models
                    (id, tenant_id, connection_id, name, goal, status,
                     target_column, source_table, version)
                VALUES
                    (:id, :tenant_id, :connection_id, :name, :goal, 'pending',
                     :target_col, :source_table, 1)
            """), {
                "id":            model_id,
                "tenant_id":     tenant_id,
                "connection_id": connection_id,
                "name":          f"{goal}_model",
                "goal":          goal,
                "target_col":    target_col,
                "source_table":  source_table,
            })
        return model_id
    finally:
        engine.dispose()
'''

content = content.rstrip() + helper

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Done! ml_trigger.py patched.")