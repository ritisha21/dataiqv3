from app.infrastructure.cache.celery_app import celery_app
from app.core.config import settings
from app.core.security import decrypt_credential
import structlog

logger = structlog.get_logger()


@celery_app.task(bind=True, max_retries=2, name="app.infrastructure.tasks.ml_tasks.train_model_task")
def train_model_task(self, model_id: str, tenant_id: str, connection_config: dict, training_config: dict):
    """
    Async ML training task.
    connection_config: {db_type, host, port, database, username, encrypted_password}
    training_config: {goal, target_col, source_table, hyperparameters, feature_cols}
    """
    from app.infrastructure.ml_pipeline.pipeline import ml_pipeline
    from app.infrastructure.feature_store.feature_store import feature_store
    from sqlalchemy import create_engine, text
    import pandas as pd

    logger.info("train_model_task_start", model_id=model_id, tenant_id=tenant_id)

    try:
        # Build engine
        db_type = connection_config["db_type"]
        password = decrypt_credential(connection_config["encrypted_password"])
        username = connection_config["username"]
        host = connection_config["host"]
        port = connection_config["port"]
        database = connection_config["database"]

        if db_type == "postgres":
            url = f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}"
        else:
            url = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"

        engine = create_engine(url, pool_pre_ping=True)

        # Load data
        source_table = training_config["source_table"]
        with engine.connect() as conn:
            df = pd.read_sql(text(f'SELECT * FROM "{source_table}" LIMIT 50000'), conn)

        engine.dispose()

        dataset_hash = feature_store.compute_dataset_hash(df)

        # Feature engineering
        feature_df, definitions = feature_store.build_features(
            df,
            training_config.get("semantic_mappings", {}),
            source_table,
            target_col=training_config["target_col"],
        )

        # Train
        from app.domain.models.models import ModelGoal
        goal_enum = ModelGoal(training_config["goal"])

        result = ml_pipeline.train(
            df=feature_df,
            target_col=training_config["target_col"],
            goal=goal_enum,
            model_id=model_id,
            tenant_id=tenant_id,
            hyperparameters=training_config.get("hyperparameters", {}),
            dataset_hash=dataset_hash,
        )

        # Update model status in DB via sync connection
        _update_model_status(
            model_id=model_id,
            status="ready",
            metrics=result["metrics"],
            artifact_path=result["artifact_path"],
            dataset_hash=dataset_hash,
            feature_cols=result["feature_cols"],
        )

        logger.info("train_model_task_complete", model_id=model_id, metrics=result["metrics"])
        return {"status": "success", "metrics": result["metrics"]}

    except Exception as e:
        logger.error("train_model_task_failed", model_id=model_id, error=str(e))
        _update_model_status(model_id=model_id, status="failed", error_message=str(e))
        raise self.retry(exc=e, countdown=30)


def _update_model_status(model_id: str, status: str, **kwargs):
    """Synchronous DB update for model status."""
    from sqlalchemy import create_engine, text
    from app.core.config import settings
    import json

    engine = create_engine(settings.SYNC_DATABASE_URL)
    try:
        with engine.begin() as conn:
            updates = {"status": status}
            updates.update(kwargs)

            if status == "ready":
                conn.execute(text("""
                    UPDATE ml_models SET
                        status = :status,
                        metrics = :metrics,
                        artifact_path = :artifact_path,
                        dataset_hash = :dataset_hash,
                        feature_columns = :feature_cols,
                        trained_at = NOW()
                    WHERE id = :model_id
                """), {
                    "status": status,
                    "metrics": json.dumps(kwargs.get("metrics", {})),
                    "artifact_path": kwargs.get("artifact_path", ""),
                    "dataset_hash": kwargs.get("dataset_hash", ""),
                    "feature_cols": json.dumps(kwargs.get("feature_cols", [])),
                    "model_id": model_id,
                })
            else:
                conn.execute(text("""
                    UPDATE ml_models SET
                        status = :status,
                        error_message = :error_message
                    WHERE id = :model_id
                """), {
                    "status": status,
                    "error_message": kwargs.get("error_message", "Unknown error"),
                    "model_id": model_id,
                })
    finally:
        engine.dispose()
