# Security

Single-user local application — local execution still has real risks; these are the controls.

## Network

- Backend binds `127.0.0.1` by default (`API_HOST`); not exposed to the network.
- CORS allows exactly one origin (`FRONTEND_ORIGIN`, default http://localhost:3210). Tested in
  `tests/test_security.py`.
- No analytics, no third-party telemetry, no data leaves the machine except provider API calls
  (prompts + selected reference images) to BytePlus.

## Secrets

- The BytePlus key lives only in `.env` and the backend process. Never in the DB, API responses,
  browser bundles (`NEXT_PUBLIC_*` excluded), agent configs, docs, or git.
- Logging redacts `Bearer` tokens and `ark_api_key=` patterns (`app/main.py` filter).
- `.env`, `data/`, `projects/` are git-ignored; `.env.example` contains placeholders only.

## Uploads and paths

- Reference uploads: MIME allowlist (jpeg/png/webp) **verified against actual decoded image
  content** (Pillow), size limit, 300–6000 px per side, aspect ratio 0.4–2.5.
- Stored files use app-generated IDs (`ref_*.png`) — original names kept only as metadata.
- All filesystem access goes through `safe_join()` (containment check) — path traversal attempts
  are rejected and tested.
- No shell execution anywhere in the backend; no SQL string interpolation of user input
  (parameterized queries).

## Spending controls (see AGENTS.md invariants)

- Central BudgetService is the only gate to paid requests; atomic reservations; rolling windows
  include all active reservations; unknown cost fails closed; uncertain outcomes hold reservations;
  restarts never release exposure.
- There is **no API or UI to raise limits** — verified by test.
- Provider moderation decisions (e.g., real-person face policy for Seedance 2.x) are passed
  through, never bypassed.

## Provider-facing data

Sent to BytePlus on generation: final prompt (your prompt + selected bible context), reference
images (base64), and generation parameters. Nothing else. Task ids and outputs are polled/downloaded
over authenticated calls from the backend only.

## Reporting

Found something? Inspect with `@studio-security` (read-only auditor) — findings come back ranked by
severity with file:line references.
