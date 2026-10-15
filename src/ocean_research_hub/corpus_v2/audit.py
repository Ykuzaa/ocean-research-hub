"""The human audit ledger: what a person checked, when, and what they decided.

Extraction can only make a claim *sourced* — the quote exists on the cited page and
the value follows from it. Only a human reading the paper can make it *audited*.
This module is the one place that distinction is recorded, and it is deliberately
separate from the records: an audit never edits an extraction.

A verdict is given on a (value, quote) pair. If either changes, the stored verdict
becomes `stale` and the claim returns to the queue — a re-extraction can never
inherit someone's approval of the previous reading.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import tempfile
from typing import Any

LEDGER = pathlib.Path("evaluation/audit_v2/verdicts.json")

#: What an auditor can conclude. `NEEDS_FIX` keeps the claim out of the verified
#: count without asserting the paper says something else; `REJECTED` says it does not.
DECISIONS = ("ACCEPTED", "NEEDS_FIX", "REJECTED")

#: A decision against the claim is only useful with a reason, so one is required.
REASON_REQUIRED = ("NEEDS_FIX", "REJECTED")


class AuditError(ValueError):
    """An invalid verdict; carries the HTTP-facing code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def load(ledger: pathlib.Path = LEDGER) -> dict[str, dict]:
    if not ledger.exists():
        return {}
    return json.loads(ledger.read_text())


def _save(verdicts: dict[str, dict], ledger: pathlib.Path) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(verdicts, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    # Written through a temporary file so an interrupted audit session cannot
    # truncate the ledger that already holds the earlier verdicts.
    handle = tempfile.NamedTemporaryFile("w", dir=ledger.parent, delete=False, encoding="utf-8")
    try:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(handle.name, ledger)
    except BaseException:
        pathlib.Path(handle.name).unlink(missing_ok=True)
        raise


def record(claim: dict, decision: str, *, auditor: str, note: str | None = None,
           corrected_value: Any = None, ledger: pathlib.Path = LEDGER) -> dict:
    """Store one verdict, replacing any earlier verdict on the same claim."""
    if decision not in DECISIONS:
        raise AuditError("INVALID_DECISION", f"décision inconnue; valeurs admises: {', '.join(DECISIONS)}")
    if decision in REASON_REQUIRED and not (note or "").strip():
        raise AuditError(
            "REASON_REQUIRED",
            "dis ce qui est faux: une correction ou un rejet sans motif n'est pas exploitable",
        )
    if not (auditor or "").strip():
        raise AuditError("AUDITOR_REQUIRED", "un verdict est signé: mets ton nom")

    verdict = {
        "claim_id": claim["claim_id"],
        "slug": claim["slug"],
        "path": claim["path"],
        "decision": decision,
        "note": (note or "").strip() or None,
        "corrected_value": corrected_value,
        "auditor": auditor.strip(),
        "decided_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "fingerprint": claim["fingerprint"],
        "audited_value": claim["value"],
        "audited_quote": claim["quote"],
        "page_pdf": claim["page_pdf"],
    }
    verdicts = load(ledger)
    previous = verdicts.get(claim["claim_id"])
    if previous:
        verdict["supersedes"] = {key: previous[key] for key in ("decision", "auditor", "decided_at")}
    verdicts[claim["claim_id"]] = verdict
    _save(verdicts, ledger)
    return verdict


def attach(claims: list[dict], verdicts: dict[str, dict]) -> list[dict]:
    """Add each claim's current audit state: its verdict, or None when unaudited."""
    decorated = []
    for claim in claims:
        verdict = verdicts.get(claim["claim_id"])
        stale = bool(verdict) and verdict.get("fingerprint") != claim["fingerprint"]
        decorated.append({
            **claim,
            "audit": None if not verdict else {**verdict, "stale": stale},
            "audit_state": "UNAUDITED" if not verdict else ("STALE" if stale else verdict["decision"]),
        })
    return decorated


def progress(claims: list[dict], verdicts: dict[str, dict]) -> dict:
    """How much of the corpus a human has actually checked."""
    decorated = attach(claims, verdicts)
    counts: dict[str, int] = {}
    for claim in decorated:
        counts[claim["audit_state"]] = counts.get(claim["audit_state"], 0) + 1
    per_paper: dict[str, dict[str, int]] = {}
    for claim in decorated:
        bucket = per_paper.setdefault(claim["slug"], {"claims": 0, "audited": 0, "accepted": 0})
        bucket["claims"] += 1
        if claim["audit_state"] not in ("UNAUDITED", "STALE"):
            bucket["audited"] += 1
        if claim["audit_state"] == "ACCEPTED":
            bucket["accepted"] += 1
    return {
        "claims": len(decorated),
        "states": counts,
        "audited": sum(count for state, count in counts.items() if state in DECISIONS),
        "accepted": counts.get("ACCEPTED", 0),
        "needs_fix": counts.get("NEEDS_FIX", 0),
        "rejected": counts.get("REJECTED", 0),
        "stale": counts.get("STALE", 0),
        "per_paper": per_paper,
        "auditors": sorted({v["auditor"] for v in verdicts.values()}),
    }
