# Corpus v2 — extraction contract (v1.1)

One paper produces one JSON file. The unit of record is the **experiment** and the
**result**, not the paper: a paper routinely contains several experiments, and an
experiment several measured results. Flattening them into one record per paper is what
made corpus v1 unusable for analysis.

Every value carries a verbatim quote and the PDF page it was read from.
`python -m ocean_research_hub.corpus_v2.gate <file.json>` re-locates each quote on the
page it cites; a record that does not pass the gate is not part of the corpus.

## What the gate does and does not guarantee

- Guarantees: the quote exists, word for word, on the cited page.
- Does **not** guarantee: that the stored value follows from the quote. That is the
  value/quote consistency check (ported from `semantic.supports_normalization`) and
  the human audit. Until both run, a record is *sourced*, not *audited*.

## Controlled vocabularies

Anything outside these lists goes to `OTHER`, with the raw wording preserved in the
neighbouring `*_raw` field. Never invent a vocabulary entry.

- `task`: `FORECASTING`, `DATA_ASSIMILATION`, `GAP_FILLING_RECONSTRUCTION`,
  `SUPER_RESOLUTION`, `BATHYMETRY_ESTIMATION`, `CLASSIFICATION_SEGMENTATION`,
  `DETECTION`, `PARAMETERIZATION`, `BIAS_CORRECTION`, `EMULATION_SURROGATE`,
  `INVERSE_INFERENCE`, `OTHER`
- `family`: `CNN_UNET`, `CNN_AUTOENCODER`, `CNN_GENERIC`, `MLP_DNN`, `TRANSFORMER`,
  `FNO_NEURAL_OPERATOR`, `NEURAL_ODE`, `GNN`, `RNN_LSTM_GRU`, `CNN_RNN_HYBRID`,
  `DIFFUSION`, `GAN`, `SYMBOLIC_REGRESSION`, `HYBRID_PHYSICS_ML`,
  `VARIATIONAL_ANALYSIS`, `CLASSICAL_ML`, `CLASSICAL_BASELINE`, `OTHER`
- `metric`: `RMSE`, `MAE`, `MSE`, `BIAS`, `R2`, `CORRELATION`, `ANOMALY_CORRELATION`,
  `SKILL_SCORE`, `NORMALIZED_ERROR_SCORE`, `CRPS`, `SPREAD_SKILL`, `SSIM`, `PSNR`,
  `IOU`, `DICE`, `ACCURACY`, `F1`, `PRECISION`, `RECALL`, `AGREEMENT_RATE`,
  `RESOLVED_SPATIAL_SCALE`, `RESOLVED_TEMPORAL_SCALE`, `SPEEDUP`, `RUNTIME`,
  `STABILITY_HORIZON`, `OTHER`
- `metric_kind` (for grouping when `metric` is `OTHER`): `ERROR`, `SKILL`,
  `AGREEMENT`, `EFFICIENCY`, `SCALE`, `STABILITY`, `OTHER`
- `split`: `TRAIN`, `VALIDATION`, `TEST`, `CROSS_VALIDATION`, `UNSPECIFIED`
- `dataset role`: `PRIMARY_TRAINING`, `EVALUATION`, `AUXILIARY_COVARIABLE`,
  `BASELINE_PRODUCT`
- `limitation_theme`: `DATA`, `COMPUTE`, `GENERALIZATION`, `PHYSICS`, `UNCERTAINTY`,
  `REPRODUCIBILITY`, `EVALUATION`, `FUTURE_WORK`, `OTHER`
- `ocean_domains` (several per paper, these are the app's own 19 domains — use these
  identifiers, not free text): `forecasting`, `data-assimilation`, `subsurface`, `sst`,
  `ssh-altimetry`, `currents`, `eddies-fronts`, `marine-heatwaves`, `sea-ice`, `waves`,
  `biogeochemistry`, `bathymetry`, `parameterization`, `neural-operators`,
  `foundation-models`, `llm-agents`, `marine-ecology`, `benchmarks`, `reviews`.
  A **region is not a domain**: "Mediterranean Sea" or "Persian Gulf" belongs in
  `dataset.region`, never in this list. `corpus_v2.normalize` maps the wording that was
  actually read into these identifiers and keeps the original in `ocean_domains_raw`,
  so a mapping mistake is fixed without re-reading the PDF.
- `evidence_status`: `QUOTED` (default, omit), `VALUE_READ_NO_SAFE_QUOTE`

### Family classification: arbitration rules

Two extractors classified two near-identical 4DVarNet papers as
`VARIATIONAL_ANALYSIS` and `HYBRID_PHYSICS_ML`. Apply in order:

1. A learned network embedded in a variational or physical solver is
   `HYBRID_PHYSICS_ML`, even if the paper calls itself variational.
2. `VARIATIONAL_ANALYSIS` and `CLASSICAL_BASELINE` are for methods with **no learned
   parameters** (DIVAnd, optimal interpolation, k-epsilon).
