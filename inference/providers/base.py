"""Provider contract shared by image, video, and future engines such as music."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TaskInput:
    task_id: str
    media_type: str
    mode: str
    prompt: str
    params: dict
    first_image: bytes | None = None
    last_image: bytes | None = None
    first_filename: str | None = None
    last_filename: str | None = None


@dataclass
class ProviderSubmission:
    provider_task_id: str
    provider_status: str | None = None


@dataclass
class ProviderTaskStatus:
    provider_status: str
    normalized: str
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class ProviderAsset:
    media_type: str
    mime_type: str
    data: bytes
    filename: str


class Provider:
    provider_id = "provider"
    supported_media_types: tuple[str, ...] = ()
    supported_modes: tuple[str, ...] = ()

    def health(self) -> dict:
        raise NotImplementedError

    def submit(self, task: TaskInput) -> ProviderSubmission:
        raise NotImplementedError

    def poll(self, provider_task_id: str) -> ProviderTaskStatus:
        raise NotImplementedError

    def fetch_assets(self, provider_task_id: str, task: TaskInput) -> list[ProviderAsset]:
        raise NotImplementedError


class ReservedMusicProvider(Provider):
    """Extension point only. V1 has no music route and does not call a model."""

    provider_id = "music_reserved"
    supported_media_types = ("audio",)
    supported_modes = ()

    def health(self) -> dict:
        return {"provider": self.provider_id, "status": "not_implemented"}

    def submit(self, task: TaskInput) -> ProviderSubmission:
        raise NotImplementedError("Music generation is not implemented")

    def poll(self, provider_task_id: str) -> ProviderTaskStatus:
        raise NotImplementedError("Music generation is not implemented")

    def fetch_assets(self, provider_task_id: str, task: TaskInput) -> list[ProviderAsset]:
        raise NotImplementedError("Music generation is not implemented")
