import json
import socket
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from celery import Celery

from app.db.session import SessionLocal
from app.models import AnalysisJob
from app.services.jobs import dispatch_one
from tests.test_integration import make_job, upload, wait_job

pytestmark = pytest.mark.integration


def publisher(broker, backend):
    app = Celery("spikelens-publisher-fault-test", broker=broker, backend=backend)
    app.conf.update(
        task_default_queue="spikelens",
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_ignore_result=True,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
    )
    return app


def test_actual_unreachable_redis_publisher_api_bounded_and_retry_limit(
    client, registered, monkeypatch
):
    from app.tasks import celery_app as module

    original = module.celery_app
    # Reserve a local TCP port without listening; connections genuinely fail.
    # No production Redis service is stopped or mocked by this test.
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        url = f"redis://127.0.0.1:{reserved.getsockname()[1]}/2"
        unavailable = publisher(url, url)
        monkeypatch.setattr(module, "celery_app", unavailable)
        record = upload(client)
        start = time.perf_counter()
        job = make_job(client, record["id"], "actual-redis-offline-0001")
        elapsed = time.perf_counter() - start
        assert elapsed < 5, f"Bounded API dispatch took {elapsed:.3f}s"
        assert job["status"] == "QUEUED" and job["pending_dispatch"]
        timings = [elapsed]
        ident = uuid.UUID(job["id"])
        for _ in range(4):
            with SessionLocal() as db:
                db.get(AnalysisJob, ident).next_dispatch_at = datetime.now(UTC) - timedelta(
                    seconds=1
                )
                db.commit()
            start = time.perf_counter()
            assert not dispatch_one(ident)
            timings.append(time.perf_counter() - start)
            assert timings[-1] < 5
        with SessionLocal() as db:
            failed = db.get(AnalysisJob, ident)
            assert failed.status == "FAILED" and failed.dispatch_attempts == 5
            assert failed.error_code == "QUEUE_UNAVAILABLE"
        start = time.perf_counter()
        response = client.post(f"/api/v1/jobs/{ident}/retry")
        retry_elapsed = time.perf_counter() - start
        assert response.status_code == 202 and retry_elapsed < 5
        assert response.json()["pending_dispatch"]
        evidence = {
            "fault": "actual local TCP connection refusal, no send_task mock",
            "api_create_seconds": elapsed,
            "dispatch_seconds": timings,
            "api_retry_seconds": retry_elapsed,
            "asserted_each_less_than_seconds": 5,
            "dispatch_exhaustion": 5,
            "worker_startup_retry_unchanged": original.conf.broker_connection_retry_on_startup,
        }
        Path("test-output").mkdir(exist_ok=True)
        Path("test-output/PUBLISHER_REFUSAL_LATENCY.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        unavailable.close()
    assert original.conf.broker_connection_retry_on_startup is True


def test_healthy_broker_unreachable_result_backend_does_not_subscribe(
    client, registered, real_worker, monkeypatch
):
    from app.core.config import get_settings
    from app.tasks import celery_app as module

    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        backend = f"redis://127.0.0.1:{reserved.getsockname()[1]}/2"
        app = publisher(get_settings().redis_url, backend)
        monkeypatch.setattr(module, "celery_app", app)
        record = upload(client)
        start = time.perf_counter()
        job = make_job(client, record["id"], "result-backend-unused-0001")
        assert time.perf_counter() - start < 5
        assert wait_job(client, job["id"])["status"] == "SUCCEEDED"
        app.close()
