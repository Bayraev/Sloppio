# BytePlus ModelArk — verified API findings (Seedance)

Date: 2026-10-28 · Source: official documentation (fetched and verified), cross-checked with an
independent third-party implementation. Region: **Asia Pacific**.

## Verified facts

### Endpoints (region: ap-southeast)

- Base URL: `https://ark.ap-southeast.bytepluses.com/api/v3`
- `POST   /contents/generations/tasks` — create task (async)
- `GET    /contents/generations/tasks/{id}` — poll task
- `GET    /contents/generations/tasks?page_size=N` — list recent tasks (free read; returns `model` per task)
- `DELETE /contents/generations/tasks/{id}` — cancel/delete task

### Create-task request (verified from official docs + example)

```json
{
  "model": "dreamina-seedance-2-5-260628",
  "content": [
    { "type": "text", "text": "Prompt text... @Image1 ... @Video1" },
    { "type": "image_url", "image_url": { "url": "data:image/png;base64,..." }, "role": "reference_image" }
  ],
  "resolution": "720p",
  "ratio": "16:9",
  "duration": 5,
  "seed": 11,
  "camera_fixed": false,
  "watermark": true,
  "generate_audio": true
}
```

- Output parameters (`resolution`, `ratio`, `duration`, `frames`, `seed`, `camera_fixed`,
  `watermark`) go **directly in the request body** (strict validation) — preferred over the
  legacy `--param` prompt suffix.
- Image roles: `first_frame`, `last_frame`, `reference_image`. Scenario groups are **mutually
  exclusive** (i2v first frame / first+last frame / omni reference-to-video cannot be mixed).
- Image constraints: jpeg/png/webp/bmp/tiff(+heic for newer models); aspect ratio 0.4–2.5;
  300–6000 px per side; < 30 MB per image; request body ≤ 64 MB (base64 inflates ~4/3).
- Reference image counts: Seedance 2.5 up to **30**, Seedance 2.0 series up to **9**;
  first-frame i2v exactly 1; first+last exactly 2. Our app enforces a conservative ceiling of 9.
- Mention syntax in official examples: **`@Image1`**, `@Video1` (numbered in content order).
- Face policy: 2.5/2.0 series reject uploads containing real human faces except via the official
  portrait-asset workflow (asset IDs / trusted prior outputs). Moderation errors must be passed
  through, never bypassed.

### Task response / lifecycle

- `status`: `queued` → `running` → `succeeded` | `failed` | `cancelled` | `expired`.
- `content.video_url` (and `content.last_frame_url` where applicable) on success.
- `usage.completion_tokens` / `usage.total_tokens` — **actual billed tokens** (input tokens
  always 0 for video; total = completion). Seedance 2.0 series has a **minimum token usage**
  when input includes video.
- Task IDs are valid ~7 days (draft IDs 14 days for IDs created after 2026-10-28 10:00 UTC+8).
- Auth: `Authorization: Bearer <key>`; HTTP 401/403 auth, 429 rate limit, 5xx transient.

### Pricing — verified from official pricing page (last updated 2026-10-23)

Token price = USD per million tokens. **Charged only for successfully generated videos.**

| Model ID | 480p | 720p | 1080p | 4K |
|---|---|---|---|---|
| `dreamina-seedance-2-5-260628` | $10.70 | $10.70 | $11.70 | — |
| `dreamina-seedance-2-0-260128` | $7.00 | $7.00 | $7.70 | $4.00 |
| `dreamina-seedance-2-0-fast-260128` | $5.60 | — | — | — |
| `dreamina-seedance-2-0-mini-260615` | $3.50 | — | — | — |
| `seedance-1-0-pro-250528` | $2.50 | $2.50 | — | — |
| `seedance-1-0-pro-fast-251015` | $1.00 | $1.00 | — | — |

Derived per-second prices (official per-video examples, 16:9, 5 s):

| Model | 480p/s | 720p/s | 1080p/s | 4K/s |
|---|---|---|---|---|
| Seedance 2.5 | $0.103 | $0.231 | $0.569 | — |
| Seedance 2.0 | $0.07 | $0.15 | $0.37 | $0.78 |
| Seedance 2.0 Fast | $0.06 | $0.12 | — | — |
| Seedance 2.0 Mini | $0.04 | $0.08 | — | — |
| Seedance 1.0 Pro | $0.024 | $0.052 | $0.122 | — |
| Seedance 1.0 Pro Fast | $0.010 | $0.021 | $0.049 | — |

Token estimate formula (official): `(input_video_duration + output_duration) × width × height
× fps / 1024` tokens. Actual billing comes from `usage.completion_tokens`.

Model activation (2.0/2.5): requires account balance > $30 USD, or an AI Savings Plan ≥ $30
tier, or a Seedance resource pack.

## Assumptions (clearly marked, not verified)

- Supported `duration` step lists per model: pricing tables verify 5 s and 10 s for 1.0 Pro;
  Seedance 2.5 documents coherent generation up to 30 s. Our registry ships `[5, 10]` for all
  models and is user-editable (`data/config/models.json`) — durations outside the registry are
  rejected (fail closed) rather than guessed.
- `generate_audio` is enabled only for models whose docs state audio support (2.x series).
- Model IDs above are **documented IDs**, not proof this account can call them. Availability is
  account/region gated; the app marks a model `verified` only after the first successful task
  with that model, or lists recent tasks (free) so the user can copy a model ID they actually
  use.

### Verified live (2026-10-29, first real-mode requests)

- `image_to_video` / `first_last_frame` REJECT an explicit `ratio` ("The parameter ratio specified
  in the request is not valid. For first-frame or first-last-frame generation, the output ratio
  follows the first-frame image.") — omit `ratio` for these modes.
- Unactivated models are rejected at task creation with a clear activation error — no task, no charge.

## Safety rules derived

1. Never blind-retry `POST /tasks` after an uncertain timeout — a task may already exist and
   bill. Mark `needs_reconciliation`, keep the budget reservation.
2. Reserve `per_second × duration × (1 + margin)` before submission; settle with actual
   `completion_tokens × token_price / 1e6` after success; release only on confirmed
   no-charge outcomes (`failed`, `cancelled`, `expired`, pre-submission validation).
3. Failed generations are not billed (official statement) — but an unknown status is never
   treated as "no charge".
