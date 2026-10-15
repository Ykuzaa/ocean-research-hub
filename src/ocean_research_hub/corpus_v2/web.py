"""API routes for the corpus v2: the browser, the record view, and the audit queue.

Everything served here is *sourced*: each value carries the sentence it was read from
and the page that sentence is on, re-located by `corpus_v2.gate` on every commit.
Nothing served here is *audited* unless a verdict in `corpus_v2.audit` says a person
checked it, which is why the audit state travels with every claim.
"""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import audit, entities, recheck, store
from .build_poc import build

SOURCING_NOTICE = (
    "Chaque valeur est sourcée: la citation existe mot pour mot sur la page citée, "
    "vérifiée par corpus_v2.gate. Une seconde lecture machine indépendante a contrôlé "
    "que la valeur est la bonne lecture du bon contexte. « Sourcé » et « contre-vérifié » "
    "ne veulent pas dire « audité »: seul un verdict humain dans la file de revue rend "
    "une information auditée."
)


class VerdictRequest(BaseModel):
    claim_id: str = Field(min_length=1, max_length=400)
    decision: str = Field(min_length=1, max_length=40)
    auditor: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)
    corrected_value: Any = None


def register_corpus_v2_routes(
    app: FastAPI,
    gold_dir: pathlib.Path = store.GOLD_DIR,
    ledger: pathlib.Path = audit.LEDGER,
    manifest: pathlib.Path = pathlib.Path(".data/oa-manifest-full.json"),
) -> None:
    def error(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})

    def claims_by_id() -> dict[str, dict]:
        return {claim["claim_id"]: claim for claim in store.all_claims(gold_dir)}

    @app.get("/api/v2/summary")
    async def v2_summary() -> dict[str, Any]:
        payload = build(gold_dir, manifest)
        return {
            "notice": SOURCING_NOTICE,
            **payload["agg"],
            "audit": audit.progress(store.all_claims(gold_dir), audit.load(ledger)),
            "recheck": recheck.progress(store.all_claims(gold_dir), recheck.load_ledger(),
                                        recheck.load_triage()),
        }

    @app.get("/api/v2/papers")
    async def v2_papers(
        q: str | None = Query(default=None, max_length=200),
        task: str | None = Query(default=None, max_length=60),
        family: str | None = Query(default=None, max_length=60),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        records = store.load_records(gold_dir)
        summaries = store.search(records, q, task, family)
        progress = audit.progress(store.all_claims(gold_dir), audit.load(ledger))["per_paper"]
        papers = [{**summary, "audit": progress.get(summary["slug"])}
                  for summary in summaries[offset:offset + limit]]
        return {
            "notice": SOURCING_NOTICE,
            "total": len(summaries),
            "limit": limit,
            "offset": offset,
            "tasks": sorted({task for summary in summaries for task in summary["tasks"]}),
            "families": sorted({f for summary in summaries for f in summary["families"]}),
            "papers": papers,
        }

    @app.get("/api/v2/papers/{slug}", response_model=None)
    async def v2_paper(slug: str) -> dict[str, Any] | JSONResponse:
        record = store.load_record(slug, gold_dir)
        if record is None:
            return error(404, "NOT_FOUND", f"no corpus v2 record named {slug!r}")
        verdicts = audit.load(ledger)
        claims = recheck.attach(
            audit.attach(list(store.claims(slug, record)), verdicts),
            recheck.load_ledger(), recheck.load_triage(),
        )
        return {
            "notice": SOURCING_NOTICE,
            **store.paper_detail(slug, record),
            "claims": claims,
            "audit": audit.progress(list(store.claims(slug, record)), verdicts)["per_paper"].get(slug),
        }

    @app.get("/api/v2/review/queue")
    async def v2_queue(
        slug: str | None = Query(default=None, max_length=120),
        kind: str | None = Query(default=None, max_length=40),
        limit: int = Query(default=25, ge=1, le=200),
    ) -> dict[str, Any]:
        verdicts = audit.load(ledger)
        claims = recheck.attach(audit.attach(store.all_claims(gold_dir), verdicts),
                                recheck.load_ledger(), recheck.load_triage())
        pending = [claim for claim in claims if claim["audit_state"] in ("UNAUDITED", "STALE")]
        if slug:
            pending = [claim for claim in pending if claim["slug"] == slug]
        if kind:
            pending = [claim for claim in pending if claim["kind"] == kind]
        # Values read off the page without a quote come first — the gate cannot check
        # them at all. Then measurements: a wrong result misleads more than a label.
        pending.sort(key=lambda claim: (bool(claim["quote"]),
                                        store.KIND_PRIORITY.get(claim["kind"], 9),
                                        claim["slug"], claim["path"]))
        return {
            "notice": SOURCING_NOTICE,
            "pending": len(pending),
            "progress": audit.progress(store.all_claims(gold_dir), verdicts),
            "claims": pending[:limit],
        }

    @app.post("/api/v2/review/verdicts", response_model=None)
    async def v2_verdict(request: VerdictRequest) -> dict[str, Any] | JSONResponse:
        claim = claims_by_id().get(request.claim_id)
        if claim is None:
            return error(404, "NOT_FOUND", f"no claim named {request.claim_id!r}")
        try:
            verdict = audit.record(
                claim,
                request.decision,
                auditor=request.auditor,
                note=request.note,
                corrected_value=request.corrected_value,
                ledger=ledger,
            )
        except audit.AuditError as failure:
            return error(422, failure.code, str(failure))
        return {"verdict": verdict,
                "progress": audit.progress(store.all_claims(gold_dir), audit.load(ledger))}

    @app.get("/api/v2/analysis")
    async def v2_analysis() -> dict[str, Any]:
        """Entity-first views and the field's empty cells (issues #22 and #23)."""
        return {"notice": SOURCING_NOTICE, **entities.overview(gold_dir)}

    @app.get("/api/v2/entities/{kind}/{name:path}", response_model=None)
    async def v2_entity(kind: str, name: str) -> dict[str, Any] | JSONResponse:
        detail = entities.detail(kind, name, gold_dir)
        if detail is None:
            return error(404, "NOT_FOUND", f"no {kind} named {name!r} in the corpus")
        return {"notice": SOURCING_NOTICE, **detail}

    @app.get("/api/v2/review/progress")
    async def v2_progress() -> dict[str, Any]:
        return {"notice": SOURCING_NOTICE,
                **audit.progress(store.all_claims(gold_dir), audit.load(ledger))}
