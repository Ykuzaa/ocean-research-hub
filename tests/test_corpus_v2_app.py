"""The corpus v2 app surface: claim enumeration, the audit ledger, and the API."""

from __future__ import annotations

import json
import pathlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ocean_research_hub.corpus_v2 import audit, store
from ocean_research_hub.corpus_v2.gate import walk
from ocean_research_hub.corpus_v2.web import register_corpus_v2_routes

GOLD = pathlib.Path("evaluation/gold_v2")
RECORDS = sorted(GOLD.glob("*.json"))


@pytest.fixture
def client(tmp_path: pathlib.Path) -> TestClient:
    app = FastAPI()
    register_corpus_v2_routes(app, GOLD, tmp_path / "verdicts.json", pathlib.Path("/nonexistent.json"))
    return TestClient(app)


@pytest.mark.parametrize("path", RECORDS, ids=[p.stem for p in RECORDS])
def test_claims_cover_everything_the_gate_checks_and_more(path: pathlib.Path) -> None:
    """The audit queue may never be narrower than the deterministic gate."""
    record = json.loads(path.read_text())
    claims = list(store.claims(path.stem, record))
    assert {path_ for path_, _ in walk(record)} <= {claim["path"] for claim in claims}
    assert len(claims) == len(list(walk(record))) + len(list(store.walk_unquoted(record)))


@pytest.mark.parametrize("path", RECORDS, ids=[p.stem for p in RECORDS])
def test_every_claim_is_reviewable(path: pathlib.Path) -> None:
    record = json.loads(path.read_text())
    for claim in store.claims(path.stem, record):
        assert claim["page_pdf"], claim["claim_id"]
        if not claim["quote"]:
            # Unquotable by construction: the value was read off the rendered page, so
            # it must say so and carry the reason, since the gate cannot check it.
            assert claim["evidence_status"] == "VALUE_READ_NO_SAFE_QUOTE", claim["claim_id"]
            assert claim["value"] is not None, claim["claim_id"]
        assert claim["kind"] != "OTHER", claim["claim_id"]
        assert claim["paper_title"]


def test_claim_ids_are_unique_across_the_corpus() -> None:
    ids = [claim["claim_id"] for claim in store.all_claims(GOLD)]
    assert len(ids) == len(set(ids))


def test_search_filters_combine() -> None:
    records = store.load_records(GOLD)
    everything = store.search(records, None, None, None)
    bathymetry = store.search(records, None, "BATHYMETRY_ESTIMATION", None)
    assert 0 < len(bathymetry) < len(everything)
    assert all("BATHYMETRY_ESTIMATION" in paper["tasks"] for paper in bathymetry)


def _claim() -> dict:
    return next(claim for claim in store.all_claims(GOLD) if claim["kind"] == "RESULT")


def test_a_verdict_is_signed_and_reasoned(tmp_path: pathlib.Path) -> None:
    ledger = tmp_path / "verdicts.json"
    claim = _claim()
    with pytest.raises(audit.AuditError, match="décision inconnue"):
        audit.record(claim, "LOOKS_FINE", auditor="mehdi", ledger=ledger)
    with pytest.raises(audit.AuditError):
        audit.record(claim, "NEEDS_FIX", auditor="mehdi", note="  ", ledger=ledger)
    with pytest.raises(audit.AuditError):
        audit.record(claim, "ACCEPTED", auditor="", ledger=ledger)
    assert not ledger.exists()

    audit.record(claim, "ACCEPTED", auditor="mehdi", ledger=ledger)
    stored = audit.load(ledger)[claim["claim_id"]]
    assert stored["decision"] == "ACCEPTED"
    assert stored["auditor"] == "mehdi"
    assert stored["fingerprint"] == claim["fingerprint"]


def test_a_changed_extraction_invalidates_its_verdict(tmp_path: pathlib.Path) -> None:
    ledger = tmp_path / "verdicts.json"
    claim = _claim()
    audit.record(claim, "ACCEPTED", auditor="mehdi", ledger=ledger)
    verdicts = audit.load(ledger)

    assert audit.attach([claim], verdicts)[0]["audit_state"] == "ACCEPTED"
    reextracted = {**claim, "value": 0.1234, "fingerprint": store.fingerprint(0.1234, claim["quote"])}
    attached = audit.attach([reextracted], verdicts)[0]
    assert attached["audit_state"] == "STALE"
    assert attached["audit"]["stale"] is True


