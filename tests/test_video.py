import json

from inference.jobs.scheduler import drain
from tests.helpers import API_KEY, build_stack, data_image, video_payload


def _post(stack, payload):
    return stack.client.post("/v2/video_generation", headers={**stack.headers, "Content-Type": "application/json"}, json=payload)


def test_video_protocol_rejects_bad_auth_and_inputs(tmp_path):
    stack = build_stack(tmp_path)
    try:
        denied = stack.client.post("/v2/video_generation", json=video_payload())
        assert denied.status_code == 401
        assert denied.json()["error"]["type"] == "authorized_error"
        assert API_KEY not in denied.text
        remote = video_payload()
        remote["content"] = [
            {"type": "text", "text": "hello"},
            {"type": "image_url", "role": "first_frame", "image_url": {"url": "http://127.0.0.1/private"}},
        ]
        assert _post(stack, remote).status_code == 422
        two_k = video_payload()
        two_k["resolution"] = "2K"
        assert _post(stack, two_k).status_code == 422
        bad_image = video_payload()
        bad_image["content"] = [
            {"type": "text", "text": "hello"},
            {"type": "image_url", "role": "first_frame", "image_url": {"url": "data:image/png;base64,YWJj"}},
        ]
        assert _post(stack, bad_image).status_code == 422
        tiny = video_payload()
        tiny["content"] = [
            {"type": "text", "text": "hello"},
            {"type": "image_url", "role": "first_frame", "image_url": {"url": data_image(64, 64)}},
        ]
        assert _post(stack, tiny).status_code == 422
        assert stack.video.prompt_calls == []
    finally:
        stack.client.__exit__(None, None, None)


def test_fallback_is_explicit(tmp_path):
    stack = build_stack(tmp_path, video_allow_resolution_fallback=False)
    try:
        response = _post(stack, video_payload())
        assert response.status_code == 422
        assert "608x352" in response.text
        assert stack.video.prompt_calls == []
    finally:
        stack.client.__exit__(None, None, None)


def test_t2v_i2v_and_flf_submit_directly_to_comfyui(tmp_path):
    cases = {
        "t2v": video_payload(),
        "i2v": None,
        "flf": None,
    }
    i2v = video_payload()
    i2v["ratio"] = "adaptive"
    i2v["content"] = [
        {"type": "text", "text": "A cinematic scene"},
        {"type": "image_url", "role": "first_frame", "image_url": {"url": data_image()}},
    ]
    flf = video_payload()
    flf["content"] = [
        {"type": "text", "text": "A cinematic scene"},
        {"type": "image_url", "role": "first_frame", "image_url": {"url": data_image(color=(255, 0, 0))}},
        {"type": "image_url", "role": "last_frame", "image_url": {"url": data_image(color=(0, 255, 0))}},
    ]
    cases["i2v"] = i2v
    cases["flf"] = flf
    for mode, payload in cases.items():
        stack = build_stack(tmp_path / mode)
        try:
            created = _post(stack, payload)
            assert created.status_code == 200, created.text
            assert created.headers["x-h3-native-resolution"] == "608x352"
            assert created.headers["x-h3-resolution-adjusted"] == "true"
            task_id = created.json()["task_id"]
            assert len(task_id) == 32
            queued = stack.client.get(f"/v2/query/video_generation/{task_id}", headers=stack.headers)
            assert queued.json()["task"]["status"] == "queued"
            assert queued.json()["task"]["resolution"] == "608x352"
            assert drain(stack.settings, stack.registry) == 1
            done = stack.client.get(f"/v2/query/video_generation/{task_id}", headers=stack.headers)
            task = done.json()["task"]
            assert task["status"] == "succeeded"
            assert task["resolution"] == "608x352"
            assert task["requested_resolution"] == "768P"
            assert "signature=" in task["content"]["url"]
            assert task["content"]["url"].startswith("http://127.0.0.1:8090/v2/files/")
            downloaded = stack.client.get(task["content"]["url"].removeprefix("http://127.0.0.1:8090"))
            assert downloaded.status_code == 200, downloaded.text
            assert downloaded.content.startswith(b"\x00\x00\x00\x18ftyp")
            assert "8189" not in downloaded.headers.get("content-disposition", "")
            workflow = stack.video.prompt_calls[0]["json"]["prompt"]
            encoded = json.dumps(workflow)
            assert "__H3_STUDIO_PROMPT__" not in encoded
            assert "A cinematic scene" in encoded
            resolution = next(node for node in workflow.values() if node["class_type"] == "ResolutionSelector")
            assert float(resolution["inputs"]["megapixels"]) == 0.2
            urls = [call["url"] for call in stack.video.transport.calls if not call["url"].endswith("/system_stats")]
            assert urls[0].endswith("/prompt") if mode == "t2v" else urls[0].endswith("/upload/image")
            assert all(url.startswith("http://127.0.0.1:8189/") for url in urls)
            assert all("/api/tasks" not in url for url in urls)
            if mode == "i2v":
                assert len([url for url in urls if url.endswith("/upload/image")]) == 1
            if mode == "flf":
                assert len([url for url in urls if url.endswith("/upload/image")]) == 2
            assert len(stack.video.prompt_calls) == 1
        finally:
            stack.client.__exit__(None, None, None)


def test_video_failure_upstream_and_signature(tmp_path):
    stack = build_stack(tmp_path, video=__import__("tests.helpers", fromlist=["ScriptedComfy"]).ScriptedComfy(mode="fail"))
    try:
        created = _post(stack, video_payload())
        drain(stack.settings, stack.registry)
        task_id = created.json()["task_id"]
        body = stack.client.get(f"/v2/query/video_generation/{task_id}", headers=stack.headers).json()["task"]
        assert body["status"] == "failed"
        assert body["error"]["code"] == "local_generation_failed"
        assert body["content"] == {}
        expired = stack.client.get(f"/v2/files/{task_id}?expires=1&signature=abcd")
        assert expired.status_code == 403
        assert len(stack.video.prompt_calls) == 1
    finally:
        stack.client.__exit__(None, None, None)


def test_upstream_timeout_is_needs_review_and_is_not_retried(tmp_path):
    stack = build_stack(tmp_path, video=__import__("tests.helpers", fromlist=["ScriptedComfy"]).ScriptedComfy(mode="timeout"))
    try:
        created = _post(stack, video_payload())
        drain(stack.settings, stack.registry)
        task = stack.client.get(f"/v2/query/video_generation/{created.json()['task_id']}", headers=stack.headers).json()["task"]
        assert task["status"] == "needs_review"
        assert task["status"] != "failed"
        assert task["status"] != "succeeded"
        assert task["attention_required"] is True
        assert task["error"]["code"] == "submission_uncertain"
        drain(stack.settings, stack.registry)
        assert len(stack.video.prompt_calls) == 1
    finally:
        stack.client.__exit__(None, None, None)
