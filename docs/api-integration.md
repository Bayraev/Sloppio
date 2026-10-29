# API Integration

## BytePlus ModelArk (external)

All provider specifics verified against official docs — see `docs/research/byteplus-api-findings.md`
(endpoints, request schema, roles, statuses, usage/billing, pricing table with per-second values).

- Base: `https://ark.ap-southeast.bytepluses.com/api/v3` (Asia Pacific), `Authorization: Bearer`.
- Create: `POST /contents/generations/tasks` — `{model, content:[{type:text|image_url,...}], resolution,
  ratio, duration, generate_audio?, seed?, watermark}`; image roles `first_frame|last_frame|reference_image`
  are mutually exclusive scenario groups. For first-frame / first-last-frame modes the output ratio
  follows the first-frame image — `ratio` is omitted (verified live 2026-10-29).
- Poll: `GET /contents/generations/tasks/{id}` — `status` queued/running/succeeded/failed/cancelled/
  expired; `content.video_url`; `usage.completion_tokens` (actual billed tokens).
- Cancel: `DELETE /contents/generations/tasks/{id}`.
- Free read: `GET /contents/generations/tasks?page_size=5` — model ids actually used by the account
  (used by `POST /api/v1/provider/check`).
- Billed only on success; estimate = verified per-second price × duration (+ safety margin on
  reservation); settlement = `completion_tokens × token price / 1e6`.
- Face policy: 2.x models reject real-person reference uploads outside the official portrait-asset
  workflow — moderation errors surface as `content_rejected`.

## Local REST API (prefix `/api/v1`, served by apps/api)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | status, provider mode, missing settings |
| GET | `/capabilities` | models (registry), upload limits, budget snapshot |
| POST | `/provider/check` | free read: model ids seen on recent provider tasks |
| GET/POST | `/projects` | list / create (seeds the full bible) |
| GET/PATCH/DELETE | `/projects/{id}` | read / update / delete (optional `delete_files=true`) |
| GET | `/projects/{id}/bible` | bible doc index |
| GET/PUT | `/projects/{id}/bible/{name}` | read / write a whitelisted bible doc |
| POST/GET | `/projects/{id}/scenes` | create / list scenes |
| POST/GET | `/projects/{id}/references` | upload (multipart, validated) / list |
| PATCH/DELETE | `/projects/references/{id}` | role/entity / delete (refused while referenced) |
| GET | `/projects/references/{id}/file` | serve reference image |
| POST | `/generations` | create generation (see flow below) |
| GET | `/generations` | list with filters (project/scene/model/status, limit/offset) |
| GET | `/generations/{id}` | detail incl. events, refs, final prompt |
| POST | `/generations/{id}/retry` | new generation copying inputs (original preserved) |
| POST | `/generations/{id}/cancel` | provider cancel; honest about remote state |
| POST | `/generations/{id}/reconcile` | resolve needs_reconciliation |
| DELETE | `/generations/{id}` | delete (refused while in flight / unresolved) |
| GET | `/generations/{id}/video` | stream output (mock outputs labeled `.mock.mp4`) |
| GET | `/budget` | limits, spend, reservations, recent charges |

### Create generation — body

```json
{
  "project_id": "prj_…", "scene_id": "scn_… (optional)",
  "model_id": "dreamina-seedance-2-0-mini-260615",
  "mode": "text_to_video | image_to_video | first_last_frame | reference_to_video",
  "prompt": "…", "ratio": "16:9", "resolution": "720p", "duration_seconds": 5,
  "generate_audio": false, "seed": null,
  "reference_asset_ids": ["ref_…"], "bible_docs": ["characters.md"],
  "user_approved": false
}
```

Errors carry `{detail: {code, message}}` with meaningful codes: `budget_exceeded` (429),
`approval_required` (409), `unknown_cost` (422), validation codes (400), `uncertain_submission` (409),
`needs_reconciliation` (409).

Generation statuses: `validating → submitting → queued → processing → downloading → completed |
failed | cancelled | expired | needs_reconciliation` (event log per generation).

## Adding a future provider

Implement the `VideoProvider` protocol (`apps/api/app/providers/base.py`): `create_generation`,
`get_generation_status`, `cancel_generation`, `download_result`, `list_recent_models`, `aclose`.
Register models (with verified pricing) in `data/config/models.json`, wire the factory in
`app/main.py`, add mock-based tests. Budget and lifecycle layers are provider-agnostic.
