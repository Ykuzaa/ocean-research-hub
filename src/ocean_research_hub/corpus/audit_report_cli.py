"""Replay an independently authored claim audit report into the append-only ledger.

The report is checked against the imported row and the pinned local source
before any audit event is appended. Rerunning the same report is idempotent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from .repository import CorpusRepository


def _event(report: dict, item: dict, source: dict) -> dict:
    original_provenance = item["provenance_type"]
    provenance = original_provenance if original_provenance in {
        "AUTHOR_REPORTED_FACT", "AUTHOR_REPORTED_LIMITATION", "AI_INTERPRETATION", "TEAM_NOTE"
    } else "TEAM_NOTE"
    return {
        "event_id": str(uuid5(NAMESPACE_URL, ":".join((
            report["paper"]["paper_id"], item["claim_id"], item["final_status"],
            report["auditor_id"], report["audited_at"], source["sha256"],
        )))),
        "target_kind": "CLAIM", "target_id": item["claim_id"],
        "decision": item["final_status"], "justification": item["audit_note"],
        "auditor_id": report["auditor_id"], "audited_at": report["audited_at"],
        "provenance_type": provenance, "source_kind": item["source_kind"],
        "source_edition": f"{item['source_edition']} sha256:{source['sha256']}",
        "page": item.get("page"), "section": item.get("section"),
        "locator": item.get("locator"),
        "evidence": f"Auditor paraphrase: {item['evidence_summary']}",
        "reviewed": {
            "value": item["extracted_value"], "unit": item.get("unit"),
            "experiment_id": item.get("experiment_id"), "field_path": item["field_path"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--database", type=Path, default=Path(os.getenv(
        "OCEAN_HUB_DB_PATH", ".data/ocean-research-hub.db"
    )))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if report.get("report_kind") != "INDEPENDENT_SCIENTIFIC_AUDIT":
            raise ValueError("report is not an independent scientific audit")
        source = report["sources"]["primary_paper"]
        source_path = Path(source["path"])
        if not source_path.is_file() or hashlib.sha256(source_path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("primary source file is missing or its SHA-256 differs")
        repository = CorpusRepository(args.database)
        paper = repository.get_paper(report["paper"]["paper_id"])
        if paper["doi"].casefold() != report["paper"]["doi"].casefold():
            raise ValueError("report DOI differs from the imported paper")
        events = []
        for item in report["claims"]:
            claim = repository.get_claim(item["claim_id"])
            if claim["paper_id"] != paper["paper_id"]:
                raise ValueError(f"{item['claim_id']}: claim belongs to another paper")
            reviewed = _event(report, item, source)
            for key, stored_key in (
                ("value", "value"), ("unit", "unit"),
                ("experiment_id", "experiment_id"), ("field_path", "field_path"),
            ):
                if reviewed["reviewed"][key] != claim[stored_key]:
                    raise ValueError(f"{item['claim_id']}: reviewed {key} differs from imported row")
            if item["final_status"] in {"VERIFIED", "PARTIALLY_VERIFIED"} and (
                item["provenance_type"] != claim["claim_type"]
                or "SOURCE_REVIEW" in str(claim["experiment_id"] or "")
            ):
                raise ValueError(f"{item['claim_id']}: imported provenance or experiment cannot be verified")
            events.append(reviewed)
        if len({event["target_id"] for event in events}) != len(events):
            raise ValueError("report repeats a claim ID")
        existing = {event["event_id"] for event in repository.list_audits()}
        if args.dry_run:
            print(json.dumps({"status": "VALID_NOT_RECORDED", "events": len(events),
                              "new_events": sum(event["event_id"] not in existing for event in events)}))
            return 0
        added = 0
        for event in events:
            if event["event_id"] in existing:
                continue
            repository.record_audit(event)
            added += 1
        print(json.dumps({"status": "RECORDED", "events": len(events), "added": added}))
        return 0
    except (OSError, KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
