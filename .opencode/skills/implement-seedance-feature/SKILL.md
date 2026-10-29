---
name: implement-seedance-feature
description: Use when implementing any Seedance/BytePlus functionality — adapter changes, new generation modes, model registry updates, reference handling; enforces the eight-step safe path
---

# Implement a Seedance feature

Mandatory order — do not skip steps:

1. **Inspect existing architecture.** Read `apps/api/app/providers/`, `app/services/generations.py`,
   `docs/research/byteplus-api-findings.md`, and `docs/architecture.md` before writing anything.
2. **Confirm the official API contract** for everything you touch (endpoint, field, status, limit)
   against official docs or the verified findings doc. If a detail is not verified, stop and research it
   (skill: research-provider-api); never guess request fields.
3. **Validate model capabilities** via the model registry (`data/config/models.json` + ModelRegistry
   validation). New model = registry entry with verified pricing and `verified` flag; account-level
   availability stays unverified until the first successful generation.
4. **Use the provider adapter.** All provider logic goes through the VideoProvider protocol in
   `app/providers/` — no direct httpx calls to BytePlus elsewhere in the codebase.
5. **Route paid requests through the budget service.** Every generation entry point must call
   `BudgetService.reserve()` before `provider.create_generation()`. No alternate path is acceptable.
   Uncertain submissions → `needs_reconciliation`, reservation kept.
6. **Add tests using the mock provider.** Lifecycle, failure modes, and validation — tests never make
   paid calls (MockProvider + httpx MockTransport).
7. **Verify error and recovery behavior.** Timeouts, rate limits, restart recovery
   (`recover_unfinished`), cancel semantics, integrity failures (empty downloads).
8. **Update documentation.** `docs/api-integration.md` / `docs/architecture.md` when contracts change;
   registry JSON when models change.

## Done means
`pytest` green in apps/api, the change reviewed against the diff (not the description), and no secret in
code, logs, or tests.
