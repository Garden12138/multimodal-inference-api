"""Video workflow preparation. Model, steps, and resolution knobs stay as exported."""

from __future__ import annotations

import json
from pathlib import Path

PROMPT_MARKER = "__H3_STUDIO_PROMPT__"
FIRST_MARKER = "STUDIO_FIRST.png"
LAST_MARKER = "STUDIO_LAST.png"

ACTUAL_WIDTH = 608
ACTUAL_HEIGHT = 352
ACTUAL_RESOLUTION = "608x352"
NOMINAL_REQUEST_RESOLUTION = "768P"
NOMINAL_RATIO = "16:9"
DURATION_SECONDS = 5

BASELINE = {
    "unet": "minimax_h3_fl2va_pruned_fp8_scaled.safetensors",
    "clip": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "vae": "minimax_h3_video_vae_fp16.safetensors",
    "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
    "lora": "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors",
    "lora_strength": 1,
    "megapixels": 0.2,
    "aspect_ratio": "16:9 (Widescreen)",
    "multiple": 32,
    "duration": 5.0,
    "sampler_name": "res_multistep",
    "scheduler": "simple",
    "denoise": 1,
    "turbo_steps": 4,
    "base_steps": 20,
    "lightning": True,
    "fps": 24,
    "length_expression": "max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17",
}


def workflow_file(workflow_dir: Path, mode: str) -> Path:
    if mode not in {"t2v", "i2v", "flf"}:
        raise ValueError("unsupported video mode")
    return workflow_dir / "video" / f"{mode}_api.json"


def prepare_video_workflow(
    path: Path,
    mode: str,
    prompt: str,
    task_id: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> dict:
    workflow = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(workflow, dict) or not workflow or not all(
        isinstance(node, dict) and "class_type" in node and isinstance(node.get("inputs"), dict)
        for node in workflow.values()
    ):
        raise ValueError("workflow is not API JSON")
    _assert_baseline(workflow, mode)
    mapping = {PROMPT_MARKER: prompt}
    if mode in {"i2v", "flf"}:
        if not first_name:
            raise ValueError("missing first frame")
        mapping[FIRST_MARKER] = first_name
    if mode == "flf":
        if not last_name:
            raise ValueError("missing last frame")
        mapping[LAST_MARKER] = last_name
    counts: dict[str, int] = {}
    workflow = _replace(workflow, mapping, counts)
    for marker in mapping:
        if counts.get(marker, 0) < 1:
            raise ValueError(f"missing marker {marker}")
    saved = [node for node in workflow.values() if node.get("class_type") == "SaveVideo"]
    if len(saved) != 1 or "filename_prefix" not in saved[0].get("inputs", {}):
        raise ValueError("workflow must contain one SaveVideo node")
    saved[0]["inputs"]["filename_prefix"] = f"video/inference_{task_id}"
    _assert_baseline(workflow, mode)
    rendered = json.dumps(workflow)
    for marker in mapping:
        if marker in rendered:
            raise ValueError(f"marker remained {marker}")
    return workflow


def _assert_baseline(workflow: dict, mode: str) -> None:
    nodes = list(workflow.values())

    def inputs_of(class_type: str) -> list[dict]:
        return [node["inputs"] for node in nodes if node.get("class_type") == class_type]

    unets = inputs_of("UNETLoader")
    if len(unets) != 1 or unets[0].get("unet_name") != BASELINE["unet"]:
        raise ValueError("video unet baseline mismatch")
    clips = inputs_of("CLIPLoader")
    if len(clips) != 1 or clips[0].get("clip_name") != BASELINE["clip"]:
        raise ValueError("video clip baseline mismatch")
    vaes = {item.get("vae_name") for item in inputs_of("VAELoader")}
    if vaes != {BASELINE["vae"], BASELINE["audio_vae"]}:
        raise ValueError("video vae baseline mismatch")
    loras = inputs_of("LoraLoaderModelOnly")
    if len(loras) != 1 or loras[0].get("lora_name") != BASELINE["lora"]:
        raise ValueError("video lora baseline mismatch")
    if float(loras[0].get("strength_model")) != float(BASELINE["lora_strength"]):
        raise ValueError("video lora strength baseline mismatch")
    resolutions = inputs_of("ResolutionSelector")
    if len(resolutions) != 1:
        raise ValueError("video resolution baseline mismatch")
    resolution = resolutions[0]
    if (
        resolution.get("aspect_ratio") != BASELINE["aspect_ratio"]
        or float(resolution.get("megapixels")) != float(BASELINE["megapixels"])
        or resolution.get("multiple") != BASELINE["multiple"]
    ):
        raise ValueError("video resolution baseline mismatch")
    durations = [
        node["inputs"].get("value")
        for node in nodes
        if node.get("class_type") == "PrimitiveFloat" and (node.get("_meta") or {}).get("title") == "Float (duration)"
    ]
    if durations != [BASELINE["duration"]] and durations != [int(BASELINE["duration"])]:
        if len(durations) != 1 or float(durations[0]) != float(BASELINE["duration"]):
            raise ValueError("video duration baseline mismatch")
    samplers = inputs_of("KSamplerSelect")
    if len(samplers) != 1 or samplers[0].get("sampler_name") != BASELINE["sampler_name"]:
        raise ValueError("video sampler baseline mismatch")
    schedulers = inputs_of("BasicScheduler")
    if len(schedulers) != 1 or schedulers[0].get("scheduler") != BASELINE["scheduler"]:
        raise ValueError("video scheduler baseline mismatch")
    if float(schedulers[0].get("denoise")) != float(BASELINE["denoise"]):
        raise ValueError("video denoise baseline mismatch")
    ints = [
        node["inputs"].get("value")
        for node in nodes
        if node.get("class_type") == "PrimitiveInt"
    ]
    if BASELINE["turbo_steps"] not in ints or BASELINE["base_steps"] not in ints:
        raise ValueError("video step baseline mismatch")
    booleans = [
        node["inputs"].get("value")
        for node in nodes
        if node.get("class_type") == "PrimitiveBoolean"
    ]
    if booleans != [BASELINE["lightning"]]:
        raise ValueError("video lightning switch baseline mismatch")
    created = inputs_of("CreateVideo")
    if len(created) != 1 or created[0].get("fps") != BASELINE["fps"]:
        raise ValueError("video fps baseline mismatch")
    expressions = inputs_of("ComfyMathExpression")
    if len(expressions) != 1 or expressions[0].get("expression") != BASELINE["length_expression"]:
        raise ValueError("video length expression baseline mismatch")
    loaders = inputs_of("LoadImage")
    expected_loaders = {"t2v": 0, "i2v": 1, "flf": 2}[mode]
    if len(loaders) != expected_loaders:
        raise ValueError("video reference image nodes mismatch")


def _replace(value, mapping: dict[str, str], counts: dict[str, int]):
    if isinstance(value, dict):
        return {key: _replace(item, mapping, counts) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace(item, mapping, counts) for item in value]
    if isinstance(value, str):
        for marker, replacement in mapping.items():
            found = value.count(marker)
            if found:
                counts[marker] = counts.get(marker, 0) + found
                value = value.replace(marker, replacement)
    return value
