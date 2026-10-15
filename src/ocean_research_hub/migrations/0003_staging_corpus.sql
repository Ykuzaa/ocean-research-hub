CREATE TABLE IF NOT EXISTS staging_corpus_import_runs (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    workbook_sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    counts_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_field_contract (
    field_path TEXT PRIMARY KEY,
    field_group TEXT NOT NULL,
    field_name TEXT NOT NULL,
    position INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_papers (
    paper_id TEXT PRIMARY KEY,
    doi_key TEXT,
    title_key TEXT,
    year TEXT,
    index_json TEXT NOT NULL,
    record_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    linked_paper_record_id TEXT,
    import_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS staging_corpus_papers_doi
    ON staging_corpus_papers(doi_key) WHERE doi_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS staging_corpus_paper_aliases (
    alias_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES staging_corpus_papers(paper_id),
    matched_on TEXT NOT NULL,
    import_run_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_claims (
    claim_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES staging_corpus_papers(paper_id),
    experiment_id TEXT,
    field_path TEXT NOT NULL,
    scientific_status TEXT NOT NULL,
    independent_audit TEXT,
    row_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS staging_corpus_claims_paper ON staging_corpus_claims(paper_id);
CREATE INDEX IF NOT EXISTS staging_corpus_claims_field ON staging_corpus_claims(field_path);
CREATE TABLE IF NOT EXISTS staging_corpus_research_gaps (
    gap_key TEXT PRIMARY KEY,
    row_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_field_markers (
    marker_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES staging_corpus_papers(paper_id),
    field_path TEXT NOT NULL,
    extraction_status TEXT NOT NULL,
    scientific_status TEXT NOT NULL,
    independent_audit TEXT,
    row_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS staging_corpus_field_markers_paper ON staging_corpus_field_markers(paper_id);
CREATE TABLE IF NOT EXISTS staging_corpus_paper_coverage (
    coverage_key TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES staging_corpus_papers(paper_id),
    source_name TEXT NOT NULL,
    row_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_row_versions (
    table_name TEXT NOT NULL,
    row_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    PRIMARY KEY (table_name, row_key, fingerprint)
);
CREATE TABLE IF NOT EXISTS staging_corpus_documents (
    name TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_audit_events (
    event_id TEXT PRIMARY KEY,
    target_kind TEXT NOT NULL CHECK (target_kind IN ('CLAIM', 'MARKER', 'PAPER')),
    target_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN (
        'VERIFIED', 'PARTIALLY_VERIFIED', 'NOT_VERIFIED', 'NOT_REPORTED',
        'CONFLICT', 'EXTRACTION_ERROR', 'BLOCKED'
    )),
    justification TEXT NOT NULL,
    auditor_id TEXT NOT NULL,
    audited_at TEXT NOT NULL,
    provenance_type TEXT NOT NULL CHECK (provenance_type IN (
        'AUTHOR_REPORTED_FACT', 'AUTHOR_REPORTED_LIMITATION', 'AI_INTERPRETATION', 'TEAM_NOTE'
    )),
    source_kind TEXT NOT NULL CHECK (source_kind IN (
        'PRIMARY_PAPER', 'SUPPLEMENTARY_MATERIAL', 'AUTHOR_CODE',
        'PUBLISHER_METADATA', 'OTHER'
    )),
    source_edition TEXT NOT NULL,
    page INTEGER CHECK (page IS NULL OR page >= 1),
    section TEXT,
    locator TEXT,
    evidence TEXT,
    search_scope TEXT,
    target_fingerprint TEXT NOT NULL,
    reviewed_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS staging_corpus_audit_target
    ON staging_corpus_audit_events(target_kind, target_id, audited_at);
CREATE TRIGGER IF NOT EXISTS staging_corpus_audit_no_update
BEFORE UPDATE ON staging_corpus_audit_events BEGIN
    SELECT RAISE(ABORT, 'scientific audit events are append-only');
END;
CREATE TRIGGER IF NOT EXISTS staging_corpus_audit_no_delete
BEFORE DELETE ON staging_corpus_audit_events BEGIN
    SELECT RAISE(ABORT, 'scientific audit events are append-only');
END;
CREATE TABLE IF NOT EXISTS staging_corpus_mapping_versions (
    version_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    workbook_sha256 TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_field_mappings (
    version_id TEXT NOT NULL REFERENCES staging_corpus_mapping_versions(version_id),
    original_path TEXT NOT NULL,
    canonical_path TEXT,
    decision TEXT NOT NULL CHECK (decision IN ('MAPPED', 'UNMAPPED', 'AMBIGUOUS')),
    basis TEXT NOT NULL,
    provenance_type TEXT NOT NULL CHECK (provenance_type IN ('AI_INTERPRETATION', 'TEAM_NOTE')),
    review_status TEXT NOT NULL CHECK (review_status IN ('PENDING', 'VALIDATED', 'REJECTED')),
    auditor_id TEXT,
    reviewed_at TEXT,
    source_candidate TEXT,
    PRIMARY KEY (version_id, original_path),
    CHECK (review_status != 'VALIDATED' OR (auditor_id IS NOT NULL AND reviewed_at IS NOT NULL)),
    CHECK (decision != 'MAPPED' OR canonical_path IS NOT NULL)
);
