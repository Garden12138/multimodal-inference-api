import threading
import time

from inference.db.repository import claim_next, create_task, get_task, init_db, mark_running, update_task, write_recovery_prompt
from inference.jobs.scheduler import drain
from tests.helpers import ScriptedComfy, build_stack, make_settings, png_bytes


def _image_task(settings):
    return create_task(
        settings,
        media_type="image",
        model="MiniMax-H3-Image",
        mode="t2i",
        prompt="lake",
        params={"size": "1024x1024", "width": 1024, "height": 1024},
        provider="comfyui_h3_image",
    )


def test_claim_is_exclusive_under_concurrent_connections(tmp_path):
    settings = make_settings(tmp_path)
    init_db(settings)
    _image_task(settings)
    found = []
    barrier = threading.Barrier(8)

    def worker(index):
        barrier.wait()
        found.append(claim_next(settings, "image", f"worker-{index}"))

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    claimed = [task for task in found if task is not None]
    assert len(claimed) == 1
    assert claimed[0].status == "submitting"
    assert get_task(settings, claimed[0].id).worker_id == claimed[0].worker_id


def test_image_and_video_claims_do_not_block_each_other(tmp_path):
    settings = make_settings(tmp_path)
    init_db(settings)
    _image_task(settings)
    create_task(
        settings,
        media_type="video",
        model="MiniMax-H3",
        mode="t2v",
        prompt="cat",
        params={"ratio": "16:9"},
        provider="comfyui_h3_video",
    )
    image = claim_next(settings, "image", "image-0")
    video = claim_next(settings, "video", "video-0")
    assert image.media_type == "image"
    assert video.media_type == "video"
    assert claim_next(settings, "image", "image-1") is None


def test_restart_continues_known_prompt_and_holds_uncertain_submit(tmp_path):
    stack = build_stack(tmp_path, image=ScriptedComfy(image=png_bytes(1024, 1024)))
    try:
        known = _image_task(stack.settings)
        update_task(stack.settings, known.id, status="submitting", started_at=time.time())
        mark_running(stack.settings, known.id, "prompt-1")
        lost = _image_task(stack.settings)
        update_task(stack.settings, lost.id, status="submitting", started_at=time.time())
        recoverable = _image_task(stack.settings)
        update_task(stack.settings, recoverable.id, status="submitting", started_at=time.time())
        write_recovery_prompt(stack.settings, recoverable.id, "prompt-1")
        init_db(stack.settings)
        assert get_task(stack.settings, known.id).status == "running"
        assert get_task(stack.settings, known.id).provider_task_id == "prompt-1"
        assert get_task(stack.settings, lost.id).status == "needs_review"
        assert get_task(stack.settings, recoverable.id).status == "running"
        assert drain(stack.settings, stack.registry) >= 1
        assert get_task(stack.settings, known.id).status == "succeeded"
        assert len(stack.image.prompt_calls) == 0
        assert get_task(stack.settings, lost.id).status == "needs_review"
    finally:
        stack.client.__exit__(None, None, None)


def test_transient_poll_and_download_retry_without_resubmit(tmp_path):
    comfy = ScriptedComfy(image=png_bytes(1024, 1024))
    comfy.poll_failures = 1
    comfy.view_failures = 1
    stack = build_stack(tmp_path, image=comfy)
    try:
        created = stack.client.post(
            "/v1/images/generations",
            headers=stack.headers,
            json={"model": "MiniMax-H3-Image", "prompt": "lake", "size": "1024x1024"},
        )
        drain(stack.settings, stack.registry)
        current = get_task(stack.settings, created.json()["task_id"])
        assert current.status == "succeeded"
        assert len(stack.image.prompt_calls) == 1
        assert stack.image.polls >= 2
    finally:
        stack.client.__exit__(None, None, None)


def test_timeout_download_loss_and_worker_exception(tmp_path):
    timed = build_stack(tmp_path / "timeout", image=ScriptedComfy(mode="pending", image=png_bytes(1024, 1024)), image_task_timeout=1)
    try:
        task = _image_task(timed.settings)
        update_task(timed.settings, task.id, status="submitting", started_at=time.time() - 50)
        mark_running(timed.settings, task.id, "prompt-1")
        drain(timed.settings, timed.registry)
        current = get_task(timed.settings, task.id)
        assert current.status == "failed"
        assert current.error_code == "PROVIDER_TIMEOUT"
        assert timed.image.prompt_calls == []
    finally:
        timed.client.__exit__(None, None, None)

    missing = build_stack(tmp_path / "missing", image=ScriptedComfy(image=png_bytes(1024, 1024)))
    try:
        created = missing.client.post(
            "/v1/images/generations",
            headers=missing.headers,
            json={"model": "MiniMax-H3-Image", "prompt": "lake", "size": "1024x1024"},
        )
        drain(missing.settings, missing.registry)
        body = missing.client.get(f"/v1/images/generations/{created.json()['task_id']}", headers=missing.headers).json()
        asset_id = body["assets"][0]["asset_id"]
        url = body["assets"][0]["url"]
        from inference.db.repository import get_asset
        from inference.assets.storage import resolve_key

        asset = get_asset(missing.settings, asset_id)
        resolve_key(missing.settings.data_dir, asset.storage_key).unlink()
        lost = missing.client.get(url, headers=missing.headers)
        assert lost.status_code == 404
        assert get_task(missing.settings, created.json()["task_id"]).status == "succeeded"
    finally:
        missing.client.__exit__(None, None, None)

    crashed = build_stack(tmp_path / "crash", image=ScriptedComfy(image=png_bytes(1024, 1024)))
    try:
        calls = {"n": 0}

        def explode(_task):
            calls["n"] += 1
            raise RuntimeError("worker exploded")

        crashed.registry.image.submit = explode
        created = crashed.client.post(
            "/v1/images/generations",
            headers=crashed.headers,
            json={"model": "MiniMax-H3-Image", "prompt": "lake", "size": "1024x1024"},
        )
        drain(crashed.settings, crashed.registry)
        assert get_task(crashed.settings, created.json()["task_id"]).status == "needs_review"
        drain(crashed.settings, crashed.registry)
        assert calls["n"] == 1
    finally:
        crashed.client.__exit__(None, None, None)
