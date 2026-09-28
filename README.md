# Ocean Research Hub

Ocean Research Hub is a local, evidence-first MVP for ingesting, inspecting, comparing, and
benchmarking structured ocean-science paper records. Scientific fields retain their verification
status, provenance, and source evidence. Missing values remain `NOT_REPORTED`, disagreements remain
`CONFLICT`, and AI/team interpretation stays separate from author-reported content.

The scientific and multi-agent operating contract is in [`AGENTS.md`](AGENTS.md).

## Prerequisites

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/)
- Network access only when importing DOI metadata from Crossref

## Install and start

From the repository root, install exactly the locked dependencies and start the API:

```bash
uv sync --all-extras --frozen
uv run ocean-research-hub
```

The server listens on `http://127.0.0.1:8000`. Check it at:

- health: `http://127.0.0.1:8000/health`
- interactive API documentation: `http://127.0.0.1:8000/docs`
- OpenAPI schema: `http://127.0.0.1:8000/openapi.json`

Records are stored in `.data/ocean-research-hub.db` by default. To use another SQLite file:

```bash
OCEAN_HUB_DB_PATH=/absolute/path/ocean-hub.db uv run ocean-research-hub
```

## Ingest a paper

Import bibliographic metadata by DOI through Crossref:

```bash
curl -X POST http://127.0.0.1:8000/api/papers/ingest \
  -H 'content-type: application/json' \
  -d '{"doi":"10.5194/gmd-16-2119-2023"}'
```

For deterministic or offline ingestion, post `metadata`, `parsed_paper`, or both to the same
endpoint. `parsed_paper` must be a complete `PaperRecord`; the canonical example is
[`specs/paper-record.example.json`](specs/paper-record.example.json). For example:

```bash
uv run python - <<'PY' > /tmp/ocean-hub-ingest.json
import json
from pathlib import Path

record = json.loads(Path("specs/paper-record.example.json").read_text())
print(json.dumps({"parsed_paper": record}))
PY
curl -X POST http://127.0.0.1:8000/api/papers/ingest \
  -H 'content-type: application/json' \
  --data-binary @/tmp/ocean-hub-ingest.json
```

The response contains the stable paper `id`. Repeating identical input returns the existing record;
reusing the same identity with different content returns HTTP `409` and does not overwrite it.
Schema-invalid or scientifically unsafe structured fields are rejected.

## Retrieve and compare papers

Replace `PAPER_ID` with an ID returned by ingestion:

```bash
curl http://127.0.0.1:8000/api/papers/PAPER_ID
```

The evidence/status-aware HTML detail is at `http://127.0.0.1:8000/papers/PAPER_ID`.

Compare two distinct stored records in request order:

```bash
curl "http://127.0.0.1:8000/api/papers/compare?left_id=PAPER_ID_A&right_id=PAPER_ID_B"
```

The side-by-side HTML view is at
`http://127.0.0.1:8000/papers/compare?left_id=PAPER_ID_A&right_id=PAPER_ID_B`. It covers data,
architecture, training, losses, evaluation, results, and limitations without stripping status,
provenance, evidence, `NOT_REPORTED`, or conflict alternatives.

## Query normalized research intelligence

Every successful ingest is also projected into normalized, cross-paper entities while the complete
`PaperRecord` remains the lossless source of truth. Query all datasets, for example:

```bash
curl "http://127.0.0.1:8000/api/research/entities?entity_type=DATASET"
```

`GET /api/research/entities/{ENTITY_ID}` returns every paper relationship with original wording,
status, provenance, and evidence. `GET /api/research/papers/{PAPER_ID}` returns source editions,
all canonical field states, entity relationships, all training hyperparameters (including `NOT_REPORTED` and
`EXTRACTION_ERROR`), entity-field states, reported results, limitations, and future work. Field
states preserve audit metadata and exact evidence-edition bindings. Entity-to-entity relationships
require an explicit evidence-backed API call and are never inferred from co-occurring lists.
Bibliography field states are also edition-scoped, so a primary-source upgrade does not erase the
superseded metadata title, authors, identifiers, URLs, or their evidence.

Register an additional PDF or supplement edition without overwriting another version:

```bash
curl -X POST http://127.0.0.1:8000/api/research/papers/PAPER_ID/source-editions \
  -H 'content-type: application/json' \
  -d '{"edition_key":"publisher-v2","source_type":"PRIMARY_PDF","uri":"https://example.org/paper-v2.pdf","content_hash":"sha256:...","version_label":"version 2","is_primary":true}'
```

Edition-key retries must be identical; changed identity returns HTTP `409`. The normalization and
future corpus-manifest boundary are documented in
[`docs/adr/0002-research-intelligence-model.md`](docs/adr/0002-research-intelligence-model.md).

## Run the extraction benchmark

The repository includes three independently audited golden papers and a deterministic field-level
benchmark. Smoke-test the CLI with the intentionally empty example predictions:

```bash
uv run ocean-research-hub-benchmark evaluation/example_predictions.json
```

Evaluate another prediction file, optionally against a different audited corpus:

```bash
uv run ocean-research-hub-benchmark path/to/predictions.json
uv run ocean-research-hub-benchmark path/to/predictions.json \
  --golden-dir path/to/golden_dataset
```

The input contract, strict metrics, corpus sources, and audit procedure are documented in
[`evaluation/README.md`](evaluation/README.md).

## Validate the project

```bash
uv run pytest
uv run python -m compileall -q src tests
uv build
```

`pytest` runs schema, ingestion, persistence, API, detail/comparison rendering, golden-dataset,
benchmark, provenance, and scientific-integrity regressions.

## MVP boundaries

- Persistence is local SQLite; there is no PostgreSQL/Supabase deployment, authentication, or
  multi-user collaboration yet.
- DOI ingestion retrieves Crossref bibliographic metadata. The MVP does not download or parse PDFs;
  structured parsed records are supplied by the caller behind a replaceable parser interface.
- Retrieval is by stable paper ID. There is no catalog, keyword search, or semantic/vector search.
- The server-rendered detail and comparison pages are intentionally minimal; there is no Next.js
  client yet.
- The three-paper golden dataset is a compact safety benchmark, not a comprehensive scientific
  corpus. Extraction outputs remain pre-audit until an independent Scientific Auditor verifies
  them against primary sources.

The local architecture decision and replacement boundaries are recorded in
[`docs/adr/0001-local-vertical-slice.md`](docs/adr/0001-local-vertical-slice.md).

# PDF scientific extraction

The ingestion API accepts a local PDF path or a resolvable PDF URL:

```json
{"pdf_path": "/data/papers/ocean-paper.pdf"}
```

The parser records page-aware primary-paper evidence and the deterministic
extractor emits conservative `NOT_VERIFIED` claims. Fields not found in the
extractable page text remain `NOT_REPORTED`; parser failures return
`PARSER_ERROR` and are not represented as absent science. Repeated conflicting
claims retain both alternatives as `CONFLICT`. The extraction search scope is
stored in the paper warnings for audit review.
