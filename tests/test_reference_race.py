import sqlite3
import threading

import pytest

from inference.assets.storage import resolve_key
from inference.db.repository import claim_next, get_task
from tests.helpers import build_stack, data_image, video_payload


def _i2v():
    body = video_payload()
    body["ratio"] = "adaptive"
    body["content"] = [
        {"type": "text", "text": "A cinematic scene"},
        {"type": "image_url", "role": "first_frame", "image_url": {"url": data_image()}},
    ]
    return body


def _flf():
    body = video_payload()
    body["content"] = [
        {"type": "text", "text": "A cinematic scene"},
        {"type": "image_url", "role": "first_frame", "image_url": {"url": data_image(color=(255, 0, 0))}},
        {"type": "image_url", "role": "last_frame", "image_url": {"url": data_image(color=(0, 255, 0))}},
    ]
    return body


def _post(stack, payload):
    return stack.client.post(
        "/v2/video_generation",
        headers={**stack.headers, "Content-Type": "application/json"},
        json=payload,
    )


@pytest.mark.parametrize("payload_factory", [_i2v, _flf])
def test_reference_frames_are_stored_before_the_task_is_claimable(tmp_path, monkeypatch, payload_factory):
    stack = build_stack(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    seen = []
    real_save = __import__("inference.api.video_minimax", fromlist=["save_bytes"]).save_bytes

    def slow_save(settings, key, data):
        entered.set()
        assert release.wait(5)
        return real_save(settings, key, data)

    monkeypatch.setattr("inference.api.video_minimax.save_bytes", slow_save)

    def watcher():
        assert entered.wait(5)
        for _ in range(30):
            seen.append(claim_next(stack.settings, "video", "racer"))
        release.set()

    worker = threading.Thread(target=watcher)
    worker.start()
    try:
        created = _post(stack, payload_factory())
        assert created.status_code == 200, created.text
    finally:
        release.set()
        worker.join(5)
        stack.client.__exit__(None, None, None)

    assert seen
    assert all(item is None for item in seen)
    task = get_task(stack.settings, created.json()["task_id"])
    assert task.status == "queued"
    assert task.params["first_frame_key"]
    assert resolve_key(stack.settings.data_dir, task.params["first_frame_key"]).is_file()
    if payload_factory is _flf:
        assert task.params["last_frame_key"]
        assert resolve_key(stack.settings.data_dir, task.params["last_frame_key"]).is_file()
    claimed = claim_next(stack.settings, "video", "later")
    assert claimed is not None
    assert claimed.params["first_frame_key"]
    assert resolve_key(stack.settings.data_dir, claimed.params["first_frame_key"]).is_file()


def test_failed_reference_save_does_not_leave_a_queued_task(tmp_path, monkeypatch):
    stack = build_stack(tmp_path)
    try:
        def fail_save(_settings, _key, _data):
            raise OSError("disk full")

        monkeypatch.setattr("inference.api.video_minimax.save_bytes", fail_save)
        created = _post(stack, _i2v())
        assert created.status_code == 500
        connection = sqlite3.connect(stack.settings.database_path)
        try:
            count = connection.execute("SELECT COUNT(*) FROM inference_tasks").fetchone()[0]
        finally:
            connection.close()
        assert count == 0
        inputs = stack.settings.data_dir / "inputs"
        assert [path for path in inputs.rglob("*") if path.is_file()] == []
    finally:
        stack.client.__exit__(None, None, None)
