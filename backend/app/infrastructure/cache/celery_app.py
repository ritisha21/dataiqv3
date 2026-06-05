from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "dataiq",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.infrastructure.tasks.ml_tasks", "app.infrastructure.tasks.schema_tasks", "app.infrastructure.tasks.etl_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.infrastructure.tasks.ml_tasks.*": {"queue": "ml"},
        "app.infrastructure.tasks.schema_tasks.*": {"queue": "schema"},
    },
)
