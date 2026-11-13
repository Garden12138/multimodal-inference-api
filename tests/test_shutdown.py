import threading
import time

from inference.db.repository import get_task, init_db, mark_running, update_task
from inference.jobs.scheduler import worker_loop
from inference.jobs.worker import execute, process_one
from inference.providers.base import ProviderSubmission
from tests.helpers import ScriptedComfy, build_stack, make_settings, png_bytes


def _image_task(settings):
    from inference.db.repository import create_task

    return create_task(
        settings,
        media_type="image",
        model="MiniMax-H3-Image",
        mode="t2i",
        prompt="lake",
        params={"size": "1024x1024", "width": 1024, "height": 1024},
        provider="comfyui_h3_image",
    )


def test_stop_event_prevents_new_claims_and_preserves_prompt_id(tmp_path):
    comfy = ScriptedComfy(image=png_bytes(1024, 1024))
    stack = build_stack(tmp_path, image=comfy)
    try:
        running = _image_task(stack.settings)
        update_task(stack.settings, running.id, status="submitting", started_at=time.time(), worker_id="image-0")
        mark_running(stack.settings, running.id, "prompt-1")
        queued = _image_task(stack.settings)
        stop = threading.Event()
        stop.set()
        assert process_one(stack.settings, stack.registry.image, "image", "image-0", stop) is False
        assert get_task(stack.settings, running.id).status == "running"
        assert get_task(stack.settings, running.id).provider_task_id == "prompt-1"
        assert get_task(stack.settings, queued.id).status == "queued"
        assert comfy.prompt_calls == []
    finally:
        stack.client.__exit__(None, None, None)


def test_shutdown_before_submit_returns_the_task_to_the_queue(tmp_path):
    settings = make_settings(tmp_path)
    init_db(settings)
    task = _image_task(settings)
    update_task(settings, task.id, status="submitting", started_at=time.time(), worker_id="image-0")

    class ExplodingProvider:
        def submit(self, _task):
            raise AssertionError("upstream submit was attempted during shutdown")

        def poll(self, _provider_task_id):
            raise AssertionError("poll")

    stop = threading.Event()
    stop.set()
    execute(settings, ExplodingProvider(), task.id, "image-0", stop)
    current = get_task(settings, task.id)
    assert current.status == "queued"
    assert current.provider_task_id is None
    assert current.worker_id is None


def test_stop_during_submit_keeps_prompt_id_and_later_resume_does_not_resubmit(tmp_path):
    comfy = ScriptedComfy(image=png_bytes(1024, 1024))
    stack = build_stack(tmp_path, image=comfy)
    entered = threading.Event()
    release = threading.Event()
    original_submit = stack.registry.image.submit

    def blocking_submit(task):
        entered.set()
        assert release.wait(5)
        return original_submit(task)

    stack.registry.image.submit = blocking_submit
    task = _image_task(stack.settings)
    stop = threading.Event()
    worker = threading.Thread(
        target=process_one,
        args=(stack.settings, stack.registry.image, "image", "image-0", stop),
    )
    worker.start()
    try:
        assert entered.wait(5)
        stop.set()
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        current = get_task(stack.settings, task.id)
        assert current.status == "running"
        assert current.provider_task_id == "prompt-1"
        assert comfy.polls == 0
        assert len(comfy.prompt_calls) == 1
        assert process_one(stack.settings, stack.registry.image, "image", "image-1", stop) is False
        stop.clear()
        stack.registry.image.submit = original_submit
        assert process_one(stack.settings, stack.registry.image, "image", "image-0", stop) is True
        assert get_task(stack.settings, task.id).status == "succeeded"
        assert len(comfy.prompt_calls) == 1
    finally:
        release.set()
        worker.join(2)
        stack.client.__exit__(None, None, None)


def test_stop_during_poll_keeps_prompt_id_for_restart(tmp_path):
    comfy = ScriptedComfy(mode="pending", image=png_bytes(1024, 1024))
    stack = build_stack(tmp_path, image=comfy)
    entered = threading.Event()
    release = threading.Event()
    original = comfy.transport.handler

    def blocking_poll(call):
        if "/history/" in call["url"]:
            entered.set()
            assert release.wait(5)
        return original(call)

    comfy.transport.handler = blocking_poll
    task = _image_task(stack.settings)
    update_task(stack.settings, task.id, status="submitting", started_at=time.time(), worker_id="image-0")
    mark_running(stack.settings, task.id, "prompt-1")
    stop = threading.Event()
    worker = threading.Thread(
        target=process_one,
        args=(stack.settings, stack.registry.image, "image", "image-0", stop),
    )
    worker.start()
    try:
        assert entered.wait(5)
        stop.set()
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        current = get_task(stack.settings, task.id)
        assert current.status == "running"
        assert current.provider_task_id == "prompt-1"
        assert comfy.prompt_calls == []
        comfy.mode = "success"
        comfy.transport.handler = original
        stop.clear()
        assert process_one(stack.settings, stack.registry.image, "image", "image-0", stop) is True
        assert get_task(stack.settings, task.id).status == "succeeded"
        assert comfy.prompt_calls == []
    finally:
        release.set()
        worker.join(2)
        stack.client.__exit__(None, None, None)


def test_worker_loop_exits_when_stop_is_set(tmp_path):
    settings = make_settings(tmp_path)
    init_db(settings)
    task = _image_task(settings)
    stop = threading.Event()
    stop.set()

    class Unused:
        def submit(self, _task):
            return ProviderSubmission("should-not-run")

    thread = threading.Thread(target=worker_loop, args=(settings, Unused(), "image", "image-0", stop))
    thread.start()
    thread.join(2)
    assert not thread.is_alive()
    assert get_task(settings, task.id).status == "queued"
