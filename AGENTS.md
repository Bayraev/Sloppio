# AGENTS.md — AI Film Studio

Local-first AI film production workspace. First release: **Seedance via BytePlus ModelArk only**,
persistent film projects, reference assets, a structured film bible, generation history, and strict
application-side spending controls.

Every coding agent working in this repository MUST follow these rules. Project agents are defined in
`.opencode/agents/` (see `docs/agents/agent-team.md` for the coordination protocol).

## Architecture map

```
apps/api   FastAPI backend (Python 3.12+)
           app/providers/    VideoProvider protocol — ark.py (BytePlus), mock.py, registry.py (models)
           app/services/     budget.py (spending controls), generations.py (lifecycle),
                             projects.py (projects/bible/scenes), references.py (uploads), paths.py
           app/api/          HTTP routes (/api/v1)
           app/migrations/   versioned SQL migrations
           tests/            pytest (mock provider only — never paid calls)
apps/web   Next.js 15 + React 19 + TypeScript + Tailwind v4 frontend (port 3210)
data/      SQLite DB, generated videos, config/models.json (model registry)  [never committed]
projects/  One folder per film: project.json, bible/, references/, scenes/, generations/  [never committed]
docs/      architecture, setup, security, api-integration, operations, research, agents
bible-templates/  seed templates for every new project bible
```

## Development & testing commands

```bash
# Backend (apps/api) — venv at .venv (uv-managed)
cd apps/api && .venv/bin/python -m pytest          # tests (mock provider, no paid calls)
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000   # run backend

# Frontend (apps/web)
cd apps/web
npm run dev        # dev server on :3210
npm test           # vitest
npm run typecheck  # tsc --noEmit
npm run build      # production build
```

## Scope

- Current release: a local single-user AI video studio with Seedance as the only provider.
- Do NOT introduce other providers, image/audio models, multi-user, cloud deployment, containers,
  queues, or extra databases without an explicit task.
- Prefer small, reviewable changes. Inspect the repo and read the relevant implementation before editing.
- Preserve existing functionality; avoid duplicate modules and competing sources of truth.
- Update docs (architecture, api-integration, registry) whenever configuration or API contracts change.

## Secrets

- Never request, print, or log API keys. Never commit `.env`, databases, reference images, or generated media.
- Secrets never go into prompts, browser bundles (NEXT_PUBLIC_*), agent configuration, or docs. Use placeholders.
- Credentials live only in `.env` (backend) — the frontend never sees the BytePlus key.

## Cost controls (hard invariants)

- Policy: **$7 per rolling 24 h, $50 per rolling 7 d** — application-side, enforced by
  `app/services/budget.py`. These are the only limits; agents must NEVER raise or bypass them.
- Every paid request passes through the central BudgetService: reserve (charges in window + ALL active
  reservations, atomic) → submit → settle with actual tokens or release on confirmed no-charge.
- Unknown cost FAILS CLOSED (no verified per-second price → generation refused).
- Uncertain submission outcomes (timeouts) are NEVER blind-retried: status `needs_reconciliation`,
  reservation held until resolved.
- Tests never make paid requests (mock provider / httpx MockTransport only).
- Budget increases require explicit user action in `.env` — never an agent decision.

## Film bible

- Every project has `bible/film-bible.md` (canonical) plus world/characters/visual-style/continuity/
  locations/production-rules/scene-index/reference-index/changelog.
- Approved creative facts are never silently changed; changes are recorded in changelog.md.
- Generation prompts may include ONLY explicitly selected bible docs (capped context), recorded in
  `generations.context_json`. Never send the whole bible. Never invent canonical content (`[TO FILL]`).
- Generation flows never write to the bible.

## Provider integration

- All BytePlus ModelArk logic stays in `app/providers/ark.py` behind the VideoProvider protocol.
- Region: Asia Pacific (`https://ark.ap-southeast.bytepluses.com/api/v3`). Regional base URL, model IDs,
  statuses, and billing come from official docs — see `docs/research/byteplus-api-findings.md`.
- Models come from the registry (`data/config/models.json`) with verified pricing; account availability
  is marked only after a real successful generation. Never hardcode or invent model IDs; never silently
  substitute a model.
- Failed generations are not billed per official docs — but only confirmed terminal states release a
  reservation.

## Testing

- Run relevant tests after every change; report ACTUAL command results; never fabricate outcomes.
- Fix regressions you introduce. Re-test fixes instead of assuming they work.
- QA details: see the `test-local-first-app` skill (.opencode/skills/).

## Agent coordination (summary)

1. `studio-architect` reviews the task and boundaries → 2. `oss-researcher` resolves open external
   questions only → 3. work is assigned to `studio-frontend` / `seedance-backend` / `film-bible` →
4. each agent reports files changed, decisions, tests run → 5. main agent inspects real diffs →
6. `studio-qa` verifies independently → 7. `studio-security` audits high-risk changes →
8. main agent integrates and reports.

Single-owner components (never edit in parallel): DB migrations, provider adapter, budget service,
shared API types, root config. Full protocol: `docs/agents/agent-team.md`.
