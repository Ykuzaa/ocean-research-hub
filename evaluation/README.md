# Golden dataset and extraction benchmark

This directory contains the first compact, evidence-backed and independently audited benchmark for
Ocean Research Hub. The Scientific Auditor checked every label against primary papers and linked
supplements. Directly supported assertions are `VERIFIED` at confidence `1.0`, exhaustively searched
absences are `NOT_REPORTED` at confidence `0.95`, and source contradictions remain `CONFLICT` at
confidence `1.0`. Every field retains the stable auditor identity and audit timestamp.

## Corpus and primary sources

| ID | Representative family | Stable primary source |
|---|---|---|
| `xihe-2024` | Global eddy-resolving ocean forecasting / hierarchical Transformer | [arXiv:2402.02995v4](https://arxiv.org/abs/2402.02995v4) |
| `4dvarnet-ssh-2023` | SSH reconstruction / learned variational data assimilation | [GMD 16, 2119–2147](https://doi.org/10.5194/gmd-16-2119-2023) |
| `oceannet-2023` | Neural operator / physics-inspired regional ocean forecasting | [arXiv:2310.00813v2](https://arxiv.org/abs/2310.00813v2) |

The records use the publisher paper or author-submitted paper, not search snippets or secondary
summaries. Every asserted value includes a short evidence excerpt, section, page, finer locator,
source origin, and primary-source URL. Page numbers for GMD are printed journal pages; arXiv page
numbers are manuscript page numbers. Mutable preprints are version-pinned. Composite and conflicting
claims retain every required evidence record rather than binding several pages to one locator.

## Curation method

1. Read the primary PDF, including methods, tables, figure captions, results, discussion, and
   appendices present in the PDF.
2. Transcribe only the compact field subset required by issue #3. Preserve the paper's stated
   units, periods, scope, and qualifiers in the normalized value.
3. Attach a locatable excerpt to every assertion. Do not turn a plausible convention into a fact.
4. Use `NOT_REPORTED` only after recording the primary-source sections/full-text scope searched.
   Absence is not represented by a fabricated quotation or point locator.
5. Keep author-reported limitations under `AUTHOR_REPORTED_LIMITATION`; all other paper claims use
   `AUTHOR_REPORTED_FACT`.
6. Submit every label and locator to the Scientific Auditor. The initial audit corrected 22 fields
   and assigned the current truth states; later corrections must add regression coverage when they
   expose a systematic ambiguity.

This first set is intentionally compact and should grow toward ten audited papers. A later corpus
revision must not silently change a truth label: describe the correction in the commit/PR and retain
the primary-source basis.

## Prediction format and running the benchmark

Predictions are JSON validated by `PredictionSet` in
`src/ocean_research_hub/evaluation/models.py`. A prediction contains a paper ID and zero or more
field predictions. Missing predictions count as misses. Unknown paper IDs and unknown field paths
are rejected so typos cannot disappear from the denominator.
Pre-audit predictions may explicitly retain `CONFLICT` alternatives or `EXTRACTION_ERROR`; the
benchmark does not silently select a conflict value or treat a parser failure as `NOT_REPORTED`.

Run:

```bash
uv sync --all-extras --frozen
uv run ocean-research-hub-benchmark path/to/predictions.json
```

Use `--golden-dir` to evaluate another audited corpus directory. Output is deterministic JSON with
overall metrics and the same metrics for every field family.

For a no-extraction smoke run (all fields intentionally missing), use:

```bash
uv run ocean-research-hub-benchmark evaluation/example_predictions.json
```

## Metric definitions

Values are compared by exact, type-preserving canonical JSON equality. No fuzzy matching or unit
conversion is performed because either could hide an unsupported normalization.
An audited `VERIFIED` gold assertion is matched by a pre-audit `NOT_VERIFIED` prediction with the
same value. A gold `CONFLICT` matches only a predicted `CONFLICT` with the same alternatives; the
benchmark never selects one side.

- **Precision**: exact asserted claims / all predicted asserted claims.
- **Recall**: exact asserted claims / all golden asserted claims.
- **Exact match**: fields with an exact assertion or correct `NOT_REPORTED` state / all golden fields.
- **Unsupported-claim rate**: predicted assertions that do not exactly match the golden assertion,
  including assertions where gold says `NOT_REPORTED`, / all predicted assertions.
- **`NOT_REPORTED` accuracy**: correct `NOT_REPORTED` predictions / golden `NOT_REPORTED` fields.
- **Evidence-location accuracy**: exact claims whose page, section, and locator all exactly match /
  all golden asserted claims.

A metric with no applicable denominator has JSON `value: null`; numerator and denominator are
always emitted. Evidence-location scoring is deliberately strict and independent from claim-value
precision. These definitions make unsupported claims visible rather than treating them as ordinary
string mismatches.

## Auditor checklist

For any revision, independently re-check the normalized value, every evidence record, page, section,
locator, source origin, and provenance class against the pinned source. For `NOT_REPORTED`, repeat
the documented search scope including linked supplements. Preserve `CONFLICT` whenever primary
passages disagree; do not choose a preferred value silently.
