"""MiniMax H3 image provider. ComfyUI is called directly on the image port."""

from __future__ import annotations

import io
import logging
import secrets

from PIL import Image, UnidentifiedImageError

from inference.config import Settings
from inference.errors import ProviderError
from inference.providers.base import Provider, ProviderAsset, ProviderSubmission, ProviderTaskStatus, TaskInput
from inference.providers.comfyui.client import ComfyUIClient, HttpResponse, Transport
from inference.workflows.image import RESOLUTIONS, load_workflow, prepare_workflow

logger = logging.getLogger("inference.image")
IMAGE_MODEL = "MiniMax-H3-Image"


def extract_images(record: dict) -> list[dict]:
    outputs = record.get("outputs") if isinstance(record, dict) else None
    if not isinstance(outputs, dict):
        return []
    images = []
    for node_output in outputs.values():
        if not isinstance(node_output, dict) or not isinstance(node_output.get("images"), list):
            continue
        for item in node_output["images"]:
            if not isinstance(item, dict):
                continue
            filename = item.get("filename")
            subfolder = item.get("subfolder") or ""
            image_type = item.get("type") or "output"
            if not isinstance(filename, str) or not filename or "/" in filename or "\\" in filename or ".." in filename:
                continue
            if not isinstance(subfolder, str) or ".." in subfolder.replace("\\", "/").split("/"):
                continue
            if image_type not in {"output", "temp"}:
                continue
            images.append({"filename": filename, "subfolder": subfolder, "type": image_type})
    return images


def interpret_history(provider_task_id: str, body: dict) -> tuple[ProviderTaskStatus, dict | None]:
    if not isinstance(body, dict) or provider_task_id not in body:
        return ProviderTaskStatus("pending", "running"), None
    record = body.get(provider_task_id)
    if not isinstance(record, dict):
        return ProviderTaskStatus("pending", "running"), None
    status = record.get("status") if isinstance(record.get("status"), dict) else {}
    status_str = status.get("status_str")
    if not isinstance(status_str, str) or not status_str:
        return ProviderTaskStatus("pending", "running"), record
    if status_str == "success":
        if not extract_images(record):
            return (
                ProviderTaskStatus("success", "failed", "RESULT_NOT_FOUND", "图片任务已结束，但没有输出文件。"),
                record,
            )
        return ProviderTaskStatus("success", "succeeded"), record
    if status_str == "error":
        return ProviderTaskStatus("error", "failed", "PROVIDER_REJECTED", "图片生成失败。"), record
    if status.get("completed") is True:
        return (
            ProviderTaskStatus(status_str, "failed", "PROVIDER_REJECTED", "图片服务返回了无法识别的完成状态。"),
            record,
        )
    return ProviderTaskStatus(status_str, "running"), record


