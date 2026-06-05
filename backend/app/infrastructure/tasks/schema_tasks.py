from app.infrastructure.cache.celery_app import celery_app
import structlog

logger = structlog.get_logger()


@celery_app.task(bind=True, name="app.infrastructure.tasks.schema_tasks.introspect_schema_task")
def introspect_schema_task(self, connection_id: str, tenant_id: str):
    """Async schema introspection and semantic mapping."""
    from sqlalchemy import create_engine, text
    from app.core.config import settings
    from app.core.security import decrypt_credential
    from app.infrastructure.connectors.db_connector import connector_service
    from app.infrastructure.connectors.semantic_layer import semantic_engine
    import json

    logger.info("schema_task_start", connection_id=connection_id)

    try:
        db_engine = create_engine(settings.SYNC_DATABASE_URL)

        with db_engine.connect() as conn:
            row = conn.execute(text("""
                SELECT db_type, host, port, database, username, encrypted_password
                FROM db_connections WHERE id = :id AND tenant_id = :tenant_id
            """), {"id": connection_id, "tenant_id": tenant_id}).fetchone()

        if not row:
            raise ValueError(f"Connection {connection_id} not found")

        # Build mock DBConnection object
        class MockConn:
            pass

        from app.domain.models.models import DBType
        mock = MockConn()
        mock.db_type = DBType(row[0])
        mock.host = row[1]
        mock.port = row[2]
        mock.database = row[3]
        mock.username = row[4]
        mock.encrypted_password = row[5]

        # Introspect
        graph = connector_service.introspect_schema(mock)
        semantic_mappings = semantic_engine.classify_schema(graph.to_dict(), connection_id)

        # Get current version
        with db_engine.connect() as conn:
            ver_row = conn.execute(text("""
                SELECT MAX(version) FROM schema_snapshots
                WHERE connection_id = :cid AND tenant_id = :tid
            """), {"cid": connection_id, "tid": tenant_id}).fetchone()
            current_version = (ver_row[0] or 0) + 1

        # Store schema snapshot
        with db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO schema_snapshots (tenant_id, connection_id, version, schema_graph, table_count)
                VALUES (:tenant_id, :connection_id, :version, :schema_graph, :table_count)
            """), {
                "tenant_id": tenant_id,
                "connection_id": connection_id,
                "version": current_version,
                "schema_graph": json.dumps(graph.to_dict()),
                "table_count": len(graph.nodes),
            })

            conn.execute(text("""
                INSERT INTO semantic_mappings (tenant_id, connection_id, version, mappings)
                VALUES (:tenant_id, :connection_id, :version, :mappings)
            """), {
                "tenant_id": tenant_id,
                "connection_id": connection_id,
                "version": current_version,
                "mappings": json.dumps(semantic_mappings),
            })

            conn.execute(text("""
                UPDATE db_connections SET last_tested_at = NOW()
                WHERE id = :id
            """), {"id": connection_id})

        db_engine.dispose()
        logger.info("schema_task_complete", connection_id=connection_id, tables=len(graph.nodes))
        return {"status": "success", "table_count": len(graph.nodes)}

    except Exception as e:
        logger.error("schema_task_failed", connection_id=connection_id, error=str(e))
        raise
