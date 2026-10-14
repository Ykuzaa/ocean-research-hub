# Corpus v2 — from a PDF to an audited claim

Corpus v2 is the part of the project that answers the original question: *type a paper,
get every technical detail, with the sentence it was read from*. It is deliberately
separate from the staging corpus (issue #13) and from the canonical `PaperRecord` MVP.

Three properties define it:

1. **The unit of record is the experiment and the result**, not the paper. One paper
   routinely holds several experiments and dozens of measured results; flattening them
   into one row per paper is what made the staging corpus unusable for analysis.
2. **No value without its sentence.** Every value carries a verbatim quote and the PDF
   page it sits on. `corpus_v2.gate` re-locates each quote on that page, word for word.
3. **Sourced is not audited.** The gate proves the sentence exists and the value follows
   from it. Only a person reading the paper can say the reading is right, and that
   verdict lives in a separate ledger that never edits an extraction.

## The pipeline

```bash
uv sync --all-extras --frozen

# 1. Retrieve the open-access PDFs of the indexed DOIs (no key, no email sent out).
uv run python -m ocean_research_hub.corpus_v2.fetch_oa --dois .data/dois.txt \
  --out .data/golden-pdfs --manifest .data/oa-manifest-full.json

# 2. Extract one paper into one record. The contract is evaluation/gold_v2/SCHEMA.md;
#    .claude/agents/paper-extractor.md is the agent that applies it.

# 3. Gate every record: a record that fails is not part of the corpus.
uv run python -m ocean_research_hub.corpus_v2.gate evaluation/gold_v2/*.json

# 4. Normalise the free-text labels that extraction read into the app's 19 domains.
uv run python -m ocean_research_hub.corpus_v2.normalize evaluation/gold_v2/*.json          # dry run
uv run python -m ocean_research_hub.corpus_v2.normalize --write evaluation/gold_v2/*.json

# 5. Read the corpus as a whole: practices, coverage, and what the literature omits.
uv run python -m ocean_research_hub.corpus_v2.aggregate evaluation/gold_v2/*.json

# 6. Rebuild the public one-page report from the records (never hand-edited).
uv run python -m ocean_research_hub.corpus_v2.build_poc
```

## Reading and auditing it in the app

```bash
uv run uvicorn ocean_research_hub.api:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend && npm ci
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev -- --hostname 127.0.0.1 --port 3000
```

- `/corpus` — search and filter the papers by objective and architecture.
- `/corpus/<slug>` — one paper: methods, data, experiments, every training value and
  every result, each opening onto the sentence it came from and its page.
- `/revue` — the audit queue: one claim, its sentence, its page, and three decisions.

| Route | Purpose |
|---|---|
| `GET /api/v2/summary` | corpus counters, reporting gaps, comparability, access ceiling, audit progress |
| `GET /api/v2/papers?q=&task=&family=` | the browser's list |
| `GET /api/v2/papers/{slug}` | one record, flattened for display, with its claims and their audit state |
| `GET /api/v2/review/queue?slug=&kind=&limit=` | the claims still waiting for a human |
| `POST /api/v2/review/verdicts` | records one signed verdict |
| `GET /api/v2/review/progress` | how much of the corpus a person has actually checked |

The ledger is `evaluation/audit_v2/verdicts.json`, overridable with `OCEAN_AUDIT_LEDGER`
(and the records with `OCEAN_GOLD_V2_DIR`), so a demo never writes verdicts into the
corpus. It is written through a temporary file: an interrupted session cannot truncate
the verdicts already given.

## The states, and what each one promises

| State | Meaning |
|---|---|
| quote located | the sentence exists word for word on the cited page — checked on every commit |
| support | the stored value is derivable from that sentence alone |
| `VALUE_READ_NO_SAFE_QUOTE` | the value is legible on the rendered page but no sentence can carry it (it is printed as mathematics, so PDF text extraction mangles it). The gate cannot check these, so the audit queue shows them **first** |
| `UNAUDITED` | sourced, not yet read by a person |
| `ACCEPTED` / `NEEDS_FIX` / `REJECTED` | a person's verdict, signed and dated; a decision against the claim requires a reason |
| `STALE` | the value or the quote changed after the verdict, which is therefore void and the claim returns to the queue |

A verdict is given on a `(value, quote)` pair and fingerprinted on it. A re-extraction can
never inherit someone's approval of the previous reading.

## Measured ceilings

These are findings, not shortcomings to hide:

- **45 of 82 indexed DOIs have no reachable full text** (28 publisher-blocked, 17 with no
  deposited version). Nothing was read from an abstract to fill the gap.
- **Cross-paper comparison is not computable.** Of 117 `(dataset, metric, unit)` cells in
  the corpus, **zero** are shared by two papers. The corpus describes practices and
  coverage; it is not a leaderboard.
- **Results often live in figures.** Two papers yield no numeric result at all. No value
  was ever read off a curve.
- **Reporting is partial and that is the contribution**: of 137 experiments, 35% state a
  learning rate, 23% a batch size, 42% the hardware.

## Tests

```bash
uv run pytest tests/test_corpus_v2.py tests/test_corpus_v2_app.py -q
```

`test_corpus_v2.py` runs the gate over every record (no locate failure, no support
warning). `test_corpus_v2_app.py` checks that the audit queue covers everything the gate
checks **plus** the values the gate cannot check, that no displayed value lacks its
evidence, and that a verdict must be signed and reasoned.
