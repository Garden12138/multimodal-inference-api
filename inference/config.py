"""Environment configuration.

API key priority, highest first:
1. Process environment INFERENCE_API_KEY, when non-empty.
2. Process environment H3_MINIMAX_API_KEY, when the primary variable is empty.

.env is loaded only for variables that are not already set. An empty value is
treated as unset. When both keys are non-empty, H3_MINIMAX_API_KEY is ignored.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path

from inference.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]
MIN_API_KEY_LENGTH = 24
TRUE_VALUES = {"1", "true", "yes"}
FALSE_VALUES = {"0", "false", "no"}


@dataclass(frozen=True)
class Settings:
    api_key: str
    api_key_source: str
    ignored_legacy_api_key: bool
    allowed_networks: tuple[str, ...]
    public_base_url: str
    host: str
    port: int
    database_path: Path
    data_dir: Path
    image_comfy_base_url: str
    video_comfy_base_url: str
    image_workers: int
    video_workers: int
    image_poll_interval: float
    video_poll_interval: float
    image_task_timeout: float
    video_task_timeout: float
    video_allow_resolution_fallback: bool
    resolution_fallback_source: str
    ignored_legacy_resolution_fallback: bool
    workflow_dir: Path
    image_workflow_1mp: Path
    image_workflow_4mp: Path
    image_request_timeout: float = 60.0
    video_request_timeout: float = 120.0
    max_image_bytes: int = 12 * 1024 * 1024
    max_body_bytes: int = 36 * 1024 * 1024
    max_output_image_bytes: int = 40 * 1024 * 1024
    max_output_video_bytes: int = 200 * 1024 * 1024
    file_url_ttl_seconds: int = 3600
    idle_interval: float = 1.0

    def __repr__(self) -> str:
        return (
            "Settings("
            f"api_key_source={self.api_key_source!r}, "
            f"host={self.host!r}, port={self.port}, "
            f"fallback={self.video_allow_resolution_fallback})"
        )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for name in ("outputs", "inputs", "logs", "recovery"):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


def load_env_file(path: Path, environ: dict[str, str] | None = None) -> None:
    """Load KEY=VALUE lines. Existing non-empty process values win."""
    target = os.environ if environ is None else environ
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in target and target[key].strip():
            continue
        target[key] = value.strip().strip('"').strip("'")


def load_settings(environ: dict[str, str] | None = None, *, root: Path | None = None) -> Settings:
    env = os.environ if environ is None else environ
    base = root or ROOT
    api_key, source, ignored_legacy = _resolve_api_key(env)
    if len(api_key) < MIN_API_KEY_LENGTH:
        raise ConfigError(
            f"API key must be set and at least {MIN_API_KEY_LENGTH} characters. "
            "Set INFERENCE_API_KEY. H3_MINIMAX_API_KEY is used only when INFERENCE_API_KEY is empty."
        )
    fallback, fallback_source, ignored_fallback = _resolve_fallback(env)
    port = _int_env(env, "INFERENCE_PORT", 8090)
    if port == 8089:
        raise ConfigError("INFERENCE_PORT=8089 is refused. This version must not bind the existing native API port.")
    if not 1 <= port <= 65535:
        raise ConfigError("INFERENCE_PORT is invalid")
    data_dir = _path_env(env, "INFERENCE_DATA_DIR", base / "data", base)
    database_path = _path_env(env, "INFERENCE_DATABASE_PATH", data_dir / "inference.db", base)
    workflow_dir = base / "workflows"
    settings = Settings(
        api_key=api_key,
        api_key_source=source,
        ignored_legacy_api_key=ignored_legacy,
        allowed_networks=_networks(env),
        public_base_url=_base_url(env.get("INFERENCE_PUBLIC_BASE_URL", "http://127.0.0.1:8090")),
        host=env.get("INFERENCE_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=port,
        database_path=database_path,
        data_dir=data_dir,
        image_comfy_base_url=_base_url(env.get("IMAGE_COMFYUI_BASE_URL", "http://127.0.0.1:8190")),
        video_comfy_base_url=_base_url(env.get("VIDEO_COMFYUI_BASE_URL", "http://127.0.0.1:8189")),
        image_workers=_workers(env, "IMAGE_WORKERS"),
        video_workers=_workers(env, "VIDEO_WORKERS"),
        image_poll_interval=_float_env(env, "IMAGE_POLL_INTERVAL_SECONDS", 3.0),
        video_poll_interval=_float_env(env, "VIDEO_POLL_INTERVAL_SECONDS", 5.0),
        image_task_timeout=_float_env(env, "IMAGE_TASK_TIMEOUT_SECONDS", 1800.0),
        video_task_timeout=_float_env(env, "VIDEO_TASK_TIMEOUT_SECONDS", 3600.0),
        video_allow_resolution_fallback=fallback,
        resolution_fallback_source=fallback_source,
        ignored_legacy_resolution_fallback=ignored_fallback,
        workflow_dir=workflow_dir,
        image_workflow_1mp=workflow_dir / "image" / "t2i_1mp_api.json",
        image_workflow_4mp=workflow_dir / "image" / "t2i_4mp_api.json",
    )
    return settings


def _resolve_api_key(env: dict[str, str]) -> tuple[str, str, bool]:
    primary = env.get("INFERENCE_API_KEY", "").strip()
    legacy = env.get("H3_MINIMAX_API_KEY", "").strip()
    if primary:
        return primary, "INFERENCE_API_KEY", bool(legacy and legacy != primary)
    if legacy:
        return legacy, "H3_MINIMAX_API_KEY", False
    return "", "", False


def _resolve_fallback(env: dict[str, str]) -> tuple[bool, str, bool]:
    primary_raw = env.get("VIDEO_ALLOW_RESOLUTION_FALLBACK")
    legacy_raw = env.get("H3_MM_ALLOW_RESOLUTION_FALLBACK")
    if primary_raw is not None and primary_raw.strip():
        ignored = legacy_raw is not None and legacy_raw.strip() and _bool_value(primary_raw) != _bool_value(legacy_raw)
        return _bool_value(primary_raw), "VIDEO_ALLOW_RESOLUTION_FALLBACK", ignored
    if legacy_raw is not None and legacy_raw.strip():
        return _bool_value(legacy_raw), "H3_MM_ALLOW_RESOLUTION_FALLBACK", False
    return False, "default", False


def _bool_value(raw: str) -> bool:
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise ConfigError("Boolean configuration must be 0/1, true/false, or yes/no")


def _networks(env: dict[str, str]) -> tuple[str, ...]:
    raw = env.get("INFERENCE_ALLOWED_CIDRS", "127.0.0.1/32,::1/128")
    networks = tuple(part.strip() for part in raw.split(",") if part.strip())
    for item in networks:
        try:
            ipaddress.ip_network(item, strict=False)
        except ValueError as exc:
            raise ConfigError("INFERENCE_ALLOWED_CIDRS contains an invalid network") from exc
    return networks


def _workers(env: dict[str, str], name: str) -> int:
    value = _int_env(env, name, 1)
    if not 1 <= value <= 8:
        raise ConfigError(f"{name} must be from 1 to 8")
    return value


def _int_env(env: dict[str, str], name: str, default: int) -> int:
    raw = env.get(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _float_env(env: dict[str, str], name: str, default: float) -> float:
    raw = env.get(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be positive")
    return value


def _path_env(env: dict[str, str], name: str, default: Path, root: Path) -> Path:
    raw = env.get(name, "").strip()
    path = Path(raw) if raw else default
    if not path.is_absolute():
        path = root / path
    return path


def _base_url(value: str) -> str:
    from urllib.parse import urlparse

    raw = value.strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ConfigError("Service URLs must be http(s) and must not embed credentials")
    return raw
