---
name: test-local-first-app
description: Use when verifying the AI Film Studio app — persistence, restart recovery, mock generation, budget invariants, frontend integration, type checks and builds
---

# Test the local-first app

Verify ALL of these dimensions that apply to your change:

1. **Database persistence** — entities survive across connections; migrations apply cleanly on a fresh
   workspace (`tests/conftest.py` builds isolated temp workspaces).
2. **Filesystem persistence** — bible docs, reference files, generated outputs land in the right places
   under app-managed paths; missing files surface as integrity errors, never fake success.
3. **Restart recovery** — in-flight tasks with persisted provider task ids resume (poll-only, never
   resubmit); submissions interrupted before a task id became `needs_reconciliation` with the budget
   reservation held. See `tests/test_recovery.py`.
4. **Mock generation** — full lifecycle via `MockProvider` including failure, rate-limit, uncertain
   submission, expired, and missing-file scenarios. Mock outputs must be clearly labeled mock.
5. **Frontend/backend integration** — run apps/api (mock mode) and apps/web; exercise project creation,
   bible editing, a mock generation end to end in the browser, history, budget pages.
6. **Type checks and builds** — `cd apps/web && npm run typecheck && npm run build` must pass;
   `cd apps/api && .venv/bin/python -m pytest` must pass.
7. **Budget invariants** — `tests/test_budget.py` all green: windows, concurrency, boundaries,
   persistence, settlement/release semantics.
8. **No paid calls in automated tests** — USE_MOCK_PROVIDER forced in conftest; grep new tests for
   real endpoints if in doubt.

## Reporting
Report the exact commands you ran and their real output summary. Never claim a run you did not execute.
If something cannot be tested, say so explicitly.
