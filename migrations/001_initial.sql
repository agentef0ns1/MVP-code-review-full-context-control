PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    display_name TEXT,
    workspace_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_accessed_at TEXT,
    last_agent_session_id TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'frozen', 'archived')),
    memory_size_bytes INTEGER NOT NULL DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS project_state (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,
    summary TEXT NOT NULL DEFAULT '',
    checkpoint TEXT NOT NULL DEFAULT '',
    state_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by TEXT NOT NULL DEFAULT 'system'
);

CREATE TABLE IF NOT EXISTS memory_entries (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    entry_type TEXT NOT NULL CHECK (entry_type IN (
        'event', 'decision', 'pending', 'error', 'file_ref', 'long_term', 'init'
    )),
    scope TEXT NOT NULL DEFAULT 'working' CHECK (scope IN ('working', 'persistent')),
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    sequence INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT NOT NULL DEFAULT 'agent',
    session_id TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by TEXT NOT NULL DEFAULT 'agent',
    deleted_at TEXT,
    frozen INTEGER NOT NULL DEFAULT 0,
    human_only INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL DEFAULT '',
    supersedes_id TEXT REFERENCES memory_entries(id)
);

CREATE INDEX IF NOT EXISTS idx_entries_project_seq ON memory_entries(project_id, sequence);
CREATE INDEX IF NOT EXISTS idx_entries_project_type ON memory_entries(project_id, entry_type);
CREATE INDEX IF NOT EXISTS idx_entries_deleted ON memory_entries(project_id, deleted_at);

CREATE TABLE IF NOT EXISTS memory_entry_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL REFERENCES memory_entries(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    title TEXT,
    body TEXT,
    tags_json TEXT,
    metadata_json TEXT,
    changed_at TEXT NOT NULL DEFAULT (datetime('now')),
    changed_by TEXT NOT NULL,
    change_reason TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    actor TEXT NOT NULL,
    actor_session TEXT,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    project_id TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    ip TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_log(project_id, timestamp);

CREATE TABLE IF NOT EXISTS project_locks (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    holder TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    token TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_memory USING fts5(
    entry_id UNINDEXED,
    project_id UNINDEXED,
    title,
    body,
    tags,
    tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS entry_embeddings (
    entry_id TEXT PRIMARY KEY REFERENCES memory_entries(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'hash-v1',
    vector_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
