from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "spikelens",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.analysis"],
)
celery_app.conf.update(
    task_default_queue="spikelens",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "visibility_timeout": 180,
        "socket_connect_timeout": 2,
        "socket_timeout": 2,
    },
    result_backend_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
    task_ignore_result=True,
    beat_schedule={
        "recover-durable-jobs": {
            "task": "spikelens.recover",
            "schedule": 10.0,
            "options": {"queue": "spikelens"},
        }
    },
)
