import math
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.security import digest, password_hasher, verify_password
from app.db.seed import synthetic_events
from app.schemas.events import EventInput
from app.services.csv_validation import parse_csv, safe_csv_cell
from app.services.jobs import transition


def event(**changes):
    data = {
        "ticker": "syn001",
        "event_time": datetime(2025, 1, 1, tzinfo=UTC),
        "session": "RTH",
        "p0_price": 100,
        "t5_price": 110,
        "volume": 10000,
        "price_path": [100, 102, 106, 110],
    }
    data.update(changes)
    return EventInput(**data)


def test_input_normalizes_ticker_and_utc():
    assert event(ticker=" syn001 ").ticker == "SYN001"
    assert event().event_time.tzinfo == UTC


@pytest.mark.parametrize(
    "changes",
    [
        {"event_time": "2025-01-01T00:00:00"},
        {"p0_price": 0},
        {"p0_price": math.inf},
        {"price_path": [1, math.nan]},
        {"price_path": [1]},
        {"session": "REGULAR"},
        {"ticker": "=IMPORTXML('x')"},
        {"volume": -1},
        {"volume": 1.2},
    ],
)
def test_input_rejects_unsafe_or_invalid_values(changes):
    with pytest.raises(ValidationError):
        event(**changes)




def test_synthetic_recipe_reproducible():
    one = [row.model_dump(mode="json") for row in synthetic_events(10)]
    two = [row.model_dump(mode="json") for row in synthetic_events(10)]
    assert one == two
    assert len({row["event_time"] for row in one}) == 10
    assert all(row["ticker"].startswith("SYN") for row in one)


def csv_bytes(rows):
    return ("ticker,event_time,session,p0_price,t5_price,volume,price_path\n" + rows).encode()


def test_csv_schema_and_row_errors():
    good = "SYN001,2025-01-01T12:00:00Z,RTH,100,105,5000,100;103;105\n"
    valid, errors, rows = parse_csv(csv_bytes(good), 20)
    assert len(valid) == rows == 1 and not errors
    _, errors, rows = parse_csv(csv_bytes(good + good), 20)
    assert errors[0]["row"] == 3
    assert "Duplicate" in errors[0]["message"]
    _, errors, _ = parse_csv(csv_bytes("SYN001,2025-01-01,RTH,no,105,5000,100;105\n"), 20)
    assert errors[0]["code"] == "INVALID_ROW"


def test_csv_limit_and_formula_rejection():
    rows = "SYN001,2025-01-01T12:00:00Z,RTH,100,105,5000,100;105\nSYN002,2025-01-01T12:00:00Z,RTH,100,105,5000,100;105\n"
    _, errors, _ = parse_csv(csv_bytes(rows), 1)
    assert errors[-1]["code"] == "ROW_LIMIT"
    _, errors, _ = parse_csv(
        csv_bytes("=HYPERLINK(),2025-01-01T12:00:00Z,RTH,100,105,5000,100;105\n"), 5
    )
    assert errors[0]["code"] == "INVALID_ROW"


@pytest.mark.parametrize("text", ["=1+1", "+SUM(A1)", "@SUM(A1)", "-cmd", "  =1"])
def test_export_formula_escape(text):
    assert safe_csv_cell(text).startswith("'")
    assert safe_csv_cell(12.5) == 12.5


def test_job_state_machine():
    job = SimpleNamespace(status="QUEUED")
    transition(job, "RUNNING")
    transition(job, "SUCCEEDED")
    with pytest.raises(ValueError):
        transition(job, "RUNNING")
    job.status = "FAILED"
    transition(job, "QUEUED")


def test_password_hash_and_digest():
    hashed = password_hasher.hash("test-password-123")
    assert hashed.startswith("$argon2id$") and "test-password" not in hashed
    assert verify_password(hashed, "test-password-123")
    assert not verify_password(hashed, "wrong-password")
    assert not verify_password("not-a-hash", "test-password-123")
    assert len(digest("token")) == 64


def test_storage_fsync_failure_removes_partial_content(tmp_path, monkeypatch):
    import os

    from app.services.storage import LocalUploadStorage

    storage = LocalUploadStorage(tmp_path)
    key = "a" * 32 + ".csv"

    def fail(_):
        raise OSError("Injected fsync failure")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        storage.write(key, b"partially written data")
    assert not storage.path(key).exists()
    assert list(tmp_path.iterdir()) == []


def test_storage_write_failure_removes_temporary_content(tmp_path, monkeypatch):
    from app.services import storage as module

    storage = module.LocalUploadStorage(tmp_path)
    original = module.os.fdopen

    class InterruptedWrite:
        def __init__(self, descriptor, mode):
            self.stream = original(descriptor, mode)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, data):
            self.stream.write(data[:4])
            raise OSError("Injected partial write interruption")

    monkeypatch.setattr(module.os, "fdopen", InterruptedWrite)
    with pytest.raises(OSError):
        storage.write("b" * 32 + ".csv", b"partial payload")
    assert list(tmp_path.iterdir()) == []


def test_storage_exclusive_publication_preserves_existing_file(tmp_path):
    from app.services.storage import LocalUploadStorage

    storage = LocalUploadStorage(tmp_path)
    key = "c" * 32 + ".csv"
    storage.write(key, b"original")
    with pytest.raises(FileExistsError):
        storage.write(key, b"must not overwrite")
    assert storage.read(key) == b"original"
    assert [path.name for path in tmp_path.iterdir()] == [key]
