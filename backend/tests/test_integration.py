import concurrent.futures
import io
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.integration

CSV = b"ticker,event_time,session,p0_price,t5_price,volume,price_path\nSYN900,2025-01-01T12:00:00Z,RTH,100,105,5000,100;103;105\nSYN901,2025-01-01T13:00:00Z,PREMARKET,25,24,6000,25;24.5;24\n"


def upload(client, data=CSV, filename="events.csv"):
    response = client.post(
        "/api/v1/uploads", files={"file": (filename, io.BytesIO(data), "text/csv")}
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_job(client, upload_id, key="request-key-0001"):
    response = client.post(
        "/api/v1/analyses", json={"upload_id": upload_id}, headers={"Idempotency-Key": key}
    )
    assert response.status_code == 202, response.text
    return response.json()


def wait_job(client, job_id, status="SUCCEEDED", timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = client.get(f"/api/v1/jobs/{job_id}").json()
        if result["status"] == status:
            return result
        if result["status"] == "FAILED" and status != "FAILED":
            pytest.fail(str(result))
        time.sleep(0.05)
    pytest.fail(f"Job did not reach {status}: {result}")


def test_register_login_csrf_logout_and_expired_session(client, registered):
    assert client.get("/api/v1/auth/me").json()["id"] == registered["id"]
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/v1/auth/logout").status_code == 403
    client.headers["X-CSRF-Token"] = client.cookies.get("spikelens_csrf")
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "incorrect-password"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "test-password-123"},
        ).status_code
        == 200
    )
    from app.db.session import SessionLocal
    from app.models import UserSession

    with SessionLocal() as db:
        for session in db.scalars(select(UserSession)):
            session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set("spikelens_session", "invalid-session")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_event_crud_filter_private_ownership_and_public_summary(client, registered):
    event = {
        "ticker": "SYN999",
        "event_time": "2025-01-01T12:00:00Z",
        "session": "RTH",
        "p0_price": 100,
        "t5_price": 105,
        "volume": 5000,
        "price_path": [100, 103, 105],
    }
    response = client.post("/api/v1/events", json=event)
    assert response.status_code == 201, response.text
    ident = response.json()["id"]
    assert client.post("/api/v1/events", json=event).status_code == 409
    assert (
        client.get(
            "/api/v1/events", params={"ticker": "SYN999", "session": "RTH", "limit": 1}
        ).json()["total"]
        == 1
    )
    assert (
        client.get(
            "/api/v1/events",
            params={"event_date_from": "2025-02-01", "event_date_to": "2025-01-01"},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/analytics/summary").json()["total_events"] == 0
    changed = {**event, "volume": 6000}
    assert client.put(f"/api/v1/events/{ident}", json=changed).status_code == 200
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as anonymous:
        assert anonymous.get(f"/api/v1/events/{ident}").status_code == 404
        assert anonymous.post("/api/v1/events", json=event).status_code == 401
    assert client.delete(f"/api/v1/events/{ident}").status_code == 204
    assert client.get(f"/api/v1/events/{ident}").status_code == 404


def test_upload_validation_limits_and_owner_isolation(client, registered):
    record = upload(client)
    assert record["row_count"] == 2 and record["status"] == "VALIDATED"
    assert upload(client)["id"] == record["id"]
    assert (
        client.post(
            "/api/v1/uploads", files={"file": ("../../events.csv", CSV, "text/csv")}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/uploads", files={"file": ("evil.csv", b"\x00", "text/csv")}
        ).status_code
        == 422
    )
    bad = upload(client, data=CSV.replace(b"100,105,5000", b"bad,105,5000"))
    assert bad["status"] == "INVALID" and bad["validation_errors"]
    assert (
        client.post(
            "/api/v1/analyses",
            json={"upload_id": bad["id"]},
            headers={"Idempotency-Key": "bad-request-key"},
        ).status_code
        == 422
    )
    from app.core.config import get_settings

    assert (
        client.post(
            "/api/v1/uploads",
            files={"file": ("huge.csv", b"x" * (get_settings().max_upload_bytes + 1), "text/csv")},
        ).status_code
        == 413
    )
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as other:
        assert other.get(f"/api/v1/uploads/{record['id']}").status_code == 401
        assert (
            other.post(
                "/api/v1/auth/register",
                json={"email": "bob@example.com", "password": "test-password-456"},
            ).status_code
            == 201
        )
        other.headers["X-CSRF-Token"] = other.cookies.get("spikelens_csrf")
        assert other.get(f"/api/v1/uploads/{record['id']}").status_code == 404
        assert other.get("/api/v1/uploads").json()["total"] == 0
        assert other.get("/api/v1/admin/metrics").status_code == 403


def test_real_celery_pipeline_results_sse_and_permissions(client, registered, real_worker):
    record = upload(client)
    job = make_job(client, record["id"])
    finished = wait_job(client, job["id"])
    assert (
        finished["processed_rows"] == 2
        and finished["progress"] == 100
        and finished["attempts"] == 1
    )
    assert make_job(client, record["id"])["id"] == job["id"]
    assert make_job(client, record["id"], "different-key-0002")["id"] == job["id"]
    assert client.get(f"/api/v1/jobs/{job['id']}/results").json()["total"] == 2
    assert "SYN900" in client.get(f"/api/v1/jobs/{job['id']}/results.csv").text
    with client.stream("GET", f"/api/v1/jobs/{job['id']}/stream") as stream:
        assert "job.completed" in "".join(stream.iter_text())
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as other:
        other.post(
            "/api/v1/auth/register",
            json={"email": "bob@example.com", "password": "test-password-456"},
        )
        other.headers["X-CSRF-Token"] = other.cookies.get("spikelens_csrf")
        for suffix in ["", "/results", "/results.csv", "/stream"]:
            assert other.get(f"/api/v1/jobs/{job['id']}{suffix}").status_code == 404
        assert other.post(f"/api/v1/jobs/{job['id']}/retry").status_code == 404
    assert client.post(f"/api/v1/jobs/{job['id']}/retry").status_code == 409


def test_concurrent_analysis_idempotency_constraint(client, registered):
    from app.db.session import SessionLocal
    from app.services.jobs import create_job

    record = upload(client)
    owner = uuid.UUID(registered["id"])

    def create():
        with SessionLocal() as db:
            return create_job(db, owner, uuid.UUID(record["id"]), "concurrent-request-0001").id

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(lambda _: create(), range(16)))
    assert len(set(ids)) == 1


def test_broker_failure_durable_outbox_and_recovery(client, registered, real_worker, monkeypatch):
    from app.db.session import SessionLocal
    from app.models import AnalysisJob
    from app.services.jobs import recover_and_dispatch
    from app.tasks.celery_app import celery_app

    record = upload(client)
    original = celery_app.send_task

    def outage(*args, **kwargs):
        raise ConnectionError("test broker interruption")

    monkeypatch.setattr(celery_app, "send_task", outage)
    job = make_job(client, record["id"])
    assert job["status"] == "QUEUED" and job["pending_dispatch"]
    monkeypatch.setattr(celery_app, "send_task", original)
    with SessionLocal() as db:
        db.get(AnalysisJob, uuid.UUID(job["id"])).next_dispatch_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
        db.commit()
    assert recover_and_dispatch()["dispatched"] == 1
    assert wait_job(client, job["id"])["status"] == "SUCCEEDED"


def test_failure_before_completion_and_retry_deduplicates_results(client, registered):
    from app.db.session import SessionLocal
    from app.models import AnalysisJob, AnalysisResult
    from app.services.jobs import create_job
    from app.tasks.analysis import process_job

    record = upload(client)
    with SessionLocal() as db:
        ident = create_job(
            db, uuid.UUID(registered["id"]), uuid.UUID(record["id"]), "failure-before-commit-0001"
        ).id

    def fail(stage, _):
        if stage == "before_complete":
            raise RuntimeError("Injected worker interruption before final status commit")

    assert process_job(ident, checkpoint_hook=fail)["status"] == "interrupted"
    with SessionLocal() as db:
        assert db.get(AnalysisJob, ident).status == "QUEUED"
        assert (
            db.scalar(
                select(func.count())
                .select_from(AnalysisResult)
                .where(AnalysisResult.job_id == ident)
            )
            == 2
        )
        db.get(AnalysisJob, ident).next_dispatch_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert process_job(ident)["status"] == "SUCCEEDED"
    with SessionLocal() as db:
        assert db.get(AnalysisJob, ident).attempts == 2
        assert (
            db.scalar(
                select(func.count())
                .select_from(AnalysisResult)
                .where(AnalysisResult.job_id == ident)
            )
            == 2
        )
    assert process_job(ident)["status"] == "not_claimed"


def test_expired_lease_fences_old_worker(client, registered, monkeypatch):
    from app.db.session import SessionLocal
    from app.models import AnalysisJob
    from app.services.jobs import LostLease, claim_job, create_job, fenced_job, recover_and_dispatch
    from app.tasks.celery_app import celery_app

    record = upload(client)
    with SessionLocal() as db:
        ident = create_job(
            db, uuid.UUID(registered["id"]), uuid.UUID(record["id"]), "expired-lease-0001"
        ).id
    claim = claim_job(ident)
    with SessionLocal() as db:
        db.get(AnalysisJob, ident).lease_until = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    with SessionLocal() as db, pytest.raises(LostLease):
        fenced_job(db, ident, claim["lease_token"])
    monkeypatch.setattr(celery_app, "send_task", lambda *a, **kw: None)
    assert recover_and_dispatch()["recovered"] == 1
    with SessionLocal() as db:
        job = db.get(AnalysisJob, ident)
        assert job.status == "QUEUED" and job.lease_token is None


def test_upload_checksum_corruption_fails_and_owner_retry(client, registered):
    from app.db.session import SessionLocal
    from app.models import Upload
    from app.services.jobs import create_job
    from app.services.storage import LocalUploadStorage
    from app.tasks.analysis import process_job

    record = upload(client)
    with SessionLocal() as db:
        ident = create_job(
            db, uuid.UUID(registered["id"]), uuid.UUID(record["id"]), "corruption-retry-0001"
        ).id
        key = db.get(Upload, uuid.UUID(record["id"])).storage_key
    LocalUploadStorage().path(key).write_bytes(CSV + b"tampered")
    assert process_job(ident)["status"] == "FAILED"
    assert client.get(f"/api/v1/jobs/{ident}").json()["error_code"] == "INPUT_REJECTED"
    LocalUploadStorage().path(key).write_bytes(CSV)
    # Disable eager publication in this direct pipeline test; production/queue path separately verified.
    from unittest.mock import patch

    with patch("app.api.jobs.dispatch_one", return_value=False):
        assert client.post(f"/api/v1/jobs/{ident}/retry").status_code == 202
    assert process_job(ident)["status"] == "SUCCEEDED"


def test_health_cache_fallback_and_errors(client, registered, monkeypatch):
    from app.services.cache import redis_client

    assert client.get("/api/v1/health/ready").status_code == 200
    assert client.get("/api/v1/analytics/summary").status_code == 200
    assert client.get("/api/v1/analytics/summary").status_code == 200
    assert int(redis_client.get("spikelens:metrics:cache_hits")) >= 1
    import redis

    monkeypatch.setattr(
        redis_client, "get", lambda *a: (_ for _ in ()).throw(redis.ConnectionError())
    )
    assert client.get("/api/v1/analytics/summary").status_code == 200
    response = client.get("/api/v1/events", params={"session": "BAD"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.headers["X-Request-ID"]


def test_admin_role_enforced_and_real_metrics(client, registered):
    from app.db.admin import promote

    assert client.get("/api/v1/admin/metrics").status_code == 403
    promote(registered["email"])
    response = client.get("/api/v1/admin/metrics")
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["users"] == 1 and metrics["total_jobs"] == 0
    assert metrics["dependencies"] == {"database": "ok", "redis": "ok"}
    assert metrics["api"]["requests"] > 0


def test_auth_rate_limits_accounts_independently_behind_same_proxy(client, registered):
    # Twenty attempts to one account cannot lock every other account behind Next.js.
    for _ in range(19):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "incorrect-password"},
        )
        assert response.status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "incorrect-password"},
            headers={"X-Forwarded-For": "198.51.100.123"},
        ).status_code
        == 429
    )
    response = client.post(
        "/api/v1/auth/register", json={"email": "bob@example.com", "password": "test-password-456"}
    )
    assert response.status_code == 201


