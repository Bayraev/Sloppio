# Permissions & Safety — actual configuration

How the agent team's boundaries are enforced in OpenCode 1.18 (project-level config in
`.opencode/agents/*.md` frontmatter). The user's global config (`~/.config/opencode/opencode.jsonc`,
obsidian MCP, global skills) is untouched.

## Enforced per agent (native `permission` frontmatter)

| Agent | edit/write | bash | network |
|---|---|---|---|
| `studio-architect` | denied (all) | read-only git commands allowed, everything else **ask** | webfetch denied |
| `oss-researcher` | write only inside `docs/research/**`; all other writes denied | denied except `git log*` | webfetch + websearch allowed (research) |
| `studio-frontend` | edit/write only `apps/web/**` (other paths ask/deny) | `npm run *` allowed; installs/other **ask** | external directories denied |
| `seedance-backend` | edit/write only `apps/api/**` (registry JSON requires approval) | pytest/venv/uv allowed; other **ask** | external directories denied |
| `film-bible` | bible templates, projects service, bible tests | pytest **ask**-gated | external directories denied |
| `studio-qa` | test files only | test/build commands allowed | external directories denied |
| `studio-security` | denied (read-only auditor) | grep/rg/git + the two security/budget test files | webfetch denied |

`external_directory` is denied where possible, so agents cannot wander outside the project worktree.
`task` permissions let the architect fan work out; nobody grants unrestricted bash.

## Safety properties that are NOT permission-based (by design)

- **No agent can raise spending limits**: there is deliberately no API or UI surface that mutates the
  $7/24h and $50/7d policy; changing it requires the user to edit `.env` and restart (tested in
  `tests/test_security.py::test_budget_limits_not_mutable_via_api`).
- **No paid generation from agents**: every generation goes through BudgetService; tests run in mock
  mode only. A real generation requires the user's explicit mode switch and, per threshold, explicit
  per-operation approval.
- **Secrets**: never requested, printed, or logged; the backend redacts `Bearer` tokens from logs and
  exposes no key-bearing endpoint. The frontend has no access by construction.
- **User data**: `data/` and `projects/` are git-ignored; agents may read project code but the runner
  should not commit user media.

## Known limitations (honest notes)

- OpenCode permission rules gate tools, not individual functions inside a file — e.g. `studio-frontend`
  being allowed to edit `apps/web/**` cannot be narrowed to specific components. Code-review
  discipline (skills `review-agent-changes`, `maintain-film-bible`) compensates.
- `ask` rules prompt the human in interactive sessions; in headless runs they act as blocks. Treat
  `allow` lists above as the true automatic surface.
- Subagents inherit the primary model (GLM 5.3); no model overrides were added — fewer moving parts,
  no fabricated provider/model IDs.
