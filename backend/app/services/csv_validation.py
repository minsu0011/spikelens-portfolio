import csv
import io

from pydantic import ValidationError

from app.core.errors import AppError
from app.schemas.events import EventInput

REQUIRED_COLUMNS = {
    "ticker",
    "event_time",
    "session",
    "p0_price",
    "t5_price",
    "volume",
    "price_path",
}
ALLOWED_COLUMNS = REQUIRED_COLUMNS | {"event_type"}


def parse_csv(data: bytes, max_rows: int) -> tuple[list[EventInput], list[dict], int]:
    if b"\x00" in data:
        raise AppError(422, "INVALID_CSV", "CSV must be plain UTF-8 text")
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError(422, "INVALID_ENCODING", "CSV must use UTF-8 encoding") from exc
    csv.field_size_limit(65536)
    reader = csv.DictReader(io.StringIO(decoded), strict=True)
    try:
        header = reader.fieldnames
    except csv.Error as exc:
        raise AppError(422, "INVALID_CSV", "CSV header is malformed") from exc
    if (
        not header
        or len(header) != len(set(header))
        or not REQUIRED_COLUMNS.issubset(header)
        or set(header) - ALLOWED_COLUMNS
    ):
        raise AppError(
            422,
            "CSV_SCHEMA_ERROR",
            "CSV headers must match the documented schema",
            {"required": sorted(REQUIRED_COLUMNS), "optional": ["event_type"]},
        )
    valid, errors, identities = [], [], set()
    rows = 0
    try:
        for rows, row in enumerate(reader, start=1):
            if rows > max_rows:
                errors.append(
                    {
                        "row": rows + 1,
                        "code": "ROW_LIMIT",
                        "message": f"Maximum {max_rows} data rows allowed",
                    }
                )
                break
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Row does not match the CSV header")
                row = {key: value.strip() for key, value in row.items()}
                row["price_path"] = row["price_path"].split(";")
                if not row.get("event_type"):
                    row.pop("event_type", None)
                event = EventInput.model_validate(row)
                identity = (event.ticker, event.event_time, event.session)
                if identity in identities:
                    raise ValueError("Duplicate ticker, timestamp and session in file")
                identities.add(identity)
                valid.append(event)
            except (ValueError, ValidationError) as exc:
                if len(errors) < 100:
                    if isinstance(exc, ValidationError):
                        reason = "; ".join(
                            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
                        )
                    else:
                        reason = str(exc)
                    errors.append({"row": rows + 1, "code": "INVALID_ROW", "message": reason[:500]})
    except csv.Error:
        errors.append(
            {
                "row": rows + 1,
                "code": "INVALID_CSV",
                "message": "Malformed CSV quoting or oversized field",
            }
        )
    if rows == 0:
        errors.append(
            {"row": 1, "code": "EMPTY_CSV", "message": "At least one data row is required"}
        )
    return valid, errors, rows


def safe_csv_cell(value):
    """Neutralize spreadsheet formula interpretation in downloadable text columns."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value
