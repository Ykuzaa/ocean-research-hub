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

### Reproduce the real-PDF quality gate

Issue #19 adds a runner that downloads the pinned primary PDFs when absent, parses
their real page labels and text, writes pre-audit predictions, runs the golden
benchmark, and generates the human-readable 4DVarNet-SSH audit table:

```bash
uv run ocean-research-hub-real-pdf-benchmark \
  --predictions-out evaluation/reports/issue-19-after-predictions.json \
  --benchmark-out evaluation/reports/issue-19-after-benchmark.json \
  --audit-out evaluation/reports/4dvarnet-ssh-extraction-audit.md \
  --semantic-provider claude \
  --validation-manifest evaluation/issue-19-validation-papers.json \
  --validation-report-out evaluation/reports/issue-19-four-paper-validation.md \
  --validation-json-out evaluation/reports/issue-19-four-paper-extraction.json \
  --extraction-cache evaluation/reports/issue-19-extraction-cache.json
```

Semantic extraction is a paid, non-deterministic network call, so a fresh run
will not reproduce the committed artifacts byte-for-byte. `--extraction-cache`
writes the run's extracted records beside the reports; re-running the same
command **without** `--semantic-provider` then replays that cache and
regenerates every report with no API key and no network. The cached SHA-256 is
re-checked against the PDF on disk first, so a stale cache cannot stand in for
a different document.

### Re-verify the evidence independently

The reports above are written by the same code an auditor is being asked to
trust. `ocean-research-hub-verify-evidence` closes that loop: it reads only the
published artifact, re-hashes and re-parses each pinned PDF, and checks whether
each asserted claim's stored snippet is literally on the page it cites. It
imports no extraction rule and no provider.

```bash
uv run ocean-research-hub-verify-evidence \
  evaluation/reports/issue-19-four-paper-extraction.json \
  --report-out evaluation/reports/issue-19-evidence-reverification.md \
  --json-out evaluation/reports/issue-19-evidence-reverification.json
```

Outcomes stay distinct rather than collapsing into pass/fail: `LOCATED`,
`NOT_LOCATED`, `PAGE_NOT_FOUND`, `NO_EVIDENCE`. `--offline` turns a missing
cached PDF into a visible failure instead of a silent download.

Downloaded PDFs are kept under the ignored `.data/golden-pdfs/` directory. The
runner never marks an extracted scientific claim `VERIFIED`; the audit report has
an explicit Scientific Auditor confirmation column for the independent gate.
`--semantic-provider` is explicit so tests and routine benchmark inspection
never make a paid network call. Choose `claude` (preferred) or `gemini` only
when the matching API key is configured; omitting it records a
deterministic-only provider path in the generated report.
The four-paper report adds the required heterogeneous non-golden checks (GLONET
and DINCAE 2.0). It remains explicitly pending until an independent auditor
supplies `--validation-decisions`; the runner never self-promotes claims to
`VERIFIED` or manufactures expected values.

### Absence versus extraction failure

`NOT_REPORTED` is asserted only when a field-specific lexical probe finds none
of that field's near-closed reporting vocabulary anywhere in the searched text.
The scope that establishes the absence -- the source and page count, the exact
probe patterns that found nothing, and whether supplementary material was
searched -- is stored on the field and printed in its own report column. When
the vocabulary *is* present but no value could be grounded, the field stays
`EXTRACTION_ERROR`: the concept is discussed, so absence is unprovable.

Open-vocabulary fields are deliberately unprobed and can never be declared
absent this way. The OceanNet supplement is the governing counter-example: it
reports two ablation experiments without ever writing "ablation".

Where a run was given no supplementary material, an absence means "not in the
primary document" and the recorded scope says exactly that, so an auditor can
see how far the search reached.

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
