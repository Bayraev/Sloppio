"""End-to-end generation lifecycle through the HTTP API (mock provider)."""
from __future__ import annotations

import time

from tests.conftest import png_bytes


def wait_for_status(client, gid, statuses, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        gen = client.get(f"/api/v1/generations/{gid}").json()
        if gen["status"] in statuses:
            return gen
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {statuses}; last={gen['status']} {gen.get('error_message')}")


def make_generation(client, project, prompt="A lighthouse in evening light, cinematic", **over):
    body = {
        "project_id": project["id"],
        "model_id": "mock-seedance",
        "mode": "text_to_video",
        "prompt": prompt,
        "ratio": "16:9",
        "resolution": "720p",
        "duration_seconds": 5,
    }
    body.update(over)
    resp = client.post("/api/v1/generations", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_full_success_lifecycle_charges_budget(client, project):
    gen = make_generation(client, project)
    assert gen["status"] in ("submitting", "queued", "processing")
    assert gen["cost_estimate_usd"] > 0
    done = wait_for_status(client, gen["id"], {"completed", "failed", "needs_reconciliation"})
    assert done["status"] == "completed", done.get("error_message")
    assert done["cost_actual_usd"] > 0
    assert done["provider_task_id"].startswith("cgt-")

    budget = client.get("/api/v1/budget").json()
    assert budget["spend_24h_usd"] == done["cost_actual_usd"]
    assert budget["reserved_usd"] == 0.0

    video = client.get(f"/api/v1/generations/{gen['id']}/video")
    assert video.status_code == 200
    assert video.content.startswith(b"\x00\x00\x00\x18ftyp")
    assert video.headers["content-disposition"].find("mock") != -1  # clearly labeled


def test_budget_enforced_before_submission(client, project):
    # Drain the budget with a settled charge directly.
    state = client.app.state.studio
    conn = state.conn
    from app.services.budget import iso, now_utc

    conn.execute(
        "INSERT INTO budget_charges (id, generation_id, amount_usd, created_at)"
        " VALUES ('c_drain', 'x', 6.95, ?)",
        (iso(now_utc()),),
    )
    conn.commit()
    resp = client.post(
        "/api/v1/generations",
        json={
            "project_id": project["id"], "model_id": "mock-seedance", "mode": "text_to_video",
            "prompt": "one more", "ratio": "16:9", "resolution": "720p", "duration_seconds": 10,
        },
    )
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "budget_exceeded"
    budget = client.get("/api/v1/budget").json()
    assert budget["remaining_24h_usd"] < 0.25


def test_approval_threshold_gates_expensive_operations(tmp_path, project_slug="approval"):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from tests.conftest import make_settings

    app = create_app(make_settings(tmp_path, budget_approval_threshold_usd=0.05))
    with TestClient(app) as client:
        pid = client.post("/api/v1/projects", data={"title": "Gated"}).json()["id"]
        resp = client.post(
            "/api/v1/generations",
            json={
                "project_id": pid, "model_id": "mock-seedance", "mode": "text_to_video",
                "prompt": "pricey", "ratio": "16:9", "resolution": "720p", "duration_seconds": 5,
            },
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "approval_required"
        resp2 = client.post(
            "/api/v1/generations",
            json={
                "project_id": pid, "model_id": "mock-seedance", "mode": "text_to_video",
                "prompt": "pricey", "ratio": "16:9", "resolution": "720p", "duration_seconds": 5,
                "user_approved": True,
            },
        )
        assert resp2.status_code == 201


def test_mode_validation_no_invented_capabilities(client, project):
    resp = client.post(
        "/api/v1/generations",
        json={
            "project_id": project["id"], "model_id": "mock-seedance", "mode": "text_to_video",
            "prompt": "with ref", "ratio": "16:9", "resolution": "720p", "duration_seconds": 5,
            "reference_asset_ids": ["ref_x"],
        },
    )
    assert resp.status_code in (400, 404)  # rejected either as invalid mode mix or unknown asset

    # unsupported duration for registry
    resp = client.post(
        "/api/v1/generations",
        json={
            "project_id": project["id"], "model_id": "mock-seedance", "mode": "text_to_video",
            "prompt": "7 seconds please", "ratio": "16:9", "resolution": "720p", "duration_seconds": 7,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] in ("unsupported_duration", None) or "duration" in str(resp.json()["detail"])


def test_image_to_video_with_reference(client, project):
    up = client.post(
        f"/api/v1/projects/{project['id']}/references",
        files={"file": ("still.png", png_bytes(), "image/png")},
    )
    assert up.status_code == 201
    asset_id = up.json()["id"]
    gen = make_generation(
        client, project, mode="image_to_video",
        reference_asset_ids=[asset_id], prompt="Continue this shot: waves roll in",
    )
    done = wait_for_status(client, gen["id"], {"completed", "failed", "needs_reconciliation"})
    assert done["status"] == "completed"
    assert done["reference_assets"][0]["role"] == "first_frame"


def test_failure_releases_reservation(client, project):
    gen = make_generation(client, project, prompt="[mock:fail] doom shot")
    done = wait_for_status(client, gen["id"], {"failed", "completed", "needs_reconciliation"})
    assert done["status"] == "failed"
    budget = client.get("/api/v1/budget").json()
    assert budget["spend_24h_usd"] == 0.0  # failed generations are not billed
    assert budget["reserved_usd"] == 0.0


def test_uncertain_submission_keeps_reservation(client, project):
    gen = make_generation(client, project, prompt="[mock:uncertain] maybe billed")
    done = wait_for_status(client, gen["id"], {"needs_reconciliation", "failed", "completed"})
    assert done["status"] == "needs_reconciliation"
    budget = client.get("/api/v1/budget").json()
    assert budget["reserved_usd"] > 0  # reservation held, never silently dropped
    assert budget["spend_24h_usd"] == 0.0
    # Retry is refused while outcome unknown (duplicate charge risk).
    retry = client.post(f"/api/v1/generations/{gen['id']}/retry", json={})
    assert retry.status_code == 409
    # Delete is refused too — would orphan the reservation.
    dele = client.delete(f"/api/v1/generations/{gen['id']}")
    assert dele.status_code == 409


def test_retry_creates_new_record_preserving_original(client, project):
    gen = make_generation(client, project, prompt="[mock:fail] first attempt")
    wait_for_status(client, gen["id"], {"failed"})
    retry = client.post(f"/api/v1/generations/{gen['id']}/retry", json={})
    assert retry.status_code == 201
    new_gen = retry.json()
    assert new_gen["id"] != gen["id"]
    assert new_gen["retry_of"] == gen["id"]
    original = client.get(f"/api/v1/generations/{gen['id']}").json()
    assert original["status"] == "failed"  # original preserved with inputs


def test_cancel_in_flight(client, project):
    gen = make_generation(client, project, prompt="[mock:slow] long job")
    resp = client.post(f"/api/v1/generations/{gen['id']}/cancel")
    assert resp.status_code == 200
    done = wait_for_status(client, gen["id"], {"cancelled", "failed", "completed", "needs_reconciliation"})
    assert done["status"] == "cancelled"
    budget = client.get("/api/v1/budget").json()
    assert budget["reserved_usd"] == 0.0


def test_history_and_filters(client, project):
    make_generation(client, project, prompt="shot one")
    make_generation(client, project, prompt="[mock:fail] shot two")
    gens = client.get("/api/v1/generations", params={"project_id": project["id"]}).json()["generations"]
    assert len(gens) >= 2
    failed = client.get("/api/v1/generations", params={"status": "failed"}).json()["generations"]
    time.sleep(2.0)
    failed = client.get("/api/v1/generations", params={"status": "failed"}).json()["generations"]
    assert any(g["prompt"] == "[mock:fail] shot two" for g in failed)


def test_bible_context_selected_only(client, project):
    gen = make_generation(
        client, project, prompt="hero walks the pier",
        bible_docs=["characters.md", "world.md"],
    )
    detail = client.get(f"/api/v1/generations/{gen['id']}").json()
    assert detail["status"] in ("submitting", "queued", "processing", "completed", "failed")
    # The stored final prompt embeds ONLY the selected docs, capped.
    assert "FILM BIBLE CONTEXT" in detail["final_prompt"]
    assert "characters.md" in detail["final_prompt"]
    assert "visual-style.md" not in detail["final_prompt"]
