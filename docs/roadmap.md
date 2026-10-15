# Plan of record — Ocean Research Hub

Replaces the plan in issue #20, which still described manual extraction in web apps and an
API pipeline on the critical path. Neither is true any more.

## What the project is

A database of the machine-learning literature on the ocean where **typing a paper gives
every technical detail, and every detail shows the sentence it was read from**. On top of
it, a reading of the field as a whole: what is reported, what is omitted, what nobody has
published yet.

It is not a leaderboard, and it cannot become one from this literature: of 117
(dataset, metric, unit) combinations in the corpus, **zero** are shared by two papers.

## The three states, which are never collapsed

| State | What guarantees it | Where it stands |
|---|---|---|
| **sourced** | `corpus_v2.gate` re-locates the quote on the page it cites and checks the value follows from it | 1,424 claims, 43/43 records pass |
| **re-checked** | a second independent machine reading of the paper, checking the value was read in the right context | 1,424 claims, 1,388 confirmed, 36 flagged and all ruled on |
| **audited** | a person reads the paper and signs a verdict in `/revue` | **0** |

The third row is the one that matters, and no amount of compute moves it. The audit queue
exists, the verdicts are signed and pinned to the (value, quote) pair they were given on,
and a re-extraction voids them rather than inheriting them.

## Where it stands

- 82 DOIs indexed, **37 reachable** — 28 publisher-blocked, 17 with no deposited version.
  Nothing was read from an abstract to fill the gap.
- 37 papers read in full, 6 recorded as reviews that train no model.
- 137 experiments, 433 measured results, 1,424 sourced claims.
- Reporting, measured: 35% of experiments state a learning rate, 23% a batch size, 42% the
  hardware. This is the corpus's own contribution to the field.
- Two papers yield no numeric result: their measurements live only in figures, and no value
  was read off a curve.

## What is next, in order

1. **The human audit.** 1,424 claims are sourced and re-checked; none is audited. Two to
   three minutes per paper of targeted re-reading in `/revue` covers the 37.
2. **Institutional access** (issue #32). 45 papers cannot be read without it. This is the
   only hard limit of the project, and it is not a technical one.
3. **Decide the staging corpus.** 1,867 claims with no verbatim quote. The recommendation
   is to archive it read-only as an evaluation set; the mapping machinery is finished if
   that decision changes.
4. **Extend the corpus** when access allows, one paper at a time, through the same
   contract: `evaluation/gold_v2/SCHEMA.md` for extraction, `RECHECK.md` for the second
   reading, the gate in CI.

## How a paper enters the corpus

```bash
uv run python -m ocean_research_hub.corpus_v2.fetch_oa --dois .data/dois.txt \
  --out .data/golden-pdfs --manifest .data/oa-manifest-full.json
# extraction follows evaluation/gold_v2/SCHEMA.md
uv run python -m ocean_research_hub.corpus_v2.gate evaluation/gold_v2/*.json
uv run python -m ocean_research_hub.corpus_v2.recheck evaluation/work/recheck/*.json
uv run python -m ocean_research_hub.corpus_v2.build_poc
```

Full detail in [`docs/corpus-v2.md`](corpus-v2.md).
