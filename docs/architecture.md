# Architecture

## Overview

```
┌──────────────────────────┐        ┌───────────────────────────────┐
│ apps/web (Next.js :3210) │  HTTP  │ apps/api (FastAPI :8000)      │
│ React 19 · TS · Tailwind │ ─────▶ │ /api/v1 … (CORS: one origin)  │
│ workspace · bible ·      │        │                               │
│ history · budget UI      │        │ services ──▶ providers ───────┼──▶ BytePlus ModelArk
└──────────────────────────┘        │    │         (ark | mock)     │    ark.ap-southeast…
                                    │    ▼                          │    (backend only;
                                    │ budget.py (atomic reserve/    │     key never in browser)
                                    │             settle/release)   │
                                    │    ▼                          │
                                    │ SQLite (WAL) + filesystem     │
                                    └───────────────────────────────┘
```

## Generation flow (the only path to a paid request)

1. `POST /api/v1/generations` → `GenerationService.create()`
2. Validate against the **model registry** (`data/config/models.json`): mode, ratio, resolution,
   duration, audio, reference count. Unknown/unsupported → rejected (fail closed, no invented caps).
3. Load reference assets (project-scoped, validated on upload) → base64 data URLs with roles
   (`first_frame`, `last_frame`, `reference_image`).
4. Optional **bible context**: only explicitly selected docs, hard char cap, appended to the prompt;
   both raw prompt and final prompt persisted, selections recorded in `context_json`.
5. **Cost estimate** from verified per-second prices; unknown price → 422 refused.
6. **Approval gate**: reservation above the per-operation threshold requires `user_approved=true`.
7. **BudgetService.reserve()** — atomic (BEGIN IMMEDIATE + process lock); checks charges in rolling
   24 h/7 d **plus all active reservations** against both limits.
8. Persist generation row (`submitting`) → background worker submits via the provider adapter.
9. Provider task id persisted immediately; worker polls (bounded), records transitions.
10. Success → download → verify non-empty → store under `data/generations/` → settle budget with
    actual `usage.completion_tokens × token price`.
11. Confirmed no-charge terminals (`failed`/`cancelled`/`expired`, pre-submission errors) → release.
12. **Uncertain submissions (timeouts) never blind-retry**: status `needs_reconciliation`, reservation
    held until `POST /generations/{id}/reconcile` resolves it (or the user resolves via console).

## Module boundaries

- `app/providers/` — everything BytePlus-specific. `ark.py` behind the `VideoProvider` protocol
  (`base.py`); `mock.py` for tests; `registry.py` loads/validates models. Future providers implement
  the protocol; nothing else in the codebase calls the provider HTTP API.
- `app/services/budget.py` — the only spending gate. Single owner; tested for concurrency,
  restarts, windows, boundaries.
- `app/services/generations.py` — lifecycle orchestration + recovery. Workers are daemon threads
  with their own event loops; sqlite access is serialized.
- `app/services/projects.py` — projects/scenes/**bible** (filesystem source of truth under
  `projects/<slug>/bible/`, templates from `bible-templates/`); `compose_bible_context()` is the
  controlled context selector.
- `app/services/references.py` — upload validation (MIME sniff via Pillow, size, 300–6000 px,
  aspect 0.4–2.5), safe ID-based filenames, roles/entity links.
- `app/api/` — thin HTTP routes; no business logic.
- `app/db.py` — connection + versioned SQL migrations (`app/migrations/*.sql`, tracked in
  `schema_migrations`).

## Persistence model

DB holds structured state (projects, scenes, assets, generations, refs, events, charges,
reservations, settings). Large media lives on disk with app-generated names; the DB references it.
Bible content lives in markdown files (canonical), not duplicated in the DB.

## Restart recovery (`recover_unfinished`, runs at startup)

- In-flight rows **with** a persisted provider task id → resume **polling only** (never resubmit —
  duplicate charge risk).
- Rows stuck in `submitting` **without** a task id → `needs_reconciliation`, reservation held.

## Frontend

Next.js App Router; all pages are client components against the REST API (`src/lib/api.ts`). UI
capabilities come from `GET /capabilities` (registry-driven) — the frontend never hardcodes model
abilities. A persistent badge distinguishes **MOCK MODE** from **LIVE**. Cost/budget logic shared in
`src/lib/generate-logic.ts` (pure, unit-tested).