def test_a_second_verdict_keeps_the_first_on_record(tmp_path: pathlib.Path) -> None:
    ledger = tmp_path / "verdicts.json"
    claim = _claim()
    audit.record(claim, "ACCEPTED", auditor="mehdi", ledger=ledger)
    audit.record(claim, "REJECTED", auditor="mehdi", note="la page citée parle d'un autre bassin", ledger=ledger)
    stored = audit.load(ledger)[claim["claim_id"]]
    assert stored["decision"] == "REJECTED"
    assert stored["supersedes"]["decision"] == "ACCEPTED"


def test_summary_reports_sourced_and_audited_separately(client: TestClient) -> None:
    summary = client.get("/api/v2/summary").json()
    assert summary["quotes"] > 1_000
    assert summary["audit"]["claims"] == len(store.all_claims(GOLD))
    assert summary["audit"]["accepted"] == 0  # a fresh ledger audits nothing
    assert summary["shared_cells"] == 0  # the measured ceiling, not an empty corpus
    assert summary["access"] is None  # no manifest in this fixture


def test_papers_endpoint_filters_and_lists(client: TestClient) -> None:
    everything = client.get("/api/v2/papers").json()
    assert everything["total"] == len(RECORDS)
    assert "FORECASTING" in everything["tasks"]

    filtered = client.get("/api/v2/papers", params={"task": "FORECASTING"}).json()
    assert 0 < filtered["total"] < everything["total"]

    searched = client.get("/api/v2/papers", params={"q": "bathymetry"}).json()
    assert 0 < searched["total"] < everything["total"]


@pytest.mark.parametrize("slug", ["dincae-2-2022", "seabed-net", "hidra-sea-level"])
def test_paper_detail_shows_no_value_without_its_evidence(client: TestClient, slug: str) -> None:
    """Every displayed value carries a quote, or says why no quote can carry it."""
    paper = client.get(f"/api/v2/papers/{slug}").json()
    assert paper["claims"]
    shown = [value for experiment in paper["experiments"]
             for value in experiment["training"] + experiment["results"]]
    assert shown
    for value in shown:
        if not value["quote"]:
            assert value["evidence_status"] == "VALUE_READ_NO_SAFE_QUOTE", value
            assert value["page"]
    assert client.get("/api/v2/papers/does-not-exist").status_code == 404


def test_the_queue_shrinks_only_when_a_human_decides(client: TestClient) -> None:
    before = client.get("/api/v2/review/queue", params={"limit": 1}).json()
    assert before["pending"] == len(store.all_claims(GOLD))
    # The values the gate cannot check are queued before the ones it can.
    assert before["claims"][0]["quote"] is None

    claim_id = before["claims"][0]["claim_id"]
    posted = client.post("/api/v2/review/verdicts", json={
        "claim_id": claim_id, "decision": "ACCEPTED", "auditor": "mehdi",
    })
    assert posted.status_code == 200
    assert posted.json()["progress"]["accepted"] == 1

    after = client.get("/api/v2/review/queue", params={"limit": 1}).json()
    assert after["pending"] == before["pending"] - 1
    assert after["claims"][0]["claim_id"] != claim_id


def test_the_api_refuses_an_unusable_verdict(client: TestClient) -> None:
    claim_id = store.all_claims(GOLD)[0]["claim_id"]
    unknown = client.post("/api/v2/review/verdicts", json={
        "claim_id": "nope::results[0]", "decision": "ACCEPTED", "auditor": "mehdi",
    })
    assert unknown.status_code == 404

    unreasoned = client.post("/api/v2/review/verdicts", json={
        "claim_id": claim_id, "decision": "REJECTED", "auditor": "mehdi",
    })
    assert unreasoned.status_code == 422
    assert unreasoned.json()["error"]["code"] == "REASON_REQUIRED"


def test_queue_can_be_narrowed_to_one_paper(client: TestClient) -> None:
    queue = client.get("/api/v2/review/queue", params={"slug": "dincae-2-2022", "limit": 50}).json()
    assert queue["claims"]
    assert {claim["slug"] for claim in queue["claims"]} == {"dincae-2-2022"}
