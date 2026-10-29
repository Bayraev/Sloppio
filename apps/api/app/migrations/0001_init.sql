-- Initial schema: projects, scenes, assets, generations, budget ledger.
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id, slug)
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('reference', 'output')),
    role TEXT NOT NULL DEFAULT 'none',
    entity_id TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scene_id TEXT REFERENCES scenes(id) ON DELETE SET NULL,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    mode TEXT NOT NULL,
    prompt TEXT NOT NULL,
    final_prompt TEXT NOT NULL,
    ratio TEXT NOT NULL,
    resolution TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    seed INTEGER,
    generate_audio INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    provider_task_id TEXT,
    provider_status TEXT,
    error_code TEXT,
    error_message TEXT,
    cost_estimate_usd REAL NOT NULL DEFAULT 0,
    cost_actual_usd REAL,
    reservation_id TEXT,
    output_asset_id TEXT,
    context_json TEXT NOT NULL DEFAULT '{}',
    user_approved INTEGER NOT NULL DEFAULT 0,
    retry_of TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_generations_status ON generations(status);
CREATE INDEX IF NOT EXISTS idx_generations_project ON generations(project_id);
CREATE INDEX IF NOT EXISTS idx_generations_task ON generations(provider_task_id);

CREATE TABLE IF NOT EXISTS generation_refs (
    generation_id TEXT NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'reference_image'
);

CREATE TABLE IF NOT EXISTS generation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generation_id TEXT NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_charges (
    id TEXT PRIMARY KEY,
    generation_id TEXT,
    amount_usd REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_charges_time ON budget_charges(created_at);

CREATE TABLE IF NOT EXISTS budget_reservations (
    id TEXT PRIMARY KEY,
    generation_id TEXT,
    amount_usd REAL NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'settled', 'released')),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    settled_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_reservations_status ON budget_reservations(status);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
