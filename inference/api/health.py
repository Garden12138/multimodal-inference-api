"""Liveness and authenticated provider health."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/v1/health")
def health(request: Request):
    registry = request.app.state.registry
    image = registry.image.health()
    video = registry.video.health()
    statuses = {image.get("status"), video.get("status")}
    if statuses == {"ok"}:
        overall = "ok"
    elif "ok" in statuses or "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "unreachable"
    return {
        "service": "multimodal-inference-api",
        "status": overall,
        "providers": {"image": image, "video": video},
        "reserved_providers": {"music": registry.music.health()},
    }
