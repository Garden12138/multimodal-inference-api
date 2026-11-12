"""HMAC file links. The API key is the MAC key and is never placed in the URL."""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

from inference.config import Settings


def sign(secret: str, material: str) -> str:
    return hmac.new(secret.encode("utf-8"), material.encode("utf-8"), hashlib.sha256).hexdigest()


def video_signature(settings: Settings, task_id: str, expires: int) -> str:
    return sign(settings.api_key, f"{task_id}.{expires}")


def asset_signature(settings: Settings, asset_id: str, expires: int) -> str:
    return sign(settings.api_key, f"asset.{asset_id}.{expires}")


def valid_signature(expected: str, presented: str, expires: int, *, now: float | None = None) -> bool:
    moment = time.time() if now is None else now
    if not isinstance(expires, int) or isinstance(expires, bool):
        return False
    if expires < moment or expires > moment + 3700:
        return False
    if len(expected) != len(presented):
        return False
    return hmac.compare_digest(expected, presented)


def signed_video_url(settings: Settings, task_id: str, *, now: float | None = None) -> str:
    expires = int((time.time() if now is None else now) + settings.file_url_ttl_seconds)
    query = urlencode({"expires": expires, "signature": video_signature(settings, task_id, expires)})
    return f"{settings.public_base_url}/v2/files/{task_id}?{query}"


def signed_asset_path(settings: Settings, asset_id: str, *, now: float | None = None) -> str:
    expires = int((time.time() if now is None else now) + settings.file_url_ttl_seconds)
    query = urlencode({"expires": expires, "signature": asset_signature(settings, asset_id, expires)})
    return f"/v1/files/{asset_id}?{query}"
