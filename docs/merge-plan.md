# What was merged, and in which order

Everything below is on `main`. This file used to be a plan; it is kept as the record of
what the merge actually was, because the plan was written while the session's permission
classifier was refusing `git push` and `gh pr merge` under "merge without review", and
the reader of a stale plan would go looking for work that no longer exists.

`main` was at `ec08e4c` when this started.

| PR | What | Merged as |
|---|---|---|
| **#36** | edition-aware research model (#11) and staging migrations (#30) | `26828d4` |
| **#37** | the corpus v2 line: evidence-gated corpus, independent re-check, and the tool over it | `c584228` |
| **#35** | B16 corpus, audit ledger and research workspace | closed as merged — its head commit is an ancestor of #37 |
| **#38** | which edition of each paper was read, proved by a quote; the two recovered papers | `0b25641` |
| **#39, #40** | the public page says which edition was read, per corpus and per paper | `975905a` |

## What was checked on the merge result

- `uv run pytest -q` on `main`: **598 passed, 25 skipped**. The 25 are the deterministic
  gate and the publication-marker check: both re-read the source PDFs, which are 369 MB of
  publisher files and are not versioned, so they run locally and skip visibly in CI.
- `uv run python -m ocean_research_hub.corpus_v2.gate evaluation/gold_v2/*.json`:
  **45/45 records ok**, no locate failure, no support warning.
- Frontend: `npx tsc --noEmit` clean, `npx vitest run` 11 passed, `next build` ok, and
  every page checked in a real browser at 1280 px and 390 px — no horizontal overflow, no
  console error.
- CI green on `main` for every merge commit above.

## One thing the first attempt got wrong

CI typechecked a fresh checkout and failed on `LayoutProps<"/">`, a global Next.js
generates into `.next/types` during `next dev`, `next build` or `next typegen`. It
resolves on a machine that has already built and nowhere else. Both layouts now write
their props out, which is also the form Next's own root-layout example uses (`fix(ci):
type the layouts without depending on generated route types`).

## What is left, and it is not a merge

The human audit: **0 of 1,463 claims**. It happens in `/revue`, one verdict at a time, and
no amount of compute moves it. See [`access-ceiling.md`](access-ceiling.md) for the 20
papers that need institutional access.
