import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

test_database_url = os.environ.get("TEST_DATABASE_URL")
test_redis_url = os.environ.get("TEST_REDIS_URL")
if test_database_url:
    os.environ["DATABASE_URL"] = test_database_url
if test_redis_url:
    os.environ["REDIS_URL"] = test_redis_url
os.environ.setdefault("JOB_LEASE_SECONDS", "10")
os.environ.setdefault("UPLOAD_DIR", str(Path(__file__).parent.parent / "test-output" / "uploads"))


@pytest.fixture(scope="session")
def integration_environment():
    if not test_database_url or not test_redis_url:
        if os.environ.get("CI"):
            pytest.fail("CI integration requires TEST_DATABASE_URL and TEST_REDIS_URL")
        pytest.skip("Set TEST_DATABASE_URL and TEST_REDIS_URL to isolated PostgreSQL/Redis")
    from sqlalchemy.engine import make_url

    database = make_url(test_database_url)
    redis_db = int(test_redis_url.rsplit("/", 1)[-1])
    if (
        database.get_backend_name() != "postgresql"
        or not database.database
        or "spikelens_test" not in database.database
        or redis_db < 2
    ):
        pytest.fail(
            "Refusing destructive fixture outside dedicated spikelens_test database and Redis DB >= 2"
        )
    from app.services.cache import redis_client

    assert redis_client.ping()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).parent.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    yield


@pytest.fixture
def db_clean(integration_environment):
    from sqlalchemy import text

    from app.db.session import SessionLocal
    from app.services.cache import redis_client

    with SessionLocal() as db:
        db.execute(
            text(
                "TRUNCATE audit_logs, job_attempts, analysis_results, analysis_jobs, events, uploads, user_sessions, users RESTART IDENTITY CASCADE"
            )
        )
        db.commit()
    redis_client.flushdb()
    yield


@pytest.fixture
def client(db_clean):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as value:
        yield value


@pytest.fixture
def registered(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "test-password-123", "name": "Alice"},
    )
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = client.cookies.get("spikelens_csrf")
    return response.json()


class RealWorker:
    def __init__(self):
        self.process = None
        self.log = None

    def start(self):
        from app.tasks.celery_app import celery_app

        self.log = (Path(__file__).parent.parent / "test-output" / "celery-integration.log").open(
            "ab"
        )
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "app.tasks.celery_app:celery_app",
                "worker",
                "--pool=solo",
                "--concurrency=1",
                "--queues=spikelens",
                "--hostname=spikelens-integration@%h",
                "--loglevel=INFO",
            ],
            cwd=Path(__file__).parent.parent,
            env=os.environ.copy(),
            stdout=self.log,
            stderr=self.log,
        )
        end = time.monotonic() + 20
        while time.monotonic() < end:
            if self.process.poll() is not None:
                pytest.fail("Real Celery worker exited; see test-output/celery-integration.log")
            if celery_app.control.ping(timeout=0.5):
                return
            time.sleep(0.1)
        pytest.fail("Real Celery worker did not become ready")

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=10)
        if self.log:
            self.log.close()
        self.process = None


@pytest.fixture
def real_worker(db_clean):
    path = Path(__file__).parent.parent / "test-output"
    path.mkdir(exist_ok=True)
    worker = RealWorker()
    worker.start()
    yield worker
    worker.stop()