class ComfyUIH3ImageProvider(Provider):
    provider_id = "comfyui_h3_image"
    supported_media_types = ("image",)
    supported_modes = ("t2i",)
    model = IMAGE_MODEL

    def __init__(self, settings: Settings, transport: Transport, seed_fn=None):
        self.settings = settings
        self.client = ComfyUIClient(settings.image_comfy_base_url, transport)
        self.seed_fn = seed_fn or (lambda: secrets.randbits(63))

    def _workflow_for(self, size: str) -> tuple:
        megapixels = RESOLUTIONS.get(size)
        if megapixels is None:
            raise ProviderError("INPUT_INVALID", "图片分辨率仅支持 1024x1024 和 2048x2048。", 400)
        path = self.settings.image_workflow_1mp if size == "1024x1024" else self.settings.image_workflow_4mp
        return path, megapixels

    def workflow_flags(self) -> dict[str, bool]:
        flags = {}
        for key, size in (("t2i_1mp", "1024x1024"), ("t2i_4mp", "2048x2048")):
            path, megapixels = self._workflow_for(size)
            try:
                load_workflow(path, megapixels)
                flags[key] = True
            except Exception:
                logger.info("image workflow not ready key=%s", key)
                flags[key] = False
        return flags

    def health(self) -> dict:
        workflows = self.workflow_flags()
        response = self.client.system_stats()
        if response is None:
            return {"provider": self.provider_id, "status": "unreachable", "reachable": False, "workflows": workflows}
        if response.status_code != 200:
            return {"provider": self.provider_id, "status": "degraded", "reachable": False, "workflows": workflows}
        status = "ok" if all(workflows.values()) else "degraded"
        return {"provider": self.provider_id, "status": status, "reachable": True, "workflows": workflows}

    def submit(self, task: TaskInput) -> ProviderSubmission:
        size = str((task.params or {}).get("size") or "")
        path, megapixels = self._workflow_for(size)
        try:
            workflow = prepare_workflow(path, megapixels, task.prompt, task.task_id, self.seed_fn())
        except FileNotFoundError as exc:
            raise ProviderError("WORKFLOW_NOT_READY", "图片生成工作流尚未配置。", 503) from exc
        except ValueError as exc:
            logger.info("image workflow invalid")
            raise ProviderError("WORKFLOW_INVALID", "图片生成工作流无效，已停止提交。", 503) from exc
        prompt_id = self.client.submit_prompt(workflow, task.task_id, self.settings.image_request_timeout)
        return ProviderSubmission(prompt_id, "queued")

    def poll(self, provider_task_id: str) -> ProviderTaskStatus:
        status, _record = self._history(provider_task_id)
        return status

    def fetch_assets(self, provider_task_id: str, task: TaskInput) -> list[ProviderAsset]:
        status, record = self._history(provider_task_id)
        if status.normalized != "succeeded" or record is None:
            raise ProviderError(
                status.error_code or "RESULT_NOT_FOUND",
                status.error_message or "图片结果还不存在。",
                502,
            )
        images = extract_images(record)
        if not images:
            raise ProviderError("RESULT_NOT_FOUND", "图片任务已结束，但没有输出文件。", 502)
        expected = _expected_size(task)
        assets = []
        for index, image in enumerate(images, start=1):
            response = self.client.view(
                image["filename"],
                image["subfolder"],
                image["type"],
                self.settings.image_request_timeout,
            )
            if response.status_code >= 400 or not response.content:
                raise ProviderError("RESULT_NOT_FOUND", "图片结果无法下载。", 502)
            if len(response.content) > self.settings.max_output_image_bytes:
                raise ProviderError("ASSET_STORAGE_FAILED", "图片结果过大，未能保存。", 500)
            _validated_png(response.content, expected)
            filename = f"{task.task_id}.png" if len(images) == 1 else f"{task.task_id}_{index}.png"
            assets.append(ProviderAsset("image", "image/png", response.content, filename))
        return assets

    def _history(self, provider_task_id: str) -> tuple[ProviderTaskStatus, dict | None]:
        response = self.client.history(provider_task_id, self.settings.image_request_timeout)
        if response.status_code == 404:
            return ProviderTaskStatus("pending", "running"), None
        if response.status_code >= 400:
            raise ProviderError("PROVIDER_UNAVAILABLE", "查询图片任务失败。", 503)
        try:
            body = response.json()
        except (ValueError, UnicodeError) as exc:
            raise ProviderError("PROVIDER_REJECTED", "图片任务状态无法解析。", 502) from exc
        return interpret_history(provider_task_id, body)


def _expected_size(task: TaskInput) -> tuple[int, int]:
    width = (task.params or {}).get("width")
    height = (task.params or {}).get("height")
    if width == 1024 and height == 1024:
        return (1024, 1024)
    if width == 2048 and height == 2048:
        return (2048, 2048)
    raise ProviderError("INPUT_INVALID", "图片分辨率仅支持 1024x1024 和 2048x2048。", 400)


def _validated_png(data: bytes, expected: tuple[int, int]) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            fmt = (image.format or "").upper()
            size = image.size
    except (UnidentifiedImageError, OSError) as exc:
        raise ProviderError("RESULT_INVALID", "图片服务返回的内容不是有效 PNG。", 502) from exc
    if fmt != "PNG":
        raise ProviderError("RESULT_INVALID", "图片服务返回的内容不是 PNG。", 502)
    if size != expected:
        raise ProviderError("RESULT_INVALID", "图片实际尺寸与请求不一致。", 502)
