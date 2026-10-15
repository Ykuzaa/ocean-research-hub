# ADR 0002: Normalized research-intelligence model

- Status: Accepted
- Date: 2026-09-22
- Scope: Issue #11

## Context

`PaperRecord` is the evidence-safe ingestion and display contract, but storing only its JSON cannot
support entity pages or cross-paper queries. Normalization must not discard author wording, source
edition identity, field-level evidence, provenance, verification state, missing/error states, or
conflicting alternatives.

## Decision

Keep the validated `PaperRecord` JSON as the canonical lossless record and deterministically project
queryable claims into normalized SQLite tables:

- `source_editions` identifies a PDF, supplement, metadata record, or future corpus-manifest source;
- `research_entities` deduplicates domains, tasks, models, architectures, datasets, variables,
  units, regions, metrics, losses, optimizers, and future limitation taxonomies;
- `entity_mentions` is the evidence-backed many-to-many relationship between papers and entities;
- `entity_field_states` is the generic field-state ledger for every evidence-bearing canonical
  field, including nested preprocessing, split, architecture, objective, evaluation,
  availability, and reproducibility fields. It keeps superseded claims queryable and
  `NOT_REPORTED` distinct from `EXTRACTION_ERROR` without inventing placeholder entities;
- `training_configurations` and `hyperparameters` retain every training field, including null
  `NOT_REPORTED` and `EXTRACTION_ERROR` values;
- `reported_results` preserves result wording and status without parsing an unsupported numeric
  interpretation;
- `research_statements` separates `LIMITATION` from `FUTURE_WORK` and retains provenance;
- `entity_relationships` stores only explicitly submitted, evidence-backed entity edges;
- evidence tables retain section, page, locator, excerpt, source origin, conflict binding, and the
  exact source edition.

All projected claims retain `verified_by` and `verified_at`. Evidence may select a registered
edition with `SourceEvidence.source_edition_key`; otherwise it inherits the claim edition. Original
source wording remains distinct from both the normalized entity key and the evidence excerpt.

Entity keys apply only Unicode normalization and whitespace normalization. They remain
case-sensitive because case can change scientific meaning (for example, units `M` and `m`). They do
not infer scientific aliases. Thus `SST` and `sea surface temperature` remain distinct until an
explicit, reviewed alias mechanism exists.

Migrations are packaged SQL files recorded in `schema_migrations`; initialization is repeatable on
new databases and databases created by the earlier inline schema.

## Source-edition and duplicate behavior

A source edition is idempotent only when all identity fields match. Reusing `(paper_id,
edition_key)` with a different type, URI, content hash, label, or primary flag is an explicit
conflict. The same content hash cannot be assigned to two papers. DOI normalization and paper-level
conflict behavior remain controlled by the existing ingestion service.

arXiv URLs, prefixes, case, and version suffixes normalize to a stable base-work identity. Changed
content using the same identity conflicts instead of creating another paper.
`paper_identifiers` maps every normalized DOI and arXiv alias to one stable paper ID, so a work first
seen with DOI plus arXiv cannot later be duplicated through an arXiv-only import.

A bibliography-only `INGESTED` DOI record may be upgraded in place by an `EXTRACTED` record with
primary-author evidence. Its paper ID and metadata edition remain stable. Missing primary
bibliography fields inherit metadata claims; differing primary-source bibliography can replace
secondary metadata in the canonical record. The earlier metadata value and evidence remain in the
edition-scoped field-state ledger. Other changed duplicates remain conflicts.

The issue #13 boundary is `CorpusManifestEntry`: manifest ID; DOI, arXiv ID, or title identity;
source edition with optional URI/content hash/version; and an optional schema-validated
`PaperRecord`. Batch discovery and lifecycle orchestration remain issue #13 work.

## API

- `GET /api/research/entities` supports type filtering, conservative name search, and pagination.
- `GET /api/research/entities/{id}` returns cross-paper mentions and their evidence.
- `GET /api/research/papers/{paper_id}` returns editions, all canonical field states, mentions, training claims,
  results, limitation/future-work statements, and explicit entity relationships.
- `POST /api/research/papers/{paper_id}/source-editions` registers an exact-idempotent edition.
- `POST /api/research/papers/{paper_id}/relationships` records an explicit evidence-backed entity
  relationship. No edge is inferred from parallel lists or co-occurrence.

## Consequences and integration requirements

- The SQLite adapter supplies the issue #11 interface. A PostgreSQL/Supabase adapter must preserve
  the same uniqueness and evidence semantics.
- Existing records are projected when reingested. This migration does not retroactively project all
  pre-existing rows; a future maintenance backfill should call `sync_research_record` after schema
  validation.
- The current `PaperRecord` does not associate a specific metric/dataset/variable tuple with each
  free-text result. Those foreign keys intentionally remain null rather than guessing a join.
- Issue #19 must produce the canonical `PaperRecord` and must not write these normalized tables
  directly. After #19 lands, its ingestion path must call the repository projection boundary and
  pass the exact PDF/supplement edition identity. Evidence spanning primary and supplementary
  sources must use `source_edition_key` after both editions are registered. Re-syncing one edition
  replaces only that edition's projection. No issue #19 implementation was copied here.