def test_auth_peer_ceiling_bounds_random_account_abuse(client, registered):
    from app.core.security import digest
    from app.db.session import SessionLocal
    from app.models import AuditLog

    peer = digest("testclient")
    with SessionLocal() as db:
        db.add_all(
            [
                AuditLog(
                    action="auth_attempt",
                    resource_id=digest(f"random-{n}@example.com"),
                    details={"peer_digest": peer},
                )
                for n in range(199)
            ]
        )
        db.commit()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "different@example.com", "password": "test-password-789"},
    )
    assert response.status_code == 429


def test_actual_worker_process_kill_and_lease_recovery(client, registered, real_worker):
    from app.db.session import SessionLocal
    from app.models import AnalysisResult
    from app.services.jobs import recover_and_dispatch

    header = CSV.split(b"\n", 1)[0].decode() + "\n"
    base = datetime(2025, 1, 1, tzinfo=UTC)
    rows = "".join(
        f"SYN950,{(base + timedelta(minutes=n)).isoformat()},RTH,100,105,5000,100;103;105\n"
        for n in range(2000)
    )
    record = upload(client, (header + rows).encode())
    job = make_job(client, record["id"], "real-worker-kill-0001")
    wait_job(client, job["id"], "RUNNING", timeout=15)
    real_worker.stop()  # Terminate the actual queue consumer, not a mocked processing function.
    snapshot = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert snapshot["status"] == "RUNNING" and snapshot["progress"] < 100
    from app.core.config import get_settings

    time.sleep(get_settings().job_lease_seconds + 0.25)
    assert recover_and_dispatch()["recovered"] == 1
    real_worker.start()
    time.sleep(2.1)
    recover_and_dispatch()
    finished = wait_job(client, job["id"], timeout=60)
    assert finished["attempts"] == 2 and finished["processed_rows"] == 2000
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AnalysisResult)
                .where(AnalysisResult.job_id == uuid.UUID(job["id"]))
            )
            == 2000
        )


