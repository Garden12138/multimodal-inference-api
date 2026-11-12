"""Download registered assets only. Paths outside the database are not accepted."""

from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from inference.assets.signing import asset_signature, valid_signature, video_signature
from inference.assets.storage import read_verified, safe_download_name
from inference.auth.middleware import bearer_ok
from inference.config import Settings
from inference.db.repository import get_asset, get_task, list_assets
from inference.errors import InferenceError, ProtocolError

image_router = APIRouter(prefix="/v1")
video_router = APIRouter(prefix="/v2")
HEX_ID = re.compile(r"^[0-9a-f]{32}$")
ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp", "video/mp4", "video/webm", "video/x-matroska"}


@image_router.get("/files/{asset_id}")
def download_asset(asset_id: str, request: Request, expires: int | None = None, signature: str | None = None):
    if not HEX_ID.fullmatch(asset_id):
        raise InferenceError("NOT_FOUND", "文件不存在。", 404)
    settings: Settings = request.app.state.settings
    signed = False
    if expires is not None and signature is not None:
        signed = valid_signature(asset_signature(settings, asset_id, expires), signature, expires)
    if not signed and not bearer_ok(request.headers.get("authorization", ""), settings.api_key):
        status = 403 if signature else 401
        code = "FORBIDDEN" if status == 403 else "UNAUTHORIZED"
        message = "下载链接无效或已过期。" if status == 403 else "需要 API Key 或有效签名。"
        raise InferenceError(code, message, status)
    asset = get_asset(settings, asset_id)
    if asset is None or asset.mime_type not in ALLOWED_MIME:
        raise InferenceError("NOT_FOUND", "文件不存在。", 404)
    path = read_verified(settings, asset.storage_key, asset.sha256)
    filename = safe_download_name(asset.filename, f"{asset.id}.bin")
    return FileResponse(
        path,
        media_type=asset.mime_type,
        filename=filename,
        content_disposition_type="attachment",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@video_router.get("/files/{task_id}")
def download_video(task_id: str, request: Request, expires: int, signature: str):
    if not HEX_ID.fullmatch(task_id):
        raise ProtocolError("NOT_FOUND", "Task not found", 404)
    settings: Settings = request.app.state.settings
    if not valid_signature(video_signature(settings, task_id, expires), signature, expires):
        raise ProtocolError("FORBIDDEN", "Link expired or invalid", 403)
    task = get_task(settings, task_id)
    if task is None or task.media_type != "video":
        raise ProtocolError("NOT_FOUND", "Task not found", 404)
    if task.status != "succeeded":
        raise ProtocolError("NOT_READY", "Video is not ready", 409)
    assets = [asset for asset in list_assets(settings, task.id) if asset.media_type == "video"]
    if not assets or assets[0].mime_type not in ALLOWED_MIME:
        raise ProtocolError("NOT_FOUND", "Video file is missing", 404)
    asset = assets[0]
    try:
        path = read_verified(settings, asset.storage_key, asset.sha256)
    except InferenceError as exc:
        if exc.http_status == 409:
            raise ProtocolError("FILE_TAMPERED", "Video file failed verification", 409) from exc
        raise ProtocolError("NOT_FOUND", "Video file is missing", 404) from exc
    extension = ".webm" if asset.mime_type == "video/webm" else ".mkv" if asset.mime_type == "video/x-matroska" else ".mp4"
    return FileResponse(
        path,
        media_type=asset.mime_type,
        filename=f"h3_{task_id}{extension}",
        content_disposition_type="attachment",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
