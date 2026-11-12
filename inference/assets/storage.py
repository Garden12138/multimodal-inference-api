"""Store files under the service data directory. Callers never choose absolute paths."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from inference.config import Settings
from inference.errors import InferenceError

SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,180}$")


def resolve_key(root: Path, storage_key: str) -> Path:
    if not isinstance(storage_key, str) or not storage_key or storage_key.startswith(("/", "\\")):
        raise InferenceError("ASSET_NOT_FOUND", "文件不存在。", 404)
    parts = Path(storage_key).parts
    if not parts or any(part in {"", ".", ".."} or "\\" in part or part.startswith("/") for part in parts):
        raise InferenceError("ASSET_NOT_FOUND", "文件不存在。", 404)
    base = root.resolve()
    path = (base / storage_key).resolve()
    if path != base and base not in path.parents:
        raise InferenceError("ASSET_NOT_FOUND", "文件不存在。", 404)
    return path


def save_bytes(settings: Settings, storage_key: str, data: bytes) -> str:
    path = resolve_key(settings.data_dir, storage_key)
    if path.is_symlink():
        raise InferenceError("ASSET_STORAGE_FAILED", "文件保存失败。", 500)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(data)
    os.replace(temporary, path)
    return hashlib.sha256(data).hexdigest()


def read_verified(settings: Settings, storage_key: str, expected_sha256: str) -> Path:
    path = resolve_key(settings.data_dir, storage_key)
    if path.is_symlink() or not path.is_file():
        raise InferenceError("FILE_MISSING", "结果文件不存在。", 404)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if not hmac_equal(digest.hexdigest(), expected_sha256):
        raise InferenceError("FILE_TAMPERED", "结果文件校验失败。", 409)
    return path


def hmac_equal(left: str, right: str) -> bool:
    import hmac

    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def safe_download_name(filename: str, fallback: str) -> str:
    name = Path(filename).name
    if SAFE_NAME.fullmatch(name):
        return name
    return fallback


def remove_key(settings: Settings, storage_key: str) -> None:
    try:
        path = resolve_key(settings.data_dir, storage_key)
    except InferenceError:
        return
    if path.is_file() and not path.is_symlink():
        path.unlink()
