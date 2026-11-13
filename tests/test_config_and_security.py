from pathlib import Path

import requests

from inference.config import ROOT, load_env_file, load_settings
from inference.errors import ConfigError
from inference.providers.comfyui.client import RequestsTransport
from tests.helpers import API_KEY, build_stack, make_settings


def test_api_key_and_fallback_priority(tmp_path, monkeypatch):
    monkeypatch.delenv("INFERENCE_API_KEY", raising=False)
    monkeypatch.delenv("H3_MINIMAX_API_KEY", raising=False)
    primary = "p" * 32
    legacy = "l" * 32
    both = load_settings({"INFERENCE_API_KEY": primary, "H3_MINIMAX_API_KEY": legacy})
    assert both.api_key == primary
    assert both.api_key_source == "INFERENCE_API_KEY"
    assert both.ignored_legacy_api_key is True
    only_legacy = load_settings({"H3_MINIMAX_API_KEY": legacy, "INFERENCE_API_KEY": "  "})
    assert only_legacy.api_key == legacy
    assert only_legacy.api_key_source == "H3_MINIMAX_API_KEY"
    try:
        load_settings({})
    except ConfigError:
        pass
    else:
        raise AssertionError("missing key was accepted")
    try:
        load_settings({"INFERENCE_API_KEY": "short-key"})
    except ConfigError:
        pass
    else:
        raise AssertionError("short key was accepted")
    try:
        load_settings({"INFERENCE_API_KEY": primary, "INFERENCE_PORT": "8089"})
    except ConfigError as exc:
        assert "8089" in str(exc)
    else:
        raise AssertionError("port 8089 was accepted")
    fallback = load_settings(
        {
            "INFERENCE_API_KEY": primary,
            "VIDEO_ALLOW_RESOLUTION_FALLBACK": "1",
            "H3_MM_ALLOW_RESOLUTION_FALLBACK": "0",
        }
    )
    assert fallback.video_allow_resolution_fallback is True
    assert fallback.resolution_fallback_source == "VIDEO_ALLOW_RESOLUTION_FALLBACK"
    assert fallback.ignored_legacy_resolution_fallback is True
    legacy_fallback = load_settings({"INFERENCE_API_KEY": primary, "H3_MM_ALLOW_RESOLUTION_FALLBACK": "yes"})
    assert legacy_fallback.video_allow_resolution_fallback is True
    assert legacy_fallback.resolution_fallback_source == "H3_MM_ALLOW_RESOLUTION_FALLBACK"
    env_file = tmp_path / ".env"
    env_file.write_text("INFERENCE_API_KEY=from-file-but-too-long-enough-ok\n", encoding="utf-8")
    environ = {"INFERENCE_API_KEY": primary}
    load_env_file(env_file, environ)
    assert environ["INFERENCE_API_KEY"] == primary


def test_requests_ignore_environment_proxy():
    transport = RequestsTransport()
    assert transport.session.trust_env is False
    assert "trust_env = False" in (ROOT / "inference/providers/comfyui/client.py").read_text(encoding="utf-8")


def test_source_has_no_studio_task_api():
    roots = [ROOT / "inference", ROOT / "app.py", ROOT / "scripts"]
    text = []
    for root in roots:
        if root.is_file():
            text.append(root.read_text(encoding="utf-8"))
            continue
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text.append(path.read_text(encoding="utf-8"))
        for path in root.rglob("*.sh"):
            text.append(path.read_text(encoding="utf-8"))
    combined = "\n".join(text)
    assert "/api/tasks" not in combined
    assert "H3_STUDIO_URL" not in combined
    assert "127.0.0.1:8088" not in combined
    assert "trust_env = True" not in combined
    assert "import studio" not in combined


def test_network_and_path_guards(tmp_path):
    stack = build_stack(tmp_path)
    try:
        outsider = stack.client.__class__(stack.client.app, client=("10.1.1.1", 9))
        denied = outsider.get("/healthz")
        assert denied.status_code == 403
        local = stack.client.get("/healthz")
        assert local.status_code == 200
        assert local.json() == {"status": "ok"}
        health = stack.client.get("/v2/health", headers=stack.headers)
        assert health.status_code == 200
        assert health.json()["studio_dependency"] is False
        assert health.json()["native_resolution"] == "608x352"
        assert "not_implemented" == stack.client.get("/v1/health", headers=stack.headers).json()["reserved_providers"]["music"]["status"]
    finally:
        stack.client.__exit__(None, None, None)

    from inference.assets.storage import resolve_key
    from inference.errors import InferenceError

    settings = make_settings(tmp_path / "paths")
    for key in ("../secrets", "/etc/passwd", "outputs/../../secrets", "outputs/../../../etc/passwd"):
        try:
            resolve_key(settings.data_dir, key)
        except InferenceError:
            continue
        raise AssertionError(f"path escaped data dir: {key}")


def test_repr_hides_api_key():
    settings = load_settings({"INFERENCE_API_KEY": API_KEY})
    assert API_KEY not in repr(settings)
    assert "requests" in requests.__name__
