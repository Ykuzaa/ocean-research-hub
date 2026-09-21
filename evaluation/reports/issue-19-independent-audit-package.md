# Issue #19 — independent scientific audit package

This package exists so a reviewer who trusts **neither** the Codex session that
built most of issue #19 **nor** the Claude session that finished it can decide
for themselves whether the extraction is scientifically defensible.

Nothing in this package asks you to accept a summary. Every number has a
committed artifact behind it, every artifact names the exact source document it
came from by SHA-256, and every command needed to regenerate or re-check it is
written out below.

**Audit state: `PENDING_INDEPENDENT_AUDIT`.**
No field in any artifact is `VERIFIED`. The implementation cannot promote its
own output, and the session that wrote the implementation is not permitted to
record the final Scientific Auditor decision. The pre-flight columns in the
reports are the implementer's own comparison against existing golden labels;
they are a convenience for the auditor, not a verdict.

---

## 0. Headline results of the run under audit

| | |
|---|---|
| Golden benchmark | precision 24.00% (6/25), recall 13.64% (6/44), exact match 17.31% (9/52), unsupported-claim rate 76.00% (19/25), `NOT_REPORTED` accuracy 37.50% (3/8), evidence-location accuracy 0% (0/44) |
| Evidence re-verification | **73 of 73** stored quotations relocated on the exact page cited; **4 of 4** source hashes reproduced |
| Non-golden extraction | GLONET 15 populated fields, DINCAE 2.0 21 populated fields, with no paper-specific code |
| Unsupported proposals rejected | 85 across the four validation papers |
| Fabricated claims found | 0 |

The two numbers that look contradictory — a 76% "unsupported-claim rate"
alongside zero failed evidence re-verifications — are not a mistake. The
benchmark's metric counts any claim that is not byte-identical to the golden
label, including claims that quote the paper correctly but normalize it
differently. `issue-19-benchmark-summary.md` lists all 19 side by side.
Do not read that metric as a hallucination rate.

