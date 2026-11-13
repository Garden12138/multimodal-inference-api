"""MiniMax H3 video generation V2 protocol, backed by local ComfyUI."""

from __future__ import annotations

import base64
import binascii
import io
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError

from inference.api.responses import read_json_object
from inference.assets.storage import remove_key, save_bytes
from inference.assets.signing import signed_video_url
from inference.config import Settings
from inference.db.repository import create_task, get_task
from inference.errors import ProtocolError
from inference.workflows.video import (
    ACTUAL_RESOLUTION,
    DURATION_SECONDS,
    NOMINAL_RATIO,
)

router = APIRouter(prefix="/v2")
HEX_ID = re.compile(r"^[0-9a-f]{32}$")
VIDEO_MODEL = "MiniMax-H3"


def checked_image(url: str, role: str, settings: Settings) -> tuple[str, bytes, str]:
    if not isinstance(url, str) or not url.startswith("data:image/"):
        raise ProtocolError(
            "INPUT_INVALID",
            f"{role}: only data:image/...;base64 URLs are supported by this local adapter; https:// and mm_file:// are unsupported",
            422,
        )
    header, comma, encoded = url.partition(",")
    if not comma or not header.endswith(";base64"):
        raise ProtocolError("INPUT_INVALID", f"{role}: expected base64 image data URL", 422)
    mime = header[5:-7].lower()
    if mime not in ("image/png", "image/jpeg", "image/webp"):
        raise ProtocolError("INPUT_INVALID", f"{role}: only PNG/JPEG/WebP are supported", 422)
    if len(encoded) > (settings.max_image_bytes * 4 // 3) + 16:
        raise ProtocolError("BODY_TOO_LARGE", f"{role}: image too large", 413)
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ProtocolError("INPUT_INVALID", f"{role}: invalid base64", 422) from exc
    if not 0 < len(raw) <= settings.max_image_bytes:
        raise ProtocolError("BODY_TOO_LARGE", f"{role}: image too large or empty", 413)
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ("PNG", "JPEG", "WEBP"):
                raise ProtocolError("INPUT_INVALID", f"{role}: unsupported actual image format", 422)
            width, height = image.size
            if width < 256 or height < 256 or width > 5760 or height > 5760 or not 0.4 <= width / height <= 2.5:
                raise ProtocolError("INPUT_INVALID", f"{role}: image dimensions/ratio outside supported range", 422)
    except ProtocolError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProtocolError("INPUT_INVALID", f"{role}: invalid image bytes", 422) from exc
    suffix = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]
    return (f"{role}.{suffix}", raw, mime)


def parse_request(body: dict, settings: Settings) -> tuple[str, str, str | None, dict[str, tuple[str, bytes, str]]]:
    if body.get("model") != VIDEO_MODEL:
        raise ProtocolError("INPUT_INVALID", "Only model MiniMax-H3 (local FP8 Scaled) is supported", 422)
    content = body.get("content")
    if not isinstance(content, list) or not content:
        raise ProtocolError("INPUT_INVALID", "content must be a nonempty array", 422)
    texts = []
    images: dict[str, tuple[str, bytes, str]] = {}
    for item in content:
        if not isinstance(item, dict):
            raise ProtocolError("INPUT_INVALID", "content items must be objects", 422)
        kind = item.get("type")
        if kind == "text":
            if not isinstance(item.get("text"), str):
                raise ProtocolError("INPUT_INVALID", "text item requires text", 422)
            texts.append(item["text"])
        elif kind == "image_url":
            role = item.get("role", "first_frame")
            if role not in ("first_frame", "last_frame"):
                raise ProtocolError(
                    "INPUT_INVALID",
                    "reference_image mode is not yet supported; use first_frame/last_frame",
                    422,
                )
            if role in images:
                raise ProtocolError("INPUT_INVALID", f"duplicate image role: {role}", 422)
            ref = item.get("image_url")
            url = ref.get("url") if isinstance(ref, dict) else None
            images[role] = checked_image(url, role, settings)
        else:
            raise ProtocolError(
                "INPUT_INVALID",
                f"unsupported content type: {kind}; this local adapter supports text and 1-2 frame images only",
                422,
            )
    if len(texts) != 1 or not (1 <= len(texts[0].strip()) <= 2000):
        raise ProtocolError("INPUT_INVALID", "exactly one text item with 1-2000 characters is required", 422)
    if "last_frame" in images and "first_frame" not in images:
        raise ProtocolError("INPUT_INVALID", "last_frame-only mode is not supported by current local workflow", 422)
    if type(body.get("duration")) is not int or body["duration"] != DURATION_SECONDS:
        raise ProtocolError("INPUT_INVALID", "Only duration=5 is validated locally", 422)
    if body.get("resolution") != "768P":
        raise ProtocolError(
            "INPUT_INVALID",
            "Only a 768P request with explicit low-resolution fallback enabled is accepted; 2K and other resolutions are not supported",
            422,
        )
    if not settings.video_allow_resolution_fallback:
        raise ProtocolError(
            "INPUT_INVALID",
            f"Local output is {ACTUAL_RESOLUTION}, not 768P; set VIDEO_ALLOW_RESOLUTION_FALLBACK=1 to explicitly allow 768P requests to produce {ACTUAL_RESOLUTION}",
            422,
        )
    ratio = body.get("ratio")
    if images:
        if ratio not in (None, "adaptive", "16:9"):
            raise ProtocolError(
                "INPUT_INVALID",
                "Local image-to-video workflow supports only its current approximate 16:9 output",
                422,
            )
    elif ratio != "16:9":
        raise ProtocolError("INPUT_INVALID", "Text-to-video requires ratio=16:9 on this local workflow", 422)
    unknown = set(body) - {"model", "content", "resolution", "duration", "ratio", "callback_url", "extra", "aigc_watermark"}
    if unknown:
        raise ProtocolError("INPUT_INVALID", "Unsupported request fields: " + ", ".join(sorted(unknown)), 422)
    for field in ("callback_url", "extra", "aigc_watermark"):
        if field in body and body[field] not in (None, False):
            raise ProtocolError("INPUT_INVALID", f"{field} is not implemented by this local adapter", 422)
    mode = "flf" if "last_frame" in images else "i2v" if images else "t2v"
    stored_ratio = ratio or ("adaptive" if images else "16:9")
    return mode, texts[0].strip(), stored_ratio, images


