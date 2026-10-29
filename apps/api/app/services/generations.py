"""Generation lifecycle orchestration.

Flow (mirrors the documented contract in AGENTS.md):
 validate → estimate → (approval gate) → reserve budget → persist generation →
 submit to provider → persist task id → poll → download → verify → settle/release.

Hard rules:
- Every paid path goes through BudgetService (single entry: `_start_generation`).
- Uncertain submissions NEVER blind-retry: status -> needs_reconciliation, reservation kept.
- Mock outputs are clearly marked (provider="mock", .mock.mp4 files, UI badge).
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass, field

from app.config import Settings
from app.providers.base import (
    GenerationRequest,
    ProviderError,
    UncertainSubmission,
    VideoProvider,
)
from app.providers.mock import MockProvider
from app.providers.registry import ModelRegistry
from app.services.budget import BudgetExceededError, BudgetService, iso, now_utc
from app.services.projects import ProjectError, ProjectService, new_id
from app.services.references import ReferenceService

logger = logging.getLogger("studio.generations")

STATUSES = (
    "validating", "submitting", "queued", "processing", "downloading",
    "completed", "failed", "cancelled", "expired", "needs_reconciliation",
)
TERMINAL = {"completed", "failed", "cancelled", "expired"}
IMAGE_ROLES = {"image_to_video": ["first_frame"], "first_last_frame": ["first_frame", "last_frame"]}


class GenerationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass
class CreateGenerationInput:
    project_id: str
    model_id: str
    mode: str
    prompt: str
    ratio: str
    resolution: str
    duration_seconds: int
    scene_id: str | None = None
    generate_audio: bool = False
    seed: int | None = None
    reference_asset_ids: list[str] = field(default_factory=list)
    bible_docs: list[str] = field(default_factory=list)
    user_approved: bool = False
    retry_of: str | None = None


class GenerationService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings,
        registry: ModelRegistry,
        budget: BudgetService,
        projects: ProjectService,
        references: ReferenceService,
        provider: VideoProvider,
    ) -> None:
        self.conn = conn
        self.settings = settings
        self.registry = registry
        self.budget = budget
        self.projects = projects
        self.references = references
        self.provider = provider
        self._pollers: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------ create
    def create(self, data: CreateGenerationInput) -> dict:
        prompt = data.prompt.strip()
        if not prompt or len(prompt) > 8000:
            raise GenerationError("invalid_prompt", "Prompt must be 1-8000 characters.")
        try:
            self.projects.get_project(data.project_id)
        except ProjectError as exc:
            raise GenerationError("unknown_project", str(exc), 404)
        if data.scene_id:
            try:
                self.projects.get_scene(data.scene_id)
            except ProjectError as exc:
                raise GenerationError("unknown_scene", str(exc), 404)

        try:
            spec = self.registry.validate_request(
                data.model_id, data.mode, data.ratio, data.resolution,
                data.duration_seconds, data.generate_audio, len(data.reference_asset_ids),
            )
        except ProviderError as exc:
            raise GenerationError(exc.code, exc.message, 400)
        if not self.settings.use_mock_provider and spec.provider == "mock":
            raise GenerationError(
                "invalid_model", f"{spec.id} is a mock-provider model and cannot be used in live mode.", 400
            )

        # Validate + load reference assets (files must exist on disk).
        data_urls: list[tuple[str, str]] = []
        for position, asset_id in enumerate(data.reference_asset_ids):
            asset = self.references.get(asset_id)
            if asset["project_id"] != data.project_id:
                raise GenerationError(
                    "invalid_reference", f"Reference {asset_id} belongs to a different project."
                )
            roles = IMAGE_ROLES.get(data.mode, ["reference_image"])
            data_urls.append((self.references.as_data_url(asset_id), roles[position] if position < len(roles) else "reference_image"))

        # Controlled bible context selection (explicit docs only, hard cap).
        context_block = ""
        if data.bible_docs:
            try:
                context_block = self.projects.compose_bible_context(data.project_id, data.bible_docs)
            except ProjectError as exc:
                raise GenerationError("invalid_context", str(exc))
        final_prompt = prompt
        if context_block:
            final_prompt = f"{prompt}\n\n--- FILM BIBLE CONTEXT (selected) ---\n{context_block}"

        # Cost estimate — fail closed on unknown price.
        try:
            estimate = spec.estimate_cost_usd(data.resolution, data.duration_seconds)
        except ProviderError as exc:
            raise GenerationError("unknown_cost", exc.message, 422)
        reserve_amount = round(estimate * (1 + self.settings.budget_safety_margin), 4)

        # Approval gate for expensive single operations (user-side, not agent-raisable).
        if reserve_amount > self.settings.budget_approval_threshold_usd and not data.user_approved:
            raise GenerationError(
                "approval_required",
                f"This operation reserves ${reserve_amount:.2f} (above the ${self.settings.budget_approval_threshold_usd:.2f} "
                "per-operation threshold). Explicit user approval is required.",
                409,
            )

        gen_id = new_id("gen")
        now = iso(now_utc())
        self.conn.execute(
            "INSERT INTO generations (id, project_id, scene_id, model_id, provider, mode, prompt,"
            " final_prompt, ratio, resolution, duration_seconds, seed, generate_audio, status,"
            " cost_estimate_usd, context_json, user_approved, retry_of, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                gen_id, data.project_id, data.scene_id, data.model_id, self.provider.name, data.mode,
                prompt, final_prompt, data.ratio, data.resolution, data.duration_seconds, data.seed,
                int(data.generate_audio), "validating", estimate,
                json.dumps({"bible_docs": data.bible_docs}),
                int(data.user_approved), data.retry_of, now, now,
            ),
        )
        for position, asset_id in enumerate(data.reference_asset_ids):
            roles = IMAGE_ROLES.get(data.mode, ["reference_image"])
            self.conn.execute(
                "INSERT INTO generation_refs (generation_id, asset_id, position, role) VALUES (?,?,?,?)",
                (gen_id, asset_id, position, roles[position] if position < len(roles) else "reference_image"),
            )
        self._event(gen_id, "validating", f"estimate=${estimate:.4f}")

        # Budget gate — the ONLY path to a paid submission.
        try:
            reservation_id = self.budget.reserve(gen_id, reserve_amount, note=f"model={data.model_id}")
        except BudgetExceededError as exc:
            self.conn.execute(
                "UPDATE generations SET status='failed', error_code='budget_exceeded',"
                " error_message=?, updated_at=? WHERE id=?",
                (str(exc), now, gen_id),
            )
            self._event(gen_id, "failed", f"budget: {exc}")
            raise GenerationError("budget_exceeded", str(exc), 429)
        self.conn.execute(
            "UPDATE generations SET reservation_id=?, updated_at=? WHERE id=?",
            (reservation_id, now, gen_id),
        )

        request = GenerationRequest(
            model_id=data.model_id, mode=data.mode, prompt=final_prompt, ratio=data.ratio,
            resolution=data.resolution, duration_seconds=data.duration_seconds,
            generate_audio=data.generate_audio, seed=data.seed, images=data_urls,
        )
        self._set_status(gen_id, "submitting")
        self._submit(gen_id, request)
        return self.get(gen_id)

    # ----------------------------------------------------------------- submit
    def _submit(self, gen_id: str, request: GenerationRequest) -> None:
        """Hand submission to the running event loop (or run it for sync callers)."""
        self._spawn_submitter(gen_id, request)

    def _spawn_submitter(self, gen_id: str, request: GenerationRequest) -> None:
        """Run submission+polling in a dedicated background thread/event loop.

        Works from both sync route handlers (threadpool) and async contexts;
        never blocks the request. sqlite conn is check_same_thread=False and
        writes are serialized via write_tx.
        """
        import threading

        def runner():
            try:
                asyncio.run(self._submit_and_poll(gen_id, request))
            except Exception:
                logger.exception("generation worker crashed for %s", gen_id)
                try:
                    self._set_status(
                        gen_id, "needs_reconciliation",
                        error_code="worker_crash",
                        error_message="Internal worker error; reservation kept for manual reconciliation.",
                    )
                except Exception:
                    pass

        threading.Thread(target=runner, name=f"gen-{gen_id}", daemon=True).start()

    async def _submit_and_poll(self, gen_id: str, request: GenerationRequest) -> None:
        try:
            task = await self.provider.create_generation(request)
        except UncertainSubmission as exc:
            # A billing task may exist. Keep reservation; never blind-retry.
            self._set_status(
                gen_id, "needs_reconciliation",
                error_code=exc.code, error_message=exc.message,
            )
            self._event(gen_id, "needs_reconciliation", str(exc))
            return
        except ProviderError as exc:
            self._fail_with_release(gen_id, exc.code, exc.message)
            return
        now = iso(now_utc())
        self.conn.execute(
            "UPDATE generations SET provider_task_id=?, provider_status=?, status='queued',"
            " updated_at=? WHERE id=?",
            (task.provider_task_id, task.status, now, gen_id),
        )
        self.conn.commit()
        self._event(gen_id, "queued", f"provider_task={task.provider_task_id}")
        await self._poll_loop(gen_id)

    # ------------------------------------------------------------------ poll
    async def _poll_loop(self, gen_id: str, max_attempts: int | None = None) -> None:
        interval = self.settings.ark_poll_interval_seconds
        if isinstance(self.provider, MockProvider):
            interval = min(interval, 0.2)
        attempts = 0
        limit = max_attempts or 2000
        while attempts < limit:
            await asyncio.sleep(interval)
            attempts += 1
            gen = self.get(gen_id)
            if gen["status"] in TERMINAL or gen["status"] == "needs_reconciliation":
                return
            if gen["provider_task_id"] is None:
                return
            try:
                task = await self.provider.get_generation_status(gen["provider_task_id"])
            except ProviderError as exc:
                if exc.retryable and attempts < limit - 1:
                    self._event(gen_id, gen["status"], f"transient poll error: {exc.code}")
                    await asyncio.sleep(min(30, 2 ** min(attempts, 5)))
                    continue
                self._set_status(
                    gen_id, "needs_reconciliation", error_code=exc.code, error_message=exc.message
                )
                self._event(gen_id, "needs_reconciliation", str(exc))
                return
            if task.status != gen["provider_status"]:
                # Only intermediate transitions; terminal states are finalized below.
                status_map = {"queued": "queued", "running": "processing"}
                if task.status in status_map:
                    self._set_status(gen_id, status_map[task.status])
                self.conn.execute(
                    "UPDATE generations SET provider_status=? WHERE id=?", (task.status, gen_id)
                )
                self.conn.commit()
            if task.status == "succeeded":
                await self._finalize_success(gen_id, task)
                return
            if task.status in ("failed", "cancelled", "expired"):
                self._finalize_terminal_nocharge(gen_id, task.status, task)
                return
        self._set_status(
            gen_id, "needs_reconciliation",
            error_code="poll_exhausted",
            error_message="Polling budget exhausted before a terminal state; reservation kept.",
        )

    async def _finalize_success(self, gen_id: str, task) -> None:
        self._set_status(gen_id, "downloading")
        gen = self.get(gen_id)
        try:
            if not task.video_url:
                raise ProviderError("download_failed", "Provider succeeded but returned no video_url")
            data = await self.provider.download_result(task.video_url)
            if not data:
                raise ProviderError(
                    "integrity_error", "Downloaded video is empty — integrity failure, kept for reconciliation."
                )
            asset = self.references.output_asset(gen["project_id"], gen_id, data, gen["provider"])
        except ProviderError as exc:
            # File integrity problems keep the reservation (charge may exist).
            self._set_status(gen_id, "needs_reconciliation", error_code=exc.code, error_message=exc.message)
            self._event(gen_id, "needs_reconciliation", str(exc))
            return
        spec = self.registry.get(gen["model_id"])
        if task.completion_tokens:
            actual = spec.tokens_to_usd(task.completion_tokens)
        else:
            actual = gen["cost_estimate_usd"]  # conservative fallback: assume estimate
        if gen["reservation_id"]:
            self.budget.settle(gen["reservation_id"], actual)
        now = iso(now_utc())
        self.conn.execute(
            "UPDATE generations SET status='completed', output_asset_id=?, cost_actual_usd=?,"
            " completed_at=?, updated_at=?, provider_status='succeeded' WHERE id=?",
            (asset["id"], actual, now, now, gen_id),
        )
        self.conn.commit()
        self._event(gen_id, "completed", f"actual=${actual:.4f} tokens={task.completion_tokens}")
        self._mark_model_account_verified(gen["model_id"])

    def _finalize_terminal_nocharge(self, gen_id: str, provider_status: str, task) -> None:
        gen = self.get(gen_id)
        # Official docs: only successful videos are billed. failed/expired/cancelled -> release.
        if gen["reservation_id"]:
            self.budget.release(gen["reservation_id"], note=f"terminal:{provider_status}")
        message = task.error_message or f"Generation ended as {provider_status} at provider."
        self._set_status(
            gen_id,
            provider_status if provider_status in ("failed", "cancelled", "expired") else "failed",
            error_code=task.error_code or provider_status,
            error_message=message,
        )

    def _fail_with_release(self, gen_id: str, code: str, message: str) -> None:
        gen = self.get(gen_id)
        if gen["reservation_id"]:
            self.budget.release(gen["reservation_id"], note=f"submit_failed:{code}")
        self._set_status(gen_id, "failed", error_code=code, error_message=message)
        self._event(gen_id, "failed", f"{code}: {message}")

    # ----------------------------------------------------------------- actions
    async def cancel(self, gen_id: str) -> dict:
        gen = self.get(gen_id)
        if gen["status"] in TERMINAL:
            raise GenerationError("invalid_state", f"Generation already {gen['status']}.")
        if not gen["provider_task_id"]:
            # Not submitted yet (or uncertain) — local cancel; reservation handling:
            if gen["status"] == "needs_reconciliation":
                raise GenerationError(
                    "needs_reconciliation",
                    "Outcome unknown at provider; reservation is kept. Resolve via reconcile.",
                    409,
                )
            if gen["reservation_id"]:
                self.budget.release(gen["reservation_id"], note="cancelled_before_submit")
            self._set_status(
                gen_id, "cancelled", error_code="cancelled_local",
                error_message="Cancelled locally before provider submission. Remote charge not possible.",
            )
            return self.get(gen_id)
        try:
            await self.provider.cancel_generation(gen["provider_task_id"])
        except ProviderError as exc:
            # Cannot guarantee remote cancellation — do not fake it.
            raise GenerationError(
                "cancel_failed",
                f"Provider refused cancellation ({exc.code}). The remote task may still run and bill; "
                "polling continues until a terminal provider state.",
                409,
            )
        task = await self.provider.get_generation_status(gen["provider_task_id"])
        if task.status in ("failed", "cancelled", "expired"):
            self._finalize_terminal_nocharge(gen_id, task.status, task)
        else:
            self._event(gen_id, gen["status"], "cancel requested at provider; awaiting terminal state")
        return self.get(gen_id)

    async def reconcile(self, gen_id: str) -> dict:
        """Re-check a needs_reconciliation generation against the provider."""
        gen = self.get(gen_id)
        if gen["status"] != "needs_reconciliation":
            raise GenerationError("invalid_state", "Only needs_reconciliation generations can be reconciled.")
        if not gen["provider_task_id"]:
            raise GenerationError(
                "uncertain_submission",
                "No provider task id was persisted before the failure. The submission outcome is unknown; "
                "check the BytePlus console task list (free) and either delete this record or retry as a new generation. "
                "The budget reservation stays held for safety.",
                409,
            )
        task = await self.provider.get_generation_status(gen["provider_task_id"])
        if task.status == "succeeded":
            await self._finalize_success(gen_id, task)
        elif task.status in ("failed", "cancelled", "expired"):
            self._finalize_terminal_nocharge(gen_id, task.status, task)
        else:
            self._set_status(gen_id, "queued" if task.status == "queued" else "processing")
            self.conn.execute(
                "UPDATE generations SET provider_status=? WHERE id=?", (task.status, gen_id)
            )
            self.conn.commit()
            self._spawn_submitter_from_existing(gen_id)
        return self.get(gen_id)

    def _spawn_submitter_from_existing(self, gen_id: str) -> None:
        """Recovery path: task id already persisted — NEVER resubmit (charge risk). Poll only."""
        self._spawn(self._poll_loop(gen_id))

    def _spawn(self, coro) -> None:
        import threading

        def runner():
            try:
                asyncio.run(coro)
            except Exception:
                logger.exception("generation worker crashed for coro")
                try:
                    self._event("", "worker_crash", "poller crashed")
                except Exception:
                    pass

        threading.Thread(target=runner, daemon=True).start()

    def retry(self, gen_id: str, user_approved: bool = False) -> dict:
        gen = self.get(gen_id)
        if gen["status"] not in TERMINAL | {"needs_reconciliation"}:
            raise GenerationError("invalid_state", "Only terminal generations can be retried.")
        if gen["status"] == "needs_reconciliation" and not gen["provider_task_id"]:
            raise GenerationError(
                "uncertain_submission",
                "Original submission outcome unknown — resolve it before retrying (duplicate charge risk).",
                409,
            )
        refs = [
            r["asset_id"]
            for r in self.conn.execute(
                "SELECT asset_id FROM generation_refs WHERE generation_id=? ORDER BY position", (gen_id,)
            ).fetchall()
        ]
        context = json.loads(gen["context_json"] or "{}")
        return self.create(
            CreateGenerationInput(
                project_id=gen["project_id"], scene_id=gen["scene_id"], model_id=gen["model_id"],
                mode=gen["mode"], prompt=gen["prompt"], ratio=gen["ratio"], resolution=gen["resolution"],
                duration_seconds=gen["duration_seconds"], generate_audio=bool(gen["generate_audio"]),
                seed=gen["seed"], reference_asset_ids=refs,
                bible_docs=context.get("bible_docs", []), user_approved=user_approved, retry_of=gen_id,
            )
        )

    def delete(self, gen_id: str, delete_files: bool = True) -> None:
        gen = self.get(gen_id)
        if gen["status"] in ("submitting", "queued", "processing", "downloading"):
            raise GenerationError(
                "invalid_state",
                "Generation is in flight. Cancel it first (remote task may still bill).",
                409,
            )
        if gen["status"] == "needs_reconciliation":
            raise GenerationError(
                "needs_reconciliation",
                "Outcome unresolved; deleting would orphan a held budget reservation.",
                409,
            )
        if delete_files and gen["output_asset_id"]:
            try:
                path = self.settings.resolved_storage_root() / "generations" / self.references.get(gen["output_asset_id"])["filename"]
                path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Could not remove output file for %s", gen_id)
        self.conn.execute("DELETE FROM generations WHERE id=?", (gen_id,))
        self.conn.commit()

    # ------------------------------------------------------------------ recovery
    def recover_unfinished(self) -> dict:
        """Startup recovery: resume polling for in-flight tasks; flag uncertain submissions."""
        recovered, flagged = [], []
        rows = self.conn.execute(
            "SELECT id, status, provider_task_id FROM generations"
            " WHERE status IN ('submitting','queued','processing','downloading')"
        ).fetchall()
        for row in rows:
            if row["provider_task_id"]:
                self._event(row["id"], row["status"], "recovered after restart; resuming poll")
                self._spawn_submitter_from_existing(row["id"])
                recovered.append(row["id"])
            else:
                # Submission interrupted before task id persisted — outcome unknown.
                self._set_status(
                    row["id"], "needs_reconciliation",
                    error_code="interrupted_submission",
                    error_message="Application restarted before the provider task id was persisted; "
                    "submission outcome unknown, reservation held.",
                )
                flagged.append(row["id"])
        return {"resumed": recovered, "flagged": flagged}

    # ------------------------------------------------------------------ helpers
    def _set_status(self, gen_id: str, status: str, error_code: str | None = None, error_message: str | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"Invalid status {status}")
        now = iso(now_utc())
        self.conn.execute(
            "UPDATE generations SET status=?, error_code=?, error_message=?, updated_at=? WHERE id=?",
            (status, error_code, error_message, now, gen_id),
        )
        self.conn.commit()
        self._event(gen_id, status, error_message or "")

    def _event(self, gen_id: str, status: str, detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO generation_events (generation_id, status, detail, created_at) VALUES (?,?,?,?)",
            (gen_id, status, detail[:1000], iso(now_utc())),
        )
        self.conn.commit()

    def _mark_model_account_verified(self, model_id: str) -> None:
        path = self.settings.models_config_path
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        for m in raw.get("models", []):
            if m["id"] == model_id:
                if not m.get("account_verified"):
                    m["account_verified"] = True
                    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
                return

    def get(self, gen_id: str) -> dict:
        row = self.conn.execute("SELECT * FROM generations WHERE id = ?", (gen_id,)).fetchone()
        if row is None:
            raise GenerationError("not_found", f"Generation {gen_id} not found", 404)
        d = dict(row)
        d["generate_audio"] = bool(d["generate_audio"])
        d["user_approved"] = bool(d["user_approved"])
        refs = self.conn.execute(
            "SELECT asset_id, position, role FROM generation_refs WHERE generation_id=? ORDER BY position",
            (gen_id,),
        ).fetchall()
        d["reference_assets"] = [dict(r) for r in refs]
        d["events"] = [
            dict(r)
            for r in self.conn.execute(
                "SELECT status, detail, created_at FROM generation_events WHERE generation_id=?"
                " ORDER BY id",
                (gen_id,),
            ).fetchall()
        ]
        return d

    def list(
        self,
        project_id: str | None = None,
        scene_id: str | None = None,
        model_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses, params = ["1=1"], []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if scene_id:
            clauses.append("scene_id = ?")
            params.append(scene_id)
        if model_id:
            clauses.append("model_id = ?")
            params.append(model_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        params.extend([limit, offset])
        rows = self.conn.execute(
            f"SELECT * FROM generations WHERE {' AND '.join(clauses)}"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["generate_audio"] = bool(d["generate_audio"])
            d.pop("final_prompt", None)
            d["events"] = []
            d["reference_assets"] = []
            out.append(d)
        return out

    def output_path(self, gen_id: str) -> Path:
        gen = self.get(gen_id)
        if not gen["output_asset_id"]:
            raise GenerationError("not_found", "No output file for this generation", 404)
        asset = self.references.get(gen["output_asset_id"])
        from app.services.paths import safe_join as _sj

        return _sj(self.settings.resolved_storage_root() / "generations", asset["filename"])
