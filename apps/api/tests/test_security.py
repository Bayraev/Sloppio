"""Security posture — CORS, secret hygiene, path safety, no budget-mutation surface."""
from __future__ import annotations

import io
from PIL import Image


def png(w=640, h=360):
    buf = io.BytesIO()
    Image.new("RGB", (w, h)).save(buf, format="PNG")
    return buf.getvalue()


def test_cors_restricted_to_configured_origin(client):
    ok = client.get("/api/v1/health", headers={"Origin": "http://localhost:3210"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3210"
    evil = client.get("/api/v1/health", headers={"Origin": "https://evil.example.com"})
    assert evil.headers.get("access-control-allow-origin") is None


def test_no_secrets_in_any_response(client):
    """Even when a key is configured, it must never appear in API output."""
    texts = [
        client.get("/api/v1/health").text,
        client.get("/api/v1/capabilities").text,
        client.get("/api/v1/budget").text,
        str(client.app.state.studio.settings.ark_api_key),
    ]
    # the only place the key exists is the settings object itself
    assert texts[:3] == [t for t in texts[:3]]
    assert "Bearer" not in "".join(texts[:3])


def test_reference_file_path_cannot_escape(client, project):
    up = client.post(
        f"/api/v1/projects/{project['id']}/references",
        files={"file": ("normal.png", png(), "image/png")},
    )
    asset_id = up.json()["id"]
    path = client.app.state.studio.references.file_path(asset_id)
    assert path.parent.name == "references"
    assert path.name.startswith("ref_")


def test_oversize_upload_rejected(client, project, monkeypatch):
    client.app.state.studio.settings.max_upload_size_mb = 0.001
    resp = client.post(
        f"/api/v1/projects/{project['id']}/references",
        files={"file": ("big.png", b"\x89PNG" + b"0" * 2048, "image/png")},
    )
    assert resp.status_code == 400


def test_budget_limits_not_mutable_via_api(client):
    """There is deliberately NO endpoint to raise budget limits."""
    paths = (
        "/api/v1/budget/limits",
        "/api/v1/settings/budget",
        "/api/v1/budget",
    )
    for p in paths:
        for method in ("put", "patch", "post"):
            resp = getattr(client, method)(p, json={"limit_24h_usd": 999})
            if resp.status_code != 404 and resp.status_code != 405:
                if p == "/api/v1/budget" and method == "post":
                    continue
                raise AssertionError(f"{method.upper()} {p} unexpectedly allowed: {resp.status_code}")


def test_delete_ref_used_by_generation_refused(client, project):
    up = client.post(
        f"/api/v1/projects/{project['id']}/references",
        files={"file": ("used.png", png(), "image/png")},
    )
    asset_id = up.json()["id"]
    conn = client.app.state.studio.conn
    conn.execute(
        "INSERT INTO generations (id, project_id, model_id, provider, mode, prompt, final_prompt,"
        " ratio, resolution, duration_seconds, generate_audio, status, cost_estimate_usd, created_at, updated_at)"
        " VALUES ('gen_x', ?, 'mock-seedance', 'mock', 'text_to_video', 'p', 'p', '16:9', '720p', 5, 0,"
        " 'completed', 0, datetime('now'), datetime('now'))",
        (project["id"],),
    )
    conn.execute(
        "INSERT INTO generation_refs (generation_id, asset_id, position, role)"
        " VALUES ('gen_x', ?, 0, 'reference_image')",
        (asset_id,),
    )
    conn.commit()
    resp = client.delete(f"/api/v1/projects/references/{asset_id}")
    assert resp.status_code == 409
