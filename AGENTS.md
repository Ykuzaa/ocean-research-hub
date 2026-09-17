# AGENTS.md — Ocean Research Hub

This file is the operating contract for Codex and all project agents.

## Mission

Build a collaborative scientific knowledge base for Oceanography × Statistics × ML/DL × Data Assimilation × Scientific ML.

The application must ingest scientific papers, extract detailed technical information, preserve provenance, support search/comparison, and expose research gaps without inventing missing information.

## Non-negotiable scientific rules

1. **Never guess.** If a technical value is not explicitly supported by the paper, store `NOT_REPORTED`.
2. **Evidence before verification.** No scientific field may be marked `VERIFIED` without source evidence.
3. **Separate fact from interpretation.** Use distinct provenance classes:
   - `AUTHOR_REPORTED_FACT`
   - `AUTHOR_REPORTED_LIMITATION`
   - `AI_INTERPRETATION`
   - `TEAM_NOTE`
4. **Do not infer conventions.** Example: if a Transformer paper does not state GELU, activation must not be filled as GELU.
5. **Conflicts stay visible.** If two parts of the paper disagree, use `CONFLICT`; do not silently choose one.
6. **Primary source wins.** Prefer the paper/supplement over secondary summaries.
7. **Scientific traceability is more important than extraction coverage or speed.**

## Three-agent model

Ocean Research Hub uses three independent specialist roles coordinated by the parent Codex session.

### Codex model routing policy

Use the project configurations in `.codex/config.toml` and `.codex/agents/`.

| Role | Model | Reasoning effort | Intent |
|---|---|---|---|
| Orchestrator / parent | `gpt-5.6-sol` | `high` | planning, delegation, difficult cross-agent decisions |
| Developer | `gpt-5.6-sol` | `medium` | architecture and implementation |
| QA Engineer | `gpt-5.6-terra` | `high` | high-throughput adversarial review and testing |
| Scientific Auditor | `gpt-5.6-sol` | `high` | evidence-sensitive scientific verification |

The Scientific Auditor must not be downgraded merely to save quota. Scientific evidence validation is a high-reasoning task.

### Runtime model verification

Model routing is a requested runtime policy, not something agents may silently assume succeeded.

When Codex exposes effective child-thread model/effort metadata, the orchestrator should verify it at the start of a multi-agent run. If the runtime ignores a role-specific model pin and a child inherits the parent model, report that explicitly in the final run summary. Do not claim cost/quota separation unless the effective runtime confirms it.

If a configured model is unavailable to the current account/runtime, fail visibly or use an explicitly approved fallback; never silently substitute a weaker scientific-audit model.

### Agent 1 — Developer

Responsible for implementation only.

Owns:
- web application;
- backend/API;
- database schema/migrations;
- ingestion pipeline;
- PDF parsing integration;
- metadata retrieval;
- structured extraction engine;
- search and comparison;
- authentication/team collaboration;
- developer documentation.

The Developer may implement extraction logic but **must not self-certify scientific correctness**.

### Agent 2 — QA Engineer

Independent quality engineer. Its job is to break the implementation and find regressions.

Owns:
- unit tests;
- integration tests;
- end-to-end tests;
- malformed/edge-case PDF tests;
- schema validation tests;
- API/database failure tests;
- reproducibility tests;
- regression suite;
- CI checks.

The QA agent must test at least:
- missing DOI;
- missing metadata;
- multi-column papers;
- long papers;
- appendices and supplementary material;
- tables containing hyperparameters;
- figure captions containing architecture details;
- absent technical parameters;
- conflicting values;
- parser failures;
- duplicate papers;
- partial extraction;
- invalid model outputs.

QA reports `PASS`, `FAIL`, or `BLOCKED` and explains why.

### Agent 3 — Scientific Auditor

Independent scientific validation agent. It must distrust extracted values until verified against the source.

For each field it checks:
- value;
- source page;
- source section;
- evidence text/caption/table reference;
- provenance class;
- confidence;
- verification status.

Allowed verification statuses:
- `VERIFIED`
- `PARTIALLY_VERIFIED`
- `NOT_VERIFIED`
- `NOT_REPORTED`
- `CONFLICT`
- `EXTRACTION_ERROR`

