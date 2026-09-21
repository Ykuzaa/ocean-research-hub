# Issue #19 — four-paper generalization report

This report answers one question:

> Did the system extract scientifically defensible information from papers it
> was **not** specifically programmed for?

The short answer is **yes for the extraction, not yet for the normalization**,
with three named weaknesses that a reviewer should attack first (§6).

Every claim below is backed by `issue-19-four-paper-validation.md` (per-field
tables with page, section, locator and exact quotation),
`issue-19-four-paper-extraction.json` (the machine-readable evidence) and
`issue-19-evidence-reverification.md` (an independent re-check of every
quotation against freshly parsed PDFs).

**Nothing here is `VERIFIED`. This is a pre-audit artifact.**

---

## 1. The four papers

| Paper | Golden labels? | Why it is in the set |
|---|---|---|
| 4DVarNet-SSH (`10.5194/gmd-16-2119-2023`) | yes | mandated by issue #19 |
| OceanNet (`10.1038/s41598-024-72145-0`) | yes | heterogeneous: arXiv manuscript **plus** a publisher supplement |
| GLONET (`10.1029/2025JH000686`) | **no** | non-golden; global neural forecasting, 34 pages |
| DINCAE 2.0 (`10.5194/gmd-15-2183-2022`) | **no** | non-golden; convolutional autoencoder reconstruction with error estimates |

GLONET and DINCAE 2.0 are the generalization evidence. They have no golden
labels, no expected-value registry and no paper-specific code. A reviewer can
confirm the last point directly:

```bash
grep -ri "glonet\|dincae" src/      # returns nothing
```

The extraction modules (`src/ocean_research_hub/ingestion/`) contain no paper
title, no dataset name and no expected value for any paper, golden or not. The
benchmark runner does reference two golden paper IDs, for run configuration
only: which paper gets the mandatory per-field audit report, and where to fetch
OceanNet's supplement. Neither carries a scientific value.

## 2. What was extracted

42 fields were targeted per paper. Every populated field carries a quotation
that was re-located in the parsed source before storage.

| Paper | Populated | `NOT_REPORTED` | `EXTRACTION_ERROR` | `CONFLICT` | Proposals rejected |
|---|---:|---:|---:|---:|---:|
| 4DVarNet-SSH | 20 | 2 | 20 | 0 | 21 |
| OceanNet | 17 | 9 | 16 | 0 | 15 |
| **GLONET** (non-golden) | **15** | 1 | 26 | 0 | 18 |
| **DINCAE 2.0** (non-golden) | **21** | 1 | 20 | 0 | 31 |

The two non-golden papers are not outliers: DINCAE 2.0 yields more populated
fields than either golden paper.

## 3. Successful fields on papers the system had never seen

DINCAE 2.0, all with page, section and verbatim quotation in the artifact:

| Field | Extracted value | Page |
|---|---|---:|
| `architecture.family` | `["convolutional autoencoder", "U-Net"]` | 2184 |
| `architecture.encoder` | five convolutional layers with 16, 30, 58, 110 and 209 output filters, kernel 3×3 | 2187 |
| `architecture.decoder` | five upsampling layers (nearest-neighbour or bilinear) | 2187 |
| `architecture.activations` | `["RELU"]` | 2187 |
| `training.optimizer` | `Adam` | 2188 |
| `training.learning_rate` | `0.00058` | 2188 |
| `training.batch_size` | `32` | 2188 |
| `training.epochs_or_steps` | `1000 epochs` | 2187 |
| `training.hardware` | `["GeForce GTX 1080 GPU", "Intel Core i7-7700 CPU"]` | 2186 |
| `objective.primary_loss` | negative log-likelihood of a Gaussian with mean ŷ and variance σ̂² | 2185 |
| `data.splits.train` / `.validation` | `70 % training data` / `20 % development data` | 2186 |
| `data.preprocessing.interpolation` | bi-linear interpolation onto the common SST grid | 2186 |

GLONET:

| Field | Extracted value | Page |
|---|---|---:|
| `data.spatial_resolution` | `[1/4]◦` | 8 |
| `data.splits.train` | daily mean GLORYS12 reanalysis outputs from 1993 to 2019 | 8 |
| `data.preprocessing.interpolation` | GLORYS12 1/12° fields interpolated to a 1/4° grid | 8 |
| `architecture.encoder` / `.decoder` | the operator definitions `Eω : V×U→Z` / `Dω : Z→Y` | 6 |
| `training.optimizer` | `Adam` | 9 |
| `training.learning_rate` | decreasing from e-4 to e-5 | 9 |
| `training.training_time` | around 3 weeks | 9 |
| `evaluation.ablations` | alternative cutoff wavelengths (Lc = 200, 500, 1000 km) | 31 |

The GLONET ablation is worth noting: it was found on page 31, in an appendix,
and the paper never uses the word "ablation".

## 4. Rejected claims, errors and absences

### Unsupported proposals rejected: 85 across the four papers

A proposal is discarded when its quotation cannot be relocated on the cited
page, when the value does not overlap the quotation it was supposedly derived
from, when an acronym in the value is absent from the quotation, when the
quotation is hedged (`e.g.`, `such as`, `could`, `may`), when a number in the
value is not literally written in the quotation, or when the quotation does not
entail the field's role (a positive "code is available" statement is not a
reproducibility *limitation*).

