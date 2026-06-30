"""
backend/app/infrastructure/tasks/storage_tasks.py
───────────────────────────────────────────────────
Celery task: extract a table from the connected DB, write it as CSV,
upload to MinIO. Reuses the same Dask-based extraction pattern as
etl_tasks.py for consistency on large tables.
"""

from __future__ import annotations

import io
from typing import Any, Dict, List

import pandas as pd
import dask.dataframe as dd
from sqlalchemy import create_engine, text

from app.infrastructure.cache.celery_app import celery_app
from app.infrastructure.etl.scanner import etl_scanner
from app.infrastructure.storage.minio_client import minio_storage
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    max_retries=2,
    name="app.infrastructure.tasks.storage_tasks.extract_to_minio_task",
)
def extract_to_minio_task(
    self,
    tenant_id: str,
    connection_id: str,
    tables: List[str],
    connection_config: Dict[str, Any],
):
    """
    Extracts one or more tables from the connected DB and uploads each
    as a CSV snapshot to MinIO.

    connection_config: {db_type, host, port, database, username, encrypted_password}
    tables: list of table names to extract. Empty list = extract all tables
            found in the most recent schema scan (caller resolves this).
    """
    logger.info("extract_to_minio_start", tenant_id=tenant_id, tables=tables)

    class _Conn:
        pass

    from app.domain.models.models import DBType
    mock = _Conn()
    mock.db_type            = DBType(connection_config["db_type"])
    mock.host                = connection_config["host"]
    mock.port                = connection_config["port"]
    mock.database            = connection_config["database"]
    mock.username             = connection_config["username"]
    mock.encrypted_password  = connection_config["encrypted_password"]

    url = etl_scanner._build_url(mock)
    results = []

    for table in tables:
        try:
            engine = create_engine(url, pool_pre_ping=True)
            row_count = etl_scanner._fast_count(engine, table)

            if row_count > 50_000:
                idx_col = etl_scanner._find_index_col(engine, table)
                engine.dispose()
                ddf = dd.read_sql_table(
                    table_name=table, con=url, index_col=idx_col,
                    npartitions=max(4, row_count // 100_000),
                )
                df = ddf.compute()
            else:
                with engine.connect() as c:
                    df = pd.read_sql(text(f'SELECT * FROM "{table}"'), c)
                engine.dispose()

            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_bytes = csv_buffer.getvalue().encode("utf-8")

            upload_result = minio_storage.upload_csv(
                tenant_id=tenant_id,
                connection_id=connection_id,
                table_name=table,
                csv_bytes=csv_bytes,
            )

            results.append({
                "table": table,
                "status": "success",
                "row_count": len(df),
                "object_key": upload_result["object_key"],
                "size_bytes": upload_result["size_bytes"],
            })
            logger.info("extract_to_minio_table_done", table=table, rows=len(df))

        except Exception as exc:
            logger.error("extract_to_minio_table_failed", table=table, error=str(exc))
            results.append({
                "table": table,
                "status": "failed",
                "error": str(exc),
            })

    logger.info("extract_to_minio_done", results_count=len(results))
    return {"status": "done", "results": results}