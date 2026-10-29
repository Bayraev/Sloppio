# Agent Team — AI Film Studio

OpenCode 1.18 agent team for this repository. All agents are subagents of the main session
(the primary GLM 5.3 session); none overrides the model — subagents inherit the invoking agent's
model, preserving the user's configuration.

## Roles

| Agent | File | Owns | May write | Never |
|---|---|---|---|---|
| `studio-architect` | `.opencode/agents/studio-architect.md` | module boundaries, release scope, integration risk | nothing (read-only) | editing code; approving from descriptions alone |
| `oss-researcher` | `.opencode/agents/oss-researcher.md` | external evidence (repos, licenses, official API facts) | `docs/research/**` only | paid calls; code changes |
| `studio-frontend` | `.opencode/agents/studio-frontend.md` | apps/web UI | `apps/web/**` | secrets in bundles; bypassing backend; second API contract |
| `seedance-backend` | `.opencode/agents/seedance-backend.md` | apps/api, provider adapter, persistence | `apps/api/**` | logging keys; blind retries; bypassing budget; invented models |
| `film-bible` | `.opencode/agents/film-bible.md` | bible structure, stable IDs, context selection | `bible-templates/**`, projects service, bible tests | inventing canon; silent overwrites; bible writes from generation flows |
| `studio-qa` | `.opencode/agents/studio-qa.md` | verification truth | test files | paid calls; weakened assertions; fabricated results |
| `studio-security` | `.opencode/agents/studio-security.md` | security & cost audit | nothing (read-only) | destructive tests; weakening controls |

## Single-owner components

Parallel edits are forbidden on: `apps/api/app/migrations/`, `apps/api/app/providers/ark.py`,
`apps/api/app/services/budget.py`, shared API route contracts, root config (.env.example, AGENTS.md,
.opencode/). One implementer; at least one independent reviewer (usually `studio-security` for the
budget/provider files).

## Coordination protocol

1. Main agent triages the task; `studio-architect` reviews boundaries and risks (invoke for anything
   cross-module or provider/budget-related).
2. Unresolved external questions go to `oss-researcher` (docs/research output only).
3. Implementation is assigned to exactly one owner per module; single-owner components never run in
   parallel.
4. Implementing agents report: files changed, decisions, exact commands + results.
5. Main agent inspects real diffs (skill: `review-agent-changes`).
6. `studio-qa` verifies independently (skill: `test-local-first-app`).
7. `studio-security` audits high-risk changes (skills: `audit-generation-costs`; secret hygiene).
8. Main agent resolves conflicts and integrates.

Do not start all agents for every task — invoke only those relevant.

## Invocation (OpenCode 1.18)

```
@studio-architect review this change plan
@oss-researcher verify model IDs X for region ap-southeast
@studio-frontend implement the bible editor improvements
@seedance-backend add duration support to the registry + adapter
@film-bible restructure reference-index and entity IDs
@studio-qa run the full verification suite and report
@studio-security audit the retry path for budget bypasses
```

Skills (auto-discovered, load with the `skill` tool when relevant):
`research-provider-api`, `implement-seedance-feature`, `test-local-first-app`,
`audit-generation-costs`, `maintain-film-bible`, `review-agent-changes`.
