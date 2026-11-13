"""Fake ComfyUI transport and in-memory service setup."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from fastapi.testclient import TestClient

from inference.app_factory import create_app
from inference.config import ROOT, Settings
from inference.providers.comfyui.client import HttpResponse
from inference.providers.registry import Registry

API_KEY = "k" * 40


def png_bytes(width: int = 320, height: int = 320, color=(20, 40, 60)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def data_image(width: int = 320, height: int = 320, color=(255, 0, 0)) -> str:
    import base64

    return "data:image/png;base64," + base64.b64encode(png_bytes(width, height, color)).decode()


class FakeTransport:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def request(self, method, url, *, headers=None, json_body=None, data=None, files=None, timeout=None):
        call = {
            "method": method,
            "url": url,
            "headers": headers or {},
            "json": json_body,
            "data": data,
            "files": files,
            "timeout": timeout,
        }
        self.calls.append(call)
        result = self.handler(call)
        if isinstance(result, HttpResponse):
            return result
        status, payload = result
        if isinstance(payload, bytes):
            return HttpResponse(status, {"content-type": "application/octet-stream"}, payload)
        return HttpResponse(status, {"content-type": "application/json"}, json.dumps(payload).encode())


class ScriptedComfy:
    def __init__(self, *, mode="success", image: bytes | None = None, prompt_id="prompt-1", pending_polls=0):
        self.mode = mode
        self.image = image
        self.prompt_id = prompt_id
        self.pending_polls = pending_polls
        self.polls = 0
        self.poll_failures = 0
        self.view_failures = 0
        self.video = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64
        self.transport = FakeTransport(self.handle)

    def handle(self, call):
        url = call["url"]
        if url.endswith("/system_stats"):
            return 200, {"system": "mock"}
        if url.endswith("/upload/image"):
            name = call["files"]["image"][0]
            return 200, {"name": name, "subfolder": "", "type": "input"}
        if url.endswith("/prompt"):
            if self.mode == "timeout":
                raise TimeoutError("read timeout")
            if self.mode == "disconnect":
                raise ConnectionError("reset")
            if self.mode == "reject":
                return 400, {"error": {"message": "rejected"}}
            if self.mode == "node_error":
                return 200, {"error": {"message": "bad graph"}, "node_errors": {"1": "bad"}}
            if self.mode == "empty":
                return 200, {}
            return 200, {"prompt_id": self.prompt_id}
        if "/history/" in url:
            self.polls += 1
            if self.poll_failures:
                self.poll_failures -= 1
                raise TimeoutError("poll")
            if self.mode == "fail":
                return 200, {self.prompt_id: {"status": {"status_str": "error", "completed": True}, "outputs": {}}}
            if self.mode == "pending" or self.polls <= self.pending_polls:
                return 200, {}
            if self.image is not None:
                body = {
                    self.prompt_id: {
                        "status": {"status_str": "success", "completed": True},
                        "outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}},
                    }
                }
                return 200, body
            body = {
                self.prompt_id: {
                    "status": {"status_str": "success", "completed": True},
                    "outputs": {"92": {"videos": [{"filename": "out.mp4", "subfolder": "video", "type": "output"}]}},
                }
            }
            return 200, body
        if "/view?" in url:
            if self.view_failures:
                self.view_failures -= 1
                raise TimeoutError("view")
            if self.image is not None:
                return HttpResponse(200, {"content-type": "image/png"}, self.image)
            return HttpResponse(200, {"content-type": "video/mp4"}, self.video)
        return 404, {"missing": True}

    @property
    def prompt_calls(self) -> list[dict]:
        return [call for call in self.transport.calls if call["url"].endswith("/prompt")]


def make_settings(tmp: Path, **overrides) -> Settings:
    workflow_dir = ROOT / "workflows"
    values = dict(
        api_key=API_KEY,
        api_key_source="test",
        ignored_legacy_api_key=False,
        allowed_networks=("127.0.0.1/32", "::1/128"),
        public_base_url="http://127.0.0.1:8090",
        host="127.0.0.1",
        port=8090,
        database_path=tmp / "inference.db",
        data_dir=tmp / "data",
        image_comfy_base_url="http://127.0.0.1:8190",
        video_comfy_base_url="http://127.0.0.1:8189",
        image_workers=1,
        video_workers=1,
        image_poll_interval=0.01,
        video_poll_interval=0.01,
        image_task_timeout=30.0,
        video_task_timeout=30.0,
        video_allow_resolution_fallback=True,
        resolution_fallback_source="test",
        ignored_legacy_resolution_fallback=False,
        workflow_dir=workflow_dir,
        image_workflow_1mp=workflow_dir / "image" / "t2i_1mp_api.json",
        image_workflow_4mp=workflow_dir / "image" / "t2i_4mp_api.json",
        idle_interval=0.01,
    )
    values.update(overrides)
    settings = Settings(**values)
    settings.ensure_dirs()
    return settings


def build_stack(tmp: Path, *, image: ScriptedComfy | None = None, video: ScriptedComfy | None = None, **overrides):
    image = image or ScriptedComfy(image=png_bytes(1024, 1024))
    video = video or ScriptedComfy()
    settings = make_settings(tmp, **overrides)
    registry = Registry(settings, image.transport, video.transport)
    app = create_app(settings, registry, start_workers_enabled=False)
    client = TestClient(app, client=("127.0.0.1", 12345))
    client.__enter__()
    return SimpleNamespace(settings=settings, registry=registry, client=client, image=image, video=video, headers={"Authorization": "Bearer " + settings.api_key})


def video_payload(**extra):
    body = {
        "model": "MiniMax-H3",
        "content": [{"type": "text", "text": "A cinematic scene"}],
        "resolution": "768P",
        "duration": 5,
        "ratio": "16:9",
    }
    body.update(extra)
    return body
