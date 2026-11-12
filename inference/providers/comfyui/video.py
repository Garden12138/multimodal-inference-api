"""MiniMax H3 video provider. Reference frames are uploaded to video ComfyUI."""

from __future__ import annotations

import logging
from pathlib import Path

from inference.config import Settings
from inference.errors import ProviderError
from inference.providers.base import Provider, ProviderAsset, ProviderSubmission, ProviderTaskStatus, TaskInput
from inference.providers.comfyui.client import ComfyUIClient, Transport, safe_filename, safe_subfolder
from inference.workflows.video import prepare_video_workflow, workflow_file

logger = logging.getLogger("inference.video")
VIDEO_MODEL = "MiniMax-H3"
VIDEO_SUFFIXES = {".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska"}


def extract_videos(record: dict) -> list[dict]:
    outputs = record.get("outputs") if isinstance(record, dict) else None
    if not isinstance(outputs, dict):
        return []
    videos = []
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for key in ("videos", "gifs", "images"):
            items = node_output.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                filename = item.get("filename")
                subfolder = item.get("subfolder") or ""
                file_type = item.get("type") or "output"
                if not isinstance(filename, str) or Path(filename).suffix.lower() not in VIDEO_SUFFIXES:
                    continue
                if not safe_filename(filename) or not isinstance(subfolder, str) or not safe_subfolder(subfolder):
                    continue
                if file_type not in {"output", "temp"}:
                    continue
                videos.append({"filename": filename, "subfolder": subfolder, "type": file_type})
    return videos


def interpret_video_history(provider_task_id: str, body: dict) -> tuple[ProviderTaskStatus, dict | None]:
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
        if not extract_videos(record):
            return (
                ProviderTaskStatus("success", "failed", "RESULT_NOT_FOUND", "视频任务已结束，但没有输出文件。"),
                record,
            )
        return ProviderTaskStatus("success", "succeeded"), record
    if status_str == "error":
        return ProviderTaskStatus("error", "failed", "PROVIDER_REJECTED", "视频生成失败。"), record
    if status.get("completed") is True:
        return (
            ProviderTaskStatus(status_str, "failed", "PROVIDER_REJECTED", "视频服务返回了无法识别的完成状态。"),
            record,
        )
    return ProviderTaskStatus(status_str, "running"), record


def video_mime(data: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    mime = VIDEO_SUFFIXES.get(suffix)
    if mime == "video/mp4" and b"ftyp" in data[:64]:
        return mime
    if mime in {"video/webm", "video/x-matroska"} and data.startswith(b"\x1a\x45\xdf\xa3"):
        return mime
    raise ProviderError("RESULT_INVALID", "视频服务返回的内容不是有效视频。", 502)


class ComfyUIH3VideoProvider(Provider):
    provider_id = "comfyui_h3_video"
    supported_media_types = ("video",)
    supported_modes = ("t2v", "i2v", "flf")
    model = VIDEO_MODEL

    def __init__(self, settings: Settings, transport: Transport):
        self.settings = settings
        self.client = ComfyUIClient(settings.video_comfy_base_url, transport)

    def workflow_flags(self) -> dict[str, bool]:
        flags = {}
        for mode in self.supported_modes:
            try:
                first = "first.png" if mode in {"i2v", "flf"} else None
                last = "last.png" if mode == "flf" else None
                prepare_video_workflow(
                    workflow_file(self.settings.workflow_dir, mode),
                    mode,
                    "prompt",
                    "check",
                    first,
                    last,
                )
                flags[mode] = True
            except Exception:
                logger.info("video workflow not ready mode=%s", mode)
                flags[mode] = False
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
        first_name = None
        last_name = None
        if task.mode in {"i2v", "flf"}:
            first_name = self._upload(task.first_filename, task.first_image, task.task_id, "first")
        if task.mode == "flf":
            last_name = self._upload(task.last_filename, task.last_image, task.task_id, "last")
        path = workflow_file(self.settings.workflow_dir, task.mode)
        try:
            workflow = prepare_video_workflow(path, task.mode, task.prompt, task.task_id, first_name, last_name)
        except FileNotFoundError as exc:
            raise ProviderError("WORKFLOW_NOT_READY", "视频生成工作流尚未配置。", 503) from exc
        except ValueError as exc:
            logger.info("video workflow invalid")
            raise ProviderError("WORKFLOW_INVALID", "视频生成工作流无效，已停止提交。", 503) from exc
        prompt_id = self.client.submit_prompt(workflow, task.task_id, self.settings.video_request_timeout)
        return ProviderSubmission(prompt_id, "queued")

    def poll(self, provider_task_id: str) -> ProviderTaskStatus:
        status, _record = self._history(provider_task_id)
        return status

    def fetch_assets(self, provider_task_id: str, task: TaskInput) -> list[ProviderAsset]:
        status, record = self._history(provider_task_id)
        if status.normalized != "succeeded" or record is None:
            raise ProviderError(
                status.error_code or "RESULT_NOT_FOUND",
                status.error_message or "视频结果还不存在。",
                502,
            )
        videos = extract_videos(record)
        if not videos:
            raise ProviderError("RESULT_NOT_FOUND", "视频任务已结束，但没有输出文件。", 502)
        chosen = videos[0]
        response = self.client.view(
            chosen["filename"],
            chosen["subfolder"],
            chosen["type"],
            self.settings.video_request_timeout,
        )
        if response.status_code >= 400 or not response.content:
            raise ProviderError("RESULT_NOT_FOUND", "视频结果无法下载。", 502)
        if len(response.content) > self.settings.max_output_video_bytes:
            raise ProviderError("ASSET_STORAGE_FAILED", "视频结果过大，未能保存。", 500)
        mime = video_mime(response.content, chosen["filename"])
        suffix = Path(chosen["filename"]).suffix.lower()
        return [ProviderAsset("video", mime, response.content, f"{task.task_id}{suffix}")]

    def _history(self, provider_task_id: str) -> tuple[ProviderTaskStatus, dict | None]:
        response = self.client.history(provider_task_id, self.settings.video_request_timeout)
        if response.status_code == 404:
            return ProviderTaskStatus("pending", "running"), None
        if response.status_code >= 400:
            raise ProviderError("PROVIDER_UNAVAILABLE", "查询视频任务失败。", 503)
        try:
            body = response.json()
        except (ValueError, UnicodeError) as exc:
            raise ProviderError("PROVIDER_REJECTED", "视频任务状态无法解析。", 502) from exc
        return interpret_video_history(provider_task_id, body)

    def _upload(self, filename: str | None, data: bytes | None, task_id: str, role: str) -> str:
        if not data or not filename:
            raise ProviderError("INPUT_INVALID", "缺少参考图片。", 400)
        suffix = Path(filename).suffix.lower() or ".png"
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".png"
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[suffix]
        upload_name = f"{role}_{task_id[:12]}{suffix}"
        return self.client.upload_image(upload_name, data, mime, self.settings.video_request_timeout)
