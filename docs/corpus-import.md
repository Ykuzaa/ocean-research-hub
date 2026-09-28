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

## Supplement workbook: ENRICHED_B16

`import_staging/Ocean_Research_Intelligence_ENRICHED_B16.xlsx` (SHA-256
`084ecf1c254b1044c4e3075b97e79dac9f5522b5821aa8cbb5b05b27c1f0238f`) is the
current cumulative supplement. Import it after B15:

```bash
uv run ocean-research-hub-import-corpus import_staging/Ocean_Research_Intelligence_ENRICHED_B16.xlsx \
  --database .data/ocean-research-hub.db --report-out .data/corpus-import-b16.json
uv run ocean-research-hub-import-corpus import_staging/Ocean_Research_Intelligence_ENRICHED_B16.xlsx \
  --database .data/ocean-research-hub.db --dry-run
```

B16 has 1,936 `SCIENTIFIC_CLAIMS` rows: 1,867 value-bearing candidate claims
and 69 absence markers. Relative to B15 it adds 121 claims, changes no existing
claim or marker, and updates five paper/coverage rows (OAI-0001, OAI-0003,
OAI-0045, OAI-0054 and OAI-0111). All claims remain `NOT_VERIFIED`. The
workbook supplies 482 page locators and no verbatim evidence. A page number is
an audit lead, not an attestation.

`FIELD_PATH_MAP` contains 981 source paths. Import stores every row as a
versioned `AI_INTERPRETATION` candidate. Exact contract-path matches may carry a
proposed canonical path, but every rule starts `PENDING`; only `VALIDATED`
rules are eligible for projection. The workbook never validates its own map.

## Recording an independent audit

Audits are append-only events bound to the exact imported row fingerprint and
reviewed value, unit, experiment and original field path. Later imports cannot
erase decisions; a changed row makes the earlier decision visibly stale. Prepare
one JSON object and append it:

```bash
uv run ocean-research-hub-audit-corpus audit-event.json \
  --database .data/ocean-research-hub.db
```

Every event identifies `target_kind` (`CLAIM`, `MARKER`, or `PAPER`),
`target_id`, `decision`, `justification`, `auditor_id`, timezone-aware
`audited_at`, provenance, source kind and exact source edition. `VERIFIED` and
`PARTIALLY_VERIFIED` require author-reported provenance, primary-paper,
supplement or author-code evidence, an evidence excerpt, and a page, section or
locator. `NOT_REPORTED` requires a documented `search_scope`. Corrections are
new events; SQL triggers reject update and delete.

Paper state has three independent axes:

- `extraction_completeness`: `NOT_EXTRACTED`, `PARTIAL`, or `READY_FOR_AUDIT`;
- `verification_state`: `NOT_VERIFIED`, `PARTIALLY_VERIFIED`, or
  `FULLY_VERIFIED`;
- `conflict_blocker_state`: `CLEAR`, `CONFLICT`, or `BLOCKED`.

`DETAILED` alone never makes a paper an audit candidate. The candidate rule
requires actual claims, a documented review scope, a full-text/code evidence
basis, and at least one locatable claim. No B16 paper has a documented
field-by-field completeness review spanning the paper, supplements and relevant
code, so `completion_candidate` is false for all 115 papers. `FULLY_VERIFIED`
requires a current independent PAPER-level `VERIFIED` completeness attestation
with documented scope, every claim to have a latest `VERIFIED` audit, and no
markers, conflicts, or blockers. A partial field audit cannot satisfy this gate.

The two independently authored reports currently available can be replayed
after importing B16. The PDFs are not bundled with the repository. Download
the exact editions from the report's `download_url` values and verify their
hashes before replay:

```bash
mkdir -p .data/golden-pdfs
curl -fL 'https://gmd.copernicus.org/articles/16/2119/2023/gmd-16-2119-2023.pdf' -o .data/golden-pdfs/4dvarnet-ssh-2023.pdf
curl -fL 'https://arxiv.org/pdf/2310.00813v2' -o .data/golden-pdfs/oceannet-2023.pdf
curl -fL 'https://media.springernature.com/original/springer-static/esm/art:10.1038%2Fs41598-024-72145-0/MediaObjects/41598_2024_72145_MOESM1_ESM.pdf' -o .data/golden-pdfs/oceannet-2023-supplement.pdf
sha256sum .data/golden-pdfs/4dvarnet-ssh-2023.pdf .data/golden-pdfs/oceannet-2023.pdf .data/golden-pdfs/oceannet-2023-supplement.pdf
```

