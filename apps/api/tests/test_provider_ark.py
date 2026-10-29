"""Ark provider adapter — serialization, auth, error normalization, uncertain outcomes.
All HTTP is mocked with httpx.MockTransport. No paid calls, ever."""
from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.providers.ark import ArkProvider, build_payload, parse_task
from app.providers.base import GenerationRequest, ProviderError, UncertainSubmission
from tests.conftest import make_settings


def make_request(**kw):
    defaults = dict(
        model_id="dreamina-seedance-2-0-mini-260615", mode="reference_to_video",
        prompt="A lighthouse in a storm, cinematic. @Image1",
        ratio="16:9", resolution="720p", duration_seconds=5, generate_audio=True,
        images=[("data:image/png;base64,AAA", "reference_image")],
    )
    defaults.update(kw)
    return GenerationRequest(**defaults)


def make_provider(handler, settings=None):
    settings = settings or make_settings(__import__("pathlib").Path("/tmp/opencode/ark-t"))
    return ArkProvider(settings, transport=httpx.MockTransport(handler))


def test_payload_serialization():
    payload = build_payload(make_request(seed=11))
    assert payload["model"] == "dreamina-seedance-2-0-mini-260615"
    assert payload["content"][0] == {"type": "text", "text": payload["content"][0]["text"]}
    assert payload["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,AAA"},
        "role": "reference_image",
    }
    assert payload["resolution"] == "720p"
    assert payload["ratio"] == "16:9"
    assert payload["duration"] == 5
    assert payload["generate_audio"] is True
    assert payload["seed"] == 11
    assert payload["watermark"] is False


def test_payload_omits_optional_fields_when_unset():
    payload = build_payload(make_request(generate_audio=False, seed=None))
    assert "generate_audio" not in payload
    assert "seed" not in payload


def test_payload_omits_ratio_for_image_modes():
    """Regression: provider rejects explicit ratio for i2v modes (ratio follows
    the first-frame image) — verified live 2026-10-29, request id 02179323..."""
    i2v = build_payload(make_request(mode="image_to_video", images=[("data:image/png;base64,F", "first_frame")]))
    assert "ratio" not in i2v
    flf = build_payload(make_request(mode="first_last_frame", images=[("data:image/png;base64,F", "first_frame"), ("data:image/png;base64,L", "last_frame")]))
    assert "ratio" not in flf
    t2v = build_payload(make_request(mode="text_to_video", images=[]))
    assert t2v["ratio"] == "16:9"
    ref2v = build_payload(make_request(mode="reference_to_video"))
    assert ref2v["ratio"] == "16:9"


def test_provider_usable_across_sequential_event_loops():
    """Regression: a shared pooled client bound to a closed worker loop raised
    'RuntimeError: Event loop is closed'. The provider must hold no loop-bound
    state — sequential asyncio.run calls (worker-thread pattern) must work."""

    def handler(request):
        return httpx.Response(200, json={"id": "cgt-x", "status": "queued"})

    provider = make_provider(handler)
    import asyncio

    first = asyncio.run(provider.create_generation(make_request()))
    assert first.provider_task_id == "cgt-x"
    # second worker thread = new, independent event loop
    second = asyncio.run(provider.create_generation(make_request()))
    assert second.provider_task_id == "cgt-x"


def test_first_last_frame_roles():
    req = make_request(
        mode="first_last_frame",
        images=[("data:image/png;base64,F", "first_frame"), ("data:image/png;base64,L", "last_frame")],
    )
    payload = build_payload(req)
    roles = [c.get("role") for c in payload["content"] if c["type"] == "image_url"]
    assert roles == ["first_frame", "last_frame"]


async def test_create_success_and_auth_header():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"id": "cgt-123", "status": "queued"})

    provider = make_provider(handler, make_settings(__import__("pathlib").Path("/tmp/opencode/ark-t"), ark_api_key="secret-key"))
    try:
        task = await provider.create_generation(make_request())
        assert task.provider_task_id == "cgt-123"
        assert task.status == "queued"
        assert captured["path"].endswith("/contents/generations/tasks")
        assert captured["auth"] == "Bearer secret-key"
    finally:
        await provider.aclose()


async def test_get_status_maps_statuses_and_usage():
    body = {
        "id": "cgt-1",
        "status": "succeeded",
        "content": {"video_url": "https://example.com/v.mp4"},
        "usage": {"completion_tokens": 109200, "total_tokens": 109200},
    }
    provider = make_provider(lambda r: httpx.Response(200, json=body))
    try:
        task = await provider.get_generation_status("cgt-1")
        assert task.status == "succeeded"
        assert task.video_url == "https://example.com/v.mp4"
        assert task.completion_tokens == 109200
    finally:
        await provider.aclose()


def test_parse_task_unknown_status_rejected():
    with pytest.raises(ProviderError):
        parse_task({"id": "x", "status": "warp-speed"})


def test_parse_task_failed_maps_moderation():
    task = parse_task({"id": "x", "status": "failed", "error": {"code": "InputSensitive", "message": "sensitive content"}})
    assert task.error_code == "content_rejected"


@pytest.mark.parametrize(
    "status,body,code",
    [
        (401, {"error": {"message": "bad key"}}, "authentication_failed"),
        (429, {"error": {"message": "rate"}}, "rate_limited"),
        (403, {"error": {"code": "InsufficientBalance", "message": "no funds"}}, "insufficient_balance"),
        (400, {"error": {"code": "InvalidParameter", "message": "ratio"}}, "invalid_request"),
        (404, {"error": {"code": "ModelNotExist", "message": "no model"}}, "model_unavailable"),
    ],
)
async def test_http_error_normalization(status, body, code):
    provider = make_provider(lambda r: httpx.Response(status, json=body))
    try:
        with pytest.raises(ProviderError) as exc:
            await provider.get_generation_status("cgt-1")
        assert exc.value.code == code
        assert not exc.value.retryable
    finally:
        await provider.aclose()


async def test_timeout_becomes_uncertain_submission():
    def handler(request):
        raise httpx.ConnectTimeout("timed out")

    provider = make_provider(handler)
    try:
        with pytest.raises(UncertainSubmission):
            await provider.create_generation(make_request())
    finally:
        await provider.aclose()


async def test_transient_5xx_retried_then_success():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={"error": {"message": "unavailable"}})
        return httpx.Response(200, json={"id": "cgt-2", "status": "queued"})

    provider = make_provider(handler)
    try:
        task = await provider.create_generation(make_request())
        assert task.provider_task_id == "cgt-2"
        assert calls["n"] == 2
    finally:
        await provider.aclose()


async def test_list_recent_models():
    body = {"items": [{"model": "dreamina-seedance-2-0-mini-260615"}, {"model": "seedance-1-0-pro-250528"}, {"model": "dreamina-seedance-2-0-mini-260615"}]}
    provider = make_provider(lambda r: httpx.Response(200, json=body))
    try:
        models = await provider.list_recent_models()
        assert models == ["dreamina-seedance-2-0-mini-260615", "seedance-1-0-pro-250528"]
    finally:
        await provider.aclose()
