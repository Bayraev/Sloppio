"""Restart recovery — unfinished tasks resume; interrupted submissions flag for reconciliation."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def test_recovery_resumes_inflight_and_flags_interrupted(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        pid = client.post("/api/v1/projects", data={"title": "Recover"}).json()["id"]
        # 1) a healthy generation that completes (leaves no in-flight row)
        ok = client.post(
            "/api/v1/generations",
            json={
                "project_id": pid, "model_id": "mock-seedance", "mode": "text_to_video",
                "prompt": "finish me", "ratio": "16:9", "resolution": "720p", "duration_seconds": 5,
            },
        ).json()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if client.get(f"/api/v1/generations/{ok['id']}").json()["status"] == "completed":
                break
            time.sleep(0.1)

        # 2) simulate an interrupted submission: no task id persisted.
        state = client.app.state.studio
        from app.services.budget import iso, now_utc

        rid = state.budget.reserve("gen_interrupted", 0.5, note="simulated")
        state.conn.execute(
            "INSERT INTO generations (id, project_id, model_id, provider, mode, prompt, final_prompt,"
            " ratio, resolution, duration_seconds, generate_audio, status, cost_estimate_usd,"
            " reservation_id, created_at, updated_at)"
            " VALUES ('gen_interrupted', ?, 'mock-seedance', 'mock', 'text_to_video', 'p', 'p',"
            " '16:9', '720p', 5, 0, 'submitting', 0.5, ?, ?, ?)",
            (pid, rid, iso(now_utc()), iso(now_utc())),
        )
        state.conn.commit()

        # 3) simulate an in-flight task WITH a persisted provider task id.
        rid2 = state.budget.reserve("gen_inflight", 0.5, note="simulated")
        mock = state.provider
        import asyncio
        from app.providers.base import GenerationRequest

        task = asyncio.run(
            mock.create_generation(
                GenerationRequest(
                    model_id="mock-seedance", mode="text_to_video", prompt="[mock:slow] long",
                    ratio="16:9", resolution="720p", duration_seconds=5,
                )
            )
        )
        state.conn.execute(
            "INSERT INTO generations (id, project_id, model_id, provider, mode, prompt, final_prompt,"
            " ratio, resolution, duration_seconds, generate_audio, status, provider_task_id,"
            " provider_status, cost_estimate_usd, reservation_id, created_at, updated_at)"
            " VALUES ('gen_inflight', ?, 'mock-seedance', 'mock', 'text_to_video', 'p', 'p',"
            " '16:9', '720p', 5, 0, 'processing', ?, 'running', 0.5, ?, ?, ?)",
            (pid, task.provider_task_id, rid2, iso(now_utc()), iso(now_utc())),
        )
        state.conn.commit()

    # ---- restart ----
    app2 = create_app(make_settings(tmp_path))
    with TestClient(app2) as client2:
        interrupted = client2.get("/api/v1/generations/gen_interrupted").json()
        assert interrupted["status"] == "needs_reconciliation"
        assert "reservation held" in (interrupted["error_message"] or "")

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            inflight = client2.get("/api/v1/generations/gen_inflight").json()
            if inflight["status"] in ("completed", "failed", "cancelled", "expired", "needs_reconciliation"):
                break
            time.sleep(0.1)
        assert inflight["status"] == "completed", inflight.get("error_message")

        budget = client2.get("/api/v1/budget").json()
        # interrupted reservation still held; inflight settled by actual charge;
        # the earlier completed generation also charged — sum of actuals == 24h spend.
        assert budget["reserved_usd"] == 0.5
        assert budget["spend_24h_usd"] >= inflight["cost_actual_usd"] > 0


def test_completed_history_survives_restart(tmp_path):
    app = create_app(make_settings(tmp_path))
    with TestClient(app) as client:
        pid = client.post("/api/v1/projects", data={"title": "History"}).json()["id"]
        gen = client.post(
            "/api/v1/generations",
            json={
                "project_id": pid, "model_id": "mock-seedance", "mode": "text_to_video",
                "prompt": "remember me", "ratio": "16:9", "resolution": "720p", "duration_seconds": 5,
            },
        ).json()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if client.get(f"/api/v1/generations/{gen['id']}").json()["status"] == "completed":
                break
            time.sleep(0.1)

    app2 = create_app(make_settings(tmp_path))
    with TestClient(app2) as client2:
        got = client2.get(f"/api/v1/generations/{gen['id']}")
        assert got.status_code == 200
        assert got.json()["status"] == "completed"
        video = client2.get(f"/api/v1/generations/{gen['id']}/video")
        assert video.status_code == 200
        assert len(video.content) > 0  # file persisted; missing file would be an integrity error
