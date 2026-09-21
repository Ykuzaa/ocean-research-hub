# Issue #19 golden benchmark: BEFORE and FINAL

Both runs use the three audited golden papers (`4dvarnet-ssh-2023`,
`oceannet-2023`, `xihe-2024`) and the compact benchmark field set. The BEFORE
column is the historical baseline from PR #18, preserved verbatim. The FINAL
column is the run committed beside this file, reproducible with the commands in
`issue-19-independent-audit-package.md`.

| Metric | BEFORE | FINAL |
|---|---:|---:|
| Precision | 5.5556% (1/18) | **24.0000% (6/25)** |
| Recall | 2.3256% (1/43) | **13.6364% (6/44)** |
| Exact match | 17.6471% (9/51) | **17.3077% (9/52)** |
| Unsupported-claim rate | 94.4444% (17/18) | **76.0000% (19/25)** |
| `NOT_REPORTED` accuracy | 100% (8/8) | **37.5000% (3/8)** |
| Evidence-location accuracy | 0% (0/43) | **0% (0/44)** |

These are not good numbers and they are not presented as good ones. Read the
explanations below before drawing any conclusion from the table.

---

## An earlier "AFTER" table reported far better numbers. It should be ignored.

A previous revision of this file reported 100% precision, 77.27% recall and
77.27% evidence-location accuracy. Those numbers were real outputs of the code
at that time, but they were produced by paper-specific extraction profiles that
encoded the golden papers' expected values, pages, sections and locator strings.
Issue #19 explicitly forbids that ("Do not optimize by hard-coding the golden
papers"), so the profiles were removed. The FINAL numbers are what the general
extraction path actually achieves.

The whole of the apparent regression between that table and this one is the
removal of the hard-coding, not a loss of capability.

---

## Why each metric moved

### Precision 5.56% → 24.00%, recall 2.33% → 13.64%

The pipeline now extracts real claims from real PDFs through a general path:
deterministic rules, then LLM-proposed claims, then an evidence gate that
re-locates every proposed quotation in the parsed source before any value may
be stored. Six of 44 audited claims now match the golden label byte-for-byte.

### Unsupported-claim rate 94.44% → 76.00%: **this metric does not mean what its name suggests**

The benchmark defines an "unsupported claim" as any asserted prediction that is
not byte-identical to the golden label. It does not test whether the claim is
supported by the paper. All 19 FINAL mismatches are source-grounded claims that
normalize differently from the hand-written golden string:

| Field | Extracted | Golden |
|---|---|---|
| `4dvarnet data.inputs` | `["raw satellite altimeter data", "optimally interpolated fields"]` | `[..., "optimally interpolated SSH fields"]` |
| `4dvarnet data.splits.test` | `"22 October to 2 December 2012 (42 d)"` | `"2012-10-22 through 2012-12-02 (42 days)"` |
| `4dvarnet architecture.activations` | `["linear", "rectified linear unit (ReLU)"]` | `["linear", "ReLU"]` |
| `oceannet data.splits.test` | `"2019-2020"` | `"2019 through 2020"` |
| `xihe evaluation.baselines` | `["PSY4", "GIOPS", "FOAM", "BLUElink OceanMAPS (BLK)"]` | `["PSY4", "GIOPS", "BLUElink OceanMAPS", "FOAM"]` |

The last row differs only in list order and one parenthesised acronym. The full
list of 19 is in `issue-19-four-paper-validation.md` and
`4dvarnet-ssh-extraction-audit.md`, each beside its exact quotation.

**Zero of the 25 asserted claims failed independent evidence re-verification.**
`issue-19-evidence-reverification.md` re-hashed and re-parsed all four
validation PDFs and relocated 73 of 73 stored quotations on the exact pages
cited. So the true fabrication rate measured by that artifact is 0/73, while
this metric reads 76%. Do not quote the 76% as a hallucination rate.

That said, the mismatches are a real product problem, just not the one the
metric names: the corpus cannot deduplicate or compare values that are written
five different ways. Fixing it means a normalization contract, which belongs to
the canonical data model in #11, not here.

