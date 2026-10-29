"""BytePlus ModelArk (Seedance) provider adapter.

Verified against the official API reference — see docs/research/byteplus-api-findings.md.
Never logs the API key or Authorization header.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import Settings
from app.providers.base import (
    GenerationRequest,
    ProviderError,
    ProviderTask,
    UncertainSubmission,
)

logger = logging.getLogger("studio.ark")

STATUS_MAP = {
    "queued": "queued",
    "running": "processing",
    "succeeded": "succeeded",
    "failed": "failed",
    "cancelled": "cancelled",
    "expired": "expired",
}
RETRYABLE_HTTP = {500, 502, 503, 504}
MAX_RETRIES = 2
# Bounded overall poll window: ~30 min of polling before marking needs_reconciliation.
MAX_POLL_ATTEMPTS = 360


def build_payload(request: GenerationRequest) -> dict:
    content: list[dict] = [{"type": "text", "text": request.prompt}]
    for data_url, role in request.images:
        content.append(
            {"type": "image_url", "image_url": {"url": data_url}, "role": role}
        )
    payload: dict = {
        "model": request.model_id,
        "content": content,
        "resolution": request.resolution,
        "duration": request.duration_seconds,
        "watermark": False,
    }
    # Verified live (2026-10-29): for first-frame / first-last-frame generation the
    # provider rejects an explicit ratio — the output ratio follows the first-frame
    # image ("The parameter ratio specified in the request is not valid...").
    if request.mode not in ("image_to_video", "first_last_frame"):
        payload["ratio"] = request.ratio
    if request.generate_audio:
        payload["generate_audio"] = True
    if request.seed is not None:
        payload["seed"] = request.seed
    return payload


def _http_error(status_code: int, body: dict | str) -> ProviderError:
    if isinstance(body, str):
        body = {"message": body[:500]}
    error = body.get("error") or {}
    message = str(error.get("message") or body.get("message") or f"HTTP {status_code}")
    code_raw = str(error.get("code") or "").lower()
    retryable = status_code in RETRYABLE_HTTP
    if "quota" in code_raw or "balance" in code_raw or "insufficient" in code_raw or "arrears" in code_raw:
        code = "insufficient_balance"
    elif "model" in code_raw and ("not" in code_raw or "exist" in code_raw):
        code = "model_unavailable"
    elif "sensitive" in code_raw or "moderation" in code_raw or "content" in code_raw:
        code = "content_rejected"
    elif status_code in (401, 403):
        code = "authentication_failed"
    elif status_code == 429 or "ratelimit" in code_raw or "flow control" in code_raw:
        code = "rate_limited"
    elif retryable:
        code = "provider_unavailable"
    elif 400 <= status_code < 500:
        code = "invalid_request"
    else:
        code = "unknown_provider_error"
    return ProviderError(code, message, retryable=retryable)


def parse_task(payload: dict) -> ProviderTask:
    provider_status = str(payload.get("status", "")).lower()
    status = STATUS_MAP.get(provider_status)
    if status is None:
        raise ProviderError("unknown_provider_error", f"Unrecognized provider status {provider_status!r}")
    usage = payload.get("usage") or {}
    content = payload.get("content") or {}
    task = ProviderTask(
        provider_task_id=str(payload.get("id", "")),
        status=status,
        video_url=content.get("video_url"),
        completion_tokens=usage.get("completion_tokens"),
    )
    if status == "failed":
        error = payload.get("error") or {}
        task.error_message = str(error.get("message") or "Generation failed at provider.")
        raw = str(error.get("code") or "").lower()
        if "sensitive" in raw or "moderation" in raw:
            task.error_code = "content_rejected"
        elif "quota" in raw or "balance" in raw:
            task.error_code = "insufficient_balance"
        else:
            task.error_code = "generation_failed"
    return task


class ArkProvider:
    """Stateless-per-request HTTP client.

    Every request gets a fresh AsyncClient on purpose: generation workers each
    run on their own event loop, and a shared pooled client binds connections
    to the first loop that used it (cross-loop reuse raised 'Event loop is
    closed' in production). No shared pool → that failure class is impossible.
    """

    name = "ark"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport  # tests inject MockTransport

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._settings.ark_base_url,
            headers={
                "Authorization": f"Bearer {self._settings.ark_api_key}",
                "Content-Type": "application/json",
            },
            timeout=self._settings.ark_request_timeout_seconds,
            transport=self._transport,
        )

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        last: ProviderError | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with self._new_client() as client:
                    response = await client.request(method, url, **kwargs)
            except httpx.TimeoutException as exc:
                last = ProviderError("provider_timeout", f"Request timed out: {exc}", retryable=True)
            except httpx.HTTPError as exc:
                last = ProviderError("network_error", f"Network error: {exc}", retryable=True)
            else:
                if response.status_code < 400:
                    return response.json() if response.content else {}
                try:
                    body: dict | str = response.json()
                except ValueError:
                    body = response.text[:500]
                err = _http_error(response.status_code, body)
                if not err.retryable:
                    raise err
                last = err
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2**attempt)
        assert last is not None
        raise last

    async def create_generation(self, request: GenerationRequest) -> ProviderTask:
        payload = build_payload(request)
        try:
            data = await self._request("POST", "/contents/generations/tasks", json=payload)
        except ProviderError as exc:
            # Non-idempotent create: an uncertain outcome may have created a billing task.
            if exc.code in ("provider_timeout", "network_error"):
                raise UncertainSubmission(
                    "uncertain_submission",
                    "Task submission outcome unknown (timeout). The task may exist at the provider; "
                    "kept for reconciliation instead of blind retry.",
                ) from exc
            raise
        task_id = str(data.get("id", ""))
        if not task_id:
            raise ProviderError("unknown_provider_error", "Provider returned no task id")
        status = STATUS_MAP.get(str(data.get("status", "queued")).lower(), "queued")
        return ProviderTask(provider_task_id=task_id, status=status)

    async def get_generation_status(self, provider_task_id: str) -> ProviderTask:
        data = await self._request("GET", f"/contents/generations/tasks/{provider_task_id}")
        return parse_task(data)

    async def cancel_generation(self, provider_task_id: str) -> None:
        await self._request("DELETE", f"/contents/generations/tasks/{provider_task_id}")

    async def download_result(self, video_url: str) -> bytes:
        # Signed one-off URL; fetched without auth headers to avoid leaking the key.
        async with httpx.AsyncClient(timeout=self._settings.ark_request_timeout_seconds) as client:
            for attempt in range(MAX_RETRIES + 1):
                try:
                    response = await client.get(video_url)
                except httpx.TimeoutException:
                    if attempt == MAX_RETRIES:
                        raise ProviderError("provider_timeout", "Video download timed out", retryable=True)
                    await asyncio.sleep(2**attempt)
                    continue
                if response.status_code < 400:
                    return response.content
                raise ProviderError(
                    "download_failed", f"Video download failed with HTTP {response.status_code}"
                )
        raise ProviderError("download_failed", "Video download failed")

    async def list_recent_models(self, limit: int = 5) -> list[str]:
        data = await self._request("GET", "/contents/generations/tasks", params={"page_size": limit})
        items = data.get("items") or []
        seen: list[str] = []
        for item in items:
            model = item.get("model")
            if model and model not in seen:
                seen.append(model)
        return seen

    async def aclose(self) -> None:
        return None  # no persistent resources; clients are per-request
