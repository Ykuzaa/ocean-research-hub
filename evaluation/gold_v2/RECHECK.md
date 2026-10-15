# Independent re-check contract (machine channel)

A record that passes `corpus_v2.gate` is **sourced**: every stored quote exists word for
word on the page it cites, and the stored value is derivable from that quote. That is a
*textual* guarantee. It says nothing about whether the value was read in the **right
context** — whether this RMSE belongs to this model rather than its baseline, on this
dataset rather than the next column, on the test split rather than the training one.

The re-check is a second, independent reading of the paper that answers exactly that
question. It is a **machine channel**: its verdicts are recorded as such and never
presented as a human scientific audit. `evaluation/audit_v2/verdicts.json` (the human
ledger) and `evaluation/audit_v2/recheck.json` (this one) are separate files on purpose.

## What a re-checker does

For **every** claim in one record:

1. Open the cited PDF page with `pypdf` and read the surrounding text, not just the quote.
2. Decide whether the stored value is the correct reading **of that context**:
   - a number must belong to the stored `metric`, `unit`, `split`, `dataset_id` and
     `experiment_id`; the single most common extraction defect is a value taken from the
     neighbouring column, row, or model;
   - `baseline_value` must be the comparison, never the proposed model's own number, and
     the two must not be swapped;
   - `is_best_in_table` must hold in the table as printed;
   - a training value must belong to the experiment it is attached to, not to another
     configuration of the same paper;
   - a `limitation` must be a limitation the **authors** state, not an inference;
   - a `family` must follow the arbitration rules in `SCHEMA.md`, not the closest-looking
     entry.
3. Emit one verdict per claim:
   - `CONFIRMED` — the value is the right reading of the right context.
   - `SUSPECT` — something does not line up and a human must look; give the reason and,
     when you can read it, the value you believe is correct.
   - `UNREADABLE` — the page text is too mangled to judge (say which symbol breaks it).

## Hard rules

- **Never edit a record, or any other repository file.** Write only your own report. A
  correction is a finding reported to the orchestrator, never an edit you make.
- **Never invent.** If you cannot find the context, the verdict is `UNREADABLE`, not a
  guess.
- **Never mark a claim `CONFIRMED` because the gate passed.** The gate is a precondition,
  not evidence: you are checking what the gate cannot see.
- Read the PDF as text with Python (`pypdf`), never as images.
- The quote may differ cosmetically from the page (ligatures, hyphenation, Unicode minus):
  that is expected and already handled; it is never by itself a reason to flag a claim.

## Report shape

One JSON file, `evaluation/work/recheck/<slug>.json`:

```json
{
  "slug": "", "checked_at": "YYYY-MM-DD", "model": "",
  "claims": {
    "results[3]": {"verdict": "CONFIRMED"},
    "results[7]": {"verdict": "SUSPECT", "reason": "0.42 is the UNet-bathy column, not Seabed-Net",
                   "correct_reading": 0.408, "page_pdf": 10},
    "experiments[2].training.epochs": {"verdict": "UNREADABLE", "reason": "..."}
  },
  "judgement_calls": ["..."],
  "summary": {"confirmed": 0, "suspect": 0, "unreadable": 0}
}
```

The keys are the claim paths exactly as the orchestrator supplies them: every path must
appear in `claims`, or the report is incomplete and is rejected.
