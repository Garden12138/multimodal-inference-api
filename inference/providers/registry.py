"""Provider registry. Music is reserved and is not exposed as an API."""

from __future__ import annotations

from inference.config import Settings
from inference.providers.base import ReservedMusicProvider
from inference.providers.comfyui.client import RequestsTransport, Transport
from inference.providers.comfyui.image import ComfyUIH3ImageProvider
from inference.providers.comfyui.video import ComfyUIH3VideoProvider


class Registry:
    def __init__(self, settings: Settings, image_transport: Transport | None = None, video_transport: Transport | None = None):
        self.image = ComfyUIH3ImageProvider(settings, image_transport or RequestsTransport())
        self.video = ComfyUIH3VideoProvider(settings, video_transport or RequestsTransport())
        self.music = ReservedMusicProvider()

    def for_media(self, media_type: str):
        if media_type == "image":
            return self.image
        if media_type == "video":
            return self.video
        raise KeyError(media_type)
