"""Claim, submit, and poll tasks. Uncertain submission is never retried."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path

from inference.assets.storage import remove_key, resolve_key, save_bytes
from inference.config import Settings
from inference.db.models import TERMINAL_STATES, Task
from inference.db.repository import (
    claim_next,
    clear_recovery_prompt,
    get_task,
    list_assets,
    mark_running,
    mark_terminal,
    release_worker,
    store_assets_and_succeed,
    write_recovery_prompt,
)
from inference.errors import InferenceError, ProviderError
from inference.providers.base import Provider, TaskInput

logger = logging.getLogger("inference.worker")
TRANSIENT = {"PROVIDER_UNAVAILABLE", "PROVIDER_TIMEOUT", "ASSET_STORAGE_FAILED"}
UNCERTAIN_MESSAGE = "无法确认上游是否已接受任务，未自动重新提交。"


def process_one(settings: Settings, provider: Provider, media_type: str, worker_id: str) -> bool:
    task = claim_next(settings, media_type, worker_id)
    if task is None:
        return False
    try:
        execute(settings, provider, task.id, worker_id, threading.Event())
    except Exception:
        logger.exception("worker crashed task=%s", task.id)
        _crash(settings, task.id)
    return True


def execute(settings: Settings, provider: Provider, task_id: str, worker_id: str, stop: threading.Event) -> None:
    try:
        task = get_task(settings, task_id)
        if task is None or task.status in TERMINAL_STATES:
            return
        if task.status == "submitting" and not task.provider_task_id:
            if not _submit(settings, provider, task):
                return
            task = get_task(settings, task_id)
        if task is not None and task.status == "running" and task.provider_task_id:
            _poll(settings, provider, task, stop)
    finally:
        release_worker(settings, task_id, worker_id)


def _submit(settings: Settings, provider: Provider, task: Task) -> bool:
    try:
        submission = provider.submit(_task_input(settings, task))
    except ProviderError as exc:
        _finish_provider_error(settings, task.id, exc)
        return False
    except Exception:
        logger.exception("submit crashed task=%s", task.id)
        mark_terminal(settings, task.id, "needs_review", "SUBMISSION_UNCERTAIN", UNCERTAIN_MESSAGE)
        return False
    prompt_id = submission.provider_task_id
    if not prompt_id:
        mark_terminal(settings, task.id, "needs_review", "SUBMISSION_UNCERTAIN", UNCERTAIN_MESSAGE)
        return False
    file_saved = _retry(lambda: write_recovery_prompt(settings, task.id, prompt_id))
    db_saved = _retry(lambda: mark_running(settings, task.id, prompt_id))
    if db_saved:
        try:
            clear_recovery_prompt(settings, task.id)
        except Exception:
            logger.info("recovery file left in place task=%s", task.id)
        return True
    logger.error("prompt id is not durable task=%s prompt_id=%s", task.id, prompt_id)
    if not file_saved:
        mark_terminal(settings, task.id, "needs_review", "SUBMISSION_UNCERTAIN", UNCERTAIN_MESSAGE)
    return False


def _poll(settings: Settings, provider: Provider, task: Task, stop: threading.Event) -> None:
    timeout = settings.image_task_timeout if task.media_type == "image" else settings.video_task_timeout
    interval = settings.image_poll_interval if task.media_type == "image" else settings.video_poll_interval
    while not stop.is_set():
        current = get_task(settings, task.id)
        if current is None or current.status in TERMINAL_STATES:
            return
        overdue = _overdue(current, timeout)
        try:
            status = provider.poll(current.provider_task_id or "")
        except ProviderError as exc:
            if exc.code in TRANSIENT and not overdue:
                logger.info("poll will retry task=%s code=%s", current.id, exc.code)
                stop.wait(interval)
                continue
            code = "PROVIDER_TIMEOUT" if overdue and exc.code in TRANSIENT else exc.code
            mark_terminal(settings, current.id, "failed", code, exc.message)
            return
        if status.normalized == "succeeded":
            if _complete(settings, provider, current):
                return
            if overdue:
                mark_terminal(settings, current.id, "failed", "ASSET_STORAGE_FAILED", "结果下载失败，未自动重新提交。")
                return
            stop.wait(interval)
            continue
        if status.normalized == "failed":
            mark_terminal(
                settings,
                current.id,
                "failed",
                status.error_code or "PROVIDER_REJECTED",
                status.error_message or "生成失败。",
            )
            return
        if status.normalized not in {"queued", "running"}:
            mark_terminal(settings, current.id, "needs_review", "PROVIDER_REJECTED", "上游返回了无法确认的状态，未自动重新提交。")
            return
        if overdue:
            mark_terminal(settings, current.id, "failed", "PROVIDER_TIMEOUT", "任务等待超时，未自动重新提交。")
            return
        stop.wait(interval)


def _complete(settings: Settings, provider: Provider, task: Task) -> bool:
    if list_assets(settings, task.id):
        store_assets_and_succeed(settings, task.id, [])
        return True
    try:
        fetched = provider.fetch_assets(task.provider_task_id or "", _task_input(settings, task))
    except ProviderError as exc:
        if exc.code in TRANSIENT:
            return False
        mark_terminal(settings, task.id, "failed", exc.code, exc.message)
        return True
    saved: list[str] = []
    rows = []
    try:
        now = time.time()
        for asset in fetched:
            storage_key = f"outputs/{task.id}/{asset.filename}"
            digest = save_bytes(settings, storage_key, asset.data)
            saved.append(storage_key)
            rows.append(
                {
                    "id": uuid.uuid4().hex,
                    "media_type": asset.media_type,
                    "mime_type": asset.mime_type,
                    "filename": asset.filename,
                    "storage_key": storage_key,
                    "size_bytes": len(asset.data),
                    "sha256": digest,
                    "created_at": now,
                }
            )
        store_assets_and_succeed(settings, task.id, rows)
        return True
    except Exception:
        logger.exception("asset persist failed task=%s", task.id)
        for key in saved:
            remove_key(settings, key)
        return False


def _task_input(settings: Settings, task: Task) -> TaskInput:
    first = _read_frame(settings, task.params.get("first_frame_key"))
    last = _read_frame(settings, task.params.get("last_frame_key"))
    return TaskInput(
        task_id=task.id,
        media_type=task.media_type,
        mode=task.mode,
        prompt=task.prompt,
        params=task.params,
        first_image=None if first is None else first[0],
        first_filename=None if first is None else first[1],
        last_image=None if last is None else last[0],
        last_filename=None if last is None else last[1],
    )


def _read_frame(settings: Settings, storage_key: str | None) -> tuple[bytes, str] | None:
    if not storage_key:
        return None
    try:
        path = resolve_key(settings.data_dir, storage_key)
    except InferenceError as exc:
        raise ProviderError("INPUT_INVALID", "参考图片不存在。", 400) from exc
    if path.is_symlink() or not path.is_file():
        raise ProviderError("INPUT_INVALID", "参考图片不存在。", 400)
    return path.read_bytes(), Path(storage_key).name


def _finish_provider_error(settings: Settings, task_id: str, exc: ProviderError) -> None:
    status = "needs_review" if exc.uncertain else "failed"
    mark_terminal(settings, task_id, status, exc.code, exc.message)


def _crash(settings: Settings, task_id: str) -> None:
    task = get_task(settings, task_id)
    if task is None or task.status in TERMINAL_STATES:
        return
    if task.provider_task_id:
        release_worker(settings, task_id, task.worker_id or "")
        return
    mark_terminal(settings, task_id, "needs_review", "SUBMISSION_UNCERTAIN", UNCERTAIN_MESSAGE)


def _overdue(task: Task, timeout: float) -> bool:
    if task.started_at is None:
        return False
    return time.time() - float(task.started_at) > timeout


def _retry(action) -> bool:
    for _ in range(3):
        try:
            action()
            return True
        except Exception:
            time.sleep(0.05)
    return False