def test_bounded_processing_and_dispatch_retries(client, registered, monkeypatch):
    from app.db.session import SessionLocal
    from app.models import AnalysisJob
    from app.services.jobs import create_job, dispatch_one
    from app.tasks.analysis import process_job
    from app.tasks.celery_app import celery_app

    record = upload(client)
    with SessionLocal() as db:
        ident = create_job(
            db, uuid.UUID(registered["id"]), uuid.UUID(record["id"]), "bounded-processing-0001"
        ).id

    def failure(stage, _):
        raise RuntimeError("Injected processing interruption")

    for _ in range(3):
        with SessionLocal() as db:
            db.get(AnalysisJob, ident).next_dispatch_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
        process_job(ident, checkpoint_hook=failure)
    assert client.get(f"/api/v1/jobs/{ident}").json()["status"] == "FAILED"
    assert client.post(f"/api/v1/jobs/{ident}/retry").status_code == 409
    assert process_job(ident)["status"] == "not_claimed"
    record2 = upload(client, CSV.replace(b"SYN900", b"SYN902"))
    with SessionLocal() as db:
        ident2 = create_job(
            db, uuid.UUID(registered["id"]), uuid.UUID(record2["id"]), "bounded-dispatch-0001"
        ).id

    def broker_failure(*args, **kwargs):
        raise ConnectionError("Injected queue interruption")

    monkeypatch.setattr(celery_app, "send_task", broker_failure)
    for _ in range(5):
        with SessionLocal() as db:
            db.get(AnalysisJob, ident2).next_dispatch_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
        assert not dispatch_one(ident2)
    with SessionLocal() as db:
        job = db.get(AnalysisJob, ident2)
        assert job.status == "FAILED" and job.dispatch_attempts == 5


