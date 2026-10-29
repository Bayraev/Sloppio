# Open-Source Evaluation — AI Film Studio (Seedance / BytePlus ModelArk)

Date: 2026-10-28 · Investigated by: `oss-researcher` workflow · Region under test: Asia Pacific (`ark.ap-southeast.bytepluses.com`)

## Decision: Strategy B — reuse established components, build a focused application

No community-verified, locally operated Seedance/ModelArk film studio exists today. We therefore
build a focused application on mature foundations (FastAPI, SQLite, Next.js, React, TypeScript,
Tailwind) and integrate the **official BytePlus ModelArk video-generation API** directly.

## Candidates investigated

### 1. Seedance Personal Studio — `monmonsky/seedance-studio`

Verified observations (from the public repository page, 2026-10-28):

| Signal | Value |
|---|---|
| Stars / forks / watchers | **0 / 0 / 0** |
| Commits | **4** (single author, no description, no LICENSE file) |
| Contributors | 1 |
| Tests / CI | Claims pytest + lint in README; **no CI workflows, no license** |
| Stack | Next.js frontend + FastAPI backend + SQLite (Alembic) |

- Does integrate the real ModelArk Seedance API (t2v/i2v, `@Image N` mentions, mock provider,
  localhost binding, CORS allowlist). README quality is good.
- **Not community-verified** (0 stars, 4 commits, no license ⇒ default all-rights-reserved;
  copying code would be legally unsafe and reliability is unproven).
- No film projects, no film bible, no scenes, **no budget manager / spending controls** —
  all core requirements of this product.
- Conclusion: **rejected as a foundation**; used only as a cross-check for API behaviour
  (its provider adapter independently confirms the endpoint paths, status values, and
  reference-image role semantics we verified against official docs).

### 2. ComfyUI — `Comfy-Org/ComfyUI`

- Very mature, huge community, GPL-3.0, active development, extensive test/CI culture.
- It is a **local GPU inference graph runtime**, not a hosted-API studio. Running Seedance
  through it requires local VRAM-class hardware and custom nodes; it has no film-project
  persistence, bible, or ModelArk billing/budget controls.
- Wrong shape for a local-first **API-driven** studio on arbitrary hardware.
- Conclusion: **rejected for v1**; remains a possible future local-generation provider behind
  the same provider adapter interface.

### 3. Velorn — `VelornLabs/velorn`

| Signal | Value |
|---|---|
| Stars / forks | **514 / 73** · 424 commits · multiple contributors · releases |
| License | **GPL-3.0** (copyleft) |
| Stack | Electron + Vite/React desktop editor; generation via **local ComfyUI**; local MCP server (100+ tools) |

- Genuinely maintained and agent-friendly (MCP), but it is a **timeline video editor** whose
  generation depends on a local ComfyUI instance, not a BytePlus ModelArk client. GPL-3 would
  also force copyleft onto any derivative foundation.
- No film bible, no ModelArk budget enforcement.
- Conclusion: **rejected for v1**; strong inspiration for future MCP/agent orchestration
  (their preview-first MCP write-tool pattern is documented in `docs/agents/`).

### 4. Official BytePlus ModelArk SDKs / docs (chosen integration path)

- Official REST API is simple (create task / get task / cancel / list), fully documented,
  and verified during this research (see `byteplus-api-findings.md`).
- Using the REST API directly with `httpx` keeps the adapter small, typed, and dependency-light;
  the official Python SDK adds weight without benefit for the four endpoints we use.

## Reused established components (Strategy B)

| Component | Choice | Why |
|---|---|---|
| Backend | FastAPI + uvicorn | Async provider polling, typed schemas, TestClient |
| DB | SQLite (WAL) + versioned SQL migrations | Single-user local app; zero-ops; restart-safe |
| HTTP | httpx (AsyncClient, MockTransport for tests) | Provider calls testable without paid requests |
| Images | Pillow | Upload dimension/format validation |
| Frontend | Next.js (App Router) + React + TypeScript | Mature, typed, single-command dev |
| Styling | Tailwind CSS v4 | Utility-first, no component-library lock-in |
| FE tests | Vitest + Testing Library | Fast, standard |

## Explicit statement

**No community-verified Seedance-specific studio existed at research time.** The smallest
credible path is a focused custom application on the mature stack above, integrating the
official BytePlus ModelArk API through a replaceable provider adapter.
