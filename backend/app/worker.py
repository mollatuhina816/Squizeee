from celery import Celery
from .config import settings

celery = Celery("quizeee", broker=settings().redis_url, backend=settings().redis_url)
celery.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"],
                   task_track_started=True, task_time_limit=300, task_soft_time_limit=270,
                   worker_prefetch_multiplier=1, result_expires=3600)


@celery.task(name="quizeee.worker.health")
def health():
    return {"status": "ok"}