def test_real_connection_refusal_database_and_redis_readiness(client, registered, monkeypatch):
    import redis
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import main
    from app.db.session import get_db
    from app.services import cache

    refused_engine = create_engine(
        "postgresql+psycopg://spikelens@127.0.0.1:1/spikelens_test",
        connect_args={"connect_timeout": 1},
    )
    refused_session = sessionmaker(bind=refused_engine)
    monkeypatch.setattr(main, "SessionLocal", refused_session)
    response = client.get("/api/v1/health/ready")
    assert (
        response.status_code == 503 and response.json()["dependencies"]["database"] == "unavailable"
    )

    def failed_db():
        with refused_session() as db:
            yield db

    main.app.dependency_overrides[get_db] = failed_db
    try:
        response = client.get("/api/v1/events")
        assert (
            response.status_code == 503
            and response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        )
        assert "password" not in response.text.lower() and "psycopg" not in response.text.lower()
    finally:
        main.app.dependency_overrides.pop(get_db)
        refused_engine.dispose()
    bad_redis = redis.Redis.from_url(
        "redis://127.0.0.1:1/2", socket_connect_timeout=0.2, socket_timeout=0.2
    )
    monkeypatch.setattr(main, "redis_client", bad_redis)
    monkeypatch.setattr(cache, "redis_client", bad_redis)
    assert client.get("/api/v1/health/ready").json()["dependencies"]["redis"] == "unavailable"
    assert client.get("/api/v1/analytics/summary").status_code == 200
