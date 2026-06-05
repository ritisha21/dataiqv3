from app.infrastructure.cache.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    max_retries=1,
    name="app.infrastructure.tasks.etl_tasks.run_etl_task",
)
def run_etl_task(
    self,
    tenant_id:     str,
    connection_id: str,
    suggestions:   list,
    connection_config: dict,
):
    """
    Celery task wrapping ETLTrainer.run_etl_pipeline.
    connection_config: {db_type, host, port, database, username, encrypted_password}
    """
    from app.infrastructure.etl.trainer import etl_trainer
    from app.core.security import decrypt_credential

    logger.info("etl_task_start", tenant_id=tenant_id, count=len(suggestions))

    # Reconstruct a minimal mock DBConnection so scanner/trainer can use it
    class _Conn:
        pass

    from app.domain.models.models import DBType
    mock = _Conn()
    mock.db_type           = DBType(connection_config["db_type"])
    mock.host              = connection_config["host"]
    mock.port              = connection_config["port"]
    mock.database          = connection_config["database"]
    mock.username          = connection_config["username"]
    mock.encrypted_password= connection_config["encrypted_password"]

    try:
        results = etl_trainer.run_etl_pipeline(
            tenant_id     = tenant_id,
            connection_id = connection_id,
            suggestions   = suggestions,
            conn_record   = mock,
        )
        logger.info("etl_task_done", results_count=len(results))
        return {"status": "done", "results": results}
    except Exception as exc:
        logger.error("etl_task_error", error=str(exc))
        raise self.retry(exc=exc, countdown=10)