3. For a plain convolutional network that is neither a U-Net nor an autoencoder, use
   `CNN_GENERIC`, not the closest-looking entry.
4. When the paper names two backbones (for example "transformer" and "Fourier neural
   operator"), classify on the one described in the architecture section and record
   the other in `architecture_note`.
5. Classify **the network itself**, not the system it is coupled into. A CNN running
   inside an ocean model stays `CNN_GENERIC`, with the coupling in
   `architecture_note`; rule 1 applies only when the learned part is itself built
   around the solver.
6. A stack of two backbones in sequence has its own entry: CNN then LSTM is
   `CNN_RNN_HYBRID`, not a choice between the two. Equations discovered by fitting
   (symbolic regression, Gaussian-process or least-squares fits) are
   `SYMBOLIC_REGRESSION`.
7. `is_novel_in_paper` is false when the authors say they adapt an existing model,
   even if `role` is `PROPOSED`. Being the paper's subject is not the same as being
   its contribution.
8. **A fitted model is not a `CLASSICAL_BASELINE`.** Rule 2 is about learned
   parameters, not about being a comparison: random forest, SVM, logistic
   regression and the empirical SDB regressions (Lyzenga, Stumpf) all fit
   coefficients to data, so they are `CLASSICAL_ML` even when their `role` is
   `BASELINE`. `CLASSICAL_BASELINE` stays for optimal interpolation, DIVAnd,
   Okubo-Weiss, persistence and physics-based models with no fitted parameter.
   `SYMBOLIC_REGRESSION` is narrower still: it is for work whose contribution is
   the *discovered functional form*, not for a regression whose form the authors
   took from the literature.
9. **The family is read from the paper, not from outside knowledge.** When a paper
   only names a method it compares against ("we also compare with SegFormer"), the
   family is `OTHER` with the name kept in `family_raw`, even when the method is
   famous and its architecture well known elsewhere. Knowing what SegFormer is does
   not make it something this paper says. Classifying it anyway is the one kind of
   inference this corpus exists to refuse.

### Which edition was read

10. **The edition is evidenced, never assumed.** A preprint's table is not always the
    published one, so a record states which file was read — `VERSION_OF_RECORD`,
    `ACCEPTED_MANUSCRIPT` (accepted but not typeset: an IEEE early-access page, a
    publisher proof), `AUTHOR_MANUSCRIPT` (the authors' own file, deposited nowhere) or
    `PREPRINT` (an arXiv/EarthArXiv deposit, a "submitted to" footer) — and proves it
    with a quote from the file itself, which the gate relocates like any other quote.
    `corpus_v2.edition.classify` must read the declared edition back out of that quote:
    a label its own evidence does not carry is a defect, not a judgement call.

    The edition describes **the file that was read**, not the paper's publication status.
    An arXiv file whose article has since appeared in a journal is still `PREPRINT`,
    because the numbers in the corpus came from the arXiv file.

    **A DOI alone is not proof of publication.** An accepted manuscript and a publisher's
    proof both print the DOI of the article they will become, so a `VERSION_OF_RECORD`
    record must also carry, on the page its evidence cites, a mark only a published
    article has: the citation line, the editorial dates ("Received… Accepted…"), the
    copyright line, or the article number. That second check reads the page text, not the
    quote, and `tests/test_corpus_v2_edition.py` runs it wherever the PDFs are.

    When the file read prints no DOI of its own but was located through one (a preprint
    found from its published DOI), that identifier goes in `source.resolved_from`, which
    is provenance: it says how the file was found and may never be cited as the source of
    a value. `paper.doi` stays null, because the file carries none.

    The evidence node holds no `value`, so it never enters the human audit queue: there
    is nothing left to rule on that the gate and the classifier do not already settle.
    `store.PROVENANCE_PATHS` names that exception, and the coverage test asserts the
    queue is never narrower than the gate anywhere else.

## Shape

```json
{
  "source": {
    "source_id": "", "file": ".data/golden-pdfs/<file>.pdf",
    "sha256_prefix": "", "pdf_pages": 0, "printed_page_offset": 0,
    "edition": "VERSION_OF_RECORD | ACCEPTED_MANUSCRIPT | AUTHOR_MANUSCRIPT | PREPRINT",
    "edition_evidence": {"page_pdf": 1, "quote": ""},
    "resolved_from": {"doi": "", "via": "", "note": ""},
    "extracted_by": "", "extracted_at": "YYYY-MM-DD"
  },
  "paper": {
    "paper_id": "P-<SLUG>", "doi": null, "title": "", "year": 0,
    "venue": null, "ocean_domains": []
  },
  "methods": [{
    "method_id": "M-<SLUG>", "canonical_name": "", "family": "<vocab>",
    "family_raw": "", "architecture_note": null,
    "is_novel_in_paper": false, "role": "PROPOSED | BASELINE",
    "evidence": [{"field": "family", "page_pdf": 0, "page_printed": 0, "quote": ""}]
  }],
  "datasets": [{
    "dataset_id": "D-<SLUG>", "canonical_name": "", "variables": [],
    "spatial_resolution": null, "temporal_resolution": null, "region": null,
    "period_start": null, "period_end": null, "role": "<vocab>",
    "evidence": [{"field": "canonical_name", "page_pdf": 0, "page_printed": 0, "quote": ""}]
  }],
  "experiments": [{
    "experiment_id": "X-<SLUG>", "task": "<vocab>", "task_raw": "",
    "method_id": "M-<SLUG>", "dataset_ids": ["D-<SLUG>"], "target_variable": "",
    "training": {
      "loss":          {"value": null, "page_pdf": 0, "page_printed": 0, "quote": ""},
      "optimizer":     {"value": null, "page_pdf": 0, "page_printed": 0, "quote": ""},
      "learning_rate": {"value": null, "page_pdf": 0, "page_printed": 0, "quote": ""},
      "batch_size":    {"value": null, "page_pdf": 0, "page_printed": 0, "quote": ""},
      "epochs":        {"value": null, "page_pdf": 0, "page_printed": 0, "quote": ""},
      "hardware":      {"value": null, "page_pdf": 0, "page_printed": 0, "quote": ""}
    }
  }],
  "results": [{
    "experiment_id": "X-<SLUG>", "dataset_id": "D-<SLUG>",
    "metric": "<vocab>", "metric_raw": "", "metric_kind": "<vocab>",
    "value": 0, "unit": "", "higher_is_better": false, "split": "<vocab>",
    "config": "", "baseline_name": null, "baseline_value": null,
    "source_table": null, "is_best_in_table": false,
    "page_pdf": 0, "page_printed": 0, "quote": ""
  }],
  "limitations": [{"theme": "<vocab>", "page_pdf": 0, "page_printed": 0, "quote": ""}],
  "conflicts": [{
    "field": "results[2].value", "values": [0.8743, 0.6177],
    "sources": [{"page_pdf": 8, "quote": ""}, {"page_pdf": 17, "quote": ""}],
    "chosen": 0.8743, "reason": "Results section preferred over the conclusion."
  }],
  "not_reported": [{"field": "experiments[X-...].training.batch_size", "searched": []}]
}
```

## Filling rules

- A training field the paper does not give: remove it from `training` and add it to
  `not_reported` with the sections actually searched. Do not store `null` silently.
- A value must be carried **entirely** by its own quote. When the paper describes one
  field across several sentences (an MSE plus a spectral regulariser), keep `value` to
  what the main quote supports and attach the rest as
  `"extra_evidence": [{"claim": "", "page_pdf": 0, "page_printed": 0, "quote": ""}]`
  inside that field's node. Never widen the value past its quote: the support check
  rejects it, and rightly.
- Several experiments per paper is normal and expected (one per task × dataset).
  Never merge them. When the paper gives one training setup for all of them, copy it
  and say so in `note`.
- `results`: one row per (experiment, dataset, metric, configuration). Tables produce
  several rows; take at least the reference row and the best row, and set
  `is_best_in_table` on the best. `higher_is_better` is mandatory — without it a
  ranking cannot be computed.
- When two places in the paper disagree, record both in `conflicts` with their quotes
  and state which you kept and why. Do not silently pick one.
- Numbers are bare numerics in `value` (`0.00058`, not `"0.00058"`); the unit goes in
  `unit` (`degC`, `K`, `cm`, `m`, `days`, `%`).
- A paper that trains no ML model is not a failure. Write only `source`, `paper` and
  `excluded: {"reason": "", "page_pdf": 0, "quote": ""}`.
- **A `limitation` is a limit the authors state about their own work.** Four things
  that are routinely mistaken for one, and are not: a promise of future work ("we
  plan to investigate this"), a data- or code-availability statement, a positive
  result, and a remark about someone else's method. A limit phrased as a need ("a
  higher resolution would be required") counts when it sits in the authors' own
  enumeration of limits. When in doubt, the test is whether removing the sentence
  would remove an admission.
- **A training value belongs to the experiment the paper attaches it to.** A runtime
  measured on another dataset, an epoch count stated for another case, hardware
  given for a different implementation: each belongs to that experiment or to
  nothing. Copying one setup across several experiments is allowed only when the
  paper gives a single training section for all of them, and then `note` says so.
- **A threshold is not a measurement.** "R > 0.6" states a bound the authors claim
  to exceed, not a value they measured: it is not a `result`. The same holds for
  "less than 0.1 degC" unless the config records it as an upper bound.

## Known ceilings (measured on the 8-paper pilot)

- **Results often live in figures, not tables.** OceanNet yields zero numeric results,
  GLONET one across 34 pages. Text extraction cannot fix this; do not compensate by
  reading values off a curve.
- **Cross-paper comparison is mostly impossible.** On the pilot, zero
  (dataset, metric, unit) cells were shared by two papers. The corpus describes
  practices and coverage; it is not a leaderboard.
- **What the field omits is itself the finding.** Learning rate was absent in 6 of 19
  experiments, batch size in 5, hardware in 5.
