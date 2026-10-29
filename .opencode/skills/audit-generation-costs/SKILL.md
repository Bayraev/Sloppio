---
name: audit-generation-costs
description: Use when changing anything that affects generation cost, pricing, retries, task recovery, or batch workflows — full code-path audit of every route that can incur a provider charge
---

# Audit generation costs

Perform a **code-path audit of every operation that can incur a provider charge** — not a spot check.

## Checklist
1. Enumerate every route to `provider.create_generation(...)` (and any future batch/agent loop).
   Each one must pass through `BudgetService.reserve()` FIRST, in the same flow.
2. **Unknown cost is unsafe.** `estimate_cost_usd` must fail closed when the registry has no verified
   per-second price for the model+resolution. Grep for fallbacks that default to 0 or skip the estimate.
3. **In-flight reservations count.** Rolling-window checks must include charges in the window PLUS ALL
   active reservations (regardless of age) in BOTH the 24h and 7d checks.
4. **Concurrency.** `reserve()` runs under BEGIN IMMEDIATE + process lock. Prove no new path bypasses it
   (threads, async tasks, retries). `tests/test_budget.py::test_concurrent_reservations_cannot_exceed_limit`
   must stay green.
5. **Retries and uncertain outcomes.** No blind retry of create-task after timeout. needs_reconciliation
   keeps its reservation until reconcile() resolves it. Retry-of-a-generation creates a NEW reservation.
6. **Reconciliation.** Success settles with actual `usage.completion_tokens × token price`; confirmed
   no-charge outcomes (failed/cancelled/expired/pre-submission) release. A provider failure is never
   assumed to be free unless the official lifecycle confirms the terminal state.
7. **Limits are immutable from code.** No endpoint, env fallback, or agent path can raise
   $7/24h or $50/7d. Only the user editing `.env` deliberately changes them.
8. **Approval gate.** Reservations above the per-operation threshold require `user_approved=true`.

## Output
A table: route → reserve-before-submit? → unknown-cost behavior → concurrency-safe? → verdict.
Any "no" is a blocking finding.
