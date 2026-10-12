import json

from app.core.config import get_settings
from app.core.errors import AppError


class UploadLimitMiddleware:
    """Bound actual streamed multipart bytes before Starlette spools a large request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        maximum = (
            get_settings().max_upload_bytes + 65536
            if scope["path"] == "/api/v1/uploads"
            else 1024 * 1024
        )
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = maximum + 1
        if declared > maximum:
            body = json.dumps(
                {
                    "error": {
                        "code": "UPLOAD_TOO_LARGE",
                        "message": "Request exceeds the configured size limit",
                    },
                    "request_id": None,
                }
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > maximum:
                    raise AppError(
                        413, "UPLOAD_TOO_LARGE", "Request exceeds the configured size limit"
                    )
            return message

        return await self.app(scope, bounded_receive, send)