def require_task_id(task_id: str) -> None:
    if not HEX_ID.fullmatch(task_id):
        raise ProtocolError("NOT_FOUND", "Task not found", 404)


def public_status(status: str) -> str:
    if status == "submitting":
        return "running"
    return status


def task_payload(settings: Settings, task) -> dict:
    status = public_status(task.status)
    data = {
        "id": task.id,
        "model": VIDEO_MODEL,
        "status": status,
        "created_at": int(task.created_at),
        "updated_at": int(task.finished_at or task.started_at or task.created_at),
        "content": {"url": signed_video_url(settings, task.id)} if status == "succeeded" else {},
        "resolution": ACTUAL_RESOLUTION,
        "requested_resolution": "768P",
        "duration": DURATION_SECONDS,
        "ratio": task.params.get("ratio") or NOMINAL_RATIO,
        "task_type": "generation",
        "modality": "video",
        "resolution_source": "verified_workflow_baseline",
    }
    if status == "failed":
        data["error"] = {
            "code": "local_generation_failed",
            "message": (task.error_message or "Unknown generation error")[:500],
            "detail_code": task.error_code,
        }
    elif status == "needs_review":
        data["attention_required"] = True
        data["error"] = {
            "code": "submission_uncertain",
            "message": (task.error_message or "Submission result is uncertain and was not retried.")[:500],
            "detail_code": task.error_code,
        }
    return data


@router.get("/health")
def health(request: Request):
    provider = request.app.state.registry.video
    report = provider.health()
    connected = bool(report.get("reachable"))
    workflows_ready = all((report.get("workflows") or {}).values())
    settings: Settings = request.app.state.settings
    return {
        "service": "h3-minimax-v2",
        "implementation": "multimodal-inference-api",
        "status": "ok" if connected and workflows_ready else "degraded",
        "backend_connected": connected,
        "native_resolution": ACTUAL_RESOLUTION,
        "degraded_resolution_compat": settings.video_allow_resolution_fallback,
        "studio_dependency": False,
    }


@router.post("/video_generation")
async def create_video(request: Request):
    settings: Settings = request.app.state.settings
    if "application/json" not in request.headers.get("content-type", "").lower():
        raise ProtocolError("UNSUPPORTED_MEDIA", "Content-Type must be application/json", 415)
    body = await read_json_object(request, settings.max_body_bytes)
    mode, prompt, ratio, images = parse_request(body, settings)
    params = {
        "resolution": "768P",
        "actual_resolution": ACTUAL_RESOLUTION,
        "actual_width": 608,
        "actual_height": 352,
        "duration": DURATION_SECONDS,
        "ratio": ratio,
        "resolution_fallback": True,
        "resolution_source": "verified_workflow_baseline",
    }
    task_id = uuid.uuid4().hex
    stored = dict(params)
    saved_keys: list[str] = []
    try:
        for role, (filename, raw, _mime) in images.items():
            suffix = Path(filename).suffix
            key = f"inputs/{task_id}/{role}{suffix}"
            save_bytes(settings, key, raw)
            saved_keys.append(key)
            stored[f"{role}_key"] = key
            stored[f"{role}_filename"] = filename
        task = create_task(
            settings,
            task_id=task_id,
            media_type="video",
            model=VIDEO_MODEL,
            mode=mode,
            prompt=prompt,
            params=stored,
            provider="comfyui_h3_video",
        )
    except Exception as exc:
        for key in saved_keys:
            remove_key(settings, key)
        if isinstance(exc, ProtocolError):
            raise
        raise ProtocolError("STORAGE_FAILED", "Reference image could not be stored", 500) from exc
    return JSONResponse(
        {"task_id": task.id},
        headers={"X-H3-Native-Resolution": ACTUAL_RESOLUTION, "X-H3-Resolution-Adjusted": "true"},
    )


@router.get("/query/video_generation/{task_id}")
def query_video(task_id: str, request: Request):
    require_task_id(task_id)
    settings: Settings = request.app.state.settings
    task = get_task(settings, task_id)
    if task is None or task.media_type != "video":
        raise ProtocolError("NOT_FOUND", "Task not found", 404)
    return JSONResponse(
        {"task": task_payload(settings, task)},
        headers={"X-H3-Native-Resolution": ACTUAL_RESOLUTION},
    )