These rejections are the reason the fabrication count is zero, and they are also
the main reason recall is low. The trade is deliberate.

### Extraction errors: 82 across the four papers

`EXTRACTION_ERROR` means the pipeline could not ground a value and could not
prove absence either. It is never reported as the paper not stating the value.
The largest cluster is architecture internals — `hidden_dimensions`, `blocks`,
`attention`, `positional_encoding` — which are usually stated in figures,
equations or tables that the text-only parser flattens or loses.

### Absence: 13 assertions, all with a recorded scope

Nine of the thirteen are OceanNet. Its arXiv manuscript plus its three-page
supplement genuinely contain no occurrence of `epoch`, `batch`, `GPU`,
`learning rate`, `optimizer`, `validat` or any normalization-layer term — the
paper reports essentially no training configuration. The independent golden
audit reached the same conclusion for the three of those fields it labelled,
which is the only external corroboration of the absence machinery currently
available.

Every absence stores the probe patterns that found nothing and whether
supplementary material was searched, so a reviewer can re-run the probe by
hand.

## 5. Evidence integrity

`issue-19-evidence-reverification.md`, produced by a tool that imports no
extraction rule and no provider:

| Paper | SHA-256 reproduced | Evidence records | Located | Not located | Page missing | No evidence |
|---|---|---:|---:|---:|---:|---:|
| 4DVarNet-SSH | yes | 20 | 20 | 0 | 0 | 0 |
| OceanNet | yes | 17 | 17 | 0 | 0 | 0 |
| GLONET | yes | 15 | 15 | 0 | 0 | 0 |
| DINCAE 2.0 | yes | 21 | 21 | 0 | 0 | 0 |

**73 of 73 stored quotations were relocated on the exact page cited, and all
four source hashes reproduced.**

This establishes that no stored claim rests on invented text. It does **not**
establish that the normalized value is the correct scientific reading of that
text. That is precisely what the independent Scientific Auditor must decide, and
it is the reason the per-field tables print the quotation next to the value.

### Provider failures

None in this run. All four papers completed the semantic pass. A provider
failure is recorded in the report's provider-path string and converts nothing
to absence; the deterministic results survive it.

### Supplementary-material provenance

OceanNet's supplement was fetched (SHA-256
`c3e7f690…`), parsed, searched, and is named in the absence scope of all nine
OceanNet absences. In this run no *asserted* OceanNet claim was sourced from the
supplement, so the supplementary provenance path is exercised here only for
absence scope. Its claim path is covered by regression test
`test_supplementary_semantic_claim_carries_the_pinned_supplement_url`, not by
this run's output — an auditor should treat it as tested but not
field-demonstrated.

## 6. Remaining generalization weaknesses

Ordered by how much damage a reviewer should expect them to do.

1. **No value normalization contract.** The same fact is written differently
   every time: `"1/20◦"`, `"22 October to 2 December 2012 (42 d)"`,
   `"2019-2020"`. All are faithful to their sources and none can be compared,
   deduplicated or aggregated across papers. This produces the 76%
   unsupported-claim rate even though no claim is unsupported, and it blocks
   the corpus-level analytics the roadmap depends on. It belongs to #11.
2. **Absence rests on a finite vocabulary.** `NOT_REPORTED` is asserted when
   none of a field's listed terms occurs. Two false absences were caught during
   development — GLONET and XiHe both write regridding as "interpolating X to
   \<resolution\>", and DINCAE 2.0 writes its schedule as a gamma-decay formula
   without naming a scheduler — and the probes were broadened. More may remain.
   **This is the highest-risk residual defect: a false absence is a wrong
   scientific claim, while a false `EXTRACTION_ERROR` is only a missed one.**
3. **The deterministic path is a safety net, not an extractor.** Without the
   semantic provider it populates 2, 0, 0 and 1 fields on the four papers. The
   generalization result therefore depends on an LLM plus the evidence gate. If
   the provider is unavailable, output collapses to near nothing — visibly, not
   silently, but it collapses.
4. **Non-prose content is largely lost.** Hyperparameter tables, architecture
   figures and equations are flattened by the text-only parser, which is why
   architecture internals dominate the extraction errors. The `ParsedBlock`
   boundary exists for a GROBID or Docling parser; nothing plugs into it yet.
5. **Two golden papers still produce no claim for high-value fields.**
   `architecture.family`, `evaluation.baselines`, `evaluation.metrics` and
   `limitations.author_reported` are `EXTRACTION_ERROR` on several papers where
   the golden corpus has audited values. The deterministic rule for
   `architecture.family` rejects every candidate it finds, by design, and the
   semantic proposals for these fields were rejected by the evidence gate.
   These are the clearest targets for the next iteration.
6. **Evidence-location accuracy cannot be scored as currently defined.** The
   extractor agrees with the audited page on 21 of 25 claims and with the
   section on 19, but with the golden prose locator on 0. See
   `issue-19-benchmark-summary.md`.

## 7. What this report does not claim

- No field is `VERIFIED`, and no extraction path can set that status.
- No Scientific Auditor has reviewed these outputs. The pre-flight columns in
  the generated tables are the implementer's comparison against existing golden
  labels, not a verdict.
- The implementer of this work is not permitted to record the final audit
  decision, and has not.
