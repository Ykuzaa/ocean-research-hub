# Issue triage, 2026-10-15

Every open issue, with a verdict and the evidence behind it. Written after the corpus v2
run (43 records, 1,424 sourced claims, every claim re-checked against its paper) and
after the mapping-audit work was finished and made green.

The GitHub writes themselves — pushing the branch, merging the two pull requests, closing
these issues — were **refused by this session's permission classifier** ("merge without
review"). Nothing here has been pushed, merged or closed. This document is what to act on,
and `docs/merge-plan.md` is the exact sequence.

Four verdicts are used:

- **DONE** — delivered; the evidence says by what.
- **SUPERSEDED** — the goal was met another way, and the original plan should not be
  resumed.
- **BLOCKED** — cannot be done here; says what would unblock it.
- **REMAINS** — still open, with its scope narrowed to what is actually left.

| # | Title | Verdict |
|---|---|---|
| 11 | P1 canonical data model | DONE (PR #36 + corpus v2) |
| 12 | P3 workspace, universal search | REMAINS (narrowed) |
| 13 | P2 literature discovery and bulk ingestion | DONE, with #32 as its ceiling |
| 14 | P4 research analytics | DONE (`/analyse`, public page) |
| 19 | P0 accurate PDF extraction | SUPERSEDED (gate + independent re-check) |
| 20 | ROADMAP | REMAINS (update the plan of record) |
| 22 | P5 entity pages | DONE (`/analyse/<kind>/<name>`) |
| 23 | P6 problems and gap explorer | DONE (`/analyse`) |
| 24 | P7 Ask the Literature | REMAINS (narrowed to a deterministic query layer) |
| 25 | ENG1 Codex/Claude workflow | DONE (AGENTS.md + agent and extraction contracts) |
| 29 | P1.1 map the 713 staging field paths | DONE for the machinery; data work not worth doing |
| 30 | P1.2 staging tables into the migrations runner | DONE (PR #36) |
| 31 | P0.1 verify staging claims | SUPERSEDED (re-extracted from the PDFs instead) |
| 32 | P2.1 full text for blocked papers | BLOCKED (institutional access) |
| 33 | P2.2 extraction spec and workbook corrections | SUPERSEDED (SCHEMA.md + RECHECK.md) |
| 34 | P2.3 staging importer hardening | SUPERSEDED (staging is read-only) |

## #11 — P1: canonical data model · DONE

PR #36 carries the edition-aware research model, the numbered migrations runner and the
rollback-safe upgrade path; its branch is green on its own (273 tests) and merges cleanly
with the corpus v2 line (464 tests together, conflicts only in `README.md` and `api.py`,
both resolved automatically). Corpus v2 is the model of record for *extracted science*:
the unit is the experiment and the result, and `evaluation/gold_v2/SCHEMA.md` is its
contract. Close once #36 is merged.

## #12 — P3: workspace, universal search · REMAINS, narrowed

Delivered: `/corpus` (free-text search over the whole record, facets by objective and
architecture), `/corpus/<slug>` (every experiment, setting and result with its source
sentence), `/analyse` (entity-first navigation), `/revue` (the audit queue).

Not delivered: the app shell the issue describes — command palette, saved views, column
presets, cross-entity filter state. That is real work and nothing in the corpus blocks it.
Keep the issue, with its scope reduced to the shell.

## #13 — P2: discovery and bulk ingestion · DONE, with #32 as its ceiling

`corpus_v2.fetch_oa` resolves DOIs through OpenAlex, prefers open hosts, validates the
`%PDF` magic bytes so a paywall page cannot pass as an article, de-duplicates by sha256
and writes a manifest with a per-paper state. Run over the 82 indexed DOIs it reached 37.
It sends no `mailto`, so no address of yours reaches a third party. The remaining 45 are
#32, which no pipeline can fix.

## #14 — P4: research analytics · DONE

`/analyse` and the public page answer the issue's questions without confusing frequency
with superiority: reporting rates per architecture and per objective, the task x
architecture coverage matrix, the limitation taxonomy, and the comparability finding —
**0 shared (dataset, metric, unit) cells out of 117**, stated wherever a number could be
mistaken for a ranking.

## #19 — P0: accurate PDF extraction · SUPERSEDED

The plan was provider-API extraction, and it was blocked on credits. What replaced it:
extraction by subagents against a written contract, a deterministic gate that re-locates
every quote on the page it cites, and a second independent machine reading of all 1,424
claims. Measured: 0 gate failures, 36 flags, all of them ruled on, 31 of which were real
defects now corrected. Cost: no provider credit. Close it; keep
`codex/issue-19-scientific-extraction-clean` as history.

## #20 — ROADMAP · REMAINS

M2 as written is complete, but the plan of record still describes manual web-app
extraction and an API pipeline on the critical path. It should be rewritten around the
three states this project actually distinguishes — **sourced → re-checked → audited** —
and around the real ceiling: 37 of 82 papers reachable, 0 claims audited by a human.

## #22 — P5: entity pages · DONE

`/analyse/<kind>/<name>` for architecture, objective, data source, variable and named
method: paper count, experiments, datasets, metrics, reporting rates, and the limitations
stated in those papers with their quotes. The "later-compatible" entities (regions,
metrics, losses, optimizers) are not built; the index supports them.

One finding from building it: a page keyed on the dataset name read from each paper is
almost always a page about one paper, because every team names the same source
differently. `dataset_group` gathers names by source with explicit keyword rules — 12
sources of 61 names appear in more than one paper — and never overwrites the names read.

## #23 — P6: problems and gap explorer · DONE

Part A: author-stated limitations grouped by theme, each with its sentence and page. The
clean-up that made this honest removed 19 "limitations" that were future-work promises,
data-availability statements, positive results or performance measurements.

Part B: the coverage matrix shows 111 empty cells out of 154, with the caveat attached to
the data, not to a footnote — an empty cell is a gap in this corpus, not a demonstrated
opportunity.

## #24 — P7: Ask the Literature · REMAINS, narrowed

Not built, and the version in the issue needs a model at query time, which there is no
budget for. The honest version is deterministic: a question maps to filters and
aggregations over the claims, and the answer is a list of quoted claims with their pages.
`/corpus`'s search is the first step of that; the aggregation layer (`corpus_v2.entities`)
is the second.

## #29 — P1.1: map the 713 staging field paths · DONE for the machinery

The audit machinery is complete and green: hash-pinned evidence sources validated in
Python, append-only decisions, dissent kept with the prior decision superseded, stale
detection against the mapping version, CLI replay and an observable API route. Six
adversarial regressions that had never passed now pass.

The data is at `PROPOSAL_PENDING_INDEPENDENT_VALIDATION`: 981 rules, 325 mapped and
concurred, 567 ambiguous, 17 unmapped, 14 guard-blocked.

**Recommendation: do not finish the data work.** It would map a corpus with 0 verbatim
quotes and ~39% unconfirmed claims on the audited sample — the corpus that corpus v2
replaced by re-reading the PDFs. Close #29 on the machinery, and archive the staging
corpus (see #31). If you disagree, the machinery is ready and needs no credits.

## #30 — P1.2: staging tables into the migrations runner · DONE

PR #36 carries `feat(#30): register staging corpus in numbered migrations`. Close with #36.

## #31 — P0.1: verify staging claims · SUPERSEDED

The staging claims cannot be verified as they stand: they carry no verbatim quote, so
there is nothing to re-locate. Rather than audit paraphrase, the reachable papers were
re-read from their PDFs into corpus v2. Archive the staging corpus read-only as an
evaluation set and close this.

## #32 — P2.1: full text for blocked papers · BLOCKED

Now measured exactly: of 82 indexed DOIs, **37 are reachable**, 28 are publisher-blocked
and 17 have no deposited version. No method available here changes that, and nothing was
read from an abstract to fill the gap. This needs institutional access, and it is the real
limit of the project.

## #33 — P2.2: extraction spec and workbook corrections · SUPERSEDED

The spec now exists as `evaluation/gold_v2/SCHEMA.md` (contract, vocabularies, nine
arbitration rules, filling rules), `evaluation/gold_v2/RECHECK.md` (the independent
re-check contract) and `.claude/agents/paper-extractor.md`. The listed corrections are
about staging workbooks that are being archived; the defects behind them (a dataset period
filed as a training split, a hedge dropped, `NOT_REPORTED` used for "not applicable") are
exactly what the new rules forbid.

## #34 — P2.3: staging importer hardening · SUPERSEDED

Small QA points on an importer whose corpus becomes read-only. Not worth the change risk;
close with the reason, reopen if staging ever becomes live again.
