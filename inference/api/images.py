"""Asynchronous MiniMax H3 image generation API."""

from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from inference.api.responses import read_json_object
from inference.assets.signing import signed_asset_path
from inference.config import Settings
from inference.db.repository import create_task, get_task, list_assets
from inference.errors import InferenceError, ProtocolError
from inference.workflows.image import RESOLUTIONS

router = APIRouter(prefix="/v1")
IMAGE_MODEL = "MiniMax-H3-Image"
HEX_ID = re.compile(r"^[0-9a-f]{32}$")
PROMPT_LIMIT = 4000


@router.post("/images/generations", status_code=202)
async def create_image(request: Request):
    settings: Settings = request.app.state.settings
    if "application/json" not in request.headers.get("content-type", "").lower():
        raise InferenceError("UNSUPPORTED_MEDIA", "Content-Type 必须是 application/json。", 415)
    try:
        body = await read_json_object(request, 1024 * 1024)
    except ProtocolError as exc:
        raise InferenceError("BAD_JSON", "请求 JSON 无法解析。", exc.http_status) from exc
    model, prompt, size = _parse_image_request(body)
    width, height = (1024, 1024) if size == "1024x1024" else (2048, 2048)
    task = create_task(
        settings,
        media_type="image",
        model=model,
        mode="t2i",
        prompt=prompt,
        params={"size": size, "width": width, "height": height},
        provider="comfyui_h3_image",
    )
    return {"task_id": task.id, "model": model, "status": task.status, "size": size}


@router.get("/images/generations/{task_id}")
def get_image(task_id: str, request: Request):
    if not HEX_ID.fullmatch(task_id):
        raise InferenceError("NOT_FOUND", "任务不存在。", 404)
    settings: Settings = request.app.state.settings
    task = get_task(settings, task_id)
    if task is None or task.media_type != "image":
        raise InferenceError("NOT_FOUND", "任务不存在。", 404)
    assets = []
    if task.status == "succeeded":
        for asset in list_assets(settings, task.id):
            assets.append(
                {
                    "asset_id": asset.id,
                    "mime_type": asset.mime_type,
                    "url": signed_asset_path(settings, asset.id),
                    "sha256": asset.sha256,
                    "size_bytes": asset.size_bytes,
                }
            )
    payload = {
        "task_id": task.id,
        "model": task.model,
        "status": task.status,
        "size": task.params.get("size"),
        "assets": assets,
    }
    if task.status in {"failed", "needs_review"}:
        payload["error"] = {"code": task.error_code, "message": task.error_message}
    if task.status == "needs_review":
        payload["attention_required"] = True
    return JSONResponse(payload)


def _parse_image_request(body: dict) -> tuple[str, str, str]:
    unknown = set(body) - {"model", "prompt", "size"}
    if unknown:
        raise InferenceError("INPUT_INVALID", "请求包含不支持的字段。", 422)
    if body.get("model") != IMAGE_MODEL:
        raise InferenceError("INPUT_INVALID", "图片模型仅支持 MiniMax-H3-Image。", 422)
    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise InferenceError("INPUT_INVALID", "提示词不能为空。", 422)
    prompt = prompt.strip()
    if not 1 <= len(prompt) <= PROMPT_LIMIT:
        raise InferenceError("INPUT_INVALID", "提示词长度必须在 1 到 4000 个字符之间。", 422)
    size = body.get("size")
    if size not in RESOLUTIONS:
        raise InferenceError("INPUT_INVALID", "图片尺寸仅支持 1024x1024 和 2048x2048。", 422)
    return IMAGE_MODEL, prompt, size
