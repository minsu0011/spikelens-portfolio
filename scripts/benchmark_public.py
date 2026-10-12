"""Measure public synthetic queries; no private data, models or remote providers."""
import concurrent.futures
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import redis
from dotenv import dotenv_values
from sqlalchemy import create_engine, text

root = Path(__file__).resolve().parents[1]
settings = {**dotenv_values(root / ".env"), **os.environ}
base = settings.get("BENCHMARK_BASE_URL", "http://127.0.0.1:8200")
engine = create_engine(settings["DATABASE_URL"], connect_args={"connect_timeout": 5})
cache = redis.Redis.from_url(settings["REDIS_URL"], socket_timeout=3)
output = {"utc": datetime.now(timezone.utc).isoformat(), "scope": "Public synthetic demo only; local Docker HTTP; endpoint200requests, concurrency8", "concurrency": 8}


def stats(samples):
    ordered = sorted(samples)
    return {"N": len(ordered), "p50_ms": round(statistics.median(ordered), 3), "p95_ms": round(ordered[int((len(ordered) - 1) * .95)], 3)}


def plan(db, sql):
    return db.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql)).scalar_one()[0]


with httpx.Client(timeout=15, trust_env=False) as client:
    ready = client.get(base + "/api/v1/health/ready"); ready.raise_for_status()
    summary = client.get(base + "/api/v1/analytics/summary"); summary.raise_for_status()
    output["synthetic_public_N"] = summary.json()["total_events"]
    assert output["synthetic_public_N"] == 10000
    output["HTTP"] = {}
    for name, url in {"recent": "/api/v1/events?limit=30", "ticker": "/api/v1/events?ticker=SYN037", "session": "/api/v1/events?session=RTH", "cached_summary": "/api/v1/analytics/summary"}.items():
        for _ in range(5):
            client.get(base + url).raise_for_status()
        def request(_):
            started = time.perf_counter(); client.get(base + url).raise_for_status()
            return (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            values = list(pool.map(request, range(200)))
        output["HTTP"][name] = {**stats(values), "requests_per_second": round(200 / (time.perf_counter() - started), 3)}
    cold, warm = [], []
    for _ in range(20):
        cache.delete("spikelens:public:summary:v1")
        start = time.perf_counter(); client.get(base + "/api/v1/analytics/summary").raise_for_status(); cold.append((time.perf_counter() - start) * 1000)
        start = time.perf_counter(); client.get(base + "/api/v1/analytics/summary").raise_for_status(); warm.append((time.perf_counter() - start) * 1000)
    output["cache_paired"] = {"miss": stats(cold), "hit": stats(warm), "method": "20pairs, delete only public summary key, no FLUSHDB"}
with engine.connect() as db:
    db.execute(text("CREATE TEMP TABLE benchmark_public ON COMMIT DROP AS SELECT id,event_time,ticker,session FROM events WHERE is_public=true AND is_synthetic=true"))
    db.execute(text("ANALYZE benchmark_public"))
    sql = "SELECT id,event_time FROM benchmark_public WHERE ticker='SYN037' ORDER BY event_time DESC,id DESC LIMIT 30"
    before = [plan(db, sql) for _ in range(10)]
    db.execute(text("CREATE INDEX benchmark_public_ticker_time ON benchmark_public(ticker,event_time DESC,id DESC)"))
    db.execute(text("ANALYZE benchmark_public"))
    after = [plan(db, sql) for _ in range(10)]
    output["index_comparison"] = {"scope": "temporary synthetic-only table, no original index dropped; anchor/production effects not claimed", "before_execution_ms": [p["Execution Time"] for p in before], "after_execution_ms": [p["Execution Time"] for p in after], "before_example_plan": before[0], "after_example_plan": after[0]}
output["status"] = "PASS_MEASURED"
destination = root / "docs/evidence/PUBLIC_PERFORMANCE.json"
destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(output, indent=2), encoding="utf-8")
print(json.dumps({"status": output["status"], "HTTP": output["HTTP"], "cache_paired": output["cache_paired"], "index_median_ms": {"before": statistics.median(output["index_comparison"]["before_execution_ms"]), "after": statistics.median(output["index_comparison"]["after_execution_ms"])}}))
