"""Ingest the independent machine re-check reports into one ledger.

The re-check answers what the gate cannot: whether a value was read in the right
context. It is a *machine* channel, kept in its own file so it can never be mistaken
for the human audit in `audit.py`. See `evaluation/gold_v2/RECHECK.md`.

    uv run python -m ocean_research_hub.corpus_v2.recheck evaluation/work/recheck/*.json
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

from . import audit, store

LEDGER = pathlib.Path("evaluation/audit_v2/recheck.json")
#: What each checker was handed, path by path, as it stood when it was handed over.
SNAPSHOTS = pathlib.Path("evaluation/work/recheck/claims")
#: What the orchestrator decided about each flagged claim, and why.
TRIAGE = pathlib.Path("evaluation/audit_v2/triage.json")
VERDICTS = ("CONFIRMED", "SUSPECT", "UNREADABLE")


def _content(claim: dict) -> tuple:
    """What a verdict was really given on, independent of where the claim sat."""
    return (json.dumps(claim.get("value"), sort_keys=True, ensure_ascii=False), claim.get("quote"))


def ingest(report_paths: list[pathlib.Path], gold_dir: pathlib.Path = store.GOLD_DIR,
           ledger: pathlib.Path = LEDGER) -> tuple[dict, list[str]]:
    """Merge reports into the ledger; returns the ledger and the complaints about it."""
    known = {claim["claim_id"]: claim for claim in store.all_claims(gold_dir)}
    entries = json.loads(ledger.read_text()) if ledger.exists() else {}
    problems: list[str] = []

    for path in report_paths:
        report = json.loads(path.read_text())
        slug = report.get("slug") or path.stem
        expected = {claim["path"] for claim in known.values() if claim["slug"] == slug}
        reported = set(report.get("claims", {}))
        if missing := expected - reported:
            problems.append(f"{slug}: {len(missing)} claim(s) not re-checked, e.g. {sorted(missing)[:3]}")
        if unknown := reported - expected:
            problems.append(f"{slug}: {len(unknown)} unknown path(s), e.g. {sorted(unknown)[:3]}")

        # A correction applied after the check can renumber a list, so a path alone no
        # longer identifies what was checked. Where the snapshot handed to the checker
        # is still on disk, the verdict is re-attached by content; a claim that moved is
        # followed, and one that was removed drops out instead of landing on a stranger.
        snapshot = {}
        snapshot_path = SNAPSHOTS / f"{slug}.json"
        if snapshot_path.exists():
            snapshot = {c["path"]: c for c in json.loads(snapshot_path.read_text())["claims"]}
        by_content: dict[tuple, list[str]] = {}
        for claim_id, claim in known.items():
            if claim["slug"] == slug:
                by_content.setdefault(_content(claim), []).append(claim_id)

        for claim_path, outcome in report.get("claims", {}).items():
            claim_id = f"{slug}::{claim_path}"
            claim = known.get(claim_id)
            checked = snapshot.get(claim_path)
            if checked is not None and (claim is None or _content(claim) != _content(checked)):
                candidates = by_content.get(_content(checked), [])
                if len(candidates) == 1:
                    claim_id = candidates[0]
                    claim = known[claim_id]
                else:
                    problems.append(
                        f"{slug}::{claim_path}: checked claim is gone or ambiguous "
                        f"({len(candidates)} candidates), verdict dropped"
                    )
                    claim = None
            if claim is None:
                continue
            verdict = outcome.get("verdict")
            if verdict not in VERDICTS:
                problems.append(f"{claim_id}: unknown verdict {verdict!r}")
                continue
            entries[claim_id] = {
                "claim_id": claim_id,
                "slug": slug,
                "path": claim_path,
                "verdict": verdict,
                "reason": outcome.get("reason"),
                "correct_reading": outcome.get("correct_reading"),
                "checked_at": report.get("checked_at"),
                "checker": report.get("model") or "unknown",
                # Pinned to what was re-read, so a later extraction change voids it too.
                "fingerprint": claim["fingerprint"],
            }

    # A correction can remove a claim or renumber the ones after it, so an entry whose
    # claim no longer exists is dropped rather than left pointing at a stranger. The
    # renumbered ones keep a fingerprint that no longer matches and read back as STALE,
    # which is what they are: re-checked before the fix, not after it.
    for orphan in [claim_id for claim_id in entries if claim_id not in known]:
        entries.pop(orphan)
        problems.append(f"{orphan}: claim no longer exists, verdict dropped")

    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps(entries, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return entries, problems


def load_ledger(path: pathlib.Path = LEDGER) -> dict[str, dict]:
    return json.loads(path.read_text()) if path.exists() else {}


def load_triage(path: pathlib.Path = TRIAGE) -> dict[str, dict]:
    """The decisions taken on flagged claims: `APPLIED` (record corrected) or `KEPT`."""
    if not path.exists():
        return {}
    return json.loads(path.read_text()).get("decisions", {})


def attach(claims: list[dict], entries: dict[str, dict],
           triage: dict[str, dict] | None = None) -> list[dict]:
    """Add each claim's re-check state, `STALE` once the extraction moved under it."""
    out = []
    for claim in claims:
        entry = entries.get(claim["claim_id"])
        stale = bool(entry) and entry.get("fingerprint") != claim["fingerprint"]
        decision = (triage or {}).get(claim["claim_id"])
        state = "NOT_RECHECKED" if not entry else ("STALE" if stale else entry["verdict"])
        # A flag that has been ruled on is no longer outstanding, whether the record was
        # corrected or the flag was argued down; both decisions are on the record.
        if state == "SUSPECT" and decision:
            state = f"SUSPECT_{decision['decision']}"
        out.append({
            **claim,
            "recheck": None if not entry else {**entry, "stale": stale, "triage": decision},
            "recheck_state": state,
        })
    return out


