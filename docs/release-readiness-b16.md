# B16 local release readiness — 2026-09-28

This is a staging collection for inspection, not a scientifically certified release.
The workbook is committed without alteration at
`import_staging/Ocean_Research_Intelligence_ENRICHED_B16.xlsx` (SHA-256
`084ecf1c254b1044c4e3075b97e79dac9f5522b5821aa8cbb5b05b27c1f0238f`).

## Current local database

| Measure | Count |
|---|---:|
| Papers | 115 |
| B16 `SCIENTIFIC_CLAIMS` worksheet rows | 1,936 |
| Value-bearing candidate claims | 1,867 |
| Absence markers, not claims | 69 (55 `NOT_EXTRACTED`, 14 `NOT_REPORTED` candidates) |
| Field-level audit events | 94 historical events for 68 distinct audited claims |
| Audited claims `VERIFIED` / `PARTIALLY_VERIFIED` | 39 / 2 |
| Audited claims `NOT_VERIFIED` / `EXTRACTION_ERROR` | 2 / 25 |
| Entirely verified papers | 0 |
| Partially verified papers | 2 (OAI-0001, OAI-0002) |
| Papers blocked by audited extraction errors | 2 (OAI-0001, OAI-0002) |
| Other papers with visible imported conflict reviews | 3 (OAI-0013, OAI-0077, OAI-0089) |
| Papers not yet field-audited | 113 |

Extraction is a separate axis: 9 `NOT_EXTRACTED`, 85 `PARTIAL`, 21
`READY_FOR_AUDIT`. None has a documented full field-by-field completeness
review. `READY_FOR_AUDIT` means usable leads exist (scope, primary-source
basis, locators), not that the extraction is finished. The 21 candidates are:
OAI-0001, OAI-0003, OAI-0005, OAI-0013, OAI-0017, OAI-0021, OAI-0022,
OAI-0026, OAI-0028, OAI-0045, OAI-0054, OAI-0059, OAI-0064, OAI-0077,
OAI-0089, OAI-0093, OAI-0095, OAI-0099, OAI-0100, OAI-0111 and OAI-0113.

The OAI-0001 and OAI-0002 audit reports distinguish author paper, supplement
and code inspection status. The decisions bind to the imported value, unit,
experiment and path. They are partial audits, not PAPER-level completion
attestations. `NOT_REPORTED` markers remain candidates until a documented,
sufficient source review supports the negative finding.

## Branch and gate status

- **PR #35**, branch `claude/issue-13-import-b15`, now carries B16, the audit
  ledger and the Next.js corpus workspace. It is a **draft**, not merge-ready.
  Local Python tests (269), frontend tests (8), typecheck and production build
  pass. Independent QA found and reproduced a timezone-ordering defect in the
  audit ledger; it is corrected with an absolute-time regression test, pending
  QA rerun. A Sourcery static-analysis check currently reports a dynamic-SQL warning
  at claim filtering; that path builds column names from a fixed tuple and binds
  all user values as query parameters. It still needs review/closure in the PR.
