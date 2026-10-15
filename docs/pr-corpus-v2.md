## What this is

The project had two parallel data models and a corpus of 1,867 claims with **zero**
verbatim quotes. This branch replaces that with a corpus where the unit of record is the
**experiment** and the **result**, and where no value exists without the sentence it was
read from.

- **45 records** — 38 papers read in full, 7 recorded as reviews that train no model.
- **141 experiments, 442 measured results, 1,463 sourced claims.**
- `corpus_v2.gate` re-locates every quote on the page it cites and checks the stored value
  follows from it. 45/45 records pass with no warning. It runs where the source PDFs are,
  which is **not** CI: they are 369 MB of publisher files and are not versioned, so the
  gate's 45 tests skip there, visibly, instead of passing on nothing.
- Every claim was then read a **second time, independently, against the PDF**, to check it
  was read in the right context: 1,388 confirmed, 36 flagged, every flag ruled on, 31
  records corrected.
- Each record says which **edition** of the paper was read — published article, accepted
  manuscript, author manuscript or preprint — and proves it with a quote the gate
  relocates. 22 of the 45 were read in a preprint.
- The three states stay three different words: **sourced → re-checked → audited**. 0 of
  the 1,463 claims is audited by a human, and every surface says so.

## What you can do with it

- `/corpus` — search the papers, filter by objective and architecture.
- `/corpus/<slug>` — one paper: methods, data, experiments, every training value and every
  result, each opening onto its source sentence and page.
- `/analyse` — enter by architecture, objective or data source; reporting rates, the
  task x architecture coverage matrix, the limitations taxonomy.
- `/revue` — the human audit queue: one claim, its sentence, its page, three decisions, and
  a verdict that is signed and pinned to the (value, quote) pair it was given on.
- A standalone public page, rebuilt from the corpus by `corpus_v2.build_poc` and never
  hand-edited.

## What it measures, and refuses to hide

- **No cross-paper comparison is computable**: 0 shared (dataset, metric, unit) cells out
  of 117. No architecture ranking can come from this literature, and the pages say so.
- **Reporting is partial**: of 137 experiments, 35% state a learning rate, 23% a batch
  size, 42% the hardware. That is the corpus's own contribution.
- **Access ceiling**: 37 of 82 indexed DOIs have a reachable full text; 28 are
  publisher-blocked, 17 have no deposited version. Nothing was read from an abstract to
  fill the gap (issue #32).
- Two papers yield no numeric result at all, because their measurements live only in
  figures. No value was ever read off a curve.

## Also in this branch

- **#29** — the independent mapping audit is finished and green: six adversarial
  regressions that had never passed now pass. The cause was an `INSERT OR IGNORE` hiding a
  missing `NOT NULL` column, so every write failed silently and reported "already
  recorded".
- **#22, #23** — entity pages and the gap explorer, built only from sourced claims.
- PR #35's commits are included; it closes as merged with this.

## Verification

`uv run pytest -q` → **448 passed**. Merged with PR #36 → **464 passed**. Gate: 43/43 ok.
Frontend: typecheck clean, 11 tests, production build ok, every page checked in a browser
at 1280 px and 390 px — no horizontal overflow, no console error.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
