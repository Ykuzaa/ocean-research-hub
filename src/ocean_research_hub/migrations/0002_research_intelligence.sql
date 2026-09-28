PRAGMA foreign_keys = ON;

CREATE TABLE paper_identifiers (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    identifier_type TEXT NOT NULL CHECK (identifier_type IN ('DOI', 'ARXIV')),
    normalized_value TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (identifier_type, normalized_value),
    UNIQUE (paper_id, identifier_type, normalized_value)
);

CREATE INDEX paper_identifiers_paper_idx ON paper_identifiers(paper_id);

CREATE TABLE source_editions (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    edition_key TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN (
        'PRIMARY_PDF', 'SUPPLEMENTARY_MATERIAL', 'PUBLISHER_METADATA',
        'CROSSREF_METADATA', 'CORPUS_MANIFEST', 'OTHER'
    )),
    uri TEXT,
    content_hash TEXT,
    version_label TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    created_at TEXT NOT NULL,
    UNIQUE (paper_id, edition_key)
);

CREATE INDEX source_editions_paper_idx ON source_editions(paper_id);
CREATE UNIQUE INDEX source_editions_content_hash_idx
    ON source_editions(content_hash) WHERE content_hash IS NOT NULL;

CREATE TABLE research_entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN (
        'DOMAIN', 'TASK', 'MODEL', 'ARCHITECTURE', 'DATASET', 'VARIABLE',
        'UNIT', 'REGION', 'METRIC', 'LOSS', 'OPTIMIZER',
        'LIMITATION_TAXONOMY'
    )),
    normalized_key TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (entity_type, normalized_key)
);

CREATE INDEX research_entities_type_name_idx
    ON research_entities(entity_type, canonical_name COLLATE NOCASE);

CREATE TABLE entity_mentions (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    source_edition_id TEXT REFERENCES source_editions(id) ON DELETE SET NULL,
    entity_id TEXT NOT NULL REFERENCES research_entities(id) ON DELETE RESTRICT,
    relationship_type TEXT NOT NULL,
    field_path TEXT NOT NULL,
    source_wording TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'VERIFIED', 'PARTIALLY_VERIFIED', 'NOT_VERIFIED', 'NOT_REPORTED',
        'CONFLICT', 'EXTRACTION_ERROR'
    )),
    provenance_type TEXT NOT NULL CHECK (provenance_type IN (
        'AUTHOR_REPORTED_FACT', 'AUTHOR_REPORTED_LIMITATION',
        'AI_INTERPRETATION', 'TEAM_NOTE'
    )),
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    verified_by TEXT,
    verified_at TEXT,
    alternative_index INTEGER,
    claim_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (paper_id, source_edition_id, claim_key)
);

CREATE INDEX entity_mentions_entity_idx ON entity_mentions(entity_id);
CREATE INDEX entity_mentions_paper_idx ON entity_mentions(paper_id);

CREATE TABLE entity_field_states (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    source_edition_id TEXT REFERENCES source_editions(id) ON DELETE SET NULL,
    field_path TEXT NOT NULL,
    value_json TEXT,
    conflict_values_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (status IN (
        'VERIFIED', 'PARTIALLY_VERIFIED', 'NOT_VERIFIED', 'NOT_REPORTED',
        'CONFLICT', 'EXTRACTION_ERROR'
    )),
    provenance_type TEXT NOT NULL CHECK (provenance_type IN (
        'AUTHOR_REPORTED_FACT', 'AUTHOR_REPORTED_LIMITATION',
        'AI_INTERPRETATION', 'TEAM_NOTE'
    )),
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    verified_by TEXT,
    verified_at TEXT,
    claim_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (paper_id, source_edition_id, field_path)
);

CREATE INDEX entity_field_states_paper_idx ON entity_field_states(paper_id);

CREATE TABLE mention_evidence (
    id TEXT PRIMARY KEY,
    mention_id TEXT NOT NULL REFERENCES entity_mentions(id) ON DELETE CASCADE,
    evidence_order INTEGER NOT NULL,
    section TEXT,
    page INTEGER CHECK (page IS NULL OR page >= 1),
    locator TEXT,
    evidence_text TEXT,
    origin TEXT,
    source_edition_id TEXT REFERENCES source_editions(id) ON DELETE SET NULL,
    source_edition_key TEXT,
    claimed_value_json TEXT,
    UNIQUE (mention_id, evidence_order)
);