The expected hashes, in that order, are
`bfad134ecdf1a4786ee4fdadc21746ab9e2106618513d8418a357cb39f9f0b88`,
`be82ff557769aff04b119490d6a2ebb718887a1e3962355ab10cc9a7291802e9`, and
`c3e7f690fab8563d4bfb2728a594bc2adb8e4d42a50872a1e0c97e34f4d7adbf`.
If any hash differs, stop; do not silently substitute a new edition. Then:

```bash
uv run ocean-research-hub-audit-report evaluation/reports/oai-0001-b16-scientific-audit.json --database .data/ocean-research-hub.db
uv run ocean-research-hub-audit-report evaluation/reports/oai-0002-b16-scientific-audit.json --database .data/ocean-research-hub.db
```

Replaying an unchanged report is idempotent. A correction to edition, locator,
evidence or justification appends a new versioned event while retaining the
old one; thus audit-event history can exceed the number of distinct audited
claims. The two reports audit 68 claims across two papers, not the entire
115-paper collection. They do not establish extraction completeness.

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
- **Audits are not overwritten.** Independent decisions are separate append-only
  rows. A changed imported row invalidates the currentness of its prior audit;
  the UI exposes `STALE_AUDIT` and keeps the decision history. Workbook-provided
  non-pending attestations remain refused.
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
| `GET /api/corpus/papers?q=&domain=&review_stage=&extraction_state=&audit_state=&limit=&offset=` | paper listing and operational-state filters |
| `GET /api/corpus/papers/{paper_id}` | full record: 162 fields with status, candidate claims with evidence, experiments, aliases, linked PaperRecord (alias IDs resolve) |
| `GET /api/corpus/claims?paper_id=&field_path=&experiment_id=` | claims |
| `GET /api/corpus/claims/{claim_id}` | one claim with source URL, DOI, edition, section, locator, page, quotation, notes |
| `GET /api/corpus/fields` | the 162-field contract |
| `GET /api/corpus/research-gaps` | the 17 research-gap candidates with their provenance |
| `GET /api/corpus/import-runs` | import history |
| `GET /api/corpus/field-mappings` | versioned, pending source-to-canonical mapping proposals |
| `GET /api/corpus/audits?target_kind=&target_id=` | immutable audit-event history |
| `GET /explore`, `/papers/{paper_id}`, `/claims/{claim_id}`, `/compare?left_id=&right_id=` | Next.js catalogue, paper, claim proof and comparison |

## Adding or completing a paper without losing history

1. Save the new source workbook as a new edition and record its SHA-256. Keep
   stable paper, claim, marker and experiment IDs. Add new IDs for new claims;
   do not recycle old IDs to mean something else.
2. Import with `--dry-run` against the existing database; inspect created,
   updated, unchanged, absent and conflicting rows. An older edition that would
   revert a row is refused unless `--allow-revert` is deliberately used.
3. Import the edition to the same database. Reimport it and confirm zero
   created/updated rows. Earlier rows and audit events remain in place; changed
   claims show stale audit decisions until independently rechecked.
4. For missing fields use `NOT_EXTRACTED` until a documented review of the
   relevant paper, supplement and code supports `NOT_REPORTED`. Record source
   edition, location and evidence per claim. Keep ambiguous mappings pending.
5. Ask an independent Scientific Auditor to inspect the primary sources and
   append field-level decisions. Record a separate PAPER-level completeness
   decision only after the field-by-field review is genuinely complete. Run QA
   and the extraction benchmark after material extraction-logic changes.

## Integration dependencies still open

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
4. **Frontend workspace (#12).** The Next.js catalogue and detail pages now
   consume `/api/corpus/*`. The public landing still aggregates canonical
   PaperRecords and must not be used as a staging-corpus count.
5. **DOI identity against the live corpus.** Linking uses lowercase DOI equality
   against `papers.doi`. Identity resolution beyond DOI, title and year (for
   example arXiv versus version of record) is part of #13's discovery pipeline
   and not in this importer.
