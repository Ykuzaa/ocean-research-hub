"""Adversarial regressions for independent, hash-bound mapping audits."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocean_research_hub.api import create_app
from ocean_research_hub.corpus.mapping_audit_cli import main as mapping_audit_main
from ocean_research_hub.corpus.repository import CorpusRepository
from ocean_research_hub.corpus.workbook import read_workbook
from ocean_research_hub.ingestion.repository import SqlitePaperRepository


ROOT = Path(__file__).resolve().parents[1]
WORKBOOKS = (
    "Ocean_Research_Hub_COMPLET.xlsx",
    "Ocean_Research_Intelligence_ENRICHED_B08.xlsx",
    "Ocean_Research_Intelligence_ENRICHED_B15.xlsx",
    "Ocean_Research_Intelligence_ENRICHED_B16.xlsx",
)


@pytest.fixture()
def mapping_repository(tmp_path: Path) -> CorpusRepository:
    repository = CorpusRepository(tmp_path / "hub.db")
    for workbook in WORKBOOKS:
        repository.import_workbook(read_workbook(ROOT / "import_staging" / workbook))
    return repository


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _rehash(report: dict[str, object]) -> None:
    report["packet_sha256"] = hashlib.sha256(
        _canonical(report["packet"]).encode("utf-8")
    ).hexdigest()


def _report(
    repository: CorpusRepository,
    *,
    producer_id: str = "producer:qa",
    auditor_id: str = "auditor:qa",
    audit_decision: str = "MAPPED",
    review_status: str = "VALIDATED",
    audited_at: str = "2026-09-30T12:00:00+00:00",
) -> dict[str, object]:
    mapping_set = repository.field_mappings()
    mapping = next(
        row for row in mapping_set["mappings"]
        if row["decision"] == "MAPPED" and row["canonical_path"]
    )
    source_mapping = {
        "original_path": mapping["original_path"],
        "decision": mapping["decision"],
        "canonical_path": mapping["canonical_path"],
        "basis": mapping["basis"],
        "provenance_type": mapping["provenance_type"],
        "source_candidate": mapping["source_candidate"],
    }
    proposal = {
        "decision": "MAPPED",
        "canonical_path": mapping["canonical_path"],
        "reason": "Producer proposes the exact identity mapping for independent review.",
    }
    packet = {
        "packet_kind": "FIELD_PATH_MAPPING_AUDIT_PACKET",
        "schema_version": 1,
        "version_id": mapping_set["version"]["version_id"],
        "producer_id": producer_id,
        "source": {
            "name": mapping_set["version"]["source_name"],
            "sha256": mapping_set["version"]["workbook_sha256"],
        },
        "source_mapping": source_mapping,
        "producer_proposal": proposal,
    }
    target = mapping["canonical_path"] if audit_decision == "MAPPED" else None
    report: dict[str, object] = {
        "report_kind": "INDEPENDENT_MAPPING_AUDIT",
        "packet": packet,
        "audit_decision": {
            "auditor_id": auditor_id,
            "decision": audit_decision,
            "canonical_path": target,
            "review_status": review_status,
            "justification": "Independent reviewer examined the exact packet and recorded this decision.",
            "evidence": "The source mapping row and canonical contract were both inspected.",
            "locator": "FIELD_PATH_MAP exact row",
            "evidence_sources": [{
                "name": "primary-source.pdf",
                "edition": "published primary source",
                "sha256": "a" * 64,
            }],
            "audited_at": audited_at,
            "auditor_model": "NOT_EXPOSED",
            "auditor_reasoning_effort": "NOT_EXPOSED",
        },
    }
    _rehash(report)
    return report


def test_mapping_audit_refuses_forged_hash_and_source_or_mapping_tampering(
    mapping_repository: CorpusRepository,
) -> None:
    forged_hash = _report(mapping_repository)
    forged_hash["packet_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="packet SHA-256 differs"):
        mapping_repository.record_mapping_audit(forged_hash)

    forged_source = copy.deepcopy(_report(mapping_repository))
    forged_source["packet"]["source"]["sha256"] = "f" * 64  # type: ignore[index]
    _rehash(forged_source)
    with pytest.raises(ValueError, match="source name or SHA-256 differs"):
        mapping_repository.record_mapping_audit(forged_source)

    forged_mapping = copy.deepcopy(_report(mapping_repository))
    forged_mapping["packet"]["source_mapping"]["basis"] = "forged basis"  # type: ignore[index]
    _rehash(forged_mapping)
    with pytest.raises(ValueError, match="source_mapping differs"):
        mapping_repository.record_mapping_audit(forged_mapping)


def test_mapping_audit_requires_distinct_producer_and_auditor(
    mapping_repository: CorpusRepository,
) -> None:
    report = _report(mapping_repository, producer_id="same:actor", auditor_id="same:actor")
    with pytest.raises(ValueError, match="producer and auditor must be distinct"):
        mapping_repository.record_mapping_audit(report)


def test_mapping_audit_requires_hash_pinned_evidence_sources(
    mapping_repository: CorpusRepository,
) -> None:
    absent = _report(mapping_repository)
    absent["audit_decision"].pop("evidence_sources")  # type: ignore[index]
    with pytest.raises(ValueError, match="evidence_sources"):
        mapping_repository.record_mapping_audit(absent)

    malformed = _report(mapping_repository)
    malformed["audit_decision"]["evidence_sources"][0]["sha256"] = "not-a-sha"  # type: ignore[index]
    with pytest.raises(ValueError, match="SHA-256"):
        mapping_repository.record_mapping_audit(malformed)


def test_mapping_audit_is_idempotent_retains_runtime_metadata_and_never_promotes_claims(
    mapping_repository: CorpusRepository,
) -> None:
    before_statuses = mapping_repository.summary()["claim_statuses"]
    report = _report(mapping_repository)

    first = mapping_repository.record_mapping_audit(report)
    second = mapping_repository.record_mapping_audit(report)

    assert first["appended"] is True
    assert second["appended"] is False
    assert second["already_recorded"] is True
    event = mapping_repository.list_mapping_audits()[0]
    assert event["auditor_model"] == "NOT_EXPOSED"
    assert event["auditor_reasoning_effort"] == "NOT_EXPOSED"
    assert event["evidence_sources"] == [{
        "name": "primary-source.pdf",
        "edition": "published primary source",
        "sha256": "a" * 64,
    }]
    assert event["current"] is True
    assert mapping_repository.summary()["claim_statuses"] == before_statuses == {"NOT_VERIFIED": 1867}

    mapping = next(
        row for row in mapping_repository.field_mappings()["mappings"]
        if row["original_path"] == event["original_path"]
    )
    assert mapping["source_review_status"] == "PENDING"
    assert mapping["effective_review_status"] == "VALIDATED"
    assert mapping["projection_applied"] is False


def test_mapping_audit_keeps_explicit_dissent_and_marks_prior_decision_superseded(
    mapping_repository: CorpusRepository,
) -> None:
    approved = _report(mapping_repository, audited_at="2026-09-30T12:00:00+00:00")
    rejected = _report(
        mapping_repository,
        audit_decision="AMBIGUOUS",
        review_status="REJECTED",
        audited_at="2026-09-30T12:01:00+00:00",
    )
    mapping_repository.record_mapping_audit(approved)
    mapping_repository.record_mapping_audit(rejected)

    events = mapping_repository.list_mapping_audits(
        original_path=approved["packet"]["source_mapping"]["original_path"]  # type: ignore[index]
    )
    assert len(events) == 2
    assert events[0]["current"] is False
    assert events[0]["stale_reason"] == "SUPERSEDED_BY_LATER_MAPPING_AUDIT"
    assert events[1]["current"] is True
    assert events[1]["review_status"] == "REJECTED"
    assert events[1]["dissent"] is True

    mapping = next(
        row for row in mapping_repository.field_mappings()["mappings"]
        if row["original_path"] == events[1]["original_path"]
    )
    assert mapping["effective_review_status"] == "REJECTED"
    assert mapping["effective_decision"] == "AMBIGUOUS"
    assert mapping["projection_applied"] is False


def test_mapping_audit_tables_and_source_rules_are_append_only(
    mapping_repository: CorpusRepository,
) -> None:
    stored = mapping_repository.record_mapping_audit(_report(mapping_repository))
    with sqlite3.connect(mapping_repository.database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="source mapping proposals are immutable"):
            connection.execute(
                "UPDATE staging_corpus_field_mappings SET basis = basis "
                "WHERE version_id = ? AND original_path = ?",
                (stored["version_id"], stored["original_path"]),
            )
        with pytest.raises(sqlite3.IntegrityError, match="mapping audit packets are immutable"):
            connection.execute(
                "UPDATE staging_corpus_mapping_audit_packets SET packet_json = packet_json "
                "WHERE packet_sha256 = ?", (stored["packet_sha256"],),
            )
        with pytest.raises(sqlite3.IntegrityError, match="mapping audit events are append-only"):
            connection.execute(
                "DELETE FROM staging_corpus_mapping_audit_events WHERE event_id = ?",
                (stored["event_id"],),
            )


def _create_interim_mapping_audit_schema(database: Path, *, with_event: bool) -> None:
    """Model the short-lived pre-packet local schema without touching production DDL."""
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE staging_corpus_mapping_audit_events (
                   event_id TEXT PRIMARY KEY, version_id TEXT NOT NULL, original_path TEXT NOT NULL,
                   decision TEXT NOT NULL, canonical_path TEXT, review_status TEXT NOT NULL,
                   justification TEXT NOT NULL, producer_id TEXT NOT NULL, auditor_id TEXT NOT NULL,
                   audited_at TEXT NOT NULL, auditor_model TEXT, source_name TEXT NOT NULL,
                   source_sha256 TEXT NOT NULL, evidence TEXT NOT NULL, locator TEXT NOT NULL,
                   reviewed_json TEXT NOT NULL, created_at TEXT NOT NULL
               )"""
        )
        if with_event:
            connection.execute(
                """INSERT INTO staging_corpus_mapping_audit_events VALUES (
                       'legacy-event', 'legacy-version', 'training.optimizer', 'MAPPED',
                       'training.optimizer', 'VALIDATED', 'legacy evidence', 'producer:legacy',
                       'auditor:legacy', '2026-09-30T12:00:00+00:00', NULL, 'legacy.xlsx',
                       'a', 'legacy evidence', 'row 1', '{}', '2026-09-30T12:00:00+00:00'
                   )"""
            )


