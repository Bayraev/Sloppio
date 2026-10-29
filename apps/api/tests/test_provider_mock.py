"""Mock provider — deterministic lifecycle simulation."""
from __future__ import annotations

import pytest

from app.providers.base import GenerationRequest, ProviderError, UncertainSubmission
from app.providers.mock import MockProvider, SYNTHETIC_MP4


def make_request(prompt="A calm sea at dawn", **kw):
    defaults = dict(
        model_id="mock-seedance", mode="text_to_video", prompt=prompt,
        ratio="16:9", resolution="720p", duration_seconds=5,
    )
    defaults.update(kw)
    return GenerationRequest(**defaults)


async def test_full_lifecycle_success():
    p = MockProvider()
    task = await p.create_generation(make_request())
    assert task.status == "queued"
    # poll until terminal
    for _ in range(100):
        task = await p.get_generation_status(task.provider_task_id)
        if task.status in ("succeeded", "failed", "expired", "cancelled"):
            break
        await asyncio_sleep()
    assert task.status == "succeeded"
    assert task.video_url and task.completion_tokens > 0
    data = await p.download_result(task.video_url)
    assert data == SYNTHETIC_MP4


async def test_fail_scenario():
    p = MockProvider()
    task = await p.create_generation(make_request("[mock:fail] a storm"))
    for _ in range(100):
        task = await p.get_generation_status(task.provider_task_id)
        if task.status == "failed":
            break
        await asyncio_sleep()
    assert task.status == "failed"
    assert task.error_code == "generation_failed"


async def test_uncertain_submission():
    p = MockProvider()
    with pytest.raises(UncertainSubmission):
        await p.create_generation(make_request("[mock:uncertain] ghost call"))


async def test_ratelimit_first_call_only():
    p = MockProvider()
    with pytest.raises(ProviderError) as exc:
        await p.create_generation(make_request("[mock:ratelimit] busy"))
    assert exc.value.code == "rate_limited"
    task = await p.create_generation(make_request("[mock:ratelimit] busy"))
    assert task.status == "queued"


async def test_expired_scenario():
    p = MockProvider()
    task = await p.create_generation(make_request("[mock:expired] stale"))
    for _ in range(100):
        task = await p.get_generation_status(task.provider_task_id)
        if task.status == "expired":
            break
        await asyncio_sleep()
    assert task.status == "expired"


async def test_missing_file_integrity():
    p = MockProvider()
    task = await p.create_generation(make_request("[mock:missingfile] hollow"))
    for _ in range(100):
        task = await p.get_generation_status(task.provider_task_id)
        if task.status == "succeeded":
            break
        await asyncio_sleep()
    data = await p.download_result(task.video_url)
    assert data == b""  # generation service must treat this as integrity failure


async def test_cancel_running_task():
    p = MockProvider()
    task = await p.create_generation(make_request("[mock:slow] long run"))
    await p.cancel_generation(task.provider_task_id)
    task = await p.get_generation_status(task.provider_task_id)
    assert task.status == "cancelled"


async def asyncio_sleep(t=0.12):
    import asyncio

    await asyncio.sleep(t)
