"""Task and asset records."""

from __future__ import annotations

import json
from dataclasses import dataclass

TRANSITIONS = {
    "queued": {"submitting", "failed", "needs_review"},
    "submitting": {"queued", "running", "failed", "needs_review"},
    "running": {"succeeded", "failed", "needs_review"},
    "succeeded": set(),
    "failed": set(),
    "needs_review": set(),
}

TERMINAL_STATES = {"succeeded", "failed", "needs_review"}
ACTIVE_STATES = {"queued", "submitting", "running"}


@dataclass
class Task:
    id: str
    media_type: str
    model: str
    mode: str
    prompt: str
    params: dict
    status: str
    provider: str
    provider_task_id: str | None
    created_at: float
    started_at: float | None
    finished_at: float | None
    error_code: str | None
    error_message: str | None
    worker_id: str | None


@dataclass
class Asset:
    id: str
    task_id: str
    media_type: str
    mime_type: str
    filename: str
    storage_key: str
    size_bytes: int
    sha256: str
    created_at: float


def task_from_row(row) -> Task:
    raw = row["params_json"]
    params: dict = {}
    if isinstance(raw, str) and raw:
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            params = loaded
    return Task(
        id=row["id"],
        media_type=row["media_type"],
        model=row["model"],
        mode=row["mode"],
        prompt=row["prompt"],
        params=params,
        status=row["status"],
        provider=row["provider"],
        provider_task_id=row["provider_task_id"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        worker_id=row["worker_id"],
    )


def asset_from_row(row) -> Asset:
    return Asset(
        id=row["id"],
        task_id=row["task_id"],
        media_type=row["media_type"],
        mime_type=row["mime_type"],
        filename=row["filename"],
        storage_key=row["storage_key"],
        size_bytes=row["size_bytes"],
        sha256=row["sha256"],
        created_at=row["created_at"],
    )
