"""The independent machine re-check: coverage, reconciliation, and its separation
from the human audit.

The re-check answers what the gate cannot — whether a value was read in the right
context — and it is a machine channel. These tests exist to keep it honest: it must
cover every claim, every flag must be ruled on, and no verdict here may ever be
counted as a human audit.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from ocean_research_hub.corpus_v2 import audit, recheck, store

GOLD = pathlib.Path("evaluation/gold_v2")
LEDGER = pathlib.Path("evaluation/audit_v2/recheck.json")


@pytest.fixture(scope="module")
def entries() -> dict:
    return recheck.load_ledger(LEDGER)


def test_every_claim_in_the_corpus_has_been_re_checked(entries: dict) -> None:
    state = recheck.progress(store.all_claims(GOLD), entries, recheck.load_triage())
    assert state["not_rechecked"] == 0, state["states"]
    assert state["stale"] == 0, "a verdict given on a value that has since changed is void"


def test_every_flag_has_been_ruled_on(entries: dict) -> None:
    """A flag nobody decided is an open defect, not a finished re-check."""
    state = recheck.progress(store.all_claims(GOLD), entries, recheck.load_triage())
    assert state["outstanding"] == 0, state["states"]
    assert state["flagged"] == state["corrected"] + state["flag_dismissed"]


def test_each_decision_carries_its_reason() -> None:
    for claim_id, decision in recheck.load_triage().items():
        assert decision["decision"] in ("APPLIED", "KEPT"), claim_id
        assert len(decision.get("reason", "")) > 40, f"{claim_id} decided without a reason"


def test_the_machine_channel_is_not_the_human_audit(entries: dict) -> None:
    claims = store.all_claims(GOLD)
    assert recheck.progress(claims, entries, recheck.load_triage())["confirmed"] > 1_000
    # Nothing the machines confirmed may count as audited.
    assert audit.progress(claims, audit.load(pathlib.Path("evaluation/audit_v2/verdicts.json")))["accepted"] == 0


def _report(tmp_path: pathlib.Path, slug: str, claims: dict) -> pathlib.Path:
    path = tmp_path / f"{slug}.json"
    path.write_text(json.dumps({"slug": slug, "checked_at": "2026-10-15", "model": "test",
                                "claims": claims}))
    return path


def test_a_verdict_follows_the_claim_it_was_given_on(tmp_path: pathlib.Path) -> None:
    """A correction that renumbers a list must not hand a verdict to a stranger."""
    slug, record = next((s, r) for s, r in store.load_records(GOLD) if len(r.get("limitations", [])) > 2)
    claims = list(store.claims(slug, record))
    moved = next(c for c in claims if c["path"] == "limitations[1]")

    snapshots = tmp_path / "claims"
    snapshots.mkdir()
    (snapshots / f"{slug}.json").write_text(json.dumps({"slug": slug, "claims": [
        {k: c[k] for k in ("path", "value", "quote")} for c in claims]}))

    shifted = {**record, "limitations": record["limitations"][1:]}  # the first one is removed
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / f"{slug}.json").write_text(json.dumps(shifted))

    original_snapshots = recheck.SNAPSHOTS
    recheck.SNAPSHOTS = snapshots
    try:
        ledger = tmp_path / "recheck.json"
        report = _report(tmp_path, slug, {"limitations[1]": {"verdict": "SUSPECT", "reason": "x"},
                                          "limitations[0]": {"verdict": "CONFIRMED"}})
        stored, problems = recheck.ingest([report], gold, ledger)
    finally:
        recheck.SNAPSHOTS = original_snapshots

    # The claim that was checked as limitations[1] now sits at limitations[0].
    assert stored[f"{slug}::limitations[0]"]["verdict"] == "SUSPECT"
    assert stored[f"{slug}::limitations[0]"]["fingerprint"] == moved["fingerprint"]
    # The one that was removed takes its verdict with it instead of landing elsewhere.
    assert any("verdict dropped" in problem for problem in problems)


def test_an_incomplete_report_is_reported_as_incomplete(tmp_path: pathlib.Path) -> None:
    slug = "dincae-2-2022"
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / f"{slug}.json").write_text((GOLD / f"{slug}.json").read_text())
    report = _report(tmp_path, slug, {"results[0]": {"verdict": "CONFIRMED"}})
    _, problems = recheck.ingest([report], gold, tmp_path / "recheck.json")
    assert any("not re-checked" in problem for problem in problems)
