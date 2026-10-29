"""Provider abstraction shared by the Ark (BytePlus) and Mock providers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

RESOLUTIONS = ("480p", "720p", "1080p", "4k")
RATIOS = ("16:9", "9:16", "1:1", "4:3", "21:9")
MODES = ("text_to_video", "image_to_video", "first_last_frame", "reference_to_video")


class ProviderError(Exception):
    """Normalized provider failure. Never contains credentials."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class UncertainSubmission(ProviderError):
    """Create-task outcome unknown (timeout/network). A task may exist and bill.
    Never blind-retry; escalate to reconciliation with the reservation kept."""


@dataclass
class GenerationRequest:
    model_id: str
    mode: str
    prompt: str
    ratio: str
    resolution: str
    duration_seconds: int
    generate_audio: bool = False
    seed: int | None = None
    # list of (base64 data URL, role); roles: first_frame|last_frame|reference_image
    images: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ProviderTask:
    provider_task_id: str
    status: str  # internal: queued|processing|succeeded|failed|cancelled|expired
    video_url: str | None = None
    completion_tokens: int | None = None
    error_code: str | None = None
    error_message: str | None = None


@runtime_checkable
class VideoProvider(Protocol):
    name: str

    async def create_generation(self, request: GenerationRequest) -> ProviderTask: ...

    async def get_generation_status(self, provider_task_id: str) -> ProviderTask: ...

    async def cancel_generation(self, provider_task_id: str) -> None: ...

    async def download_result(self, video_url: str) -> bytes: ...

    async def list_recent_models(self, limit: int = 5) -> list[str]:
        """Model IDs seen on recent tasks (free read; helps verify account models)."""
        ...

    async def aclose(self) -> None: ...
