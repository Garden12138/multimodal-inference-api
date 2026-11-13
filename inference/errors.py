"""Service errors. Uncertain upstream submission is never reported as success or failure."""

from __future__ import annotations


class ConfigError(RuntimeError):
    pass


class InferenceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 400,
        *,
        uncertain: bool = False,
        kind: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.uncertain = uncertain
        self.kind = kind or kind_for(http_status)


class ProtocolError(InferenceError):
    """MiniMax Video Generation V2 local error."""


class ProviderError(InferenceError):
    pass


class UncertainSubmission(ProviderError):
    def __init__(self, message: str):
        super().__init__("SUBMISSION_UNCERTAIN", message, 504, uncertain=True, kind="server_error")


def kind_for(status: int) -> str:
    if status in (401, 403):
        return "authorized_error"
    if status == 404:
        return "not_found_error"
    if status == 422:
        return "unprocessable_entity_error"
    if status >= 500:
        return "server_error"
    return "bad_request_error"
