"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from inference import __version__
from inference.api.files import image_router as image_files_router
from inference.api.files import video_router as video_files_router
from inference.api.health import router as health_router
from inference.api.images import router as images_router
from inference.api.responses import install_error_handlers
from inference.api.video_minimax import router as video_router
from inference.auth.middleware import install_auth
from inference.config import Settings
from inference.db.repository import init_db
from inference.jobs.scheduler import start_workers
from inference.providers.registry import Registry

logger = logging.getLogger("inference")


class _RedactFilter(logging.Filter):
    def __init__(self, secret: str):
        super().__init__()
        self._secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "Bearer " in message or (self._secret and self._secret in message):
            record.msg = "redacted log message"
            record.args = ()
        return True


def create_app(settings: Settings, registry: Registry | None = None, *, start_workers_enabled: bool = True) -> FastAPI:
    init_db(settings)
    registry = registry or Registry(settings)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    redact = _RedactFilter(settings.api_key)
    logging.getLogger().addFilter(redact)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import threading

        stop = threading.Event()
        threads = start_workers(settings, registry, stop) if start_workers_enabled else []
        app.state.stop = stop
        logger.info(
            "service started key_source=%s legacy_key_ignored=%s fallback_source=%s fallback=%s host=%s port=%s workers=%s/%s",
            settings.api_key_source,
            settings.ignored_legacy_api_key,
            settings.resolution_fallback_source,
            settings.video_allow_resolution_fallback,
            settings.host,
            settings.port,
            settings.image_workers,
            settings.video_workers,
        )
        if settings.ignored_legacy_api_key:
            logger.info("H3_MINIMAX_API_KEY is ignored because INFERENCE_API_KEY is set")
        if settings.ignored_legacy_resolution_fallback:
            logger.info("H3_MM_ALLOW_RESOLUTION_FALLBACK is ignored because VIDEO_ALLOW_RESOLUTION_FALLBACK is set")
        try:
            yield
        finally:
            stop.set()
            for thread in threads:
                thread.join(timeout=2)

    app = FastAPI(
        title="Multimodal Inference API",
        version=__version__,
        description="Local MiniMax H3 image and video inference. Music generation is not implemented.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.registry = registry
    install_error_handlers(app)
    install_auth(app)
    app.include_router(health_router)
    app.include_router(images_router)
    app.include_router(image_files_router)
    app.include_router(video_router)
    app.include_router(video_files_router)
    return app
