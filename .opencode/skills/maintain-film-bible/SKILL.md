---
name: maintain-film-bible
description: Use when changing bible structures, character/location reference handling, scene prompts, context selection, or continuity logic — preserves canonical facts, stable IDs, and traceability
---

# Maintain the film bible

Applies to any change touching `bible/` structures, reference associations, scene prompts, or the
context-selection mechanism (`ProjectService.compose_bible_context`).

## Invariants
1. **Canonical safety.** `bible/film-bible.md` is the canonical document; supporting docs must stay
   consistent with it. Approved creative facts are never silently changed — edits go through the user,
   and meaningful canonical changes are recorded in `bible/changelog.md`.
2. **Stable IDs.** Characters `char-NNN`, locations `loc-NNN`, scenes `scn_*` — IDs never change once
   assigned; they link reference-index.md entries, asset roles (`assets.entity_id`), scene prompts, and
   generation context.
3. **Explicit placeholders.** Project creation seeds `[TO FILL]` fields — never invented lore, never
   empty stubs. Keep `bible-templates/` as the single template source.
4. **Controlled context selection.** Generation requests include ONLY explicitly selected docs, capped
   (`max_chars`), composed into the final prompt verbatim, recorded in `context_json`. Never send the
   whole bible; never auto-attach references the user didn't select.
5. **Traceability.** Every generation records which bible docs and reference assets it used; the link
   survives retries and restarts.
6. **No generation writes to the bible.** Generation flows are read-only on bible files. Future
   AI-suggested changes must be proposed for approval, then changelogged.

## Tests
`pytest tests/test_projects_bible.py` and the bible-context assertions in
`tests/test_generations_api.py` must be green after your change.