def progress(claims: list[dict], entries: dict[str, dict],
             triage: dict[str, dict] | None = None) -> dict:
    counts = collections.Counter(claim["recheck_state"] for claim in attach(claims, entries, triage))
    return {
        "claims": len(claims),
        "states": dict(counts),
        "rechecked": len(claims) - counts["NOT_RECHECKED"] - counts["STALE"],
        "confirmed": counts["CONFIRMED"],
        "flagged": counts["SUSPECT"] + counts["SUSPECT_APPLIED"] + counts["SUSPECT_KEPT"],
        "corrected": counts["SUSPECT_APPLIED"],
        "flag_dismissed": counts["SUSPECT_KEPT"],
        "outstanding": counts["SUSPECT"],
        "unreadable": counts["UNREADABLE"],
        "stale": counts["STALE"],
        "not_rechecked": counts["NOT_RECHECKED"],
        "checkers": sorted({entry["checker"] for entry in entries.values()}),
    }


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m ocean_research_hub.corpus_v2.recheck <report.json> [...]")
        return 2
    entries, problems = ingest([pathlib.Path(arg) for arg in argv])
    for problem in problems:
        print(f"INCOMPLETE {problem}")
    claims = store.all_claims()
    state = progress(claims, entries, load_triage())
    print(f"{state['rechecked']}/{state['claims']} re-checked: "
          f"{state['confirmed']} confirmed, {state['flagged']} flagged "
          f"({state['corrected']} corrected, {state['flag_dismissed']} dismissed, "
          f"{state['outstanding']} outstanding), {state['stale']} stale")
    human = audit.progress(claims, audit.load())
    print(f"human audit: {human['audited']}/{human['claims']} — the machine channel does not count")
    for entry in sorted(entries.values(), key=lambda e: e["claim_id"]):
        if entry["verdict"] == "SUSPECT" and entry["claim_id"] not in load_triage():
            print(f"SUSPECT {entry['claim_id']}: {entry['reason']}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
