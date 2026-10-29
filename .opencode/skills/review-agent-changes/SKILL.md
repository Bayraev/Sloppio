---
name: review-agent-changes
description: Use before integrating substantial changes made by another agent — inspect actual diffs, test evidence, security and cost implications, duplicate implementations, and architectural fit
---

# Review agent changes

Use BEFORE integrating substantial changes produced by another agent.

## Procedure
1. **Inspect the actual diff** (`git diff`, `git status`) — never rely on the author agent's summary.
   Read every changed file; check for scope beyond the stated task.
2. **Verify test evidence.** Re-run the relevant suites yourself (apps/api: pytest; apps/web: npm test,
   typecheck). A claim of "tests pass" without command output is not evidence.
3. **Security implications.** Secrets in code/logs/bundles? New network surface? Upload/path handling?
   Shell execution? Run the `audit-generation-costs` skill if anything touched generation, pricing,
   retries, or recovery.
4. **Duplicate implementations.** Look for a second provider path, a parallel budget check, a competing
   API contract, or re-implemented utilities that already exist (grep before accepting new helpers).
5. **Architectural consistency.** Boundaries respected (providers behind the adapter, budget central,
   provider logic isolated from project logic)? Release scope respected (Seedance-only)?
6. **Bible safety.** If bible structures were touched, run the `maintain-film-bible` checklist.
7. **Docs.** API contract, architecture, or registry changed → docs updated in the same change?

## Verdict
Integrate / integrate-with-fixes (list them) / reject (reasons, file:line). Conflict with another agent's
work → escalate to the main agent with both diffs.
