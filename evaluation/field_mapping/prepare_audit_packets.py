"""Build immutable producer packets for the first B16 field-mapping audit batch.

The database is opened read-only. This script records neither an audit decision
nor a validation status; it only binds stored source rules, pre-review proposals,
and every claim currently stored under each selected original path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


SOURCE_NAME = "Ocean_Research_Intelligence_ENRICHED_B16.xlsx"
PRODUCER_ID = "developer:/root/developer_audit"
PATHS = (
    "limitations.memory",
    "limitations.swot_noise",
    "reproducibility.code_archive",
    "reproducibility.framework",
)


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def claim_context(row: sqlite3.Row) -> dict[str, object]:
    source = json.loads(row["row_json"])
    return {
        "claim_id": row["claim_id"],
        "paper_id": row["paper_id"],
        "claim_fingerprint": row["fingerprint"],
        "value": source.get("value"),
        "unit": source.get("unit"),
        "experiment_id": row["experiment_id"],
        "claim_type": source.get("claim_type"),
        "subject_scope": source.get("subject_scope"),
        "source": {
            "doi": source.get("source_doi"),
            "edition": source.get("source_edition"),
            "url": source.get("evidence_source_url"),
            "pdf_page": source.get("pdf_page"),
            "section": source.get("source_section"),
            "locator": source.get("source_locator"),
            "verbatim_evidence": source.get("verbatim_evidence"),
            "evidence_review": source.get("evidence_review"),
        },
    }


def build(database: Path, prereview_path: Path) -> dict[str, object]:
    prereview_bytes = prereview_path.read_bytes()
    prereview = json.loads(prereview_bytes)
    rules = {rule["original_path"]: rule for rule in prereview["rules"]}
    missing = sorted(set(PATHS) - rules.keys())
    if missing:
        raise ValueError(f"pre-review lacks selected path(s): {missing}")

    uri = f"file:{database.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        versions = connection.execute(
            """SELECT version_id, source_name, workbook_sha256
               FROM staging_corpus_mapping_versions WHERE source_name = ?""",
            (SOURCE_NAME,),
        ).fetchall()
        if len(versions) != 1:
            raise ValueError(f"expected one B16 mapping version, found {len(versions)}")
        version = versions[0]
        packets = []
        for original_path in PATHS:
            mapping = connection.execute(
                """SELECT original_path, decision, canonical_path, basis,
                          provenance_type, source_candidate
                   FROM staging_corpus_field_mappings
                   WHERE version_id = ? AND original_path = ?""",
                (version["version_id"], original_path),
            ).fetchone()
            if mapping is None:
                raise ValueError(f"stored B16 mapping is missing {original_path}")
            source_mapping = {
                "original_path": mapping["original_path"],
                "decision": mapping["decision"],
                "canonical_path": mapping["canonical_path"],
                "basis": mapping["basis"],
                "provenance_type": mapping["provenance_type"],
                "source_candidate": json.loads(mapping["source_candidate"])
                if mapping["source_candidate"] else None,
            }
            proposal_rule = rules[original_path]
            claims = [
                claim_context(row)
                for row in connection.execute(
                    """SELECT claim_id, paper_id, experiment_id, fingerprint, row_json
                       FROM staging_corpus_claims
                       WHERE field_path = ? ORDER BY claim_id""",
                    (original_path,),
                )
            ]
            expected_ids = sorted(proposal_rule["claim_ids"])
            actual_ids = [claim["claim_id"] for claim in claims]
            if actual_ids != expected_ids:
                raise ValueError(
                    f"{original_path}: stored claims {actual_ids} differ from pre-review {expected_ids}"
                )
            packet = {
                "packet_kind": "FIELD_PATH_MAPPING_AUDIT_PACKET",
                "schema_version": 1,
                "version_id": version["version_id"],
                "producer_id": PRODUCER_ID,
                "source": {
                    "name": version["source_name"],
                    "sha256": version["workbook_sha256"],
                },
                "source_mapping": source_mapping,
                "producer_proposal": {
                    "decision": proposal_rule["proposed_decision"],
                    "canonical_path": proposal_rule.get("proposed_canonical_path"),
                    "reason": proposal_rule["reason"],
                },
                "proposal_source": {
                    "name": prereview_path.name,
                    "sha256": hashlib.sha256(prereview_bytes).hexdigest(),
                },
                "prereview_rule": proposal_rule,
                "claims": claims,
            }
            packets.append({"packet_sha256": sha256_json(packet), "packet": packet})
    finally:
        connection.close()

    return {
        "batch_kind": "FIELD_PATH_MAPPING_AUDIT_PACKET_BATCH",
        "schema_version": 1,
        "producer_id": PRODUCER_ID,
        "notice": "Producer packets only; no audit decision or validation is recorded.",
        "paths": list(PATHS),
        "packets": packets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("prereview", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = build(args.database, args.prereview)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "packets": len(result["packets"]),
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
