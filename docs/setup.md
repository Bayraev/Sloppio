# Setup

## Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.12+ (3.14 tested) | backend |
| uv | any | venv/dependency management |
| Node.js | 20+ (22 tested) | frontend |
| FFmpeg | optional | not required for v1 (no transcoding) |

## Install

```bash
cp .env.example .env

# Backend
cd apps/api
uv venv .venv
uv pip install -e ".[dev]" pytest pytest-asyncio

# Frontend
cd ../web
npm install
```

## Run (development)

Two terminals:

```bash
# terminal 1 — API on 127.0.0.1:8000
cd apps/api && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# terminal 2 — web on localhost:3210
cd apps/web && npm run dev
```

Open http://localhost:3210 — use `localhost`, not `127.0.0.1` (CORS matches the configured origin
exactly). Header shows **API OFFLINE** if the backend is down or opened under the wrong host.

## Configuration reference (`.env`)

| Variable | Default | Notes |
|---|---|---|
| `ARK_API_KEY` | — | required in live mode; backend-only |
| `ARK_BASE_URL` | `https://ark.ap-southeast.bytepluses.com/api/v3` | Asia Pacific region |
| `ARK_MODEL_ID` | — | required in live mode; verify against your account |
| `ARK_POLL_INTERVAL_SECONDS` | `5` | task polling |
| `ARK_REQUEST_TIMEOUT_SECONDS` | `30` | per provider request |
| `USE_MOCK_PROVIDER` | `true` | mock mode: no key, no cost, simulated lifecycle |
| `STORAGE_ROOT` | `./data` | DB + generated videos |
| `PROJECTS_ROOT` | `./projects` | project folders |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8000` | keep localhost binding |
| `FRONTEND_ORIGIN` | `http://localhost:3210` | the only CORS origin |
| `MAX_UPLOAD_SIZE_MB` | `30` | per reference image |
| `BUDGET_LIMIT_24H_USD` | `7.0` | rolling window; change deliberately, never via agents |
| `BUDGET_LIMIT_7D_USD` | `50.0` | rolling window |
| `BUDGET_SAFETY_MARGIN` | `0.10` | reservation = estimate × (1+margin) |
| `BUDGET_APPROVAL_THRESHOLD_USD` | `2.0` | per-op explicit approval above this |

## Model registry (`data/config/models.json`)

Model IDs, capabilities, and per-second prices verified from the official pricing page
(`docs/research/byteplus-api-findings.md`). `account_verified` flips automatically after the first
successful generation. To add a model or durations: edit the JSON with **verified** values and
restart — the app fails closed on models/resolutions without verified pricing.

## Tests / checks

```bash
cd apps/api && .venv/bin/python -m pytest
cd apps/web && npm test && npm run typecheck && npm run build
```

## Production build (still local usage)

```bash
cd apps/web && npm run build && npm start
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `API OFFLINE` in header | backend down, or opened `127.0.0.1:3210` — use `localhost:3210` |
| Backend refuses to start in live mode | `ARK_API_KEY` / `ARK_MODEL_ID` missing — fill `.env` or set `USE_MOCK_PROVIDER=true` |
| `model_unavailable` on generate | model not activated for the account (balance > $30 / pack) or wrong ID — run the curl from README |
| `budget_exceeded` | rolling limit reached; check Budget page for held reservations |
| `needs_reconciliation` | submission outcome unknown — reservation held; use Details → reconcile after checking the console task list |
