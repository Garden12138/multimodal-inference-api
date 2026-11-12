"""CIDR allowlist and bearer authentication. Signed downloads are checked by the file route."""

from __future__ import annotations

import hmac
import ipaddress
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from inference.config import Settings

logger = logging.getLogger("inference.auth")
OPEN_PATHS = {"/healthz"}
SIGNED_DOWNLOAD_PREFIXES = ("/v2/files/", "/v1/files/")


def install_auth(app) -> None:
    @app.middleware("http")
    async def authorize(request: Request, call_next):
        settings: Settings = request.app.state.settings
        peer = request.client.host if request.client else ""
        if not network_allowed(peer, settings.allowed_networks):
            logger.info("network denied")
            return error_response(request.url.path, 403, "NETWORK_DENIED", "Network not permitted")
        if request.url.path in OPEN_PATHS:
            return await call_next(request)
        if any(request.url.path.startswith(prefix) for prefix in SIGNED_DOWNLOAD_PREFIXES):
            return await call_next(request)
        if not bearer_ok(request.headers.get("authorization", ""), settings.api_key):
            logger.info("authentication failed path=%s", request.url.path)
            return error_response(request.url.path, 401, "UNAUTHORIZED", "Invalid or missing API key")
        return await call_next(request)


def network_allowed(peer: str, networks: tuple[str, ...]) -> bool:
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    for item in networks:
        if address in ipaddress.ip_network(item, strict=False):
            return True
    return False


def bearer_ok(header: str, api_key: str) -> bool:
    if not header.startswith("Bearer "):
        return False
    token = header[7:]
    if len(token) != len(api_key):
        hmac.compare_digest(api_key, api_key)
        return False
    return hmac.compare_digest(token, api_key)


def error_response(path: str, status: int, code: str, message: str) -> JSONResponse:
    if path.startswith("/v2"):
        kind = "authorized_error"
        return JSONResponse(
            {"type": "error", "error": {"type": kind, "message": message, "http_code": str(status)}},
            status_code=status,
        )
    return JSONResponse(
        {"error": {"code": code, "message": message, "type": "authorized_error"}},
        status_code=status,
    )
