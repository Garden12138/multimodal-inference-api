"""ComfyUI HTTP client. Loopback calls do not inherit HTTP(S)_PROXY."""

from __future__ import annotations

import json
from urllib.parse import quote, urlencode

import requests

from inference.errors import ProviderError, UncertainSubmission


class HttpResponse:
    def __init__(self, status_code: int, headers, content: bytes):
        self.status_code = status_code
        self.headers = {str(key).lower(): value for key, value in dict(headers or {}).items()}
        self.content = content or b""

    def json(self):
        return json.loads(self.content.decode("utf-8"))


class Transport:
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict | None = None,
        json_body: dict | None = None,
        data: dict | None = None,
        files: dict | None = None,
        timeout: tuple[float, float] | float = 30,
    ) -> HttpResponse:
        raise NotImplementedError


class RequestsTransport(Transport):
    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict | None = None,
        json_body: dict | None = None,
        data: dict | None = None,
        files: dict | None = None,
        timeout: tuple[float, float] | float = 30,
    ) -> HttpResponse:
        payload = {}
        if json_body is not None:
            payload["json"] = json_body
        if data is not None:
            payload["data"] = data
        if files is not None:
            payload["files"] = files
        try:
            response = self.session.request(method, url, headers=headers, timeout=timeout, **payload)
        except requests.Timeout as exc:
            raise TimeoutError("provider timeout") from exc
        except requests.RequestException as exc:
            raise ConnectionError("provider connection failed") from exc
        return HttpResponse(response.status_code, response.headers, response.content)


def safe_filename(filename: str) -> bool:
    return bool(filename) and "/" not in filename and "\\" not in filename and ".." not in filename


def safe_subfolder(subfolder: str) -> bool:
    if not isinstance(subfolder, str):
        return False
    return all(part != ".." for part in subfolder.replace("\\", "/").split("/"))


class ComfyUIClient:
    def __init__(self, base_url: str, transport: Transport):
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    def system_stats(self) -> HttpResponse | None:
        try:
            return self.transport.request("GET", f"{self.base_url}/system_stats", timeout=(3, 5))
        except (TimeoutError, ConnectionError):
            return None

    def upload_image(self, filename: str, data: bytes, mime: str, timeout: float) -> str:
        if not safe_filename(filename):
            raise ProviderError("INPUT_INVALID", "参考图文件名无效。", 400)
        try:
            response = self.transport.request(
                "POST",
                f"{self.base_url}/upload/image",
                data={"overwrite": "true"},
                files={"image": (filename, data, mime)},
                timeout=(5, timeout),
            )
        except TimeoutError as exc:
            raise ProviderError("PROVIDER_TIMEOUT", "上传参考图超时，生成任务尚未提交。", 504) from exc
        except ConnectionError as exc:
            raise ProviderError("PROVIDER_UNAVAILABLE", "上传参考图失败，生成任务尚未提交。", 503) from exc
        if response.status_code >= 400:
            raise ProviderError("PROVIDER_REJECTED", "视频服务拒绝了参考图。", 502)
        try:
            body = response.json()
        except (ValueError, UnicodeError) as exc:
            raise ProviderError("PROVIDER_REJECTED", "视频服务没有返回参考图名称。", 502) from exc
        name = body.get("name") if isinstance(body, dict) else None
        if not isinstance(name, str) or not safe_filename(name):
            raise ProviderError("PROVIDER_REJECTED", "视频服务没有返回参考图名称。", 502)
        return name

    def submit_prompt(self, workflow: dict, client_id: str, timeout: float) -> str:
        try:
            response = self.transport.request(
                "POST",
                f"{self.base_url}/prompt",
                json_body={"prompt": workflow, "client_id": client_id},
                timeout=(5, timeout),
            )
        except TimeoutError as exc:
            raise UncertainSubmission("上游提交超时，无法确认是否已入队，未自动重试。") from exc
        except ConnectionError as exc:
            raise UncertainSubmission("上游连接中断，无法确认是否已入队，未自动重试。") from exc
        try:
            body = response.json()
        except (ValueError, UnicodeError):
            body = None
        prompt_id = body.get("prompt_id") if isinstance(body, dict) else None
        if isinstance(prompt_id, str) and safe_filename(prompt_id) and ".." not in prompt_id:
            return prompt_id
        if response.status_code in {400, 404, 422} or (
            isinstance(body, dict) and (body.get("error") or body.get("node_errors"))
        ):
            raise ProviderError("PROVIDER_REJECTED", "上游拒绝了这次任务。", 502)
        raise UncertainSubmission("上游没有返回可确认的任务编号，未自动重试。")

    def history(self, provider_task_id: str, timeout: float) -> HttpResponse:
        self._check_id(provider_task_id)
        try:
            return self.transport.request(
                "GET",
                f"{self.base_url}/history/{quote(provider_task_id)}",
                timeout=(5, timeout),
            )
        except TimeoutError as exc:
            raise ProviderError("PROVIDER_TIMEOUT", "查询上游任务超时。", 504) from exc
        except ConnectionError as exc:
            raise ProviderError("PROVIDER_UNAVAILABLE", "上游服务不可达。", 503) from exc

    def view(self, filename: str, subfolder: str, file_type: str, timeout: float) -> HttpResponse:
        if not safe_filename(filename) or not safe_subfolder(subfolder) or file_type not in {"output", "temp"}:
            raise ProviderError("RESULT_NOT_FOUND", "上游结果路径无效。", 502)
        query = urlencode({"filename": filename, "subfolder": subfolder, "type": file_type})
        try:
            return self.transport.request("GET", f"{self.base_url}/view?{query}", timeout=(5, timeout))
        except TimeoutError as exc:
            raise ProviderError("PROVIDER_TIMEOUT", "下载结果超时。", 504) from exc
        except ConnectionError as exc:
            raise ProviderError("ASSET_STORAGE_FAILED", "下载结果失败。", 502) from exc

    def _check_id(self, provider_task_id: str) -> None:
        if not safe_filename(provider_task_id) or ".." in provider_task_id:
            raise ProviderError("PROVIDER_REJECTED", "上游任务编号无效。", 502)
