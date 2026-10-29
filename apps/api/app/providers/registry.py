"""Model registry — typed access to data/config/models.json (with packaged default)."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.providers.base import ProviderError

PACKAGED = Path(__file__).parent.parent / "data" / "models.json"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    display_name: str
    provider: str
    modes: tuple[str, ...]
    resolutions: tuple[str, ...]
    ratios: tuple[str, ...]
    durations: tuple[int, ...]
    max_reference_images: int
    supports_audio: bool
    verified: bool
    per_second_usd: dict[str, float]
    token_price_per_million_usd: float
    account_verified: bool = False

    def estimate_cost_usd(self, resolution: str, duration_seconds: int) -> float:
        price = self.per_second_usd.get(resolution)
        if price is None or price <= 0:
            raise ProviderError(
                "unknown_cost",
                f"No verified per-second price for {self.id} at {resolution}; refusing to estimate.",
            )
        return round(price * duration_seconds, 4)

    def tokens_to_usd(self, tokens: int) -> float:
        return round(tokens * self.token_price_per_million_usd / 1_000_000, 4)


class ModelRegistry:
    def __init__(self, models: list[ModelSpec]) -> None:
        self._models = {m.id: m for m in models}

    @classmethod
    def load(cls, settings: Settings) -> "ModelRegistry":
        path = settings.models_config_path
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PACKAGED, path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        specs = []
        for m in raw.get("models", []):
            pricing = m.get("pricing") or {}
            specs.append(
                ModelSpec(
                    id=m["id"],
                    display_name=m.get("display_name", m["id"]),
                    provider=m.get("provider", "ark"),
                    modes=tuple(m.get("modes", [])),
                    resolutions=tuple(m.get("resolutions", [])),
                    ratios=tuple(m.get("ratios", [])),
                    durations=tuple(m.get("durations", [])),
                    max_reference_images=int(m.get("max_reference_images", 1)),
                    supports_audio=bool(m.get("supports_audio", False)),
                    verified=bool(m.get("verified", False)),
                    per_second_usd={k: float(v) for k, v in (pricing.get("per_second_usd") or {}).items()},
                    token_price_per_million_usd=float(pricing.get("token_price_per_million_usd", 0)),
                    account_verified=bool(m.get("account_verified", False)),
                )
            )
        return cls(specs)

    def get(self, model_id: str) -> ModelSpec:
        spec = self._models.get(model_id)
        if spec is None:
            raise ProviderError("unknown_model", f"Model {model_id!r} is not in the registry.")
        return spec

    def list(self) -> list[ModelSpec]:
        return list(self._models.values())

    def validate_request(
        self,
        model_id: str,
        mode: str,
        ratio: str,
        resolution: str,
        duration: int,
        generate_audio: bool,
        image_count: int,
    ) -> ModelSpec:
        spec = self.get(model_id)
        if mode not in spec.modes:
            raise ProviderError(
                "unsupported_mode", f"{spec.id} does not support mode {mode} (verified modes: {', '.join(spec.modes)})."
            )
        if ratio not in spec.ratios:
            raise ProviderError("unsupported_ratio", f"{spec.id} does not list ratio {ratio}.")
        if resolution not in spec.resolutions:
            raise ProviderError("unsupported_resolution", f"{spec.id} does not list resolution {resolution}.")
        if duration not in spec.durations:
            raise ProviderError(
                "unsupported_duration", f"{spec.id} does not list duration {duration}s (registry: {spec.durations})."
            )
        if generate_audio and not spec.supports_audio:
            raise ProviderError("unsupported_audio", f"{spec.id} does not have verified audio support.")
        if mode == "text_to_video" and image_count:
            raise ProviderError("invalid_request", "text_to_video must not include reference images.")
        if mode in ("image_to_video",) and image_count != 1:
            raise ProviderError("invalid_request", "image_to_video (first frame) requires exactly 1 image.")
        if mode == "first_last_frame" and image_count != 2:
            raise ProviderError("invalid_request", "first_last_frame requires exactly 2 images.")
        if mode == "reference_to_video" and not 1 <= image_count <= spec.max_reference_images:
            raise ProviderError(
                "invalid_request",
                f"reference_to_video requires 1..{spec.max_reference_images} images for {spec.id}.",
            )
        return spec
