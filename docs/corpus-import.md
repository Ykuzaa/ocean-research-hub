# Staging corpus import (issue #13)

`ocean-research-hub-import-corpus` imports the research staging workbook
`import_staging/Ocean_Research_Hub_COMPLET.xlsx` (SHA-256
`399cb1b51e3cec48f97cd990c83626b6600ea2ceeab3f7195c4acfbc0b5612d5`) into the
application database and serves it through the API and website.

```bash
uv run ocean-research-hub-import-corpus import_staging/Ocean_Research_Hub_COMPLET.xlsx --dry-run
uv run ocean-research-hub-import-corpus import_staging/Ocean_Research_Hub_COMPLET.xlsx \
  --database .data/ocean-research-hub.db --report-out .data/corpus-import-report.json
```

`--database` defaults to `$OCEAN_HUB_DB_PATH`, the same database the API reads.

## What is imported

| Worksheet | Stored as | Count |
|---|---|---:|
| `PAPER_INDEX` + `PAPER_RECORDS` | `staging_corpus_papers` (index row and full record JSON, both kept) | 115 |
| `SCIENTIFIC_CLAIMS` | `staging_corpus_claims` (all 18 source columns kept verbatim) | 144 |
| `FIELD_CONTRACT` | `staging_corpus_field_contract` (order preserved) | 162 |
| `RESEARCH_GAPS` | `staging_corpus_research_gaps` (separate from claims) | 8 |
| `README`, `AUDIT_PROTOCOL`, `METHODS_GUIDE`, `START_HERE` | `staging_corpus_documents` | 4 |

Experiments are preserved as each claim's `experiment_id` and listed per paper
(for example `OAI-0006:FNO3D` and `OAI-0006:RFNO2D`).

## Scientific integrity rules the importer enforces

- **Nothing is promoted.** All 144 claims arrive `NOT_VERIFIED` /
  `PENDING_INDEPENDENT_AUDIT` and stay that way. A workbook row claiming
  `VERIFIED`, `PARTIALLY_VERIFIED` or `NOT_REPORTED` is **refused**: a staging
  package has neither an independent attestation nor a documented search scope.
- **Missing is `NOT_EXTRACTED`.** A field whose record slot lists no claim is
  served as `NOT_EXTRACTED`, never `NOT_REPORTED`.
- **No invented evidence.** `pdf_page` and `verbatim_evidence` are stored exactly
  as supplied. They are null for all 144 rows because the package performed no
  PDF alignment.
- **Disagreements stay visible.** For 7 papers, PAPER_INDEX says `NOT_AUDITED`
  and PAPER_RECORDS says `PENDING_INDEPENDENT_AUDIT`. Both values are stored and
  served, and each import reports the disagreement. The claim type
  `AUTHOR_REPORTED_FUTURE_WORK`, which is not an AGENTS.md provenance class, is
  preserved verbatim and reported, not remapped.
- **Research-gap candidates are team hypotheses** (`TEAM_NOTE`), served from
  their own endpoint, never mixed into claims or author-reported limitations.
- **Audited rows are never overwritten.** A staging paper or claim that carries an
  audit attestation (`VERIFIED`, `PARTIALLY_VERIFIED`, `AUDITED`,
  `INDEPENDENTLY_AUDITED`, `AUDIT_PASSED`, or any non-pending `independent_audit`)
  is skipped on re-import, and the skip is reported.
- **The canonical `papers` table (PaperRecord) is never written.** A staging
  paper whose DOI matches a canonical record is linked to it read-only
  (`linked_paper_record_id`).

## Integrity validation (all-or-nothing)

A workbook is refused, and nothing is written, if any of these hold:
- a worksheet is missing, or a required column is missing;
- a count contradicts START_HERE;
- a paper, claim or field ID is duplicated, or PAPER_INDEX and PAPER_RECORDS disagree on the paper set, title, DOI or year;
- two paper IDs share a DOI or a title+year;
- a record's fields differ from FIELD_CONTRACT;
- a claim is dangling or filed under the wrong record slot, or a claim uses a path outside the contract;
- a claim has a refused or unknown status;
- a gap cites an unknown paper.

