# The access ceiling, and what is actually left to do

This document replaces issue #32. The issue was closed on 2026-10-15 because its
automatable half is finished and the other half is not a task anyone can close by
working harder: it needs a login this repository does not have.

## What was re-tried, and what came back

Issue #32 listed 22 papers whose full text could not be read. Every one of them was
resolved again on 2026-10-15 through OpenAlex, trying every open-access location it
advertises, with `ocean_research_hub.corpus_v2.fetch_oa`. The result is versioned in
[`evaluation/access/blocked-retry-2026-10-15.json`](../evaluation/access/blocked-retry-2026-10-15.json),
one line per paper with the URLs actually tried:

| Outcome | Papers | Meaning |
|---|---|---|
| `DOWNLOADED` | **2** | a PDF was obtained, and both are now extracted into the corpus |
| `BLOCKED` | 8 | a location was advertised, none returned a PDF (403, or a paywall page in HTML) |
| `NO_OA_PDF` | 12 | OpenAlex advertises no open-access location at all |

The two recovered papers:

- **10.1093/nsr/nwag063** — *AI for atmosphere–ocean sciences*, National Science Review,
  found in a co-author institute's repository. It is a review: its authors train no model
  of their own, so it is in the corpus as an **excluded** record, like the six before it.
  An independent re-check read all 27 pages and confirmed the exclusion: no loss, no
  optimizer, no learning rate, no batch size, no epoch count, no hardware anywhere.
- **10.1029/2025GL117046** — *Generalizable neural-network parameterization of mesoscale
  eddies*, found on arXiv. Fully extracted: 4 experiments, 9 results, 8 limitations, 38
  sourced claims, all 38 confirmed by an independent second reading. Recorded as
  `PREPRINT`, because the file read is `arXiv:2505.08900v6` and not the published article
  — the published DOI is kept in `source.resolved_from` as provenance, never as a source
  for a value.

## What is left, and why no amount of work here closes it

20 papers remain unreachable: 8 advertise a location that refuses the file, 12 advertise
none. Both need institutional access, which is an action for the repository's owner, not
a bug in the pipeline. There is nothing to retry: the retry is in this document.

To add one later:

1. Download the PDF through institutional access, or an author manuscript, into
   `.data/golden-pdfs/` (nothing in `.data/` is committed — these are publisher files).
2. Extract it against [`evaluation/gold_v2/SCHEMA.md`](../evaluation/gold_v2/SCHEMA.md),
   including rule 10: record which **edition** you read and prove it with a quote. A
   preprint is recorded as a preprint, never as the version of record.
3. `uv run python -m ocean_research_hub.corpus_v2.gate evaluation/gold_v2/<slug>.json`
   must pass with no locate failure and no support warning.
4. Have the new claims re-checked against the PDF
   ([`evaluation/gold_v2/RECHECK.md`](../evaluation/gold_v2/RECHECK.md)) and ingest the
   report with `python -m ocean_research_hub.corpus_v2.recheck`, or CI fails on
   `not_rechecked != 0` — which is the point: a claim nobody read twice is not finished.

## The honest total, and two inventories that must not be added together

There are two different lists, and adding them would overstate the result:

- The **OpenAlex query manifest** (`.data/oa-manifest-full.json`, 82 papers) reports
  37 reachable, 28 blocked, 17 with no open-access location. `build_poc` prints that
  line on every rebuild. None of issue #32's 22 DOIs is in this manifest.
- Issue #32's list comes from the **B08 package's `SOURCE_ACCESS` sheet**: a separate
  inventory of 22 papers. 2 of those are now read, 20 are not.

What can be said without mixing them: the corpus holds **45 records** — 38 papers read in
full and 7 reviews that train no model — and the ceiling on both lists is publisher
access, not the pipeline.
