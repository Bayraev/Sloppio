"""Application settings — read from environment / .env at repo root."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # BytePlus ModelArk
    ark_api_key: str = ""
    ark_base_url: str = "https://ark.ap-southeast.bytepluses.com/api/v3"
    ark_model_id: str = ""
    ark_poll_interval_seconds: float = 5.0
    ark_request_timeout_seconds: float = 30.0
    use_mock_provider: bool = True

    # Storage
    storage_root: Path = REPO_ROOT / "data"
    projects_root: Path = REPO_ROOT / "projects"

    # Server
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    frontend_origin: str = "http://localhost:3210"

    # Uploads
    max_upload_size_mb: int = 30

    # Budget policy (application-side; agents must never raise these)
    budget_limit_24h_usd: float = 7.0
    budget_limit_7d_usd: float = 50.0
    budget_safety_margin: float = 0.10
    budget_approval_threshold_usd: float = 2.0

    @property
    def db_path(self) -> Path:
        return self.storage_root / "database" / "studio.db"

    @property
    def generations_dir(self) -> Path:
        return self.storage_root / "generations"

    @property
    def models_config_path(self) -> Path:
        return self.storage_root / "config" / "models.json"

    @property
    def allowed_origins(self) -> list[str]:
        return [self.frontend_origin]

    def resolved_projects_root(self) -> Path:
        p = Path(os.path.expanduser(str(self.projects_root)))
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()

    def resolved_storage_root(self) -> Path:
        p = Path(os.path.expanduser(str(self.storage_root)))
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()

    def missing_settings(self) -> list[str]:
        missing = []
        if not self.use_mock_provider:
            if not self.ark_api_key:
                missing.append("ARK_API_KEY")
            if not self.ark_model_id:
                missing.append("ARK_MODEL_ID")
        return missing


settings = Settings()
