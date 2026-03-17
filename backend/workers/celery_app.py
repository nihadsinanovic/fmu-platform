from celery import Celery

from app.config import settings

celery_app = Celery("fmu_engine", broker=settings.REDIS_URL)

celery_app.conf.update(
    worker_concurrency=settings.LICENSE_POOL_SIZE,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_backend=settings.REDIS_URL,
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)

celery_app.autodiscover_tasks(["workers"])
