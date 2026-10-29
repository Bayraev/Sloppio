"""Mock provider — full task lifecycle simulation, zero paid calls, no API key.

Scenario markers embedded in the prompt drive deterministic behaviour for tests
and manual dry-runs:
  [mock:fail]        task fails after a short processing phase (no charge)
  [mock:uncertain]   submission times out -> UncertainSubmission (needs reconciliation)
  [mock:ratelimit]   first create call is rejected with rate_limited (retryable)
  [mock:expired]     task ends in expired state
  [mock:missingfile] succeeds but download returns empty bytes (integrity failure)
  [mock:slow]        takes extra polls before completing
"""
from __future__ import annotations

import json
import time
import uuid

from app.providers.base import (
    GenerationRequest,
    ProviderError,
    ProviderTask,
    UncertainSubmission,
)

# Minimal synthetic MP4 (ftyp + free boxes). Clearly synthetic; the UI labels
# mock outputs and the DB records provider="mock".
SYNTHETIC_MP4 = (
    b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
    b"\x00\x00\x00\x08free"
    b"\x00\x00\x00\x08free"
    b"MOCK-PROVIDER-SYNTHETIC-VIDEO"
)


class MockProvider:
    name = "mock"

    def __init__(self, poll_interval: float = 0.05, state_file=None) -> None:
        self.poll_interval = poll_interval
        self._tasks: dict[str, dict] = {}
        self._ratelimited_once = False
        self._state_file = state_file
        if state_file is not None:
            try:
                with open(state_file) as f:
                    self._tasks = json.load(f)
            except FileNotFoundError:
                pass

    def _persist(self) -> None:
        if self._state_file is not None:
            with open(self._state_file, "w") as f:
                json.dump(self._tasks, f)

    async def create_generation(self, request: GenerationRequest) -> ProviderTask:
        if "[mock:ratelimit]" in request.prompt and not self._ratelimited_once:
            self._ratelimited_once = True
            raise ProviderError("rate_limited", "Mock rate limit (first call only)", retryable=True)
        if "[mock:uncertain]" in request.prompt:
            raise UncertainSubmission(
                "uncertain_submission", "Mock uncertain submission (task may exist at provider)"
            )
        task_id = f"cgt-mock-{uuid.uuid4().hex[:16]}"
        fail = "[mock:fail]" in request.prompt
        expired = "[mock:expired]" in request.prompt
        slow = "[mock:slow]" in request.prompt
        self._tasks[task_id] = {
            "id": task_id,
            "status": "queued",
            "created": time.monotonic(),
            "model": request.model_id,
            "resolution": request.resolution,
            "duration": request.duration_seconds,
            "width": 1920 if request.resolution == "1080p" else 1280,
            "height": 1088 if request.resolution == "1080p" else 704,
            "fail": fail,
            "expired": expired,
            "slow": slow,
            "missing_file": "[mock:missingfile]" in request.prompt,
            "video_url": f"mock://{task_id}/video.mp4",
        }
        self._persist()
        return ProviderTask(provider_task_id=task_id, status="queued")

    async def get_generation_status(self, provider_task_id: str) -> ProviderTask:
        task = self._tasks.get(provider_task_id)
        if task is None:
            raise ProviderError("not_found", f"Mock task {provider_task_id} not found")
        elapsed = time.monotonic() - task["created"]
        terminal_after = 0.3 if not task["slow"] else 1.2
        if task["status"] not in ("succeeded", "failed", "cancelled", "expired"):
            if task["fail"] and elapsed >= terminal_after:
                task["status"] = "failed"
                task["error"] = {"message": "Mock generation failed (as requested)"}
            elif task["expired"] and elapsed >= terminal_after:
                task["status"] = "expired"
            elif elapsed >= terminal_after:
                task["status"] = "succeeded"
            elif elapsed >= terminal_after / 2:
                task["status"] = "running"
        # token estimate mirrors the official formula: w*h*fps*dur/1024
        tokens = int(task["width"] * task["height"] * 24 * task["duration"] / 1024)
        self._persist()
        result = ProviderTask(
            provider_task_id=task["id"],
            status=task["status"],
            video_url=task.get("video_url") if task["status"] == "succeeded" else None,
            completion_tokens=tokens if task["status"] == "succeeded" else None,
        )
        if task["status"] == "failed":
            result.error_code = "generation_failed"
            result.error_message = task["error"]["message"]
        return result

    async def cancel_generation(self, provider_task_id: str) -> None:
        task = self._tasks.get(provider_task_id)
        if task is None:
            raise ProviderError("not_found", f"Mock task {provider_task_id} not found")
        if task["status"] in ("succeeded", "failed", "expired"):
            raise ProviderError("invalid_request", "Mock task already terminal; cannot cancel")
        task["status"] = "cancelled"

    async def download_result(self, video_url: str) -> bytes:
        task_id = video_url.split("/")[2] if "/" in video_url else ""
        task = self._tasks.get(task_id, {})
        if task.get("missing_file"):
            return b""
        return SYNTHETIC_MP4

    async def list_recent_models(self, limit: int = 5) -> list[str]:
        return ["mock-seedance"]

    async def aclose(self) -> None:
        return None
