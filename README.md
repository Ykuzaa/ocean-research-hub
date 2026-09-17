# Ocean Research Hub

A collaborative scientific knowledge base for Oceanography × Statistics × Machine Learning × Deep Learning × Data Assimilation × Scientific ML.

## Goal

Turn scientific papers into deeply structured, evidence-backed records that researchers can search, compare, audit, and use to identify research gaps.

Core principles:

- **Scientific traceability first**: every extracted fact must point back to evidence in the source paper.
- **Never guess missing technical details**: use `NOT_REPORTED` when the paper does not state a value.
- **Separate facts from interpretation**: author-reported facts and limitations must remain distinct from AI/team analysis.
- **Multi-agent quality control**: implementation, QA, and scientific audit are independent responsibilities.

The detailed agent contract lives in `AGENTS.md`.

## Codex multi-agent setup

Project-level Codex configuration lives in `.codex/config.toml` with three specialist roles:

- **Developer** — `gpt-5.6-sol`, medium reasoning;
- **QA Engineer** — `gpt-5.6-terra`, high reasoning;
- **Scientific Auditor** — `gpt-5.6-sol`, high reasoning.

The parent/orchestrator is configured for `gpt-5.6-sol` with high reasoning.

Start Codex from the repository root:

```bash
codex
```

Then begin with:

```text
Read AGENTS.md carefully and start GitHub issue #1.
Use the Developer -> QA Engineer -> Scientific Auditor workflow.
Verify the effective subagent model/effort if the runtime exposes that metadata.
Do not move to issue #2 until issue #1 satisfies all acceptance criteria.
```

If the runtime ignores a role-specific model pin, report it explicitly rather than assuming model separation worked.

## Run the ingestion vertical slice

Install the locked dependencies and start the local API:

```bash
uv sync --all-extras --frozen
uv run ocean-research-hub
```

The service uses `.data/ocean-research-hub.db` by default. Set `OCEAN_HUB_DB_PATH` to use a
different local SQLite file. API documentation is available at `http://127.0.0.1:8000/docs`.

Import a DOI (Crossref network access required):

```bash
curl -X POST http://127.0.0.1:8000/api/papers/ingest \
  -H 'content-type: application/json' \
  -d '{"doi":"10.1000/example"}'
```

For an offline import, send `metadata`, `parsed_paper`, or both. Retrieved records are available
as JSON at `/api/papers/{id}` and as a minimal evidence/status detail page at `/papers/{id}`.
Repeated identical ingestion returns the existing paper; a duplicate identity with different
content returns `409` and never overwrites the stored record.

## Run the scientific extraction benchmark

The initial golden dataset contains three independently audited, primary-source-backed ocean-AI papers and
a deterministic field-level benchmark. Run it against a prediction JSON file with:

```bash
uv run ocean-research-hub-benchmark path/to/predictions.json
```

The corpus methodology, prediction contract, metric definitions, and Scientific Auditor handoff
are documented in [`evaluation/README.md`](evaluation/README.md). Truth labels retain audited
`VERIFIED`, `NOT_REPORTED`, or `CONFLICT` states while extractor predictions remain independently
pre-audit.

The local persistence/UI choice is documented in
[`docs/adr/0001-local-vertical-slice.md`](docs/adr/0001-local-vertical-slice.md).