### `NOT_REPORTED` accuracy 100% → 37.50%: a genuine regression against a vacuous baseline

The BEFORE run scored 8/8 because it predicted almost nothing at all, and an
unpopulated field carried the schema default `NOT_REPORTED`. It never searched
for those eight values; it defaulted into the right answer eight times.

An unearned `NOT_REPORTED` is now reported as `EXTRACTION_ERROR`, so only
absences the pipeline actually established count. Three do:

| Field | Basis |
|---|---|
| `oceannet data.splits.validation` | no occurrence of `validat`, `held-out`, `development set`, `tuning set` in the paper or its supplement |
| `oceannet training.optimizer` | no occurrence of `optimizer`, `Adam`, `AdamW`, `SGD`, `RMSProp`, `L-BFGS`, `Adagrad`, `Adadelta`, `stochastic gradient` |
| `oceannet training.learning_rate` | no occurrence of `learning rate`, `learning-rate`, `step size` |

The other five stay `EXTRACTION_ERROR` because the field's vocabulary *is*
present and absence therefore cannot be proven — for example OceanNet discusses
"flow non-linearity" without naming an activation function, and XiHe contains
"SoftMax" in its attention description. Under this issue's rule that a
conservative `EXTRACTION_ERROR` beats an unsupported claim, five conservative
misses are the correct trade against one false absence.

37.5% earned is worth more than 100% defaulted, but it is still a low number
and the absence machinery is the newest and least proven part of the pipeline.

### Evidence-location accuracy 0% → 0%: structurally unreachable as defined

The metric requires the predicted `(page, section, locator)` set to equal the
golden set exactly, across every evidence record. Measured separately over the
25 asserted claims:

| Agreement with the audited golden evidence | Count |
|---|---:|
| at least one **page** agrees | 21 / 25 |
| at least one **section** agrees | 19 / 25 |
| at least one **locator string** agrees | **0 / 25** |

The extractor finds the right page 84% of the time and the right section 76% of
the time. The metric reports 0% because golden locators are human prose —
`"opening paragraph"`, `"contributions bullet 1"`, `"Training and evaluation
setting bullet"` — and the extractor emits machine locators such as
`"PDF paragraph 3"` or `"LLM-proposed evidence"`. No general extractor can
generate those strings; the previous 77% came from profiles that stored them
verbatim.

This is a defect in the metric's contract, not a null result for evidence
grounding. Fixing it honestly means either giving the golden corpus
machine-checkable locators or scoring page and section separately from the
locator. Both change an audited corpus and a published metric definition, so
neither is done here — it is left visible for the independent auditor to rule
on.

### Exact match 17.65% → 17.31%: flat, for two opposite reasons

Nine fields are exactly right in both runs, out of 51 then and 52 now. The
composition changed completely: BEFORE was one claim plus eight defaulted
absences; FINAL is six real claims plus three established absences.

---

## Field-family detail

Per-family numerator and denominator for every metric are in
`issue-19-after-benchmark.json` under `by_field_family`.

## Reproduction

```bash
uv run ocean-research-hub-real-pdf-benchmark \
  --predictions-out evaluation/reports/issue-19-after-predictions.json \
  --benchmark-out evaluation/reports/issue-19-after-benchmark.json \
  --audit-out evaluation/reports/4dvarnet-ssh-extraction-audit.md \
  --validation-manifest evaluation/issue-19-validation-papers.json \
  --validation-report-out evaluation/reports/issue-19-four-paper-validation.md \
  --validation-json-out evaluation/reports/issue-19-four-paper-extraction.json \
  --extraction-cache evaluation/reports/issue-19-extraction-cache.json
```

Replaying the committed cache reproduces `issue-19-after-benchmark.json`
byte-for-byte; this was checked. Add `--semantic-provider claude` to re-extract
from scratch, which requires an API key and will not reproduce the artifacts
exactly, because the provider call is not deterministic.

Scientific correctness of every value above still requires the independent
Scientific Auditor gate. Nothing in this run is `VERIFIED`.