CREATE TABLE training_configurations (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    source_edition_id TEXT REFERENCES source_editions(id) ON DELETE SET NULL,
    label TEXT NOT NULL,
    configuration_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (paper_id, source_edition_id, configuration_key)
);

CREATE TABLE hyperparameters (
    id TEXT PRIMARY KEY,
    training_configuration_id TEXT NOT NULL
        REFERENCES training_configurations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    normalized_value_json TEXT,
    original_wording TEXT,
    field_path TEXT NOT NULL,
    status TEXT NOT NULL,
    provenance_type TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    verified_by TEXT,
    verified_at TEXT,
    claim_key TEXT NOT NULL,
    UNIQUE (training_configuration_id, claim_key)
);

CREATE TABLE reported_results (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    source_edition_id TEXT REFERENCES source_editions(id) ON DELETE SET NULL,
    metric_entity_id TEXT REFERENCES research_entities(id) ON DELETE RESTRICT,
    dataset_entity_id TEXT REFERENCES research_entities(id) ON DELETE RESTRICT,
    variable_entity_id TEXT REFERENCES research_entities(id) ON DELETE RESTRICT,
    normalized_value_json TEXT,
    original_wording TEXT,
    field_path TEXT NOT NULL,
    status TEXT NOT NULL,
    provenance_type TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    verified_by TEXT,
    verified_at TEXT,
    claim_key TEXT NOT NULL,
    UNIQUE (paper_id, source_edition_id, claim_key)
);

CREATE TABLE research_statements (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    source_edition_id TEXT REFERENCES source_editions(id) ON DELETE SET NULL,
    taxonomy_entity_id TEXT REFERENCES research_entities(id) ON DELETE RESTRICT,
    statement_type TEXT NOT NULL CHECK (statement_type IN ('LIMITATION', 'FUTURE_WORK')),
    original_wording TEXT,
    field_path TEXT NOT NULL,
    status TEXT NOT NULL,
    provenance_type TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    verified_by TEXT,
    verified_at TEXT,
    claim_key TEXT NOT NULL,
    UNIQUE (paper_id, source_edition_id, claim_key)
);

CREATE TABLE entity_relationships (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    source_edition_id TEXT REFERENCES source_editions(id) ON DELETE SET NULL,
    subject_entity_id TEXT NOT NULL REFERENCES research_entities(id) ON DELETE RESTRICT,
    predicate TEXT NOT NULL,
    object_entity_id TEXT NOT NULL REFERENCES research_entities(id) ON DELETE RESTRICT,
    source_wording TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'VERIFIED', 'PARTIALLY_VERIFIED', 'NOT_VERIFIED', 'CONFLICT'
    )),
    provenance_type TEXT NOT NULL CHECK (provenance_type IN (
        'AUTHOR_REPORTED_FACT', 'AUTHOR_REPORTED_LIMITATION',
        'AI_INTERPRETATION', 'TEAM_NOTE'
    )),
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    verified_by TEXT,
    verified_at TEXT,
    claim_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (paper_id, source_edition_id, claim_key)
);

CREATE INDEX entity_relationships_subject_idx ON entity_relationships(subject_entity_id);
CREATE INDEX entity_relationships_object_idx ON entity_relationships(object_entity_id);

CREATE TABLE relationship_evidence (
    id TEXT PRIMARY KEY,
    relationship_id TEXT NOT NULL REFERENCES entity_relationships(id) ON DELETE CASCADE,
    evidence_order INTEGER NOT NULL,
    section TEXT,
    page INTEGER CHECK (page IS NULL OR page >= 1),
    locator TEXT,
    evidence_text TEXT NOT NULL,
    origin TEXT,
    source_edition_id TEXT REFERENCES source_editions(id) ON DELETE SET NULL,
    source_edition_key TEXT,
    UNIQUE (relationship_id, evidence_order)
);

CREATE TABLE claim_evidence (
    id TEXT PRIMARY KEY,
    claim_table TEXT NOT NULL CHECK (claim_table IN (
        'entity_field_states', 'hyperparameters', 'reported_results', 'research_statements'
    )),
    claim_id TEXT NOT NULL,
    evidence_order INTEGER NOT NULL,
    section TEXT,
    page INTEGER CHECK (page IS NULL OR page >= 1),
    locator TEXT,
    evidence_text TEXT,
    origin TEXT,
    source_edition_id TEXT REFERENCES source_editions(id) ON DELETE SET NULL,
    source_edition_key TEXT,
    claimed_value_json TEXT,
    UNIQUE (claim_table, claim_id, evidence_order)
);
