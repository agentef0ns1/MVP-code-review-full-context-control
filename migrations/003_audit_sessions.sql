CREATE TABLE IF NOT EXISTS audit_sessions (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL,
    output_rel_dir TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
