# AI Film Studio

A local-first AI film production workspace. Generate video shots with **Seedance via BytePlus
ModelArk**, organized into persistent film projects with a structured **film bible**, reference
assets, full generation history, and strict **application-side spending controls**
($7 / rolling 24 h, $50 / rolling 7 d).

Single-user, local machine only: the backend binds to `127.0.0.1`, the BytePlus API key never
leaves the backend process, and everything (projects, bible, videos, database) is stored locally.

## Quick start

Prerequisites: Python 3.12+, Node.js 20+, uv. Optional: FFmpeg (not required).

```bash
# 1. Configure (mock mode needs no credentials)
cp .env.example .env

# 2. Backend  → http://127.0.0.1:8000
cd apps/api
uv venv .venv && uv pip install -e ".[dev]" pytest pytest-asyncio
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. Frontend → http://localhost:3210
cd apps/web
npm install
npm run dev
```

Open **http://localhost:3210** (the browser header must say **MOCK MODE** — simulated
generations, zero cost, no API key needed).

## Going live with BytePlus Seedance

1. Create a BytePlus account, top up (Seedance 2.x requires balance > $30 or a resource pack), and
   create a ModelArk API key.
2. In `.env`: set `ARK_API_KEY`, set `ARK_MODEL_ID` (see below), set `USE_MOCK_PROVIDER=false`.
3. Restart the backend. The header switches to **LIVE**; every generation is a paid request.

**Finding your model ID** — models are region/account gated, so never copy IDs from blog posts:

```bash
curl -s "$ARK_BASE_URL/contents/generations/tasks?page_size=5" \
  -H "Authorization: Bearer $ARK_API_KEY"
```

Read the `model` field on any task you actually ran. Registered IDs (verified pricing, see
`docs/research/byteplus-api-findings.md`): `dreamina-seedance-2-5-260628`,
`dreamina-seedance-2-0-260128`, `dreamina-seedance-2-0-fast-260128`,
`dreamina-seedance-2-0-mini-260615`, `seedance-1-0-pro-250528`, `seedance-1-0-pro-fast-251015`.
The UI marks a model *account-verified* only after your first successful generation with it.

## What's inside

- **Projects & film bible** — every project gets a real `bible/` (film-bible.md canonical +
  world/characters/visual-style/continuity/locations/production-rules/scene-index/reference-index/
  changelog) seeded with explicit `[TO FILL]` placeholders — never invented lore.
- **Generation workspace** — prompt composer, model/mode/ratio/resolution/duration selectors driven
  by verified capabilities, ordered reference images (`@Image1` mentions), selected bible context,
  cost estimate, remaining budget, approval gate for expensive shots.
- **History** — every generation with prompt, model, provider task id, estimated vs actual cost,
  video preview/download, retry-as-new, delete; needs-reconciliation states are explicit.
- **Budget manager** — rolling windows, atomic reservations counted in both windows, restart-safe,
  fail-closed on unknown cost, no API to raise limits.
- **Mock provider** — full lifecycle simulation (success, failure, rate limit, uncertain submission,
  expired, missing file) so everything is testable without paid calls.

## Tests, checks, builds

```bash
cd apps/api && .venv/bin/python -m pytest    # 57 tests — budget, providers, lifecycle, recovery, security
cd apps/web && npm test && npm run typecheck && npm run build
```

## Documentation

| Doc | Contents |
|---|---|
| `docs/architecture.md` | system design, data flow, module boundaries |
| `docs/setup.md` | install, configuration reference, troubleshooting |
| `docs/security.md` | threat model and controls |
| `docs/api-integration.md` | BytePlus integration details + local API reference |
| `docs/operations.md` | backup, recovery, data locations |
| `docs/research/` | open-source evaluation, verified API findings |
| `docs/agents/` | OpenCode agent team, permissions |
| `AGENTS.md` | rules every coding agent must follow |

## Data locations

- `data/database/studio.db` — SQLite (WAL)
- `data/generations/` — generated videos (app-managed filenames)
- `data/config/models.json` — model registry (edit to add models/durations; keep pricing verified)
- `projects/<slug>/` — project.json, bible/, references/, scenes/

All of `data/` and `projects/` are git-ignored. Back them up together (see `docs/operations.md`).

## Budget policy

Application-side limits: **$7 / rolling 24 h** and **$50 / rolling 7 d**, enforced before every paid
request (charges in window + all active reservations). Reservations survive restarts. Unknown cost
fails closed. Failed generations release their reservation only on a confirmed terminal provider
state. Raising a limit is a deliberate `.env` edit by you — never an agent or API call.
# Sloppio
