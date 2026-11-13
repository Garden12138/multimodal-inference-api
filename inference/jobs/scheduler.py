"""One worker pool per modality. Image and video can run at the same time."""

from __future__ import annotations

import logging
import threading

from inference.config import Settings
from inference.jobs.worker import process_one
from inference.providers.registry import Registry

logger = logging.getLogger("inference.scheduler")


def start_workers(settings: Settings, registry: Registry, stop: threading.Event) -> list[threading.Thread]:
    threads = []
    assignments = (
        ("image", settings.image_workers, registry.image),
        ("video", settings.video_workers, registry.video),
    )
    for media_type, count, provider in assignments:
        for index in range(count):
            worker_id = f"{media_type}-{index}"
            thread = threading.Thread(
                target=worker_loop,
                name=f"inference-{worker_id}",
                args=(settings, provider, media_type, worker_id, stop),
                daemon=True,
            )
            thread.start()
            threads.append(thread)
    return threads


def worker_loop(settings: Settings, provider, media_type: str, worker_id: str, stop: threading.Event) -> None:
    while not stop.is_set():
        worked = False
        try:
            worked = process_one(settings, provider, media_type, worker_id, stop)
        except Exception:
            logger.exception("worker loop failed media=%s", media_type)
        if stop.is_set() or not worked:
            if stop.is_set():
                return
            stop.wait(settings.idle_interval)


def drain(settings: Settings, registry: Registry, *, limit: int = 20, stop: threading.Event | None = None) -> int:
    """Run claimed work on the calling thread. Used by tests and operators."""
    stop = stop or threading.Event()
    ran = 0
    while ran < limit and not stop.is_set():
        progress = False
        for media_type, provider in (("image", registry.image), ("video", registry.video)):
            if process_one(settings, provider, media_type, f"manual-{media_type}", stop):
                progress = True
                ran += 1
        if not progress:
            break
    return ran
