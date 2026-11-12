"""Error envelopes for the image API and the video V2 protocol."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from inference.errors import InferenceError, kind_for


def install_error_handlers(app) -> None:
    @app.exception_handler(InferenceError)
    async def inference_error(request: Request, exc: InferenceError):
        if request.url.path.startswith("/v2"):
            return JSONResponse(
                {
                    "type": "error",
                    "error": {"type": exc.kind, "message": exc.message, "http_code": str(exc.http_status)},
                },
                status_code=exc.http_status,
            )
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message, "type": kind_for(exc.http_status)}},
            status_code=exc.http_status,
        )


async def read_json_object(request: Request, limit: int) -> dict:
    from inference.errors import ProtocolError

    total = 0
    parts: list[bytes] = []
    async for part in request.stream():
        total += len(part)
        if total > limit:
            raise ProtocolError("BODY_TOO_LARGE", "Request JSON too large", 413)
        parts.append(part)
    try:
        import json

        body = json.loads(b"".join(parts))
    except (ValueError, UnicodeError) as exc:
        raise ProtocolError("BAD_JSON", "Malformed JSON", 400) from exc
    if not isinstance(body, dict):
        raise ProtocolError("BAD_JSON", "JSON body must be an object", 400)
    return body