def test_mapping_audit_interim_schema_is_rebuilt_only_when_empty(tmp_path: Path) -> None:
    empty = tmp_path / "empty-legacy.db"
    _create_interim_mapping_audit_schema(empty, with_event=False)
    CorpusRepository(empty).initialize()
    with sqlite3.connect(empty) as connection:
        columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(staging_corpus_mapping_audit_events)"
        )}
    assert {"packet_sha256", "auditor_reasoning_effort"} <= columns

    populated = tmp_path / "populated-legacy.db"
    _create_interim_mapping_audit_schema(populated, with_event=True)
    with pytest.raises(sqlite3.IntegrityError, match="explicit data migration is required"):
        CorpusRepository(populated).initialize()
    with sqlite3.connect(populated) as connection:
        assert connection.execute(
            "SELECT event_id FROM staging_corpus_mapping_audit_events"
        ).fetchone()[0] == "legacy-event"


def test_mapping_audit_from_an_older_mapping_version_is_visibly_stale(
    mapping_repository: CorpusRepository,
) -> None:
    stored = mapping_repository.record_mapping_audit(_report(mapping_repository))
    with sqlite3.connect(mapping_repository.database_path) as connection:
        source = connection.execute(
            "SELECT * FROM staging_corpus_field_mappings WHERE version_id = ? AND original_path = ?",
            (stored["version_id"], stored["original_path"]),
        ).fetchone()
        connection.execute(
            "INSERT INTO staging_corpus_import_runs VALUES (?, ?, ?, ?, ?, ?)",
            ("qa-later-run", "qa-later-source", "a" * 64, "2099-01-01T00:00:00+00:00", "{}", "[]"),
        )
        connection.execute(
            "INSERT INTO staging_corpus_mapping_versions VALUES (?, ?, ?, ?, ?)",
            ("qa-later-version", "qa-later-source", "a" * 64, "qa-later-run", "2099-01-01T00:00:00+00:00"),
        )
        connection.execute(
            """INSERT INTO staging_corpus_field_mappings (
                   version_id, original_path, canonical_path, decision, basis, provenance_type,
                   review_status, auditor_id, reviewed_at, source_candidate
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("qa-later-version", *source[1:]),
        )

    event = mapping_repository.list_mapping_audits()[0]
    assert event["current"] is False
    assert event["stale_reason"] == "MAPPING_VERSION_SUPERSEDED"
    assert mapping_repository.field_mappings()["version"]["version_id"] == "qa-later-version"


def test_mapping_audit_cli_replay_and_api_are_observable(
    mapping_repository: CorpusRepository, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    report_path = tmp_path / "mapping-audit.json"
    report_path.write_text(json.dumps(_report(mapping_repository)), encoding="utf-8")

    assert mapping_audit_main([str(report_path), "--database", str(mapping_repository.database_path)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["status"] == "RECORDED"
    assert mapping_audit_main([str(report_path), "--database", str(mapping_repository.database_path)]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["status"] == "UNCHANGED"

    app = create_app(
        repository=SqlitePaperRepository(mapping_repository.database_path),
        corpus_repository=mapping_repository,
    )
    with TestClient(app) as client:
        response = client.get("/api/corpus/mapping-audits")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert "does not verify or promote any scientific claim" in body["notice"]
    assert body["mapping_audit_events"][0]["current"] is True
