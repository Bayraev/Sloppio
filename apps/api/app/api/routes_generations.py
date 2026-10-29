"""Generation and budget routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.services.generations import CreateGenerationInput, GenerationError, GenerationService

router = APIRouter(tags=["generations"])


def _svc(request: Request) -> GenerationService:
    return request.app.state.studio.generations


def _err(exc: GenerationError):
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)})


@router.post("/generations", status_code=201)
def create_generation(request: Request, body: dict):
    required = ("project_id", "model_id", "mode", "prompt", "ratio", "resolution", "duration_seconds")
    missing = [k for k in required if body.get(k) in (None, "")]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing fields: {', '.join(missing)}")
    data = CreateGenerationInput(
        project_id=body["project_id"],
        scene_id=body.get("scene_id"),
        model_id=body["model_id"],
        mode=body["mode"],
        prompt=body["prompt"],
        ratio=body["ratio"],
        resolution=body["resolution"],
        duration_seconds=int(body["duration_seconds"]),
        generate_audio=bool(body.get("generate_audio", False)),
        seed=body.get("seed"),
        reference_asset_ids=body.get("reference_asset_ids", []) or [],
        bible_docs=body.get("bible_docs", []) or [],
        user_approved=bool(body.get("user_approved", False)),
    )
    try:
        return _svc(request).create(data)
    except GenerationError as exc:
        raise _err(exc)


@router.get("/generations")
def list_generations(
    request: Request,
    project_id: str | None = None,
    scene_id: str | None = None,
    model_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    limit = max(1, min(limit, 100))
    return {"generations": _svc(request).list(project_id, scene_id, model_id, status, limit, offset)}


@router.get("/generations/{gid}")
def get_generation(request: Request, gid: str):
    try:
        return _svc(request).get(gid)
    except GenerationError as exc:
        raise _err(exc)


@router.post("/generations/{gid}/retry", status_code=201)
def retry_generation(request: Request, gid: str, body: dict | None = None):
    try:
        return _svc(request).retry(gid, bool((body or {}).get("user_approved", False)))
    except GenerationError as exc:
        raise _err(exc)


@router.post("/generations/{gid}/cancel")
async def cancel_generation(request: Request, gid: str):
    try:
        return await _svc(request).cancel(gid)
    except GenerationError as exc:
        raise _err(exc)


@router.post("/generations/{gid}/reconcile")
async def reconcile_generation(request: Request, gid: str):
    try:
        return await _svc(request).reconcile(gid)
    except GenerationError as exc:
        raise _err(exc)


@router.delete("/generations/{gid}")
def delete_generation(request: Request, gid: str):
    try:
        _svc(request).delete(gid)
        return {"deleted": gid}
    except GenerationError as exc:
        raise _err(exc)


@router.get("/generations/{gid}/video")
def generation_video(request: Request, gid: str):
    try:
        gen = _svc(request).get(gid)
        path = _svc(request).output_path(gid)
        return FileResponse(path, media_type="video/mp4", filename=f"{gid}{'.mock' if gen['provider'] == 'mock' else ''}.mp4")
    except GenerationError as exc:
        raise _err(exc)


# --- budget -------------------------------------------------------------------
@router.get("/budget")
def budget_status(request: Request):
    state = request.app.state.studio
    snap = state.budget.snapshot()
    data = snap.as_dict()
    data["limits"]["approval_threshold_usd"] = state.settings.budget_approval_threshold_usd
    data["policy"] = {
        "safety_margin": state.settings.budget_safety_margin,
        "note": "Application-side controls. Limits change only with explicit user approval.",
    }
    data["active_reservations"] = state.budget.active_reservations()
    data["recent_charges"] = state.budget.recent_charges()
    return data
