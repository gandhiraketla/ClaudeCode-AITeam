PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT,
    slack_channel TEXT NOT NULL,
    slack_thread_ts TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'IDLE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    role TEXT NOT NULL,        -- 'user' or 'agent'
    persona TEXT,              -- 'ba', 'architect', etc.
    content TEXT NOT NULL,
    slack_ts TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    stage TEXT NOT NULL,       -- 'ba', 'architect', 'agent-implementer', etc.
    file_path TEXT,
    content TEXT NOT NULL,
    approved BOOLEAN DEFAULT 0,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id);
CREATE INDEX IF NOT EXISTS idx_projects_thread ON projects(slack_thread_ts);
