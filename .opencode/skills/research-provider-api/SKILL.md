---
name: research-provider-api
description: Use when investigating BytePlus ModelArk or any future AI provider integration — endpoints, model IDs, request schemas, task lifecycle, pricing; verified facts only, no paid calls
---

# Research a provider API (BytePlus ModelArk / Seedance and future providers)

## Rules
1. **Official documentation first.** For BytePlus: docs.byteplus.com ModelArk API reference
   (create/retrieve/list/cancel video generation task), model pricing, and model activation pages.
   Region under use: Asia Pacific → `https://ark.ap-southeast.bytepluses.com/api/v3`.
2. **Verify regional endpoints and model identifiers** against the docs AND, where possible, free
   read-only calls (e.g., `GET /contents/generations/tasks?page_size=5` lists models actually used
   by the account — no charge). Document IDs are not proof of account availability.
3. **Validate request/response schemas** — write the exact JSON shapes into
   `docs/research/byteplus-api-findings.md` with a fetched date.
4. **Task lifecycle verification** — statuses (queued/running/succeeded/failed/cancelled/expired),
   polling, `usage.completion_tokens` billing, task-id validity windows, cancellation semantics.
5. **Pricing and cost-exposure verification** — per-second prices by resolution and token price per
   million; note minimum token rules; record the source page's last-updated date.
6. **Separate verified facts from assumptions** explicitly in every output. Mark unverified durations,
   ratios, or capabilities as ASSUMPTION until confirmed.
7. **No paid calls during research.** Free reads only. Never use a generation call to "test" anything.

## Output
Update `docs/research/byteplus-api-findings.md` (or create a provider-specific findings doc) and, if
model data changed, report the exact registry changes needed for `data/config/models.json` — but do not
edit the registry yourself.
