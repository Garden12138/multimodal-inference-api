import hashlib
import json
import os
from pathlib import Path

import pytest

from inference.config import ROOT
from inference.workflows.image import BASELINE, PROMPT_MARKER, prepare_workflow
from inference.workflows.manifest import WORKFLOW_SHA256
from inference.workflows.video import BASELINE as VIDEO_BASELINE
from inference.workflows.video import prepare_video_workflow

REFERENCE_PAIRS = {
    "image/t2i_1mp_api.json": "image/t2i_1mp_api.json",
    "image/t2i_4mp_api.json": "image/t2i_4mp_api.json",
    "video/t2v_api.json": "t2v_api.json",
    "video/i2v_api.json": "i2v_api.json",
    "video/flf_api.json": "flf_api.json",
}


def test_workflow_bytes_match_sha256_manifest():
    for relative, digest in WORKFLOW_SHA256.items():
        copied = (ROOT / "workflows" / relative).read_bytes()
        assert hashlib.sha256(copied).hexdigest() == digest


@pytest.mark.skipif(
    not os.environ.get("INFERENCE_REFERENCE_WORKFLOW_DIR"),
    reason="set INFERENCE_REFERENCE_WORKFLOW_DIR to compare with an external workflow tree",
)
def test_optional_external_workflow_bytes():
    source_root = Path(os.environ["INFERENCE_REFERENCE_WORKFLOW_DIR"])
    for relative, source_name in REFERENCE_PAIRS.items():
        copied = (ROOT / "workflows" / relative).read_bytes()
        assert copied == (source_root / source_name).read_bytes()


def test_image_source_files_differ_only_by_megapixels_prefix_and_exported_seed():
    one = json.loads((ROOT / "workflows/image/t2i_1mp_api.json").read_text(encoding="utf-8"))
    four = json.loads((ROOT / "workflows/image/t2i_4mp_api.json").read_text(encoding="utf-8"))
    one["14"]["inputs"]["megapixels"] = four["14"]["inputs"]["megapixels"]
    one["9"]["inputs"]["filename_prefix"] = four["9"]["inputs"]["filename_prefix"]
    one["23_7"]["inputs"]["seed"] = four["23_7"]["inputs"]["seed"]
    assert one == four


def test_image_preparation_keeps_verified_sampler_and_replaces_prompt():
    for size, megapixels, relative in (
        ("1024x1024", 1.0, "image/t2i_1mp_api.json"),
        ("2048x2048", 4.0, "image/t2i_4mp_api.json"),
    ):
        prepared = prepare_workflow(ROOT / "workflows" / relative, megapixels, "mountain lake", "abc123", 7)
        encoded = json.dumps(prepared)
        assert PROMPT_MARKER not in encoded
        assert "mountain lake" in encoded
        sampler = next(node for node in prepared.values() if node["class_type"] == "KSampler")
        resolution = next(node for node in prepared.values() if node["class_type"] == "ResolutionSelector")
        attention = next(node for node in prepared.values() if node["class_type"] == "ModelAttentionBackend")
        switch = next(node for node in prepared.values() if node["class_type"] == "ComfySwitchNode")
        save = next(node for node in prepared.values() if node["class_type"] == "SaveImage")
        assert sampler["inputs"]["steps"] == BASELINE["steps"]
        assert sampler["inputs"]["cfg"] == BASELINE["cfg"]
        assert sampler["inputs"]["sampler_name"] == "euler"
        assert sampler["inputs"]["scheduler"] == "simple"
        assert sampler["inputs"]["seed"] == 7
        assert float(resolution["inputs"]["megapixels"]) == megapixels
        assert attention["inputs"]["attention"] == "pytorch attention"
        assert switch["inputs"]["switch"] is False
        assert save["inputs"]["filename_prefix"] == "inference_abc123"


def test_video_preparation_keeps_model_steps_and_resolution():
    for mode, first, last in (("t2v", None, None), ("i2v", "up-first.png", None), ("flf", "up-first.png", "up-last.png")):
        prepared = prepare_video_workflow(ROOT / "workflows" / "video" / f"{mode}_api.json", mode, "rain street", "abc123", first, last)
        encoded = json.dumps(prepared)
        assert "__H3_STUDIO_PROMPT__" not in encoded
        assert "STUDIO_FIRST.png" not in encoded
        assert "STUDIO_LAST.png" not in encoded
        assert "rain street" in encoded
        resolution = next(node for node in prepared.values() if node["class_type"] == "ResolutionSelector")
        save = next(node for node in prepared.values() if node["class_type"] == "SaveVideo")
        lora = next(node for node in prepared.values() if node["class_type"] == "LoraLoaderModelOnly")
        assert float(resolution["inputs"]["megapixels"]) == VIDEO_BASELINE["megapixels"]
        assert resolution["inputs"]["aspect_ratio"] == VIDEO_BASELINE["aspect_ratio"]
        assert lora["inputs"]["lora_name"] == VIDEO_BASELINE["lora"]
        assert save["inputs"]["filename_prefix"] == "video/inference_abc123"
        if mode == "i2v":
            assert "up-first.png" in encoded
        if mode == "flf":
            assert "up-last.png" in encoded


def test_mutated_image_steps_are_rejected(tmp_path):
    source = json.loads((ROOT / "workflows/image/t2i_1mp_api.json").read_text(encoding="utf-8"))
    source["23_7"]["inputs"]["steps"] = 20
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    try:
        prepare_workflow(path, 1.0, "lake", "abc", 1)
    except ValueError as exc:
        assert "采样" in str(exc)
    else:
        raise AssertionError("mutated steps were accepted")
