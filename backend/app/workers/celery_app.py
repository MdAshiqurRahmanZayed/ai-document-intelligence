from celery import Celery
from celery.signals import setup_logging
from kombu import Queue

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
redis_url = settings.redis_url.get_secret_value()

# `include` makes workers import the tasks module, which registers its tasks.
celery_app = Celery("docint", broker=redis_url, backend=redis_url, include=["app.workers.tasks"])
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_queues=[Queue(name) for name in ("ingest", "ocr", "llm", "embed")],
    task_default_queue="ingest",
    timezone="UTC",
)


@celery_app.task(name="app.workers.ping")
def ping() -> str:
    return "pong"


@setup_logging.connect
def _configure_logging(**_: object) -> None:
    # Connecting to this signal stops Celery from installing its own log handlers.
    configure_logging(settings.log_level, "worker")
