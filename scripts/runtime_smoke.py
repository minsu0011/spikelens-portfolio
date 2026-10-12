"""Actual public Compose QA, with project-guarded stop/start and no secret output."""
import csv
import io
import json
import os
import secrets
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DOCKER = json.loads(os.environ.get("DOCKER_COMMAND_JSON", '["docker"]'))
BASE = os.environ.get("PUBLIC_API_URL", "http://127.0.0.1:8200")


def compose(*args):
    result = subprocess.run(DOCKER + ["compose", *args], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace", timeout=120)
    if result.returncode:
        raise RuntimeError("Public Compose operation failed: " + args[0])
    return result.stdout


def headers(client):
    return {"X-CSRF-Token": client.cookies["spikelens_csrf"]}


def ready(client):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if client.get("/api/v1/health/ready").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(.5)
    raise RuntimeError("Public dependencies did not recover")


def upload(client, filename):
    with (ROOT / "sample_data" / filename).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    ticker = "QA" + uuid.uuid4().hex[:10].upper()
    for row in rows[1:]:
        row[0] = ticker
    buffer = io.StringIO(newline=""); csv.writer(buffer).writerows(rows)
    response = client.post("/api/v1/uploads", files={"file": (filename, buffer.getvalue().encode(), "text/csv")}, headers=headers(client))
    response.raise_for_status()
    assert response.json()["status"] == "VALIDATED"
    return response.json()["id"]


def job(client, upload_id):
    response = client.post("/api/v1/analyses", json={"upload_id": upload_id}, headers={**headers(client), "Idempotency-Key": "qa-" + uuid.uuid4().hex})
    response.raise_for_status()
    return response.json()


def completed(client, ident):
    deadline = time.monotonic() + 100
    progress = []
    while time.monotonic() < deadline:
        response = client.get("/api/v1/jobs/" + ident); response.raise_for_status()
        state = response.json()
        if not progress or state["progress"] != progress[-1]:
            progress.append(state["progress"])
        if state["status"] == "SUCCEEDED":
            result = client.get("/api/v1/jobs/" + ident + "/results"); result.raise_for_status()
            body = result.json()
            assert body["total"] == state["total_rows"]
            assert all(row["metrics"]["fixture_only"] and row["model_version"] == "synthetic-fixture-v1" for row in body["items"])
            return {"status": "SUCCEEDED", "stored_result_rows": body["total"], "stored_progress_observed": progress, "fixture_only": True}
        if state["status"] == "FAILED":
            raise RuntimeError("Public demo job failed")
        time.sleep(.2)
    raise RuntimeError("Public demo job did not complete")


def main():
    configuration = json.loads(compose("config", "--format", "json"))
    if configuration["name"] != "spikelens-public":
        raise RuntimeError("Refusing outage operations outside explicit public project")
    result = {"utc": datetime.now(timezone.utc).isoformat(), "scope": "Actual public snapshot services only; unrelated services not stopped", "checks": {}}
    email = "qa-" + uuid.uuid4().hex[:10] + "@example.com"
    password = secrets.token_urlsafe(24)
    with httpx.Client(base_url=BASE, timeout=15, trust_env=False) as client:
        assert client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": "Synthetic QA Operator"}).status_code == 201
        assert client.post("/api/v1/auth/logout", headers=headers(client)).status_code == 204
        assert client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code == 200
        event = {"ticker": "QA" + uuid.uuid4().hex[:8].upper(), "event_time": "2025-01-01T12:00:00Z", "session": "RTH", "p0_price": 100, "t5_price": 105, "volume": 10, "price_path": [100, 105]}
        response = client.post("/api/v1/events", json=event, headers=headers(client)); assert response.status_code == 201
        ident = response.json()["id"]
        assert client.get("/api/v1/events/" + ident).status_code == 200
        assert client.put("/api/v1/events/" + ident, json={**event, "volume": 11}, headers=headers(client)).status_code == 200
        assert client.delete("/api/v1/events/" + ident, headers=headers(client)).status_code == 204
        assert client.get("/api/v1/admin/metrics").status_code == 403
        compose("exec", "-T", "backend", "python", "-m", "app.db.admin", "--email", email)
        assert client.get("/api/v1/admin/metrics").status_code == 200
        result["checks"]["auth_CRUD_admin"] = "PASS: register/logout/login, create/read/update/delete, role403 then localCLI promotion200"
        first = upload(client, "events-small.csv")
        try:
            compose("stop", "redis")
            assert client.get("/api/v1/health/ready").status_code == 503
            summary = client.get("/api/v1/analytics/summary"); assert summary.status_code == 200 and summary.json()["total_events"] == 10000
            start = time.perf_counter(); one = job(client, first); elapsed = time.perf_counter() - start
            assert one["status"] == "QUEUED" and one["pending_dispatch"] and elapsed < 5
            result["checks"]["actual_redis_stop"] = {"ready": 503, "summary_DB_fallback": 200, "durable_queued_job": True, "enqueue_seconds": elapsed}
        finally:
            compose("start", "redis")
        ready(client)
        result["checks"]["redis_recovery"] = completed(client, one["id"])
        second = upload(client, "events-progress.csv")
        try:
            compose("stop", "celery-worker")
            two = job(client, second); time.sleep(1)
            state = client.get("/api/v1/jobs/" + two["id"]).json()
            assert state["status"] == "QUEUED" and state["processed_rows"] == 0
            result["checks"]["actual_worker_stop"] = {"status": "QUEUED", "processed_rows": 0}
        finally:
            compose("start", "celery-worker")
        result["checks"]["worker_recovery"] = completed(client, two["id"])
        try:
            compose("stop", "postgres")
            assert client.get("/api/v1/health/live").status_code == 200
            assert client.get("/api/v1/health/ready").status_code == 503
            assert client.get("/api/v1/events").status_code == 503
            result["checks"]["actual_postgres_stop"] = {"live": 200, "ready": 503, "events": 503}
        finally:
            compose("start", "postgres")
        ready(client)
        assert client.get("/api/v1/events").status_code == 200
        result["checks"]["postgres_recovery"] = "PASS"
        client.post("/api/v1/auth/logout", headers=headers(client)).raise_for_status()
    result["status"] = "PASS"
    (ROOT / "docs/evidence/PUBLIC_RUNTIME_QA.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
