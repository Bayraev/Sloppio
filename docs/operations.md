# Operations

## Data locations (all git-ignored)

| Path | Contents |
|---|---|
| `data/database/studio.db` (+ `-wal`, `-shm`) | SQLite — projects, scenes, assets, generations, budget ledger |
| `data/generations/` | output videos (`out_*.mp4`, mock outputs `*.mock.mp4`) |
| `data/config/models.json` | model registry (editable; keep pricing verified) |
| `data/mock_provider_state.json` | mock provider task state (dev/test only) |
| `projects/<slug>/` | project.json, bible/, references/, scenes/ |
| `.env` | credentials + policy |

## Backup

Stop the backend (or accept a WAL snapshot), then copy `data/` and `projects/` and `.env`:

```bash
tar czf studio-backup-$(date +%F).tgz data projects .env
```

Restore by unpacking over a fresh checkout. The DB and files are enough — no external state.

## Recovery scenarios

- **App killed mid-generation** — on restart, tasks with persisted provider task ids resume polling;
  interrupted submissions become `needs_reconciliation` with the budget reservation held. Check the
  BytePlus console task list, then use History → Details → reconcile.
- **needs_reconciliation with no task id** — the submission outcome is unknowable from here. If the
  console shows no task was created, the reservation can be manually released via SQL on
  `budget_reservations` (status → released) and the record deleted. Conservative default: leave the
  reservation until the 7-day window passes.
- **Missing output file** — reported as an integrity problem; the record stays `needs_reconciliation`
  (a charge may exist). Never silently "completed".

## Budget operations

- Live view: Budget page or `GET /api/v1/budget` (spend per window, active reservations, charges).
- Limits: edit `BUDGET_LIMIT_24H_USD` / `BUDGET_LIMIT_7D_USD` in `.env` **deliberately** and restart.
  There is no API/UI to raise them — by design.
- Held reservations block new generations until settled/released (they count in both windows).

## Model registry maintenance

Edit `data/config/models.json`: add model ids with **officially verified** capabilities and
per-second pricing; keep durations conservative (registry-rejected values are refused, not guessed).
`account_verified` is set automatically after the first successful generation.

## Logs

Backend logs to stdout (`uvicorn`); secrets are redacted. Generation timelines live in
`generation_events` (per-record audit trail), visible in History → Details.
