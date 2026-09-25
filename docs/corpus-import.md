# Staging corpus import (issue #13)

`ocean-research-hub-import-corpus` imports the research staging workbook
`import_staging/Ocean_Research_Hub_COMPLET.xlsx` (SHA-256
`399cb1b51e3cec48f97cd990c83626b6600ea2ceeab3f7195c4acfbc0b5612d5`) into the
application database and serves it through the API and website.

```bash
uv run ocean-research-hub-import-corpus import_staging/Ocean_Research_Hub_COMPLET.xlsx --dry-run  # checks against the DB, writes nothing
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

## Supplement workbook: EXPANDED_V2

`import_staging/Ocean_Research_Intelligence_EXPANDED_V2.xlsx` (SHA-256
`7fa77bcda168007e99974d37fea32d5ffe7214e158ce1cc4f684facb0f4abb28`) enriches the
same 115-paper corpus. It is imported **on top of** the base workbook:

```bash
uv run ocean-research-hub-import-corpus import_staging/Ocean_Research_Intelligence_EXPANDED_V2.xlsx \
  --database .data/ocean-research-hub.db --report-out .data/corpus-import-v2-report.json
```

Against V1, the PAPER_INDEX and RESEARCH_GAPS sheets are identical and the 144 V1
claims are byte-identical. It adds 114 claims (`WEB2-0001`..`WEB2-0114`), which
brings the corpus to 258 claims. Papers with at least one claim go from 7 to 20.
The import result is `claims.created = 114`, `claims.unchanged = 144`,
`papers.unchanged = 115`, and no aliases. A second import changes nothing.

It has no `PAPER_RECORDS`, `FIELD_CONTRACT` or document sheets. It adds
`COVERAGE` and `NEW_DETAILED_PAPERS`. A workbook with that layout is read as a
**supplement**:
- It is validated against the stored base corpus inside the import transaction.
  If no base corpus is stored, or a paper is not already in the corpus, the whole
  import is refused. A supplement carries no record, so it cannot introduce a paper.
- START_HERE counts are checked (`Papers indexed`, `Claims total`,
  `Detailed papers now`, `New detailed papers`, before + added = total). Each
  COVERAGE `claim_count` must equal the paper's claim rows.
- Stored records are kept as the base package supplied them. For example,
  `detail_extraction_status` stays `NOT_EXTRACTED` for the 13 newly detailed papers.
  COVERAGE `coverage_level` / `audit_state` rows are stored in
  `staging_corpus_paper_coverage` and served as `coverage`, beside those values and
  not in place of them.
- A new claim is shown under the contract field named by its `field_path`. The
  claims `WEB2-0072` (`rl.action`), `WEB2-0073` (`rl.reward`) and `WEB2-0114`
  (`reproducibility.code`) use paths outside the 162-field contract. They are kept
  verbatim, served as `uncontracted_claims`, reported in the import warnings, and
  mapped to no field. Extending the contract is a #11 decision.
- The new claims carry `independent_audit = PENDING_PDF_AUDIT`. That value is a
  pending marker, not an attestation.
- START_HERE and NEW_DETAILED_PAPERS are stored as documents keyed by workbook
  name, so the base package's documents are not replaced.

## Supplement workbook: ENRICHED (batches B03-B07)

`import_staging/Ocean_Research_Intelligence_ENRICHED.xlsx` (SHA-256
`7265fd1674ff7810706f5984cd3cace364e06b3cedf9344355a20d7c5ca6b65f`) is imported
on top of V1 and EXPANDED_V2. It has 1497 SCIENTIFIC_CLAIMS rows: the 258 earlier
claims (unchanged), 1187 new extracted claims, and 52 field-status markers. The
import result is `claims.created = 1187`, `claims.unchanged = 258`,
`field_markers.created = 52`, `research_gaps.created = 9`, `papers.updated = 67`
(the PAPER_INDEX extraction status and notes changed; nothing is audited) and no
aliases. A second import changes nothing. Totals: 115 papers, 1445 claims,
87 papers with claims, 17 research-gap candidates.

- **New claim columns** `unit`, `extraction_status`, `extracted_on` and
  `batch_id` are served on each claim. An empty optional column is ignored by the
  fingerprint, so the 258 earlier claims stay unchanged.
- **Field-status markers.** The 52 B03 rows whose `extraction_status` is
  `NOT_EXTRACTED` (46) or `NOT_REPORTED` (6) are not claims. Their value is the
  status itself. They are stored in `staging_corpus_field_markers` and served as
  `markers` on the field, never as values. The field status is computed as follows:
  - only `NOT_EXTRACTED` markers: `NOT_EXTRACTED`;
  - only `NOT_REPORTED` markers: `NOT_REPORTED_CANDIDATE`, which stays
    `NOT_VERIFIED` and carries its `section_or_scope` and `notes` as supplied
    (the notes usually state what was searched, for example "main text and
    appendices; code not inspected");
  - a `NOT_REPORTED` marker beside an extracted claim:
    `NOT_REPORTED_CANDIDATE|NOT_VERIFIED`. Both are shown. This is not `CONFLICT`:
    the two usually cover different scopes. In OAI-0010 `training.training_time`,
    the fine-tuning time was extracted and the total training time was not found.
    `CONFLICT` is reserved for the paper disagreeing with itself.
  - a marker's own `EXTRACTION_ERROR` or `CONFLICT` status is added to the field status.

  A marker that carries a value other than its status is refused. So is an
  unknown `extraction_status`. The COVERAGE `claim_count` excludes markers, as
  START_HERE says.
- **Shifted research-gap rows.** B04-G01..G04 are stored as
  (gap id, paper id, question, status, "URL | section") under the
  (topic, question, basis, status, qualification) header. Only that exact shape
  is realigned. The original cells are kept in `realigned_from`, and the import
  reports the change. Any other malformed gap is still refused. A gap whose
  status says `AI_INTERPRETATION` is served with that provenance, not `TEAM_NOTE`.
- **PDF pages.** 291 claims carry a `pdf_page` supplied by the package. It is
  stored as supplied and is unchecked. No verbatim quotation is present.
- **Outside the contract.** 955 claims use 672 field paths that are not in the
  162-field contract (for example `loss.total`, `architecture.family`,
  `datasets.split`). They are served as `uncontracted_claims`. None is mapped.
- `SOURCE_ACCESS`, `FIELD_COVERAGE` and `NEW_DETAILED_PAPERS` are stored whole, as
  documents keyed by workbook name.

## Supplement workbook: ENRICHED_B08

`import_staging/Ocean_Research_Intelligence_ENRICHED_B08.xlsx` (SHA-256
`e9fbd101d0af507a8b33013ba9eb914d8057c7acb2d35f7634a7107003f1b7b1`) is
ENRICHED plus batch B08: 82 rows, of which 75 are claims and 7 are markers
(5 `NOT_REPORTED`, 2 `NOT_EXTRACTED`). It updates 6 papers
(OAI-0021/0022/0058/0093/0095/0112) and adds the `CHANGE_LOG` and `BATCH_LOG`
sheets, which are stored as documents. The import result is `claims.created = 75`,
`field_markers.created = 7`, `papers.updated = 6`, and a second import changes
nothing. Totals: 115 papers, 1520 claims, 59 markers, 93 papers with claims,
17 gaps.

The package counts its 7 new markers as extracted rows (1527 + 52 = 1579),
both in START_HERE and in COVERAGE, while it excludes the 52 inherited B03 markers.
A declared count is accepted when marker rows alone explain the difference, and
the import reports it. A difference that marker rows cannot explain is still
refused.

## Scientific integrity rules the importer enforces

- **Nothing is promoted.** All claims (144 base, 258 after V2, 1445 after ENRICHED) arrive `NOT_VERIFIED` /
  `PENDING_INDEPENDENT_AUDIT` and stay that way. A workbook row claiming
  `VERIFIED`, `PARTIALLY_VERIFIED` or `NOT_REPORTED` is **refused**: a staging
  package has neither an independent attestation nor a documented search scope.
- **Missing is `NOT_EXTRACTED`.** A field whose record slot lists no claim is
  served as `NOT_EXTRACTED`, never `NOT_REPORTED`.
- **No invented evidence.** `pdf_page` and `verbatim_evidence` are stored as
  supplied, with surrounding whitespace trimmed (a whitespace-only cell is empty).
  They are null for the 258 V1/V2 claims. ENRICHED and B08 supply pages for 334
  claims and quotations for none.
- **Disagreements stay visible.** For 7 papers, PAPER_INDEX says `NOT_AUDITED`
  and PAPER_RECORDS says `PENDING_INDEPENDENT_AUDIT`. Both values are stored and
  served, and each import reports the disagreement. The claim type
  `AUTHOR_REPORTED_FUTURE_WORK`, which is not an AGENTS.md provenance class, is
  preserved verbatim and reported, not remapped.
- **Research-gap candidates are team hypotheses** (`TEAM_NOTE`) **or AI
  interpretations** (`AI_INTERPRETATION`, when the row's status says so). They
  are served from their own endpoint with a provenance column, never mixed into
  claims or author-reported limitations. A gap replaced by a later workbook is
  reported.
- **A workbook cannot carry an attestation.** Only pending audit markers are
  accepted: `NOT_AUDITED`, `PENDING_INDEPENDENT_AUDIT`, `PENDING_PDF_AUDIT` or
  `PDF_AUDIT_PENDING`, in a claim's or marker's `independent_audit` and in a paper's
  `scientific_audit_status`. Anything else is refused. Otherwise the row would be
  locked against correction.
- **Audited rows are never overwritten.** A staging paper or claim that received
  an audit attestation after import (`VERIFIED`, `PARTIALLY_VERIFIED`, `AUDITED`,
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
- a claim has a refused or unknown status, a non-pending `independent_audit`, an
  unknown `extraction_status`, or a status word (`NOT_REPORTED`, ...) as its value;
- a worksheet repeats a column header;
- a gap cites an unknown paper, has no testable question, or has a status that
  claims validation.

Checks against the stored corpus (also run by `--dry-run`, on a throwaway copy of
the database):
- a supplement names a paper that is not stored under that ID or a known alias,
  or changes a stored paper's title, DOI or year;
- a DOI already belongs to another stored paper;
- a stored claim or marker ID arrives with another paper, another field path, or
  the other kind (claim versus marker);
- the workbook would revert a row to content that an earlier import already
  replaced (see below).

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
- **Older packages are refused.** Every fingerprint a row has ever had is kept in
  `staging_corpus_row_versions`. An import that would set a row back to an earlier
  version is refused. Examples: re-importing V1 after ENRICHED, or V2 after
  ENRICHED or B08, would revert 67 papers.
  - `--allow-revert` applies such rows anyway: for a newer package that
    deliberately returns to an earlier value, or to undo a mistaken import. Every
    reverted row is listed in the run's warnings.
  - A database built before versions were kept only knows its rows' *current*
    state. The versions it replaced earlier are unknown, so the older packages it
    was built from would not be caught. `--record-versions WORKBOOK` records the
    versions of an already-imported workbook without importing it. A workbook that
    is not in the import history is refused, so a newer package cannot be blocked
    in advance. The live database was treated this way for V1, V2 and ENRICHED.
  - Versions are recorded during imports only. Reading the corpus never writes.

Known limitations (confirmed by QA and deliberately not handled):
- Swapping the DOIs of two stored papers in one base workbook is refused as a
  collision, because the unique DOI index is checked row by row. Such a
  correction needs a manual migration.
- The count checks catch missing or truncated rows. When a package counts
  markers as extracted rows (see ENRICHED_B08), they cannot tell a claim from a
  marker within a new batch. A marker must still carry its status word as its
  value, so it can never pass for a value. A stored claim that turns into a
  marker is refused.

## API and website

| Route | Content |
|---|---|
| `GET /api/corpus` | counts, claim-status distribution, last import run, staging notice |
| `GET /api/corpus/papers?q=&domain=&review_stage=&limit=&offset=` | paper listing |
| `GET /api/corpus/papers/{paper_id}` | full record: 162 fields with status, candidate claims with evidence, experiments, aliases, linked PaperRecord (alias IDs resolve) |
| `GET /api/corpus/claims?paper_id=&field_path=&experiment_id=` | claims |
| `GET /api/corpus/claims/{claim_id}` | one claim with source URL, DOI, edition, section, locator, page, quotation, notes |
| `GET /api/corpus/fields` | the 162-field contract |
| `GET /api/corpus/research-gaps` | the 17 research-gap candidates with their provenance |
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
