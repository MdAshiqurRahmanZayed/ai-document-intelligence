import pytest

from app.core.config import get_settings


def test_ping_task_and_queues(valid_env: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    from app.workers.celery_app import celery_app, ping

    assert ping.apply().get() == "pong"
    assert {q.name for q in celery_app.conf.task_queues} == {"ingest", "ocr", "llm", "embed"}
    assert celery_app.conf.task_acks_late is True