- **PR #36 (#11)**, branch `codex/issue-11-research-model`, preserves the
  existing worktree implementation and is now a separate draft PR based on
  current main. Two data-integrity regressions were corrected: primary-edition
  bibliography provenance and controlled-upgrade rollback on a source-edition
  collision. Its own suite passes 272 tests after the main merge. A temporary
  cross-branch merge with PR #35 passes 286 Python tests, 8 frontend tests,
  typecheck and build. A full V1→B16 import and no-op B16 reimport also pass
  in that combined tree; running its migration runner on the populated corpus
  preserves all 115 staging papers. Independent QA and merge review are still
  required. Field-path canonicalisation is only a versioned *proposal*, not a
  scientifically validated #29 projection. PR #36 now includes numbered
  migration `0003_staging_corpus` (#30); its combined-tree QA rerun is pending.
- **#19/#31**, branch `codex/issue-19-scientific-extraction-clean`, is preserved
  with two local commits ahead of its remote. Its earlier independent scientific
  review failed (precision 29.17%, recall 15.91%, exact match 19.23%,
  evidence-location accuracy 0% in that run), and its provider credits were
  blocked. The extraction engine is not promoted to this release.
- The project-required independent QA rerun and Scientific Auditor revalidation
  *after* the latest B16 changes did not complete: the role-specific child
  sessions hit quota. Existing OAI-0001/OAI-0002 audits remain recorded with
  their actual auditor identity and date; software tests do not replace those
  missing final gates. Runtime effective model metadata was not exposed, so no
  claim about realized model or quota separation is made.

## Update — 2026-09-28 afternoon (independent QA and #29 pre-review)

### Combined PR #35 + PR #36: independent QA **PASS**

A session that authored neither PR merged #36 (`1466667`) into #35 (`dd611bc`)
in a separate worktree (local merge `a953938`, not pushed; no existing worktree
or untracked file was touched). The merge is conflict-free. 290 Python tests,
8 frontend tests, typecheck and build pass. The data checks
(`evaluation/qa/combined_merge_check.py`, results in
`evaluation/reports/pr35-pr36-combined-qa-2026-09-28.json`) pass 40 of 40 on a
**copy** of the local B16 database; the original is unchanged
(SHA-256 `e4f760d1…8f4cd9` before and after):

- migration `0003_staging_corpus` on the populated B16 database is recorded,
  leaves every `staging_corpus_*` table byte-identical, is a no-op when rerun,
  and keeps the append-only audit triggers;
- catalogue reads (7 API routes and `CorpusRepository`) on an absent database
  return 200 and create neither the file nor its directory; reads on a
  populated database leave it byte-identical;
- B16 reimport: zero created/updated rows, 115 papers, 1,867 claims,
  69 markers, no duplicate DOI; **all 94 audit events preserved**;
- report replay with the three hash-pinned PDFs adds no event (still 94);
  a PDF whose hash differs is refused;
- a fresh V1→B16 build plus replay gives 68 events for 68 claims, and serves
  the same B16 mapping version (981 rules, all `PENDING`); no paper is
  `FULLY_VERIFIED` and no mapping rule is `VALIDATED`.

Open finding before merge: the staging DDL exists twice (`SCHEMA` in
`corpus/repository.py` and `migrations/0003_staging_corpus.sql`). They are
identical today, but nothing prevents drift. After the merge, load one from the
other or add an equality test.

### #29 field-path mapping: pre-review done, human validation still required

`evaluation/field_mapping/` holds a versioned `AI_INTERPRETATION` pre-review of
all 981 B16 `FIELD_PATH_MAP` rules (`build.py` + `proposals.py` reproduce it
from the database, read-only). Policy: map only synonyms or container fields
whose original path stays the visible qualifier; leave component-, stage-,
variant-, horizon- and max-vs-actual-qualified paths pending; never project
AI interpretations, conflict notes, search-space or unlinked code config.

An independent Scientific Auditor (Claude subagent, no PDF access; judgement on
field semantics against stored claim text only) read every claim under every
non-identity rule. It concurred with 356 of 378 and dissented on 22; all 22
dissents were accepted and returned to pending.

| Proposed decision | Rules | Claims |
|---|---:|---:|
| Identity (already a contract path) | 72 | – |
| MAPPED, auditor concurred | 325 | 541 |
| UNMAPPED, with reason | 17 | – |
| Pending (incl. 14 guard blocks, 22 auditor dissents) | 567 | – |

**No rule is `VALIDATED` and no projection is applied.** #29 requires a human
to validate each rule (CSV has `human_decision` / `human_reviewer` /
`reviewed_at` columns). The auditor also flagged claim-level items for the
human reviewer (values taken from open-review author replies B05-0149/0150/0151,
inferred row assignments B14-0012/B12-0003, B06-0137 possibly a sweep point)
and guard gaps to close before any projection code is written (`CODE_REPOSITORY`
scope into `data.*`, review scopes into non-results fields, conflict notes on
single-value fields, stage qualifiers without experiment IDs).

### #19/#31: not started, gates not met

The #19 remediation (`8b015e5`, `6af7867`) has never been benchmarked: the
required provider run is blocked by credit/quota, and the last independent
scientific review failed. #31 depends on #19. Neither was touched.

## Next work, in order

1. ~~Independent QA of PR #36 and its combined head with PR #35~~ — done
   2026-09-28 (PASS, above). Remaining: close the SCHEMA/0003 duplication, PR
   review of both drafts, and the Sourcery dynamic-SQL note on #35.
2. Human validation of the #29 pre-review (`evaluation/field_mapping/*.csv`),
   starting with the 325 auditor-concurred rules; then implement projection with
   the guard gaps above closed, keeping each original path and wording.
3. Obtain and hash-pin primary PDFs, supplements and relevant code for the
   21 audit candidates. Check every populated claim and every required absence
   against its exact edition, page/section/locator, value, unit and experiment;
   record independent decisions and paper-level completeness separately.
4. Correct OAI-0001/OAI-0002 extraction errors as new versioned import rows;
   re-audit changed rows. Resolve the three explicit conflict reviews without
   suppressing either side. Expand the curated golden dataset and benchmark
   any extraction-logic change before accepting #19/#31.
5. Run independent adversarial QA and scientific audit on final branch heads,
   close PR checks, then consider merges. Reimport B16 once more and verify
   zero created/updated rows and unchanged audit-event count.

See [corpus-import.md](corpus-import.md) for exact import, audit replay,
launch and incremental-update procedure.