Automated suite at the commit under audit: **252 passed**, 2 warnings (both
third-party deprecation warnings from Starlette's test client).

---

## 1. What to audit, in order

| # | Question | Where to look |
|---|---|---|
| 1 | Are the source documents the ones claimed? | §2 source identity, then re-run the verifier in §6 |
| 2 | Is every asserted claim's quotation really on the page it cites? | `issue-19-evidence-reverification.md` |
| 3 | Is the normalized value a correct reading of that quotation? | `issue-19-four-paper-validation.md`, `4dvarnet-ssh-extraction-audit.md` |
| 4 | Is every `NOT_REPORTED` backed by an adequate search scope? | the `Absence search scope` column in both reports |
| 5 | Is anything reported as absent that the paper actually reports? | §5 known failure modes, then spot-check the probe vocabulary |
| 6 | Do the benchmark numbers follow from the artifacts? | `issue-19-benchmark-summary.md` + `issue-19-after-benchmark.json` |
| 7 | Does the system generalize beyond the golden papers? | `issue-19-generalization-report.md` |

Question 3 is the one only a domain expert can answer, and it is the reason
this package exists.

---

## 2. Exact source identity

All six documents are pinned by SHA-256. They are cached under the
git-ignored `.data/golden-pdfs/` directory and re-downloaded from the URLs
below when absent.

| Paper ID | Role | DOI / identifier | SHA-256 |
|---|---|---|---|
| `4dvarnet-ssh-2023` | golden + mandatory audit paper | `10.5194/gmd-16-2119-2023` | `bfad134ecdf1a4786ee4fdadc21746ab9e2106618513d8418a357cb39f9f0b88` |
| `oceannet-2023` | golden, heterogeneous (has supplement) | `10.1038/s41598-024-72145-0` | `be82ff557769aff04b119490d6a2ebb718887a1e3962355ab10cc9a7291802e9` |
| `oceannet-2023-supplement` | supplementary material | — | `c3e7f690fab8563d4bfb2728a594bc2adb8e4d42a50872a1e0c97e34f4d7adbf` |
| `xihe-2024` | golden (benchmark only) | `arXiv:2402.02995v4` | `a7d1c25ed007983fb496ab174dcedb0bb85180f9fb0967fe499bc455e2198114` |
| `glonet-2025` | **non-golden** generalization paper | `10.1029/2025JH000686` | `bc9627304aefb8c29b1eb069a3362996c1b240940e7f7411585987445ad7b76f` |
| `dincae-2-2022` | **non-golden** generalization paper | `10.5194/gmd-15-2183-2022` | `017757e5a2394713d7c18f9b68de0559d003c4843c63d3c84ecc16a5d05d9bf0` |

Source URLs are recorded per paper in `evaluation/issue-19-validation-papers.json`
and in the header of every generated report.

`glonet-2025` and `dincae-2-2022` have **no golden labels and no
paper-specific extraction code**. They exist to answer one question: does the
general extraction path produce defensible output on papers nobody tuned it
for? Confirm this independently — `grep -ri "glonet\|dincae" src/` must return
nothing but the manifest-driven generic path.

---

## 3. Artifacts in this package

Machine-readable (the evidence):

| File | Contents |
|---|---|
| `issue-19-four-paper-extraction.json` | every targeted field for all four validation papers: value, status, provenance, page, section, locator, exact evidence, evidence URL, absence search scope |
| `issue-19-after-predictions.json` | pre-audit predictions for the three golden papers, in the benchmark's prediction schema |
| `issue-19-after-benchmark.json` | the benchmark report: overall and per-field-family metrics, each with numerator and denominator |
| `issue-19-extraction-cache.json` | the extracted records from the exact run under review, so every report can be regenerated without a provider API key |
| `issue-19-evidence-reverification.json` | independent re-check of every stored snippet against a freshly parsed PDF |

Human-readable (the narrative, all generated or derived from the above):

| File | Contents |
|---|---|
| `4dvarnet-ssh-extraction-audit.md` | the mandatory per-field 4DVarNet-SSH table, with a blank column per field for the auditor's decision |
| `issue-19-four-paper-validation.md` | the same table for all four validation papers |
| `issue-19-evidence-reverification.md` | which stored quotations relocate in the source, and which do not |
| `issue-19-benchmark-summary.md` | BEFORE vs FINAL metrics with the explanation of every movement |
| `issue-19-generalization-report.md` | the four-paper narrative, including failures |
| `issue-19-independent-audit-package.md` | this file |

Golden labels under audit-by-comparison: `evaluation/golden_dataset/*.json`
(`4dvarnet-ssh.json`, `oceannet.json`, `xihe.json`).

---

## 4. Recording an audit decision

The runner accepts auditor-authored decision bundles and refuses to render them
unless they match the paper ID and the source PDF digest, so a decision cannot
be attached to a document other than the one that was audited.

- Single-paper (4DVarNet): `AuditDecisionSet` — `paper_id`, `source_pdf_sha256`,
  `auditor`, and one `AuditDecision` per path in `AUDIT_PATHS`. Every path must
  be covered; a partial bundle is rejected.
- Four-paper: `ValidationDecisionBundle` — a list of the above.

Both schemas are defined in `src/ocean_research_hub/evaluation/real_pdf.py`.
Pass them with `--audit-decisions` and `--validation-decisions` (§6).

---

## 5. Known failure modes, declared up front

These are stated here so the audit starts from them rather than discovering
them. Details and counts are in `issue-19-generalization-report.md` and
`issue-19-benchmark-summary.md`.

1. **Evidence-location accuracy is 0% and is expected to stay there.** Golden
   locators are human prose (`"opening paragraph"`, `"contributions bullet 1"`).
   The extractor emits machine locators (`"PDF paragraph 3"`,
   `"LLM-proposed evidence"`). The metric demands exact equality of the whole
   `(page, section, locator)` set, so it cannot be satisfied without encoding
   the golden answers. The previously reported 77% came from paper-specific
   profiles that did exactly that; those profiles were removed.
2. **The unsupported-claim rate mixes two very different faults.** It counts
   any asserted claim that is not byte-identical to the golden label, so a
   claim quoting the paper correctly but normalizing it differently
   (`"1/20°"` against `"NATL60 SSH downgraded to 1/20 degree for experiments"`)
   scores identically to a fabrication. The evidence re-verification artifact
   is the way to tell them apart; do not read this metric as a hallucination
   rate.
3. **Absence is lexical, not semantic.** `NOT_REPORTED` is asserted when none
   of a field's near-closed reporting vocabulary occurs in the searched text.
   That vocabulary is finite, so a paper can report a field in wording the
   probe does not contain. Two such false absences were found and fixed during
   development; more may remain. This is the single most dangerous residual
   risk in the pipeline and deserves the most auditor attention.
4. **Absence is scoped to what the run actually read.** Where no supplement was
   supplied, `NOT_REPORTED` means "not in the primary document", and the scope
   string says so. 4DVarNet-SSH has linked video supplements that this run did
   not fetch.
5. **Semantic extraction is non-deterministic.** The provider is called at
   temperature 0, but the output is not guaranteed reproducible. The committed
   artifacts are from one specific run; replay them from the extraction cache
   rather than expecting a fresh run to match byte-for-byte.

---

## 6. Exact reproduction commands

Install:

```bash
uv sync --all-extras --frozen
```

**Re-render every report from the exact run under review — no API key, no
network.** This is the recommended starting point: it proves the committed
markdown follows from the committed extraction cache.

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

**Independently re-verify every stored quotation against the source PDFs.**
This imports no extraction rule and no provider; it re-hashes and re-parses the
documents and asks only whether each snippet is on the page it claims.

```bash
uv run ocean-research-hub-verify-evidence \
  evaluation/reports/issue-19-four-paper-extraction.json \
  --report-out evaluation/reports/issue-19-evidence-reverification.md \
  --json-out evaluation/reports/issue-19-evidence-reverification.json
```

Add `--offline` to make a missing cached PDF a visible failure instead of a
silent download.

**Regenerate from scratch with the semantic provider** (requires
`ANTHROPIC_API_KEY`; produces a different, non-identical run):

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

`--semantic-provider gemini` selects the alternative provider; omitting the
flag runs the deterministic path only and makes no network call.

**Deterministic-only benchmark** (no provider, fully reproducible):

```bash
uv run ocean-research-hub-real-pdf-benchmark \
  --predictions-out /tmp/det-predictions.json \
  --benchmark-out /tmp/det-benchmark.json \
  --audit-out /tmp/det-audit.md
```

**Automated suite:**

```bash
uv run pytest -q
```

**Record audit decisions** once written:

```bash
uv run ocean-research-hub-real-pdf-benchmark \
  --predictions-out evaluation/reports/issue-19-after-predictions.json \
  --benchmark-out evaluation/reports/issue-19-after-benchmark.json \
  --audit-out evaluation/reports/4dvarnet-ssh-extraction-audit.md \
  --audit-decisions path/to/4dvarnet-decisions.json \
  --validation-manifest evaluation/issue-19-validation-papers.json \
  --validation-report-out evaluation/reports/issue-19-four-paper-validation.md \
  --validation-json-out evaluation/reports/issue-19-four-paper-extraction.json \
  --validation-decisions path/to/validation-decisions.json \
  --extraction-cache evaluation/reports/issue-19-extraction-cache.json
```

---

## 7. Integrity rules the implementation claims to enforce

Each rule below is testable. The named tests are the implementer's evidence
that it holds; an auditor should try to break them rather than read them.

| Rule | Where it is enforced | Regression |
|---|---|---|
| A populated claim must have a quotation located on its cited page | `EvidenceValidator.locate_free_text` | `test_evidence_reverification.py`, `test_issue19_adversarial_regressions.py` |
| An LLM value must overlap the quotation it was derived from | `EvidenceValidator.supports_normalization` | `test_semantic_extraction.py` |
| Extraction failure is never absence | `mark_extraction_error`, `_effective_status` | `test_mentioned_but_ungroundable_field_is_an_extraction_error_not_an_absence` |
| Absence requires a recorded search scope | `resolve_absences`, schema validator | `test_absence_probe_asserts_absence_only_with_a_recorded_search_scope` |
| Open-vocabulary fields are never declared absent lexically | `ABSENCE_PROBES` omits them | `test_narrative_fields_never_receive_a_lexical_absence_assertion` |
| Supplementary evidence keeps supplementary provenance and URL | `SemanticExtractor.extract` | `test_supplementary_semantic_claim_carries_the_pinned_supplement_url` |
| Contradictory claims become `CONFLICT`, never a silent choice | `set_extracted_field` | `test_third_distinct_claim_extends_conflict_instead_of_overwriting_it` |
| Nothing is promoted to `VERIFIED` by extraction | no code path sets it | `test_paper_record_scientific_audit_regression.py` |
| A baseline's or related work's number is not this paper's configuration | `ScientificExtractor._generic_extract` | `test_deterministic_hyperparameters_reject_related_work_or_baseline_context` |
| No architecture convention is inferred from silence | `ScientificExtractor._generic_extract` | `test_architecture_conventions_are_not_inferred_when_the_source_is_silent` |
