CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    identity_key TEXT NOT NULL UNIQUE,
    doi TEXT,
    fingerprint TEXT NOT NULL,
    workflow_status TEXT NOT NULL,
    record_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS papers_unique_doi
    ON papers(doi) WHERE doi IS NOT NULL;
