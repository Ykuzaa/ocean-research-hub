# Issue #19 golden benchmark: before and after

Both runs use the three audited golden papers and all 51 compact benchmark fields.
The BEFORE run was captured from commit `731049e` before extraction logic changed;
it exactly reproduces the snapshot reported in PR #18. The AFTER run is reproducible
with the command below and its complete JSON is committed beside this report.

| Metric | BEFORE | AFTER |
|---|---:|---:|
| Precision | 5.5556% (1/18) | 100% (33/33) |
| Recall | 2.3256% (1/43) | 76.7442% (33/43) |
| Exact match | 17.6471% (9/51) | 64.7059% (33/51) |
| Unsupported-claim rate | 94.4444% (17/18) | 0% (0/33) |
| NOT_REPORTED accuracy | 100% (8/8) | 0% (0/8) |
| Evidence-location accuracy | 0% (0/43) | 76.7442% (33/43) |

```bash
uv run ocean-research-hub-real-pdf-benchmark \
  --predictions-out evaluation/reports/issue-19-after-predictions.json \
  --benchmark-out evaluation/reports/issue-19-after-benchmark.json \
  --audit-out evaluation/reports/4dvarnet-ssh-extraction-audit.md
```

The remaining ten missed asserted fields are deliberately unpopulated rather than
guessed. They are predominantly semantic XiHe fields and evaluation/result fields
for which no evidence-strict normalization contract exists. The eight audited
absence fields also score as misses: this PDF-only run did not inspect applicable
supplementary material and therefore reports `EXTRACTION_ERROR`, not an unsupported
`NOT_REPORTED` assertion. No asserted AFTER prediction is unsupported. Scientific
correctness still requires the independent audit gate.
