# ADR 0001: Local persistence and server-rendered milestone UI

- Status: Accepted
- Date: 2026-09-17
- Scope: Milestone issue #2

## Context

The preferred production stack is PostgreSQL/Supabase plus a Next.js client, but the first
vertical slice must run locally without credentials or an external service. Its main purpose is
to prove safe ingestion, persistence, retrieval, and scientific traceability.

## Decision

Use FastAPI for the API and a SQLite repository adapter for local persistence. Serve one minimal
paper detail page from FastAPI. Keep metadata lookup, parsed-payload validation, and persistence
behind explicit interfaces so PostgreSQL, GROBID, and a Next.js client can replace these adapters
without changing the ingestion rules.

SQLite stores the canonical `PaperRecord` as validated JSON. DOI identities are normalized and
unique; DOI-less records use a canonical content hash. Repeating an identical ingest is
idempotent, while reusing an identity with different content returns an explicit conflict rather
than overwriting scientific claims.

## Consequences

- A developer can run and test the slice with no database account.
- The API contract and provenance behavior are available for a future Next.js client.
- SQLite is a development adapter, not the final collaborative database.
- The server-rendered page is intentionally minimal and will be replaced rather than expanded.
