"""FastAPI application factory."""
from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_generations, routes_projects, routes_system
from app.config import Settings, settings
from app.db import apply_migrations, connect
from app.providers.ark import ArkProvider
from app.providers.base import ProviderError
from app.providers.mock import MockProvider
from app.providers.registry import ModelRegistry
from app.services.budget import BudgetService
from app.services.generations import GenerationService
from app.services.projects import ProjectService
from app.services.references import ReferenceService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
# Redact secrets from all logs.
_SECRET_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_KEY_RE = re.compile(r"(ark_api_key[=:\s]+)\S+", re.IGNORECASE)


class _SecretRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SECRET_RE.sub(r"\1[REDACTED]", record.msg)
            record.msg = _KEY_RE.sub(r"\1[REDACTED]", record.msg)
        return True


for _logger in (logging.getLogger(), *tuple(logging.getLogger(n) for n in ("uvicorn", "uvicorn.access", "studio", "httpx"))):
    _logger.addFilter(_SecretRedactingFilter())


class StudioState:
    def __init__(self, settings: Settings, conn, registry, budget, projects, references, generations, provider):
        self.settings = settings
        self.conn = conn
        self.registry = registry
        self.budget = budget
        self.projects = projects
        self.references = references
        self.generations = generations
        self.provider = provider


def build_state(settings: Settings) -> StudioState:
    settings.resolved_storage_root().mkdir(parents=True, exist_ok=True)
    settings.resolved_projects_root().mkdir(parents=True, exist_ok=True)
    settings.generations_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings)
    apply_migrations(conn)
    registry = ModelRegistry.load(settings)
    if settings.use_mock_provider:
        provider = MockProvider(state_file=settings.resolved_storage_root() / "mock_provider_state.json")
    else:
        missing = settings.missing_settings()
        if missing:
            raise RuntimeError(
                "Real provider mode requires " + ", ".join(missing)
                + ". Fill .env or set USE_MOCK_PROVIDER=true. Failing fast — no generation is possible."
            )
        provider = ArkProvider(settings)
    budget = BudgetService(conn, settings.budget_limit_24h_usd, settings.budget_limit_7d_usd)
    projects = ProjectService(conn, settings.resolved_projects_root())
    references = ReferenceService(conn, settings, projects)
    generations = GenerationService(conn, settings, registry, budget, projects, references, provider)
    return StudioState(settings, conn, registry, budget, projects, references, generations, provider)


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = app.state.studio
    result = state.generations.recover_unfinished()
    if result["resumed"] or result["flagged"]:
        logging.getLogger("studio").info(
            "Recovery: resumed=%s flagged=%s", len(result["resumed"]), len(result["flagged"])
        )
    yield
    await state.provider.aclose()


def create_app(settings_: Settings | None = None) -> FastAPI:
    cfg = settings_ or settings
    state = build_state(cfg)
    app = FastAPI(title="AI Film Studio API", version="0.1.0", lifespan=lifespan)
    app.state.studio = state
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins,  # single configured frontend origin only
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_system.router, prefix="/api/v1")
    app.include_router(routes_projects.router, prefix="/api/v1")
    app.include_router(routes_generations.router, prefix="/api/v1")
    return app


app = create_app()
