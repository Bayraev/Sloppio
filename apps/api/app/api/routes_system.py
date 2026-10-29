"""System routes: health, capabilities, models, provider check."""
from __future__ import annotations

from fastapi import Request, APIRouter, HTTPException

from app.providers.base import ProviderError

router = APIRouter(tags=["system"])


def _state(request: Request):
    return request.app.state.studio


@router.get("/health")
def health(request: Request):
    state = _state(request)
    return {
        "status": "ok",
        "provider_mode": "mock" if state.settings.use_mock_provider else "seedance",
        "missing_settings": state.settings.missing_settings(),
        "version": "0.1.0",
    }


@router.get("/capabilities")
def capabilities(request: Request):
    state = _state(request)
    provider_mode = "mock" if state.settings.use_mock_provider else "seedance"
    models = [
        {
            "id": m.id,
            "display_name": m.display_name,
            "provider": m.provider,
            "modes": list(m.modes),
            "resolutions": list(m.resolutions),
            "ratios": list(m.ratios),
            "durations": list(m.durations),
            "max_reference_images": m.max_reference_images,
            "supports_audio": m.supports_audio,
            "verified": m.verified,
            "account_verified": m.account_verified,
            "pricing": {"per_second_usd": m.per_second_usd},
        }
        for m in state.registry.list()
        if state.settings.use_mock_provider or m.provider != "mock"
    ]
    return {
        "provider_mode": provider_mode,
        "models": models,
        "upload": {
            "max_size_mb": state.settings.max_upload_size_mb,
            "allowed_mime": ["image/jpeg", "image/png", "image/webp"],
            "min_side": 300,
            "max_side": 6000,
        },
        "budget": state.budget.snapshot().as_dict(),
    }


@router.post("/provider/check")
async def provider_check(request: Request):
    """Free read-only check: lists model IDs seen on recent provider tasks."""
    state = _state(request)
    if state.settings.use_mock_provider:
        return {"mode": "mock", "recent_models": ["mock-seedance"], "note": "Mock provider active; no network call made."}
    try:
        models = await state.provider.list_recent_models()
        return {"mode": "seedance", "recent_models": models}
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail={"code": exc.code, "message": exc.message})
