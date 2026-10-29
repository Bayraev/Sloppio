"""Shared fixtures — every test runs against a temp workspace with the MOCK provider.
No test can make a paid API call: USE_MOCK_PROVIDER is forced on."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def make_settings(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        use_mock_provider=True,
        storage_root=tmp_path / "data",
        projects_root=tmp_path / "projects",
        ark_poll_interval_seconds=0.1,
        budget_approval_threshold_usd=2.0,
        ark_api_key="",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def client(tmp_path):
    app = create_app(make_settings(tmp_path))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def app_state(client):
    return client.app.state.studio


def png_bytes(width=640, height=360, color=(120, 140, 160)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def png():
    return png_bytes()


@pytest.fixture
def project(client):
    resp = client.post(
        "/api/v1/projects", data={"title": "Test Film", "description": "A test"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
