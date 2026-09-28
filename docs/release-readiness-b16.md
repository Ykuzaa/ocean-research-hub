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
| Field-level audit events | 68 |
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
  Local Python tests (266), frontend tests (8), typecheck and production build
  pass. A Sourcery static-analysis check currently reports a dynamic-SQL warning
  at claim filtering; that path builds column names from a fixed tuple and binds
  all user values as query parameters. It still needs review/closure in the PR.
- **#11/#29/#30**, worktree `/home/n7student/ocean-research-hub-issue11`, is
  preserved with its staged and unstaged model/migration implementation; it is
  six main commits behind. Its independent local suite has 183 pass, 2 fail:
  provenance of missing primary-edition bibliography after metadata upgrade,
  and rollback of a controlled paper upgrade when source-edition insertion
  collides. These are data-integrity defects, so the worktree is not merged.
  Field-path canonicalisation is still only a versioned *proposal*, not a
  scientifically validated #29 projection. Numbered migration of the new
  staging tables (#30) is still outstanding.
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

## Next work, in order

1. Fix both #11 transactional/provenance regressions in its existing worktree;
   rebase carefully and run independent QA before a dedicated PR. Port staging
   DDL into its numbered migration runner without resetting the populated DB.
2. Independently review the 981 B16 `FIELD_PATH_MAP` rows, version decisions,
   leave ambiguous ones pending, and only then apply validated canonical
   projections. Preserve each original source path and wording.
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