The import runs in a single transaction.

## Idempotency and deduplication

- Every row has a content fingerprint. Re-importing the same workbook changes
  nothing and records a run whose counts are all `unchanged`.
- A changed, unaudited row is updated and counted.
- Rows missing from a later workbook are **reported** (`absent_from_source`) and
  **kept**, never silently deleted.
- A paper is resolved by staging ID, then existing alias, then normalised DOI,
  then normalised title+year. A title match never merges two works that both
  carry a DOI. A new ID that resolves to an existing work becomes an alias, so
  the work is never duplicated and the alias resolves in the API.
- Every run is logged in `staging_corpus_import_runs` with the workbook SHA-256.

## API and website

| Route | Content |
|---|---|
| `GET /api/corpus` | counts, claim-status distribution, last import run, staging notice |
| `GET /api/corpus/papers?q=&domain=&review_stage=&limit=&offset=` | paper listing |
| `GET /api/corpus/papers/{paper_id}` | full record: 162 fields with status, candidate claims with evidence, experiments, aliases, linked PaperRecord (alias IDs resolve) |
| `GET /api/corpus/claims?paper_id=&field_path=&experiment_id=` | claims |
| `GET /api/corpus/claims/{claim_id}` | one claim with source URL, DOI, edition, section, locator, page, quotation, notes |
| `GET /api/corpus/fields` | the 162-field contract |
| `GET /api/corpus/research-gaps` | the 8 team hypotheses |
| `GET /api/corpus/import-runs` | import history |
| `GET /corpus`, `GET /corpus/papers/{paper_id}` | server-rendered pages, each with the staging notice |

## Integration dependencies (not done here)

1. **#11 research-intelligence model (Codex, separate worktree, uncommitted).**
   #11 rewrites `api.py`, `ingestion/repository.py` and `schemas/paper_record.py`,
   and adds a migrations runner (`migrations/0001`, `0002`).
   - This branch leaves `repository.py` and `paper_record.py` alone. It adds four
     lines to `api.py`: an import, a `corpus_repository` parameter on
     `create_app`, and one `register_corpus_routes(...)` call. Expect a small,
     mechanical merge conflict there.
   - The `staging_corpus_*` DDL is `CREATE TABLE IF NOT EXISTS` inside
     `corpus/repository.py`. Once #11 lands, it should become a numbered migration
     in #11's runner. No table name collides with #11's.
   - #11's ADR lists a "future corpus-manifest source" kind for
     `source_editions`. Projecting staging claims into #11's normalised tables
     (`research_entities`, `entity_mentions`, `research_statements`) needs #11's
     contract, and must keep the claims `NOT_VERIFIED`. Not attempted here.
2. **#19 evidence gate.** Staging claims carry section anchors, not page-level
   quotations. Promoting any claim needs the #19 PDF relocation plus the
   independent Scientific Auditor. The importer has no promotion path by design.
3. **Field-contract mapping.** The 162 staging paths (`problem.task`,
   `data.input_variables`, ...) are not `PaperRecord` paths (`scientific_framing.task_type`,
   `data.inputs`, ...). The mapping is a scientific decision for #11; none is
   inferred here.
4. **Frontend workspace (#12).** The Next.js app currently serves the public
   landing only, and `/api/landing` aggregates canonical PaperRecords, so the
   staging corpus does not appear there, deliberately. The research workspace can
   consume `/api/corpus/*` directly.
5. **DOI identity against the live corpus.** Linking uses lowercase DOI equality
   against `papers.doi`. Identity resolution beyond DOI, title and year (for
   example arXiv versus version of record) is part of #13's discovery pipeline
   and not in this importer.
