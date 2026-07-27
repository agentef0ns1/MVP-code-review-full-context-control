CREATE TABLE IF NOT EXISTS workspace_plans (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    profile TEXT NOT NULL DEFAULT 'security_code',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    unit_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS workspace_units (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    unit_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    rel_paths_json TEXT NOT NULL DEFAULT '[]',
    total_bytes INTEGER NOT NULL DEFAULT 0,
    strategy TEXT NOT NULL DEFAULT 'read_ok',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'skipped')),
    checkpoint_key TEXT NOT NULL DEFAULT '',
    UNIQUE (project_id, unit_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_units_next
    ON workspace_units (project_id, status, sequence);
