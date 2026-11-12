"""Task persistence. Claims are conditional updates, so a task is taken once."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid

from inference.assets.storage import resolve_key
from inference.config import Settings
from inference.db.database import migrate, session, transaction
from inference.db.models import TERMINAL_STATES, TRANSITIONS, Asset, Task, asset_from_row, task_from_row
from inference.errors import InferenceError

logger = logging.getLogger("inference.db")
PROMPT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
TASK_COLUMNS = {
    "status",
    "provider_task_id",
    "started_at",
    "finished_at",
    "error_code",
    "error_message",
    "worker_id",
    "params_json",
}


def init_db(settings: Settings) -> None:
    with session(settings) as connection:
        with transaction(connection):
            migrate(connection, time.time())
            reconcile_unfinished(connection, settings, time.time())


def create_task(
    settings: Settings,
    *,
    media_type: str,
    model: str,
    mode: str,
    prompt: str,
    params: dict,
    provider: str,
) -> Task:
    task_id = uuid.uuid4().hex
    now = time.time()
    with session(settings) as connection:
        with transaction(connection):
            connection.execute(
                """INSERT INTO inference_tasks (
                    id, media_type, model, mode, prompt, params_json, status, provider,
                    provider_task_id, created_at, started_at, finished_at, error_code,
                    error_message, worker_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, NULL, ?, NULL, NULL, NULL, NULL, NULL)""",
                (task_id, media_type, model, mode, prompt, json.dumps(params, ensure_ascii=False), provider, now),
            )
        task = get_task_conn(connection, task_id)
    if task is None:
        raise InferenceError("INTERNAL_ERROR", "任务没有写入数据库。", 500)
    return task


def get_task(settings: Settings, task_id: str) -> Task | None:
    with session(settings) as connection:
        return get_task_conn(connection, task_id)


def get_task_conn(connection, task_id: str) -> Task | None:
    row = connection.execute("SELECT * FROM inference_tasks WHERE id=?", (task_id,)).fetchone()
    return task_from_row(row) if row else None


def list_assets(settings: Settings, task_id: str) -> list[Asset]:
    with session(settings) as connection:
        return list_assets_conn(connection, task_id)


def list_assets_conn(connection, task_id: str) -> list[Asset]:
    rows = connection.execute(
        "SELECT * FROM inference_assets WHERE task_id=? ORDER BY created_at, id",
        (task_id,),
    ).fetchall()
    return [asset_from_row(row) for row in rows]


def get_asset(settings: Settings, asset_id: str) -> Asset | None:
    with session(settings) as connection:
        row = connection.execute("SELECT * FROM inference_assets WHERE id=?", (asset_id,)).fetchone()
    return asset_from_row(row) if row else None


def claim_next(settings: Settings, media_type: str, worker_id: str, now: float | None = None) -> Task | None:
    moment = time.time() if now is None else now
    with session(settings) as connection:
        with transaction(connection):
            row = connection.execute(
                """SELECT id, status FROM inference_tasks
                   WHERE media_type=?
                     AND (
                        status='queued'
                        OR (
                            status='running'
                            AND provider_task_id IS NOT NULL
                            AND (worker_id IS NULL OR worker_id=?)
                        )
                     )
                   ORDER BY CASE WHEN status='running' THEN 0 ELSE 1 END, created_at
                   LIMIT 1""",
                (media_type, worker_id),
            ).fetchone()
            if row is None:
                return None
            if row["status"] == "queued":
                cursor = connection.execute(
                    """UPDATE inference_tasks
                       SET status='submitting', started_at=?, worker_id=?
                       WHERE id=? AND status='queued'""",
                    (moment, worker_id, row["id"]),
                )
            else:
                cursor = connection.execute(
                    """UPDATE inference_tasks
                       SET worker_id=?, status='running'
                       WHERE id=? AND status='running'
                         AND provider_task_id IS NOT NULL
                         AND (worker_id IS NULL OR worker_id=?)""",
                    (worker_id, row["id"], worker_id),
                )
            if cursor.rowcount != 1:
                return None
            return get_task_conn(connection, row["id"])


def update_task(settings: Settings, task_id: str, **values) -> Task:
    with session(settings) as connection:
        with transaction(connection):
            return update_task_conn(connection, task_id, **values)


def update_task_conn(connection, task_id: str, **values) -> Task:
    current = get_task_conn(connection, task_id)
    if current is None:
        raise KeyError(task_id)
    if "params" in values:
        values["params_json"] = json.dumps(values.pop("params"), ensure_ascii=False)
    unknown = set(values) - TASK_COLUMNS
    if unknown:
        raise ValueError("unsupported task columns")
    new_status = values.get("status", current.status)
    if new_status != current.status and new_status not in TRANSITIONS.get(current.status, set()):
        raise ValueError(f"invalid transition {current.status} -> {new_status}")
    if not values:
        return current
    assignments = ", ".join(f"{column}=?" for column in values)
    connection.execute(
        f"UPDATE inference_tasks SET {assignments} WHERE id=?",
        (*values.values(), task_id),
    )
    updated = get_task_conn(connection, task_id)
    if updated is None:
        raise KeyError(task_id)
    return updated


def mark_running(settings: Settings, task_id: str, prompt_id: str) -> Task:
    if not PROMPT_ID_RE.fullmatch(prompt_id):
        raise InferenceError("PROVIDER_REJECTED", "上游任务编号无效。", 502)
    with session(settings) as connection:
        with transaction(connection):
            current = get_task_conn(connection, task_id)
            if current is None:
                raise KeyError(task_id)
            if current.provider_task_id and current.provider_task_id != prompt_id:
                raise InferenceError("SUBMISSION_UNCERTAIN", "任务已经绑定了另一个上游编号。", 409, uncertain=True)
            if current.status in TERMINAL_STATES:
                return current
            return update_task_conn(
                connection,
                task_id,
                status="running" if current.status != "running" else current.status,
                provider_task_id=prompt_id,
            )


def mark_terminal(
    settings: Settings,
    task_id: str,
    status: str,
    code: str | None,
    message: str | None,
) -> Task | None:
    if status not in {"failed", "needs_review", "succeeded"}:
        raise ValueError("terminal status required")
    with session(settings) as connection:
        with transaction(connection):
            current = get_task_conn(connection, task_id)
            if current is None or current.status in TERMINAL_STATES:
                return current
            return update_task_conn(
                connection,
                task_id,
                status=status,
                finished_at=time.time(),
                error_code=code,
                error_message=(message or "")[:500] or None,
                worker_id=None,
            )


def release_worker(settings: Settings, task_id: str, worker_id: str) -> None:
    with session(settings) as connection:
        connection.execute(
            """UPDATE inference_tasks
               SET worker_id=NULL
               WHERE id=? AND worker_id=? AND status IN ('submitting', 'running')""",
            (task_id, worker_id),
        )


def store_assets_and_succeed(settings: Settings, task_id: str, rows: list[dict]) -> Task:
    with session(settings) as connection:
        with transaction(connection):
            current = get_task_conn(connection, task_id)
            if current is None:
                raise KeyError(task_id)
            if current.status == "succeeded":
                return current
            if current.status not in {"running", "submitting"}:
                raise InferenceError("INTERNAL_ERROR", "任务状态已变化，结果未标记成功。", 409)
            existing = list_assets_conn(connection, task_id)
            if not existing:
                for row in rows:
                    connection.execute(
                        """INSERT INTO inference_assets (
                            id, task_id, media_type, mime_type, filename, storage_key,
                            size_bytes, sha256, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            row["id"],
                            task_id,
                            row["media_type"],
                            row["mime_type"],
                            row["filename"],
                            row["storage_key"],
                            row["size_bytes"],
                            row["sha256"],
                            row["created_at"],
                        ),
                    )
            return update_task_conn(
                connection,
                task_id,
                status="succeeded",
                finished_at=time.time(),
                error_code=None,
                error_message=None,
                worker_id=None,
            )


