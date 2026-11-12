import json

from inference.jobs.scheduler import drain
from inference.workflows.image import BASELINE, PROMPT_MARKER
from tests.helpers import API_KEY, build_stack, png_bytes


def test_invalid_key_size_and_prompt(tmp_path):
    stack = build_stack(tmp_path)
    try:
        missing = stack.client.post("/v1/images/generations", json={"model": "MiniMax-H3-Image", "prompt": "lake", "size": "1024x1024"})
        assert missing.status_code == 401
        assert API_KEY not in missing.text
        bad_size = stack.client.post(
            "/v1/images/generations",
            headers=stack.headers,
            json={"model": "MiniMax-H3-Image", "prompt": "lake", "size": "512x512"},
        )
        assert bad_size.status_code == 422
        empty = stack.client.post(
            "/v1/images/generations",
            headers=stack.headers,
            json={"model": "MiniMax-H3-Image", "prompt": "   ", "size": "1024x1024"},
        )
        assert empty.status_code == 422
        wrong_model = stack.client.post(
            "/v1/images/generations",
            headers=stack.headers,
            json={"model": "other", "prompt": "lake", "size": "1024x1024"},
        )
        assert wrong_model.status_code == 422
        assert stack.image.prompt_calls == []
    finally:
        stack.client.__exit__(None, None, None)


def test_image_success_for_both_sizes_and_download(tmp_path):
    for size, pixels in (("1024x1024", 1024), ("2048x2048", 2048)):
        stack = build_stack(tmp_path / size, image=__import__("tests.helpers", fromlist=["ScriptedComfy"]).ScriptedComfy(image=png_bytes(pixels, pixels)))
        try:
            created = stack.client.post(
                "/v1/images/generations",
                headers=stack.headers,
                json={"model": "MiniMax-H3-Image", "prompt": "A cinematic mountain lake at sunrise", "size": size},
            )
            assert created.status_code == 202, created.text
            task_id = created.json()["task_id"]
            assert created.json()["status"] == "queued"
            assert drain(stack.settings, stack.registry) == 1
            body = stack.client.get(f"/v1/images/generations/{task_id}", headers=stack.headers)
            assert body.status_code == 200, body.text
            payload = body.json()
            assert payload["status"] == "succeeded"
            assert payload["model"] == "MiniMax-H3-Image"
            assert payload["size"] == size
            assert payload["assets"][0]["mime_type"] == "image/png"
            assert payload["assets"][0]["url"].startswith("/v1/files/")
            assert "signature=" in payload["assets"][0]["url"]
            downloaded = stack.client.get(payload["assets"][0]["url"])
            assert downloaded.status_code == 200, downloaded.text
            assert downloaded.headers["content-type"].startswith("image/png")
            assert downloaded.content == png_bytes(pixels, pixels)
            workflow = stack.image.prompt_calls[0]["json"]["prompt"]
            encoded = json.dumps(workflow)
            assert PROMPT_MARKER not in encoded
            sampler = next(node for node in workflow.values() if node["class_type"] == "KSampler")
            resolution = next(node for node in workflow.values() if node["class_type"] == "ResolutionSelector")
            assert sampler["inputs"]["steps"] == BASELINE["steps"]
            assert float(sampler["inputs"]["cfg"]) == BASELINE["cfg"]
            assert float(resolution["inputs"]["megapixels"]) == (1.0 if pixels == 1024 else 4.0)
            assert all(call["url"].startswith("http://127.0.0.1:8190") for call in stack.image.transport.calls)
        finally:
            stack.client.__exit__(None, None, None)


def test_image_generation_failure_and_wrong_dimensions(tmp_path):
    failed = build_stack(tmp_path / "fail", image=__import__("tests.helpers", fromlist=["ScriptedComfy"]).ScriptedComfy(mode="fail", image=png_bytes(1024, 1024)))
    try:
        created = failed.client.post(
            "/v1/images/generations",
            headers=failed.headers,
            json={"model": "MiniMax-H3-Image", "prompt": "lake", "size": "1024x1024"},
        )
        drain(failed.settings, failed.registry)
        body = failed.client.get(f"/v1/images/generations/{created.json()['task_id']}", headers=failed.headers).json()
        assert body["status"] == "failed"
        assert body["assets"] == []
        assert len(failed.image.prompt_calls) == 1
        drain(failed.settings, failed.registry)
        assert len(failed.image.prompt_calls) == 1
    finally:
        failed.client.__exit__(None, None, None)

    wrong = build_stack(tmp_path / "wrong", image=__import__("tests.helpers", fromlist=["ScriptedComfy"]).ScriptedComfy(image=png_bytes(320, 320)))
    try:
        created = wrong.client.post(
            "/v1/images/generations",
            headers=wrong.headers,
            json={"model": "MiniMax-H3-Image", "prompt": "lake", "size": "1024x1024"},
        )
        drain(wrong.settings, wrong.registry)
        body = wrong.client.get(f"/v1/images/generations/{created.json()['task_id']}", headers=wrong.headers).json()
        assert body["status"] == "failed"
        assert body["error"]["code"] == "RESULT_INVALID"
        assert len(wrong.image.prompt_calls) == 1
    finally:
        wrong.client.__exit__(None, None, None)
