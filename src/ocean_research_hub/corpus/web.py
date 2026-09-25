"""API routes and server-rendered pages for the staging corpus.

Everything served here is labelled as staging material: candidate claims that
are ``NOT_VERIFIED``, empty fields that are ``NOT_EXTRACTED``, and research-gap
candidates that are team hypotheses. Nothing is promoted by being displayed.
"""

from __future__ import annotations

import json
from html import escape
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

from .repository import CorpusNotFoundError, CorpusRepository

STAGING_NOTICE = (
    "Staging corpus - NOT independently verified. Candidate claims are NOT_VERIFIED; "
    "empty fields are NOT_EXTRACTED (nobody looked), never NOT_REPORTED; a field the package "
    "looked for and did not find is at most a NOT_REPORTED_CANDIDATE within its stated search scope. "
    "PDF page numbers, where present, are as supplied by the package and unchecked; no verbatim "
    "quotation has been aligned."
)


def register_corpus_routes(app: FastAPI, repository: CorpusRepository) -> None:
    def not_found(error: CorpusNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND", "message": str(error)}})

    @app.get("/api/corpus")
    async def corpus_summary() -> dict[str, Any]:
        return {"notice": STAGING_NOTICE, **repository.summary()}

    @app.get("/api/corpus/papers")
    async def corpus_papers(
        q: str | None = None, domain: str | None = None, review_stage: str | None = None,
        limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        papers, total = repository.list_papers(
            query=q, domain=domain, review_stage=review_stage, limit=limit, offset=offset,
        )
        return {"notice": STAGING_NOTICE, "total": total, "limit": limit, "offset": offset, "papers": papers}

    @app.get("/api/corpus/papers/{paper_id}", response_model=None)
    async def corpus_paper(paper_id: str) -> dict[str, Any] | JSONResponse:
        try:
            return {"notice": STAGING_NOTICE, **repository.get_paper(paper_id)}
        except CorpusNotFoundError as error:
            return not_found(error)

    @app.get("/api/corpus/claims")
    async def corpus_claims(
        paper_id: str | None = None, field_path: str | None = None, experiment_id: str | None = None,
        limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        claims, total = repository.list_claims(
            paper_id=paper_id, field_path=field_path, experiment_id=experiment_id,
            limit=limit, offset=offset,
        )
        return {"notice": STAGING_NOTICE, "total": total, "limit": limit, "offset": offset, "claims": claims}

    @app.get("/api/corpus/claims/{claim_id}", response_model=None)
    async def corpus_claim(claim_id: str) -> dict[str, Any] | JSONResponse:
        try:
            return {"notice": STAGING_NOTICE, **repository.get_claim(claim_id)}
        except CorpusNotFoundError as error:
            return not_found(error)

    @app.get("/api/corpus/fields")
    async def corpus_fields() -> dict[str, Any]:
        fields = repository.field_contract()
        return {"total": len(fields), "fields": fields}

    @app.get("/api/corpus/research-gaps")
    async def corpus_gaps() -> dict[str, Any]:
        gaps = repository.research_gaps()
        return {
            "notice": "Research-gap candidates are team hypotheses or AI interpretations, not "
                      "author-reported limitations and not established novelty.",
            "total": len(gaps), "research_gaps": gaps,
        }

    @app.get("/api/corpus/import-runs")
    async def corpus_runs() -> dict[str, Any]:
        return {"import_runs": repository.import_runs()}

    @app.get("/corpus", response_class=HTMLResponse)
    async def corpus_page(q: str | None = None, domain: str | None = None) -> HTMLResponse:
        papers, total = repository.list_papers(query=q, domain=domain, limit=500)
        return HTMLResponse(render_corpus_index(papers, total, repository.summary(), repository.research_gaps()))

    @app.get("/corpus/papers/{paper_id}", response_class=HTMLResponse)
    async def corpus_paper_page(paper_id: str) -> HTMLResponse:
        try:
            paper = repository.get_paper(paper_id)
        except CorpusNotFoundError as error:
            return HTMLResponse(_page("Not found", f"<p>{escape(str(error))}</p>"), status_code=404)
        return HTMLResponse(render_corpus_paper(paper))


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · Ocean Research Hub staging corpus</title>
<style>
body{{font:14px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1200px;padding:16px;color:#14202b;background:#fff}}
.notice{{border:1px solid #b7791f;background:#fffaf0;padding:8px 12px;margin:12px 0}}
table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #d9e1e8;padding:4px 6px;text-align:left;vertical-align:top}}
th{{background:#f3f6f9}}code{{font-size:12px}}.muted{{color:#5b6b79}}.status{{font-family:monospace;font-size:12px}}
details summary{{cursor:pointer}}a{{color:#0b5c8a}}
</style></head><body>{body}</body></html>"""


def _cell(value: Any) -> str:
    if value is None:
        return '<span class="muted">—</span>'
    if isinstance(value, (list, dict)):
        return escape(json.dumps(value, ensure_ascii=False))
    return escape(str(value))


def render_corpus_index(
    papers: list[dict[str, Any]], total: int, summary: dict[str, Any], gaps: list[dict[str, Any]],
) -> str:
    rows = "".join(
        f"<tr><td><a href=\"/corpus/papers/{escape(paper['paper_id'])}\"><code>{escape(paper['paper_id'])}</code></a></td>"
        f"<td>{_cell(paper['title'])}</td><td>{_cell(paper['year'])}</td><td>{_cell(paper['doi'])}</td>"
        f"<td>{_cell(paper['domain'])}</td><td class=\"status\">{_cell(paper['review_stage'])}</td>"
        f"<td class=\"status\">{_cell(paper['scientific_extraction_status'])}</td>"
        f"<td>{paper['claim_count']}</td></tr>"
        for paper in papers
    )
    gap_rows = "".join(
        f"<tr><td>{_cell(gap['candidate_topic'])}</td><td>{_cell(gap['testable_question'])}</td>"
        f"<td>{_cell(gap['basis_paper_ids'])}</td><td class=\"status\">{_cell(gap['status'])}</td>"
        f"<td>{_cell(gap['qualification'])}</td></tr>"
        for gap in gaps
    )
    last = summary.get("last_import") or {}
    body = f"""<h1>Staging corpus</h1>
<div class="notice">{escape(STAGING_NOTICE)}</div>
<p>{summary['papers']} papers · {summary['claims']} candidate claims · {summary['field_definitions']} field definitions ·
{summary['research_gap_candidates']} research-gap candidates. Claim statuses: <span class="status">{_cell(summary['claim_statuses'])}</span>.
Last import: <code>{_cell(last.get('source_name'))}</code> (SHA-256 <code>{_cell(last.get('workbook_sha256'))}</code>).</p>
<form method="get"><input name="q" placeholder="title or DOI"> <button>Filter</button></form>
<p class="muted">Showing {len(papers)} of {total}.</p>
<table><thead><tr><th>ID</th><th>Title</th><th>Year</th><th>DOI</th><th>Domain</th><th>Review stage</th><th>Extraction</th><th>Claims</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>Research-gap candidates (team hypotheses)</h2>
<table><thead><tr><th>Topic</th><th>Testable question</th><th>Basis papers</th><th>Status</th><th>Qualification</th></tr></thead>
<tbody>{gap_rows}</tbody></table>"""
    return _page("Staging corpus", body)


def render_corpus_paper(paper: dict[str, Any]) -> str:
    def claim_block(claim: dict[str, Any]) -> str:
        evidence = claim["evidence"]
        return (
            f"<div><code>{escape(claim['claim_id'])}</code> <span class=\"status\">{escape(claim['scientific_status'])}"
            f" · {_cell(claim['independent_audit'])}</span><br>{_cell(claim['value'])}<br>"
            f"<span class=\"muted\">subject {_cell(claim['subject_scope'])} · {_cell(claim['claim_type'])} · "
            f"experiment {_cell(claim['experiment_id'])} · {_cell(evidence['source_edition'])} · "
            f"section {_cell(evidence['section'])} · locator {_cell(evidence['locator'])} · "
            f"PDF page {_cell(evidence['pdf_page'])} · quotation {_cell(evidence['verbatim_evidence'])} · "
            f"<a href=\"{escape(evidence['source_url'] or '#')}\">source</a></span>"
            + (f"<br><span class=\"muted\">note: {_cell(claim['notes'])}</span>" if claim["notes"] else "")
            + "</div>"
        )

    def marker_block(marker: dict[str, Any]) -> str:
        return (
            f"<div><code>{escape(marker['marker_id'])}</code> <span class=\"status\">marker "
            f"{escape(marker['extraction_status'])} · {escape(marker['scientific_status'])}</span><br>"
            f"<span class=\"muted\">searched: {_cell(marker['search_scope'])} · {_cell(marker['source_edition'])} · "
            f"<a href=\"{escape(marker['source_url'] or '#')}\">source</a>"
            + (f" · note: {_cell(marker['notes'])}" if marker["notes"] else "")
            + "</span></div>"
        )

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in paper["fields"]:
        groups.setdefault(item["group"], []).append(item)
    sections = []
    for group, items in groups.items():
        populated = sum(1 for item in items if item["claims"])
        rows = "".join(
            f"<tr><td><code>{escape(item['field_path'])}</code></td><td class=\"status\">{escape(item['status'])}</td>"
            f"<td>{''.join(claim_block(claim) for claim in item['claims'])}"
            f"{''.join(marker_block(marker) for marker in item['markers'])}"
            f"{'' if item['claims'] or item['markers'] else '<span class=\"muted\">not extracted</span>'}</td></tr>"
            for item in items
        )
        sections.append(
            f"<details{' open' if populated else ''}><summary><strong>{escape(group)}</strong> — "
            f"{populated} of {len(items)} fields with candidate claims</summary>"
            f"<table><thead><tr><th>Field</th><th>Status</th><th>Candidate claims</th></tr></thead><tbody>{rows}</tbody></table></details>"
        )
    if paper["uncontracted_claims"] or paper["uncontracted_markers"]:
        sections.append(
            "<details open><summary><strong>Outside the field contract</strong> — "
            f"{len(paper['uncontracted_claims'])} candidate claim(s) whose field path is not one of the "
            "contract's fields; kept verbatim, mapped to no field</summary><table><thead><tr><th>Field path</th>"
            "<th>Candidate claim</th></tr></thead><tbody>"
            + "".join(
                f"<tr><td><code>{escape(claim['field_path'])}</code></td><td>{claim_block(claim)}</td></tr>"
                for claim in paper["uncontracted_claims"]
            )
            + "".join(
                f"<tr><td><code>{escape(marker['field_path'])}</code></td><td>{marker_block(marker)}</td></tr>"
                for marker in paper["uncontracted_markers"]
            )
            + "</tbody></table></details>"
        )
    coverage = "".join(
        f"<code>{escape(item['source_name'])}</code>: {_cell(item.get('coverage_level'))} · "
        f"{_cell(item.get('audit_state'))} · {_cell(item.get('claim_count'))} claims<br>"
        for item in paper["coverage"]
    ) or '<span class="muted">none</span>'
    audit = paper["scientific_audit_status"]
    linked = paper["linked_paper_record_id"]
    body = f"""<p><a href="/corpus">← Staging corpus</a></p>
<h1>{_cell(paper['title'])}</h1>
<div class="notice">{escape(STAGING_NOTICE)}</div>
<table>
<tr><th>Staging ID</th><td><code>{escape(paper['paper_id'])}</code></td></tr>
<tr><th>Year · DOI</th><td>{_cell(paper['year'])} · {_cell(paper['doi'])}</td></tr>
<tr><th>Source</th><td><a href="{escape(paper['source_url'] or '#')}">{_cell(paper['source_url'])}</a> ({_cell(paper['source_edition'])})</td></tr>
<tr><th>Domain · kind · tags</th><td>{_cell(paper['domain'])} · {_cell(paper['record_kind'])} · {_cell(paper['tags'])}</td></tr>
<tr><th>Review stage</th><td class="status">{_cell(paper['review_stage'])}</td></tr>
<tr><th>Extraction</th><td class="status">{_cell(paper['scientific_extraction_status'])} / {_cell(paper['detail_extraction_status'])}</td></tr>
<tr><th>Audit status</th><td class="status">PAPER_INDEX {_cell(audit['paper_index'])} · PAPER_RECORDS {_cell(audit['paper_records'])}</td></tr>
<tr><th>Supplement coverage</th><td class="status">{coverage}</td></tr>
<tr><th>Experiments</th><td>{_cell(paper['experiments'])}</td></tr>
<tr><th>Fields</th><td>{paper['populated_field_count']} with candidate claims · {paper['not_extracted_field_count']} NOT_EXTRACTED</td></tr>
<tr><th>Canonical PaperRecord</th><td>{f'<a href="/papers/{escape(linked)}">{escape(linked)}</a>' if linked else '<span class="muted">none linked</span>'}</td></tr>
</table>
{''.join(sections)}"""
    return _page(paper["title"] or paper["paper_id"], body)
