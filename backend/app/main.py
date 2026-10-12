import json
import time
import uuid
from collections import deque

import redis
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from app.api import admin, analytics, auth, events, jobs, uploads
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logger
from app.core.upload_limit import UploadLimitMiddleware
from app.db.session import SessionLocal
from app.services.cache import redis_client

logger = configure_logger()

app = FastAPI(
    title="SpikeLens API",
    version="0.1.0",
    description="Public synthetic demo with data-quality processing and fixed display fixtures; no prediction implementation.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Request-ID"],
)
app.add_middleware(UploadLimitMiddleware)
api_latencies = deque(maxlen=10000)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied = request.headers.get("x-request-id", "")
    request_id = (
        supplied
        if len(supplied) <= 80 and supplied.replace("-", "").isalnum()
        else str(uuid.uuid4())
    )
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000
    api_latencies.append(elapsed)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(elapsed, 3),
            }
        )
    )
    return response


def error_response(request: Request, status: int, code: str, message: str, details=None):
    body = {
        "error": {"code": code, "message": message},
        "request_id": getattr(request.state, "request_id", None),
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(body, status_code=status)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return error_response(request, exc.status, exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Never echo password/CSV row/input values back through validation diagnostics.
    details = [
        {"field": list(item["loc"]), "message": item["msg"], "type": item["type"]}
        for item in exc.errors()
    ]
    return error_response(request, 422, "VALIDATION_ERROR", "Request validation failed", details)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    return error_response(request, exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail))


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    logger.error(
        json.dumps(
            {
                "event": "database_error",
                "request_id": getattr(request.state, "request_id", None),
                "type": type(exc).__name__,
            }
        )
    )
    return error_response(
        request, 503, "DATABASE_UNAVAILABLE", "Database is temporarily unavailable"
    )


@app.get("/api/v1/health/live", tags=["Health"])
def live():
    return {"status": "ok", "service": "spikelens", "version": "0.1.0"}


@app.get("/api/v1/health/ready", tags=["Health"])
def ready():
    checks = {}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except SQLAlchemyError:
        checks["database"] = "unavailable"
    try:
        redis_client.ping()
        checks["redis"] = "ok"
    except redis.RedisError:
        checks["redis"] = "unavailable"
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        {"status": "ready" if healthy else "not_ready", "dependencies": checks},
        status_code=200 if healthy else 503,
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.error(
        json.dumps(
            {
                "event": "unexpected_error",
                "request_id": getattr(request.state, "request_id", None),
                "type": type(exc).__name__,
            }
        )
    )
    return error_response(request, 500, "INTERNAL_ERROR", "Unexpected server error")


for router in (
    auth.router,
    events.router,
    analytics.router,
    uploads.router,
    jobs.router,
    admin.router,
):
    app.include_router(router, prefix="/api/v1")
