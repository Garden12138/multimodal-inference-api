"""SQLite connection helpers. WAL and immediate transactions serialize claims."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from inference.config import Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS inference_tasks (
    id TEXT PRIMARY KEY,
    media_type TEXT NOT NULL,
    model TEXT NOT NULL,
    mode TEXT NOT NULL,
    prompt TEXT NOT NULL,
    params_json TEXT NOT NULL,
    status TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_task_id TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    error_code TEXT,
    error_message TEXT,
    worker_id TEXT
);

CREATE TABLE IF NOT EXISTS inference_assets (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    media_type TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(task_id) REFERENCES inference_tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_media_status_created
    ON inference_tasks(media_type, status, created_at);
CREATE INDEX IF NOT EXISTS idx_assets_task
    ON inference_assets(task_id, created_at);
"""


def connect(settings: Settings) -> sqlite3.Connection:
    settings.ensure_dirs()
    connection = sqlite3.connect(
        settings.database_path,
        timeout=30,
        isolation_level=None,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


@contextmanager
def session(settings: Settings):
    connection = connect(settings)
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def transaction(connection: sqlite3.Connection):
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except Exception:
        connection.execute("ROLLBACK")
        raise
    else:
        connection.execute("COMMIT")


def migrate(connection: sqlite3.Connection, now: float) -> None:
    for statement in SCHEMA.split(";"):
        sql = statement.strip()
        if sql:
            connection.execute(sql)
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (1, ?)",
        (now,),
    )