def reconcile_unfinished(connection, settings: Settings, now: float) -> None:
    rows = connection.execute(
        """SELECT id, status, provider_task_id
           FROM inference_tasks
           WHERE status IN ('submitting', 'running')"""
    ).fetchall()
    for row in rows:
        prompt_id = row["provider_task_id"] or read_recovery_prompt(settings, row["id"])
        if prompt_id and PROMPT_ID_RE.fullmatch(prompt_id):
            connection.execute(
                """UPDATE inference_tasks
                   SET status='running', provider_task_id=?, worker_id=NULL
                   WHERE id=?""",
                (prompt_id, row["id"]),
            )
            continue
        connection.execute(
            """UPDATE inference_tasks
               SET status='needs_review', finished_at=?, error_code=?, error_message=?, worker_id=NULL
               WHERE id=? AND provider_task_id IS NULL""",
            (
                now,
                "SUBMISSION_UNCERTAIN",
                "服务中断时无法确认上游是否已接受任务，未自动重新提交。",
                row["id"],
            ),
        )
    connection.execute(
        """UPDATE inference_tasks
           SET worker_id=NULL
           WHERE status IN ('queued', 'running', 'submitting')"""
    )


def read_recovery_prompt(settings: Settings, task_id: str) -> str | None:
    if not re.fullmatch(r"[0-9a-f]{32}", task_id):
        return None
    try:
        path = resolve_key(settings.data_dir, f"recovery/{task_id}.txt")
    except InferenceError:
        return None
    if path.is_symlink() or not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not PROMPT_ID_RE.fullmatch(text):
        return None
    return text


def write_recovery_prompt(settings: Settings, task_id: str, prompt_id: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}", task_id) or not PROMPT_ID_RE.fullmatch(prompt_id):
        raise InferenceError("PROVIDER_REJECTED", "上游任务编号无效。", 502)
    key = f"recovery/{task_id}.txt"
    path = resolve_key(settings.data_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(prompt_id + "\n", encoding="utf-8")
    temporary.replace(path)


def clear_recovery_prompt(settings: Settings, task_id: str) -> None:
    try:
        path = resolve_key(settings.data_dir, f"recovery/{task_id}.txt")
    except InferenceError:
        return
    if path.is_file() and not path.is_symlink():
        path.unlink()