The Scientific Auditor is not allowed to convert a plausible inference into a reported fact.

## Required workflow for substantial features

1. Developer implements on a dedicated branch.
2. QA independently reviews/tests.
3. If scientific extraction behavior changes, Scientific Auditor validates representative outputs.
4. Developer fixes defects.
5. QA reruns tests.
6. Scientific Auditor reruns scientific validation when applicable.
7. Only then may the feature be considered ready to merge.

## Required workflow for a paper

`INGESTED → PARSED → EXTRACTED → SCIENTIFIC_AUDIT → VERIFIED/PARTIAL/REJECTED`

A paper may be displayed before full audit, but every field must visibly expose its verification state.

## Evidence model

Each extracted scientific field should support at least:

```json
{
  "value": null,
  "status": "NOT_REPORTED",
  "provenance_type": "AUTHOR_REPORTED_FACT",
  "confidence": 0.0,
  "source": {
    "section": null,
    "page": null,
    "locator": null,
    "evidence": null
  },
  "verified_by": null,
  "verified_at": null
}
```

## Information to capture per paper

### Bibliography
- title
- authors
- year
- journal/conference
- DOI
- arXiv
- publisher URL
- PDF
- code URL
- dataset URLs

### Scientific framing
- scientific problem
- motivation
- hypothesis/objective
- task type
- domain/subdomain
- geographic region
- ocean regime

### Data
- datasets
- observational/model/reanalysis origin
- variables
- units
- depth levels
- spatial resolution
- temporal resolution
- time coverage
- train/validation/test periods
- sample counts
- missing-data handling
- masks
- interpolation/regridding
- anomaly computation
- normalization/standardization
- filtering/smoothing
- augmentation
- derived features

### Architecture
- model family
- full architecture description
- encoder/decoder structure
- layer/block count
- hidden dimensions
- channels
- patch/window size
- attention type
- positional encoding
- skip/residual connections
- activation functions
- normalization layers
- dropout
- parameter count
- autoregressive/direct setup
- deterministic/probabilistic setup
- physical components

### Training
- optimizer
- learning rate
- scheduler
- batch size
- epochs/steps
- early stopping
- weight decay
- gradient clipping
- initialization
- mixed precision
- random seeds
- hardware
- number/type of GPUs
- training time

### Objective/loss
- primary loss
- auxiliary losses
- physical constraints
- spectral losses
- gradient/front losses
- probabilistic losses
- weighting coefficients

### Evaluation
- baselines
- metrics
- forecast horizon
- evaluation datasets
- observation-space validation
- uncertainty calibration
- ablations
- robustness/OOD tests
- statistical significance when reported

### Results
- headline quantitative results
- per-variable results
- per-region/depth/horizon results
- qualitative findings
- computational cost

### Limitations and research gaps
- author-reported limitations
- author-reported future work
- reproducibility gaps
- data limitations
- physics limitations
- OOD/generalization limitations
- uncertainty limitations
- computational limitations
- AI/team interpretation kept strictly separate

## Golden dataset and evaluation

Maintain a curated `evaluation/golden_dataset/` with manually verified papers.

Track per field family:
- precision
- recall
- exact-match accuracy
- unsupported-claim rate
- `NOT_REPORTED` accuracy
- evidence-location accuracy

**Unsupported-claim rate is a critical safety metric and should be minimized.**

Any material change to extraction logic must be benchmarked against the golden dataset before acceptance.

## Initial application stack

Preferred baseline unless changed by an ADR:
- Next.js + TypeScript
- Tailwind CSS
- FastAPI/Python
- PostgreSQL / Supabase
- pgvector for semantic retrieval
- GROBID-compatible parsing layer
- Crossref-compatible metadata layer

Keep integrations behind interfaces so providers can be replaced.

## First milestone

Do not start with a visually complex dashboard.

First milestone is a trustworthy vertical slice:

1. create/import one paper;
2. store bibliographic metadata;
3. store detailed structured scientific fields;
4. attach evidence and verification status to fields;
5. render a clean paper detail page;
6. compare two papers;
7. run automated schema/tests;
8. evaluate extraction against at least one golden paper.

Reliability first, polish second.
