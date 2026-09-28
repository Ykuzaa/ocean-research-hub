"""SQLite store for the issue #13 staging corpus.

The staging corpus lives in its own ``staging_corpus_*`` tables beside the
canonical ``papers`` table and never writes to it. Two reasons:

* a staging record is not a ``PaperRecord``: its 162-field contract differs,
  and ``PaperRecord`` has no ``NOT_EXTRACTED`` state, so a missing field would
  have to be stored as ``NOT_REPORTED`` or ``EXTRACTION_ERROR`` - both false;
* independently audited ``PaperRecord`` rows must never be overwritten by a
  bulk import of unaudited material.

A staging paper whose DOI matches a canonical ``papers`` row is *linked* to it
(read-only), so both views of the same work can be found from either side.

Imports are idempotent: every row carries a content fingerprint, unchanged
rows are not rewritten, rows absent from a later workbook are reported and
kept, and a row carrying an independent audit attestation is never overwritten.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .workbook import (
    PENDING_AUDIT_MARKERS, SUPPLEMENT, StagingWorkbook, WorkbookValidationError, claim_fingerprint_payload, is_marker,
    normalize_doi, normalize_title, parse_claim_value,
)

# States that mean an independent reviewer has attested the row. A row in one
# of these states is never overwritten by an import. Staging workbooks cannot
# introduce them (see ``workbook.REFUSED_CLAIM_STATUSES``); they can only
# arise from an audit recorded after import.
ATTESTED_STATES = frozenset({
    "VERIFIED", "PARTIALLY_VERIFIED", "AUDITED", "INDEPENDENTLY_AUDITED", "AUDIT_PASSED",
})
# One definition of "not yet audited", shared with the workbook reader.
UNATTESTED_AUDIT_MARKERS = PENDING_AUDIT_MARKERS | {""}

NOT_EXTRACTED = "NOT_EXTRACTED"
NOT_REPORTED_CANDIDATE = "NOT_REPORTED_CANDIDATE"

SCHEMA = """
CREATE TABLE IF NOT EXISTS staging_corpus_import_runs (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    workbook_sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    counts_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_field_contract (
    field_path TEXT PRIMARY KEY,
    field_group TEXT NOT NULL,
    field_name TEXT NOT NULL,
    position INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_papers (
    paper_id TEXT PRIMARY KEY,
    doi_key TEXT,
    title_key TEXT,
    year TEXT,
    index_json TEXT NOT NULL,
    record_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    linked_paper_record_id TEXT,
    import_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS staging_corpus_papers_doi
    ON staging_corpus_papers(doi_key) WHERE doi_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS staging_corpus_paper_aliases (
    alias_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES staging_corpus_papers(paper_id),
    matched_on TEXT NOT NULL,
    import_run_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_claims (
    claim_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES staging_corpus_papers(paper_id),
    experiment_id TEXT,
    field_path TEXT NOT NULL,
    scientific_status TEXT NOT NULL,
    independent_audit TEXT,
    row_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS staging_corpus_claims_paper ON staging_corpus_claims(paper_id);
CREATE INDEX IF NOT EXISTS staging_corpus_claims_field ON staging_corpus_claims(field_path);
CREATE TABLE IF NOT EXISTS staging_corpus_research_gaps (
    gap_key TEXT PRIMARY KEY,
    row_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_field_markers (
    marker_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES staging_corpus_papers(paper_id),
    field_path TEXT NOT NULL,
    extraction_status TEXT NOT NULL,
    scientific_status TEXT NOT NULL,
    independent_audit TEXT,
    row_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS staging_corpus_field_markers_paper ON staging_corpus_field_markers(paper_id);
CREATE TABLE IF NOT EXISTS staging_corpus_paper_coverage (
    coverage_key TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES staging_corpus_papers(paper_id),
    source_name TEXT NOT NULL,
    row_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_row_versions (
    table_name TEXT NOT NULL,
    row_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    PRIMARY KEY (table_name, row_key, fingerprint)
);
CREATE TABLE IF NOT EXISTS staging_corpus_documents (
    name TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_audit_events (
    event_id TEXT PRIMARY KEY,
    target_kind TEXT NOT NULL CHECK (target_kind IN ('CLAIM', 'MARKER', 'PAPER')),
    target_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN (
        'VERIFIED', 'PARTIALLY_VERIFIED', 'NOT_VERIFIED', 'NOT_REPORTED',
        'CONFLICT', 'EXTRACTION_ERROR', 'BLOCKED'
    )),
    justification TEXT NOT NULL,
    auditor_id TEXT NOT NULL,
    audited_at TEXT NOT NULL,
    provenance_type TEXT NOT NULL CHECK (provenance_type IN (
        'AUTHOR_REPORTED_FACT', 'AUTHOR_REPORTED_LIMITATION', 'AI_INTERPRETATION', 'TEAM_NOTE'
    )),
    source_kind TEXT NOT NULL CHECK (source_kind IN (
        'PRIMARY_PAPER', 'SUPPLEMENTARY_MATERIAL', 'AUTHOR_CODE',
        'PUBLISHER_METADATA', 'OTHER'
    )),
    source_edition TEXT NOT NULL,
    page INTEGER CHECK (page IS NULL OR page >= 1),
    section TEXT,
    locator TEXT,
    evidence TEXT,
    search_scope TEXT,
    target_fingerprint TEXT NOT NULL,
    reviewed_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS staging_corpus_audit_target
    ON staging_corpus_audit_events(target_kind, target_id, audited_at);
CREATE TRIGGER IF NOT EXISTS staging_corpus_audit_no_update
BEFORE UPDATE ON staging_corpus_audit_events BEGIN
    SELECT RAISE(ABORT, 'scientific audit events are append-only');
END;
CREATE TRIGGER IF NOT EXISTS staging_corpus_audit_no_delete
BEFORE DELETE ON staging_corpus_audit_events BEGIN
    SELECT RAISE(ABORT, 'scientific audit events are append-only');
END;
CREATE TABLE IF NOT EXISTS staging_corpus_mapping_versions (
    version_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    workbook_sha256 TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_field_mappings (
    version_id TEXT NOT NULL REFERENCES staging_corpus_mapping_versions(version_id),
    original_path TEXT NOT NULL,
    canonical_path TEXT,
    decision TEXT NOT NULL CHECK (decision IN ('MAPPED', 'UNMAPPED', 'AMBIGUOUS')),
    basis TEXT NOT NULL,
    provenance_type TEXT NOT NULL CHECK (provenance_type IN ('AI_INTERPRETATION', 'TEAM_NOTE')),
    review_status TEXT NOT NULL CHECK (review_status IN ('PENDING', 'VALIDATED', 'REJECTED')),
    auditor_id TEXT,
    reviewed_at TEXT,
    source_candidate TEXT,
    PRIMARY KEY (version_id, original_path),
    CHECK (review_status != 'VALIDATED' OR (auditor_id IS NOT NULL AND reviewed_at IS NOT NULL)),
    CHECK (decision != 'MAPPED' OR canonical_path IS NOT NULL)
);
"""


# Tables whose rows are upserted by fingerprint; their current fingerprints
# are recorded as versions so a later import cannot revert a row to an older one.
VERSIONED_TABLES = {
    "staging_corpus_field_contract": "field_path", "staging_corpus_papers": "paper_id",
    "staging_corpus_claims": "claim_id", "staging_corpus_field_markers": "marker_id",
    "staging_corpus_research_gaps": "gap_key", "staging_corpus_documents": "name",
    "staging_corpus_paper_coverage": "coverage_key",
}


class _DryRun(Exception):
    """Raised inside the import transaction to roll a dry run back."""


class CorpusNotFoundError(LookupError):
    """The requested staging paper or claim does not exist."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def is_attested(status: str | None, independent_audit: str | None = None) -> bool:
    return status in ATTESTED_STATES or independent_audit not in UNATTESTED_AUDIT_MARKERS


@dataclass
class EntityCounts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_protected: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "created": self.created, "updated": self.updated,
            "unchanged": self.unchanged, "skipped_protected": self.skipped_protected,
        }


@dataclass
class ImportReport:
    run_id: str
    source_name: str
    workbook_sha256: str
    papers: EntityCounts = field(default_factory=EntityCounts)
    claims: EntityCounts = field(default_factory=EntityCounts)
    field_contract: EntityCounts = field(default_factory=EntityCounts)
    research_gaps: EntityCounts = field(default_factory=EntityCounts)
    documents: EntityCounts = field(default_factory=EntityCounts)
    coverage: EntityCounts = field(default_factory=EntityCounts)
    field_markers: EntityCounts = field(default_factory=EntityCounts)
    allow_revert: bool = False
    stale: list[str] = field(default_factory=list)
    reverted: list[str] = field(default_factory=list)
    seen_versions: list[tuple[str, str, str]] = field(default_factory=list)
    aliases_created: list[dict[str, str]] = field(default_factory=list)
    linked_paper_records: int = 0
    absent_from_source: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, Any]:
        return {
            "papers": self.papers.as_dict(), "claims": self.claims.as_dict(),
            "field_contract": self.field_contract.as_dict(),
            "research_gaps": self.research_gaps.as_dict(), "documents": self.documents.as_dict(),
            "coverage": self.coverage.as_dict(), "field_markers": self.field_markers.as_dict(),
            "aliases_created": len(self.aliases_created),
            "linked_paper_records": self.linked_paper_records,
            "absent_from_source": {key: len(value) for key, value in self.absent_from_source.items()},
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "source_name": self.source_name,
            "workbook_sha256": self.workbook_sha256, "counts": self.counts(),
            "aliases_created": self.aliases_created,
            "absent_from_source": self.absent_from_source, "warnings": self.warnings,
        }


class CorpusRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._initialized = False

    # -- lifecycle ---------------------------------------------------------

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript(SCHEMA)
        self._initialized = True

    @staticmethod
    def _record_current_versions(connection: sqlite3.Connection) -> None:
        """Record every stored row's current fingerprint as a known version.

        Runs inside an import transaction (never on read). A database built
        before versions existed only gains its *current* state this way; the
        versions it replaced earlier are unknown, so re-importing those older
        workbooks would not be caught. ``record_versions`` records them from
        the workbooks themselves.
        """
        for table, key in VERSIONED_TABLES.items():
            connection.execute(
                f"INSERT OR IGNORE INTO staging_corpus_row_versions "
                f"SELECT ?, {key}, fingerprint, import_run_id FROM {table}",
                (table,),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ready(self) -> sqlite3.Connection:
        if not self._initialized:
            self.initialize()
        return self._connect()

    # -- import ------------------------------------------------------------

    def import_workbook(
        self, book: StagingWorkbook, *, dry_run: bool = False, allow_revert: bool = False,
    ) -> ImportReport:
        """Import a validated workbook in one transaction. All or nothing.

        ``dry_run`` performs every check, including those against the stored
        corpus, and reports what would change, then rolls everything back.
        Raises ``WorkbookValidationError`` if the workbook conflicts with the
        stored corpus; nothing is then written.

        A row whose incoming content equals one of its earlier versions is a
        revert, and by default the import is refused as older than the stored
        corpus. ``allow_revert`` applies such rows anyway (for a newer package
        that deliberately returns to an earlier value, or to undo a mistaken
        import) and lists every reverted row in the run's warnings.
        """
        report = ImportReport(str(uuid4()), book.source_name, book.sha256, allow_revert=allow_revert)
        report.warnings.extend(book.warnings)
        now = datetime.now(UTC).isoformat()
        connection = self._ready()
        try:
            with connection:
                self._record_current_versions(connection)
                if book.kind == SUPPLEMENT:
                    self._check_supplement(connection, book, report)
                else:
                    self._import_contract(connection, book, report)
                paper_map = self._import_papers(connection, book, report, now)
                self._import_claims(connection, book, report, paper_map, now)
                self._import_gaps(connection, book, report, now)
                self._import_documents(connection, book, report)
                self._import_coverage(connection, book, report, paper_map)
                self._import_field_path_mappings(connection, book, report, now)
                if report.stale:
                    raise WorkbookValidationError([
                        f"{len(report.stale)} row(s) would be reverted to content an earlier import already "
                        f"replaced; this workbook looks older than the stored corpus (for example "
                        f"{report.stale[:5]}). Import the newest package, or pass --allow-revert if "
                        f"returning to that content is intended."
                    ])
                if report.reverted:
                    report.warnings.append(
                        f"--allow-revert: {len(report.reverted)} row(s) returned to an earlier version: "
                        f"{report.reverted[:50]}{' ...' if len(report.reverted) > 50 else ''}"
                    )
                connection.execute(
                    "INSERT INTO staging_corpus_import_runs VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        report.run_id, book.source_name, book.sha256, now,
                        _canonical(report.counts()), _canonical(report.warnings),
                    ),
                )
                if dry_run:
                    raise _DryRun
        except _DryRun:
            pass
        finally:
            connection.close()
        return report

    def record_versions(self, book: StagingWorkbook) -> int:
        """Record the fingerprints an already-imported workbook wrote, without importing it.

        For a database built before row versions existed: recording the older
        packages it was built from lets the stale guard refuse them later.
        Only a workbook whose SHA-256 appears in the import history is
        accepted, so a newer package can never be pre-emptively blocked.
        Returns the number of versions added.
        """
        with closing(self._ready()) as connection:
            known = connection.execute(
                "SELECT 1 FROM staging_corpus_import_runs WHERE workbook_sha256 = ?", (book.sha256,)
            ).fetchone()
        if known is None:
            raise WorkbookValidationError([
                f"{book.source_name} ({book.sha256[:12]}) was never imported into this database; "
                f"only versions of already-imported workbooks can be recorded"
            ])
        report = self.import_workbook(book, dry_run=True, allow_revert=True)
        with closing(self._connect()) as connection, connection:
            before = connection.execute("SELECT COUNT(*) FROM staging_corpus_row_versions").fetchone()[0]
            connection.executemany(
                "INSERT OR IGNORE INTO staging_corpus_row_versions VALUES (?, ?, ?, ?)",
                [(table, key, fingerprint, f"recorded:{book.sha256}") for table, key, fingerprint in report.seen_versions],
            )
            return connection.execute("SELECT COUNT(*) FROM staging_corpus_row_versions").fetchone()[0] - before

    @staticmethod
    def _upsert(
        connection: sqlite3.Connection, table: str, key_column: str, key: str,
        fingerprint: str, values: dict[str, Any], counts: EntityCounts,
        *, protected: bool = False, report: ImportReport | None = None,
    ) -> str:
        """Insert, update, skip or leave unchanged one row. Returns the action."""
        row = connection.execute(
            f"SELECT fingerprint FROM {table} WHERE {key_column} = ?", (key,)
        ).fetchone()
        if report is not None:
            report.seen_versions.append((table, key, fingerprint))

        def remember() -> None:
            if report is not None:
                connection.execute(
                    "INSERT OR IGNORE INTO staging_corpus_row_versions VALUES (?, ?, ?, ?)",
                    (table, key, fingerprint, report.run_id),
                )

        if row is None:
            columns = [key_column, "fingerprint", *values]
            connection.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                (key, fingerprint, *values.values()),
            )
            counts.created += 1
            remember()
            return "created"
        if row["fingerprint"] == fingerprint:
            counts.unchanged += 1
            return "unchanged"
        if protected:
            counts.skipped_protected += 1
            if report is not None:
                report.warnings.append(
                    f"{table} {key}: carries an independent audit attestation; the incoming "
                    f"different content was NOT applied"
                )
            return "skipped_protected"
        if report is not None and connection.execute(
            "SELECT 1 FROM staging_corpus_row_versions WHERE table_name = ? AND row_key = ? AND fingerprint = ?",
            (table, key, fingerprint),
        ).fetchone():
            # This exact content was stored before and later replaced.
            if not report.allow_revert:
                report.stale.append(f"{table}:{key}")
                return "stale"
            report.reverted.append(f"{table}:{key}")
        updates = {key: value for key, value in values.items() if key != "created_at"}
        connection.execute(
            f"UPDATE {table} SET fingerprint = ?, {', '.join(f'{column} = ?' for column in updates)} "
            f"WHERE {key_column} = ?",
            (fingerprint, *updates.values(), key),
        )
        counts.updated += 1
        remember()
        return "updated"

    def _import_contract(self, connection: sqlite3.Connection, book: StagingWorkbook, report: ImportReport) -> None:
        for position, row in enumerate(book.field_contract):
            payload = {"group": row["group"], "field_name": row["field_name"], "position": position}
            self._upsert(
                connection, "staging_corpus_field_contract", "field_path", row["field_path"],
                _fingerprint(payload),
                {
                    "field_group": row["group"], "field_name": row["field_name"],
                    "position": position, "import_run_id": report.run_id,
                },
                report.field_contract, report=report,
            )

    def _check_supplement(
        self, connection: sqlite3.Connection, book: StagingWorkbook, report: ImportReport,
    ) -> None:
        """Validate a supplement against the stored base corpus before any write."""
        contract = {
            row["field_path"] for row in connection.execute("SELECT field_path FROM staging_corpus_field_contract")
        }
        errors: list[str] = []
        if not contract:
            errors.append("a supplement workbook needs a base corpus; import the base workbook first")
        for row in book.paper_index:
            # A supplement names papers by their stored ID (or a known alias)
            # only, and may not change their identity: it has no record to
            # justify a new work, a new ID, or a corrected title/DOI/year.
            stored = connection.execute(
                "SELECT p.* FROM staging_corpus_papers p WHERE p.paper_id = ? UNION ALL "
                "SELECT p.* FROM staging_corpus_papers p JOIN staging_corpus_paper_aliases a "
                "ON a.paper_id = p.paper_id WHERE a.alias_id = ?",
                (row["paper_id"], row["paper_id"]),
            ).fetchone()
            if stored is None:
                errors.append(
                    f"supplement paper {row['paper_id']} is not in the stored corpus under that ID; a "
                    f"supplement carries no PAPER_RECORDS and cannot introduce a paper or a new ID"
                )
                continue
            incoming = {
                "doi": normalize_doi(row.get("doi")), "title": normalize_title(row.get("title")),
                "year": None if row.get("year") is None else str(row.get("year")),
            }
            current = {"doi": stored["doi_key"], "title": stored["title_key"], "year": stored["year"]}
            changed = [column for column in incoming if incoming[column] != current[column]]
            if changed == ["doi"] and current["doi"] is None and incoming["doi"]:
                # Filling a missing DOI names the same work; it is refused only when
                # another stored paper already holds that DOI.
                holder = connection.execute(
                    "SELECT paper_id FROM staging_corpus_papers WHERE doi_key = ? AND paper_id != ?",
                    (incoming["doi"], stored["paper_id"]),
                ).fetchone()
                if holder is None:
                    report.warnings.append(
                        f"supplement adds the missing DOI {incoming['doi']} to {row['paper_id']} "
                        f"(title and year unchanged)"
                    )
                    continue
                errors.append(
                    f"supplement gives {row['paper_id']} the DOI {incoming['doi']}, already held by "
                    f"{holder['paper_id']}"
                )
                continue
            if changed:
                errors.append(
                    f"supplement changes the identity of {row['paper_id']} ({', '.join(changed)}: stored "
                    f"{[current[c] for c in changed]}, incoming {[incoming[c] for c in changed]}); "
                    f"identity corrections need a base workbook"
                )
        if errors:
            raise WorkbookValidationError(errors)
        outside = sorted(
            f"{row['claim_id']} ({row['field_path']})" for row in book.claims
            if row["field_path"] not in contract and not is_marker(row)
        )
        if outside:
            paths = sorted({row["field_path"] for row in book.claims if row["field_path"] not in contract})
            report.warnings.append(
                f"{len(outside)} claim(s) using {len(paths)} field_path(s) outside the stored FIELD_CONTRACT "
                f"are preserved verbatim, served as uncontracted_claims and mapped to no field: "
                f"{outside[:20]}{' ...' if len(outside) > 20 else ''}"
            )
        extracted = {(row["paper_id"], row["field_path"]) for row in book.claims if not is_marker(row)}
        overlaps = sorted(
            f"{row['claim_id']} {row['extraction_status']} {row['paper_id']} {row['field_path']}"
            for row in book.claims if is_marker(row) and (row["paper_id"], row["field_path"]) in extracted
        )
        if overlaps:
            report.warnings.append(
                f"field-status marker(s) on a field that also has an extracted claim are both kept and "
                f"served side by side (NOT_VERIFIED|NOT_REPORTED_CANDIDATE when the marker is "
                f"NOT_REPORTED): {overlaps}"
            )

    def _resolve_paper(
        self, connection: sqlite3.Connection, paper_id: str, doi_key: str | None,
        title_key: str | None, year: str | None,
    ) -> tuple[str | None, str | None]:
        """Existing canonical staging id for this work, and what matched it."""
        if connection.execute(
            "SELECT 1 FROM staging_corpus_papers WHERE paper_id = ?", (paper_id,)
        ).fetchone():
            return paper_id, "paper_id"
        alias = connection.execute(
            "SELECT paper_id FROM staging_corpus_paper_aliases WHERE alias_id = ?", (paper_id,)
        ).fetchone()
        if alias:
            return alias["paper_id"], "alias"
        if doi_key:
            row = connection.execute(
                "SELECT paper_id FROM staging_corpus_papers WHERE doi_key = ?", (doi_key,)
            ).fetchone()
            if row:
                return row["paper_id"], "doi"
        if title_key:
            # A title/year match never merges two works that both carry DOIs:
            # different DOIs are different works, whatever the titles say.
            row = connection.execute(
                "SELECT paper_id, doi_key FROM staging_corpus_papers WHERE title_key = ? AND year IS ?",
                (title_key, year),
            ).fetchone()
            if row and (row["doi_key"] is None or doi_key is None):
                return row["paper_id"], "title_year"
        return None, None

    @staticmethod
    def _linked_paper_record(connection: sqlite3.Connection, doi_key: str | None) -> str | None:
        if not doi_key:
            return None
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'papers'"
        ).fetchone()
        if not exists:
            return None
        row = connection.execute(
            "SELECT id FROM papers WHERE lower(doi) = ?", (doi_key,)
        ).fetchone()
        return None if row is None else row["id"]

    def _import_papers(
        self, connection: sqlite3.Connection, book: StagingWorkbook, report: ImportReport, now: str,
    ) -> dict[str, str]:
        records = {record["paper_id"]: record for record in book.paper_records}
        paper_map: dict[str, str] = {}
        for index_row in book.paper_index:
            incoming_id = index_row["paper_id"]
            doi_key = normalize_doi(index_row.get("doi"))
            title_key = normalize_title(index_row.get("title"))
            year = None if index_row.get("year") is None else str(index_row.get("year"))
            canonical_id, matched_on = self._resolve_paper(connection, incoming_id, doi_key, title_key, year)
            if canonical_id is not None and canonical_id != incoming_id and matched_on in {"doi", "title_year"}:
                connection.execute(
                    "INSERT OR IGNORE INTO staging_corpus_paper_aliases VALUES (?, ?, ?, ?)",
                    (incoming_id, canonical_id, matched_on, report.run_id),
                )
                report.aliases_created.append(
                    {"alias_id": incoming_id, "paper_id": canonical_id, "matched_on": matched_on}
                )
            target_id = canonical_id or incoming_id
            paper_map[incoming_id] = target_id
            if doi_key:
                owner = connection.execute(
                    "SELECT paper_id FROM staging_corpus_papers WHERE doi_key = ? AND paper_id != ?",
                    (doi_key, target_id),
                ).fetchone()
                if owner is not None:
                    raise WorkbookValidationError([
                        f"{incoming_id}: DOI {doi_key} already belongs to stored paper {owner['paper_id']}; "
                        f"deduplicate before import"
                    ])
            linked = self._linked_paper_record(connection, doi_key)
            if linked:
                report.linked_paper_records += 1
            existing = connection.execute(
                "SELECT index_json, record_json FROM staging_corpus_papers WHERE paper_id = ?",
                (target_id,),
            ).fetchone()
            # A supplement has no record of its own: the stored one is kept as supplied.
            record = json.loads(existing["record_json"]) if book.kind == SUPPLEMENT else records[incoming_id]
            protected = existing is not None and (
                is_attested(json.loads(existing["index_json"]).get("scientific_audit_status"))
                or is_attested(json.loads(existing["record_json"]).get("scientific_audit_status"))
            )
            payload = {"index": index_row, "record": record}
            self._upsert(
                connection, "staging_corpus_papers", "paper_id", target_id, _fingerprint(payload),
                {
                    "doi_key": doi_key, "title_key": title_key, "year": year,
                    # An aliased row is stored under the canonical ID; the ID the
                    # workbook used is kept as source_paper_id.
                    "index_json": _canonical(
                        index_row if target_id == incoming_id
                        else {**index_row, "paper_id": target_id, "source_paper_id": incoming_id}
                    ),
                    "record_json": _canonical(record),
                    "linked_paper_record_id": linked, "import_run_id": report.run_id,
                    "created_at": now, "updated_at": now,
                },
                report.papers, protected=protected, report=report,
            )
        incoming = set(paper_map.values())
        stored = {row["paper_id"] for row in connection.execute("SELECT paper_id FROM staging_corpus_papers")}
        absent = sorted(stored - incoming)
        if absent:
            report.absent_from_source["papers"] = absent
        return paper_map

    def _import_claims(
        self, connection: sqlite3.Connection, book: StagingWorkbook, report: ImportReport,
        paper_map: dict[str, str], now: str,
    ) -> None:
        self._check_claim_identity(connection, book, paper_map)
        for row in book.claims:
            if is_marker(row):
                self._import_marker(connection, row, report, paper_map, now)
                continue
            claim_id = row["claim_id"]
            existing = connection.execute(
                "SELECT scientific_status, independent_audit FROM staging_corpus_claims WHERE claim_id = ?",
                (claim_id,),
            ).fetchone()
            protected = existing is not None and is_attested(
                existing["scientific_status"], existing["independent_audit"],
            )
            self._upsert(
                connection, "staging_corpus_claims", "claim_id", claim_id,
                _fingerprint(claim_fingerprint_payload(row)),
                {
                    "paper_id": paper_map[row["paper_id"]], "experiment_id": row.get("experiment_id"),
                    "field_path": row["field_path"], "scientific_status": row["scientific_status"],
                    "independent_audit": row.get("independent_audit"), "row_json": _canonical(row),
                    "import_run_id": report.run_id, "created_at": now, "updated_at": now,
                },
                report.claims, protected=protected, report=report,
            )
        incoming = {row["claim_id"] for row in book.claims if not is_marker(row)}
        stored = {item["claim_id"] for item in connection.execute("SELECT claim_id FROM staging_corpus_claims")}
        absent = sorted(stored - incoming)
        if absent:
            report.absent_from_source["claims"] = absent
        incoming = {row["claim_id"] for row in book.claims if is_marker(row)}
        stored = {item["marker_id"] for item in connection.execute("SELECT marker_id FROM staging_corpus_field_markers")}
        absent = sorted(stored - incoming)
        if absent:
            report.absent_from_source["field_markers"] = absent

    @staticmethod
    def _check_claim_identity(
        connection: sqlite3.Connection, book: StagingWorkbook, paper_map: dict[str, str],
    ) -> None:
        """A stored claim or marker keeps its paper, field and kind.

        Re-sending an ID under another paper or field_path, or turning a claim
        into a marker (or back), would leave the record's slots and the served
        field disagreeing; it is refused instead of applied.
        """
        errors: list[str] = []
        stored = {
            row["id"]: (row["kind"], row["paper_id"], row["field_path"])
            for row in connection.execute(
                "SELECT claim_id AS id, 'claim' AS kind, paper_id, field_path FROM staging_corpus_claims "
                "UNION ALL SELECT marker_id, 'marker', paper_id, field_path FROM staging_corpus_field_markers"
            )
        }
        for row in book.claims:
            previous = stored.get(row["claim_id"])
            if previous is None:
                continue
            incoming = ("marker" if is_marker(row) else "claim", paper_map[row["paper_id"]], row["field_path"])
            if incoming != previous:
                errors.append(
                    f"{row['claim_id']} is stored as {previous[0]} of {previous[1]} at {previous[2]!r} but "
                    f"arrives as {incoming[0]} of {incoming[1]} at {incoming[2]!r}; a new ID is needed"
                )
        if errors:
            raise WorkbookValidationError(errors)

    def _import_marker(
        self, connection: sqlite3.Connection, row: dict[str, Any], report: ImportReport,
        paper_map: dict[str, str], now: str,
    ) -> None:
        existing = connection.execute(
            "SELECT scientific_status, independent_audit FROM staging_corpus_field_markers WHERE marker_id = ?",
            (row["claim_id"],),
        ).fetchone()
        protected = existing is not None and is_attested(existing["scientific_status"], existing["independent_audit"])
        self._upsert(
            connection, "staging_corpus_field_markers", "marker_id", row["claim_id"],
            _fingerprint(claim_fingerprint_payload(row)),
            {
                "paper_id": paper_map[row["paper_id"]], "field_path": row["field_path"],
                "extraction_status": row["extraction_status"], "scientific_status": row["scientific_status"],
                "independent_audit": row.get("independent_audit"), "row_json": _canonical(row),
                "import_run_id": report.run_id, "created_at": now, "updated_at": now,
            },
            report.field_markers, protected=protected, report=report,
        )

    def _import_gaps(
        self, connection: sqlite3.Connection, book: StagingWorkbook, report: ImportReport, now: str,
    ) -> None:
        for row in book.research_gaps:
            key = normalize_title(row["candidate_topic"]) or ""
            action = self._upsert(
                connection, "staging_corpus_research_gaps", "gap_key", key, _fingerprint(row),
                {
                    "row_json": _canonical(row), "import_run_id": report.run_id,
                    "created_at": now, "updated_at": now,
                },
                report.research_gaps, report=report,
            )
            if action == "updated":
                report.warnings.append(
                    f"research-gap candidate {row['candidate_topic']!r} was replaced by this workbook's version"
                )

    def _import_documents(self, connection: sqlite3.Connection, book: StagingWorkbook, report: ImportReport) -> None:
        documents = {**book.documents, "START_HERE": _canonical(book.start_here)}
        if book.kind == SUPPLEMENT:
            # Keyed by workbook so a supplement never replaces the base package's documents.
            documents = {
                f"{book.source_name}:START_HERE": _canonical(book.start_here),
                f"{book.source_name}:NEW_DETAILED_PAPERS": _canonical(book.new_detailed_papers),
                **{
                    f"{book.source_name}:{name}": _canonical(rows)
                    for name, rows in book.supplement_documents.items() if name != "NEW_DETAILED_PAPERS"
                },
            }
        for name, text in documents.items():
            self._upsert(
                connection, "staging_corpus_documents", "name", name, _fingerprint(text),
                {"text": text, "import_run_id": report.run_id},
                report.documents, report=report,
            )

    def _import_coverage(
        self, connection: sqlite3.Connection, book: StagingWorkbook, report: ImportReport,
        paper_map: dict[str, str],
    ) -> None:
        for row in book.coverage:
            paper_id = paper_map[row["paper_id"]]
            self._upsert(
                connection, "staging_corpus_paper_coverage", "coverage_key",
                f"{book.source_name}:{paper_id}", _fingerprint(row),
                {
                    "paper_id": paper_id, "source_name": book.source_name,
                    "row_json": _canonical(row), "import_run_id": report.run_id,
                },
                report.coverage, report=report,
            )

    @staticmethod
    def _import_field_path_mappings(
        connection: sqlite3.Connection, book: StagingWorkbook, report: ImportReport, now: str,
    ) -> None:
        """Store FIELD_PATH_MAP as a versioned proposal, never as validated truth."""
        candidates = book.supplement_documents.get("FIELD_PATH_MAP", [])
        if not candidates:
            return
        version_id = f"workbook:{book.sha256}"
        connection.execute(
            "INSERT OR IGNORE INTO staging_corpus_mapping_versions VALUES (?, ?, ?, ?, ?)",
            (version_id, book.source_name, book.sha256, report.run_id, now),
        )
        contract = {
            row["field_path"]
            for row in connection.execute("SELECT field_path FROM staging_corpus_field_contract")
        }
        candidate_paths = {str(row.get("field_path") or "") for row in candidates}
        supplied_paths = {str(row.get("field_path") or "") for row in book.claims}
        missing = sorted(supplied_paths - candidate_paths)
        if missing:
            raise WorkbookValidationError([
                f"FIELD_PATH_MAP omits {len(missing)} supplied field path(s): {missing[:20]}"
            ])
        for row in candidates:
            original = str(row.get("field_path") or "").strip()
            if not original:
                continue
            exact = original in contract
            category = str(row.get("canonical_category") or "").strip()
            decision = "MAPPED" if exact else ("AMBIGUOUS" if category else "UNMAPPED")
            basis = (
                "Exact path exists in the canonical field contract; validation still pending."
                if exact else
                f"Workbook source candidate category={category or 'none'}; no canonical field selected. "
                f"Supplied basis: {row.get('mapping_basis') or 'none'}"
            )
            connection.execute(
                """INSERT OR IGNORE INTO staging_corpus_field_mappings (
                       version_id, original_path, canonical_path, decision, basis,
                       provenance_type, review_status, auditor_id, reviewed_at, source_candidate
                   ) VALUES (?, ?, ?, ?, ?, 'AI_INTERPRETATION', 'PENDING', NULL, NULL, ?)""",
                (version_id, original, original if exact else None, decision, basis, _canonical(row)),
            )

    # -- reads -------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        with closing(self._ready()) as connection:
            def count(table: str) -> int:
                return int(connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])

            statuses = {
                row["scientific_status"]: row["n"]
                for row in connection.execute(
                    "SELECT scientific_status, COUNT(*) AS n FROM staging_corpus_claims GROUP BY 1"
                )
            }
            audits = {
                row["independent_audit"]: row["n"]
                for row in connection.execute(
                    "SELECT independent_audit, COUNT(*) AS n FROM staging_corpus_claims GROUP BY 1"
                )
            }
            last = connection.execute(
                "SELECT * FROM staging_corpus_import_runs ORDER BY imported_at DESC LIMIT 1"
            ).fetchone()
            return {
                "papers": count("staging_corpus_papers"),
                "claims": count("staging_corpus_claims"),
                "field_definitions": count("staging_corpus_field_contract"),
                "research_gap_candidates": count("staging_corpus_research_gaps"),
                "aliases": count("staging_corpus_paper_aliases"),
                "claim_statuses": statuses,
                "claim_independent_audit": audits,
                "field_status_markers": {
                    row["extraction_status"]: row["n"]
                    for row in connection.execute(
                        "SELECT extraction_status, COUNT(*) AS n FROM staging_corpus_field_markers GROUP BY 1"
                    )
                },
                "claims_with_supplied_pdf_page": int(connection.execute(
                    "SELECT COUNT(*) AS n FROM staging_corpus_claims "
                    "WHERE json_extract(row_json, '$.pdf_page') IS NOT NULL"
                ).fetchone()["n"]),
                "last_import": None if last is None else self._run(last),
            }

    @staticmethod
    def _run(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "run_id": row["id"], "source_name": row["source_name"],
            "workbook_sha256": row["workbook_sha256"], "imported_at": row["imported_at"],
            "counts": json.loads(row["counts_json"]), "warnings": json.loads(row["warnings_json"]),
        }

    def import_runs(self) -> list[dict[str, Any]]:
        with closing(self._ready()) as connection:
            return [
                self._run(row) for row in connection.execute(
                    "SELECT * FROM staging_corpus_import_runs ORDER BY imported_at DESC"
                )
            ]

    def record_audit(self, event: dict[str, Any]) -> dict[str, Any]:
        """Append one independently supplied audit decision after strict validation."""
        required = {
            "target_kind", "target_id", "decision", "justification", "auditor_id",
            "audited_at", "provenance_type", "source_kind", "source_edition",
        }
        missing = sorted(key for key in required if not str(event.get(key) or "").strip())
        if missing:
            raise ValueError(f"audit event lacks required field(s): {missing}")
        target_kind = str(event["target_kind"]).upper()
        decision = str(event["decision"]).upper()
        provenance = str(event["provenance_type"]).upper()
        source_kind = str(event["source_kind"]).upper()
        if target_kind not in {"CLAIM", "MARKER", "PAPER"}:
            raise ValueError("target_kind must be CLAIM, MARKER, or PAPER")
        if decision not in {
            "VERIFIED", "PARTIALLY_VERIFIED", "NOT_VERIFIED", "NOT_REPORTED",
            "CONFLICT", "EXTRACTION_ERROR", "BLOCKED",
        }:
            raise ValueError(f"unsupported audit decision {decision}")
        if provenance not in {
            "AUTHOR_REPORTED_FACT", "AUTHOR_REPORTED_LIMITATION", "AI_INTERPRETATION", "TEAM_NOTE",
        }:
            raise ValueError(f"unsupported provenance_type {provenance}")
        if source_kind not in {
            "PRIMARY_PAPER", "SUPPLEMENTARY_MATERIAL", "AUTHOR_CODE", "PUBLISHER_METADATA", "OTHER",
        }:
            raise ValueError(f"unsupported source_kind {source_kind}")
        audited_at_raw = str(event["audited_at"])
        try:
            if len(audited_at_raw) == 10:
                date.fromisoformat(audited_at_raw)
            else:
                audited_at = datetime.fromisoformat(audited_at_raw.replace("Z", "+00:00"))
                if audited_at.tzinfo is None:
                    raise ValueError("audited_at timestamp must include a timezone")
        except ValueError as exc:
            raise ValueError("audited_at must be an ISO-8601 date or timezone-aware timestamp") from exc
        if decision in {"VERIFIED", "PARTIALLY_VERIFIED"}:
            if provenance not in {"AUTHOR_REPORTED_FACT", "AUTHOR_REPORTED_LIMITATION"}:
                raise ValueError("verified decisions require author-reported provenance")
            if source_kind not in {"PRIMARY_PAPER", "SUPPLEMENTARY_MATERIAL", "AUTHOR_CODE"}:
                raise ValueError("verified decisions require a primary-author source")
            if not str(event.get("evidence") or "").strip() or not any(
                event.get(key) not in (None, "") for key in ("page", "section", "locator")
            ):
                raise ValueError("verified decisions require evidence and a page, section, or locator")
        if decision == "NOT_REPORTED":
            if target_kind != "MARKER":
                raise ValueError("NOT_REPORTED requires a field absence marker, not a populated claim or paper")
            scope = str(event.get("search_scope") or "").strip()
            if not scope or len(scope) < 30 or "keyword" in scope.casefold() or "mot-clé" in scope.casefold():
                raise ValueError("NOT_REPORTED requires a documented search_scope beyond keyword search")
        if target_kind == "PAPER" and decision == "VERIFIED":
            scope = str(event.get("search_scope") or "").strip()
            if len(scope) < 30:
                raise ValueError("a fully verified paper requires documented field-by-field review scope")
        if event.get("page") is not None and (not isinstance(event["page"], int) or event["page"] < 1):
            raise ValueError("page must be a positive integer")

        table, key = {
            "CLAIM": ("staging_corpus_claims", "claim_id"),
            "MARKER": ("staging_corpus_field_markers", "marker_id"),
            "PAPER": ("staging_corpus_papers", "paper_id"),
        }[target_kind]
        normalized = {
            **event,
            "event_id": str(event.get("event_id") or uuid4()),
            "target_kind": target_kind,
            "decision": decision,
            "provenance_type": provenance,
            "source_kind": source_kind,
        }
        with closing(self._ready()) as connection, connection:
            target = connection.execute(
                f"SELECT * FROM {table} WHERE {key} = ?", (str(event["target_id"]),)
            ).fetchone()
            if target is None:
                raise CorpusNotFoundError(f"{target_kind.lower()} {event['target_id']} was not found")
            if target_kind == "CLAIM":
                reviewed = event.get("reviewed")
                if not isinstance(reviewed, dict) or not {"value", "unit", "experiment_id", "field_path"} <= reviewed.keys():
                    raise ValueError("claim audit requires reviewed value, unit, experiment_id, and field_path")
                source_row = json.loads(target["row_json"])
                if decision in {"VERIFIED", "PARTIALLY_VERIFIED"}:
                    if source_row.get("claim_type") != provenance:
                        raise ValueError("verified audit provenance must match the imported claim")
                    if "SOURCE_REVIEW" in str(target["experiment_id"] or ""):
                        raise ValueError("an extraction review label is not a scientific experiment")
                expected = {
                    "value": parse_claim_value(source_row.get("value")),
                    "unit": source_row.get("unit"),
                    "experiment_id": target["experiment_id"],
                    "field_path": target["field_path"],
                }
                if _canonical(reviewed) != _canonical(expected):
                    raise ValueError("reviewed claim value, unit, experiment, or field differs from the stored row")
            elif target_kind == "MARKER":
                reviewed = event.get("reviewed")
                expected = {
                    "extraction_status": target["extraction_status"],
                    "field_path": target["field_path"],
                }
                if reviewed != expected:
                    raise ValueError("reviewed marker status or field differs from the stored row")
                if decision == "NOT_REPORTED" and target["extraction_status"] != "NOT_REPORTED":
                    raise ValueError("NOT_REPORTED audit requires a NOT_REPORTED candidate marker")
            else:
                reviewed = event.get("reviewed")
                expected = {"paper_id": target["paper_id"]}
                if reviewed != expected:
                    raise ValueError("reviewed paper identity differs from the stored row")
            normalized["target_fingerprint"] = target["fingerprint"]
            normalized["reviewed"] = reviewed
            connection.execute(
                """INSERT INTO staging_corpus_audit_events (
                       event_id, target_kind, target_id, decision, justification, auditor_id,
                       audited_at, provenance_type, source_kind, source_edition, page, section,
                       locator, evidence, search_scope, target_fingerprint, reviewed_json, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    normalized["event_id"], target_kind, str(event["target_id"]), decision,
                    str(event["justification"]).strip(), str(event["auditor_id"]).strip(),
                    audited_at_raw, provenance, source_kind,
                    str(event["source_edition"]).strip(), event.get("page"),
                    event.get("section"), event.get("locator"), event.get("evidence"),
                    event.get("search_scope"), target["fingerprint"], _canonical(reviewed),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return normalized

    @staticmethod
    def _audit_event(row: sqlite3.Row) -> dict[str, Any]:
        event = {key: row[key] for key in row.keys() if key not in {"created_at", "reviewed_json"}}
        event["reviewed"] = json.loads(row["reviewed_json"])
        return event

    def list_audits(
        self, *, target_kind: str | None = None, target_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[str] = []
        if target_kind:
            clauses.append("target_kind = ?")
            parameters.append(target_kind.upper())
        if target_id:
            clauses.append("target_id = ?")
            parameters.append(target_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with closing(self._ready()) as connection:
            rows = connection.execute(
                f"SELECT * FROM staging_corpus_audit_events {where} "
                "ORDER BY julianday(audited_at), created_at, event_id",
                parameters,
            ).fetchall()
        return [self._audit_event(row) for row in rows]

    def field_mappings(self, version_id: str | None = None) -> dict[str, Any]:
        with closing(self._ready()) as connection:
            version = (
                connection.execute(
                    "SELECT * FROM staging_corpus_mapping_versions WHERE version_id = ?", (version_id,)
                ).fetchone()
                if version_id else connection.execute(
                    "SELECT v.* FROM staging_corpus_mapping_versions v "
                    "JOIN staging_corpus_import_runs r ON r.id = v.import_run_id "
                    "ORDER BY r.imported_at DESC LIMIT 1"
                ).fetchone()
            )
            if version is None:
                return {"version": None, "mappings": []}
            rows = connection.execute(
                "SELECT * FROM staging_corpus_field_mappings WHERE version_id = ? ORDER BY original_path",
                (version["version_id"],),
            ).fetchall()
        return {
            "version": {
                "version_id": version["version_id"], "source_name": version["source_name"],
                "workbook_sha256": version["workbook_sha256"],
            },
            "mappings": [
                {
                    "original_path": row["original_path"], "canonical_path": row["canonical_path"],
                    "decision": row["decision"], "basis": row["basis"],
                    "provenance_type": row["provenance_type"], "review_status": row["review_status"],
                    "auditor_id": row["auditor_id"], "reviewed_at": row["reviewed_at"],
                    "source_candidate": json.loads(row["source_candidate"]) if row["source_candidate"] else None,
                    "projection_applied": row["review_status"] == "VALIDATED" and row["decision"] == "MAPPED",
                }
                for row in rows
            ],
        }

    def field_contract(self) -> list[dict[str, Any]]:
        with closing(self._ready()) as connection:
            return [
                {"field_path": row["field_path"], "group": row["field_group"], "field_name": row["field_name"]}
                for row in connection.execute(
                    "SELECT * FROM staging_corpus_field_contract ORDER BY position"
                )
            ]

    @staticmethod
    def _latest_audits(connection: sqlite3.Connection) -> dict[tuple[str, str], dict[str, Any]]:
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        fingerprints = {
            (kind, row[id_column]): row["fingerprint"]
            for kind, table, id_column in (
                ("CLAIM", "staging_corpus_claims", "claim_id"),
                ("MARKER", "staging_corpus_field_markers", "marker_id"),
                ("PAPER", "staging_corpus_papers", "paper_id"),
            )
            for row in connection.execute(f"SELECT {id_column}, fingerprint FROM {table}")
        }
        for row in connection.execute(
            "SELECT * FROM staging_corpus_audit_events ORDER BY julianday(audited_at), created_at, event_id"
        ):
            event = CorpusRepository._audit_event(row)
            event["current"] = event["target_fingerprint"] == fingerprints.get((row["target_kind"], row["target_id"]))
            latest[(row["target_kind"], row["target_id"])] = event
        return latest

    @staticmethod
    def _operational_states(
        claim_rows: list[sqlite3.Row], marker_rows: list[sqlite3.Row],
        coverage: dict[str, Any] | None, latest_audits: dict[tuple[str, str], dict[str, Any]],
        paper_id: str,
    ) -> dict[str, Any]:
        coverage = coverage or {}
        claim_ids = [row["claim_id"] for row in claim_rows]
        claim_audits = [latest_audits.get(("CLAIM", claim_id)) for claim_id in claim_ids]
        decisions = [event["decision"] for event in claim_audits if event and event["current"]]
        stale = sum(bool(event and not event["current"]) for event in claim_audits)
        verified = sum(decision == "VERIFIED" for decision in decisions)
        partial = sum(decision == "PARTIALLY_VERIFIED" for decision in decisions)
        imported_conflict = any(
            row["scientific_status"] == "CONFLICT"
            or str(json.loads(row["row_json"]).get("evidence_review") or "").startswith("CONFLICT_REVIEW")
            for row in claim_rows
        )
        has_conflict = imported_conflict or "CONFLICT" in decisions
        has_blocker = stale > 0 or any(decision in {"BLOCKED", "EXTRACTION_ERROR"} for decision in decisions)
        paper_audit = latest_audits.get(("PAPER", paper_id))
        completion_attested = bool(
            paper_audit and paper_audit["current"] and paper_audit["decision"] == "VERIFIED"
            and len(str(paper_audit.get("search_scope") or "").strip()) >= 30
        )
        if claim_ids and verified == len(claim_ids) and not marker_rows and not has_conflict and not has_blocker and completion_attested:
            verification_state = "FULLY_VERIFIED"
        elif verified or partial:
            verification_state = "PARTIALLY_VERIFIED"
        else:
            verification_state = "NOT_VERIFIED"
        conflict_blocker_state = (
            "CONFLICT" if has_conflict else "BLOCKED" if has_blocker else "CLEAR"
        )
        locatable = sum(
            any(json.loads(row["row_json"]).get(key) not in (None, "") for key in (
                "pdf_page", "source_section", "source_locator",
            ))
            for row in claim_rows
        )
        evidence_basis = str(coverage.get("evidence_basis") or "")
        scope_documented = coverage.get("review_scope_documented") == "YES"
        primary_source_review = "FULLTEXT" in evidence_basis or "CODE" in evidence_basis
        audit_candidate = bool(claim_rows) and scope_documented and primary_source_review and locatable > 0
        declared = str(coverage.get("coverage_level") or "")
        follow_up = str(coverage.get("follow_up") or "").strip()
        if not claim_rows:
            extraction_state = "NOT_EXTRACTED"
        elif audit_candidate:
            extraction_state = "READY_FOR_AUDIT"
        else:
            extraction_state = "PARTIAL"
        return {
            "extraction_completeness": {
                "state": extraction_state,
                "declared_coverage": declared or None,
                "claim_count": len(claim_rows),
                "locatable_claim_count": locatable,
                "review_scope_documented": scope_documented,
                "primary_source_review": primary_source_review,
                "follow_up": follow_up or None,
                "completion_candidate": completion_attested,
                "completion_blocker": None if completion_attested else (
                    "No documented field-by-field completeness review of the full paper, "
                    "supplements, and relevant code; the historical DETAILED label is insufficient."
                ),
            },
            "verification_state": verification_state,
            "conflict_blocker_state": conflict_blocker_state,
            "audit_candidate": audit_candidate,
            "audit_counts": {
                "claims": len(claim_ids), "reviewed": len(decisions),
                "verified": verified, "partially_verified": partial,
                "markers": len(marker_rows), "stale": stale,
            },
        }

    def list_papers(
        self, *, query: str | None = None, domain: str | None = None,
        review_stage: str | None = None, extraction_state: str | None = None,
        audit_state: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        with closing(self._ready()) as connection:
            claim_counts = {
                row["paper_id"]: row["n"] for row in connection.execute(
                    "SELECT paper_id, COUNT(*) AS n FROM staging_corpus_claims GROUP BY 1"
                )
            }
            rows = connection.execute("SELECT * FROM staging_corpus_papers ORDER BY paper_id").fetchall()
            latest_audits = self._latest_audits(connection)
            states: dict[str, dict[str, Any]] = {}
            for row in rows:
                paper_id = row["paper_id"]
                claim_rows = connection.execute(
                    "SELECT * FROM staging_corpus_claims WHERE paper_id = ?", (paper_id,)
                ).fetchall()
                marker_rows = connection.execute(
                    "SELECT * FROM staging_corpus_field_markers WHERE paper_id = ?", (paper_id,)
                ).fetchall()
                coverage_row = connection.execute(
                    """SELECT c.row_json FROM staging_corpus_paper_coverage c
                       JOIN staging_corpus_import_runs r ON r.id = c.import_run_id
                       WHERE c.paper_id = ? ORDER BY r.imported_at DESC LIMIT 1""",
                    (paper_id,),
                ).fetchone()
                coverage = json.loads(coverage_row["row_json"]) if coverage_row else None
                states[paper_id] = self._operational_states(
                    claim_rows, marker_rows, coverage, latest_audits, paper_id,
                )
        papers = [
            {**self._paper_summary(row, claim_counts.get(row["paper_id"], 0)), **states[row["paper_id"]]}
            for row in rows
        ]
        if query:
            needle = query.casefold()
            papers = [
                paper for paper in papers
                if needle in (paper["title"] or "").casefold() or needle in (paper["doi"] or "").casefold()
            ]
        if domain:
            papers = [paper for paper in papers if paper["domain"] == domain]
        if review_stage:
            papers = [paper for paper in papers if paper["review_stage"] == review_stage]
        if extraction_state:
            papers = [
                paper for paper in papers
                if paper["extraction_completeness"]["state"] == extraction_state
            ]
        if audit_state:
            papers = [paper for paper in papers if paper["verification_state"] == audit_state]
        return papers[offset: offset + limit], len(papers)

    @staticmethod
    def _paper_summary(row: sqlite3.Row, claim_count: int) -> dict[str, Any]:
        index = json.loads(row["index_json"])
        record = json.loads(row["record_json"])
        return {
            "paper_id": row["paper_id"], "title": index.get("title"), "year": index.get("year"),
            "doi": index.get("doi"), "domain": index.get("domain"), "source_url": index.get("source_url"),
            "review_stage": index.get("review_stage"), "source_edition": index.get("source_edition"),
            "record_kind": index.get("record_kind"),
            "scientific_extraction_status": index.get("scientific_extraction_status"),
            "scientific_audit_status": {
                "paper_index": index.get("scientific_audit_status"),
                "paper_records": record.get("scientific_audit_status"),
            },
            "detail_extraction_status": record.get("detail_extraction_status"),
            "claim_count": claim_count,
            "linked_paper_record_id": row["linked_paper_record_id"],
        }

    def get_paper(self, paper_id: str) -> dict[str, Any]:
        with closing(self._ready()) as connection:
            row = connection.execute(
                "SELECT * FROM staging_corpus_papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            if row is None:
                alias = connection.execute(
                    "SELECT paper_id FROM staging_corpus_paper_aliases WHERE alias_id = ?", (paper_id,)
                ).fetchone()
                if alias is not None:
                    row = connection.execute(
                        "SELECT * FROM staging_corpus_papers WHERE paper_id = ?", (alias["paper_id"],)
                    ).fetchone()
            if row is None:
                raise CorpusNotFoundError(f"staging paper {paper_id} was not found")
            raw_claim_rows = connection.execute(
                    "SELECT * FROM staging_corpus_claims WHERE paper_id = ? ORDER BY claim_id",
                    (row["paper_id"],),
                ).fetchall()
            latest_audits = self._latest_audits(connection)
            claims = {}
            for claim_row in raw_claim_rows:
                claim = self._claim(claim_row)
                audit = latest_audits.get(("CLAIM", claim_row["claim_id"]))
                claim["latest_audit"] = audit
                claim["verification_state"] = (
                    audit["decision"] if audit and audit["current"] else
                    "STALE_AUDIT" if audit else "NOT_VERIFIED"
                )
                claims[claim_row["claim_id"]] = claim
            contract = connection.execute(
                "SELECT * FROM staging_corpus_field_contract ORDER BY position"
            ).fetchall()
            aliases = [
                {"alias_id": item["alias_id"], "matched_on": item["matched_on"]}
                for item in connection.execute(
                    "SELECT * FROM staging_corpus_paper_aliases WHERE paper_id = ?", (row["paper_id"],)
                )
            ]
            markers: dict[str, list[dict[str, Any]]] = {}
            raw_marker_rows = connection.execute(
                "SELECT * FROM staging_corpus_field_markers WHERE paper_id = ? ORDER BY marker_id", (row["paper_id"],)
            ).fetchall()
            for item in raw_marker_rows:
                marker = self._marker(item)
                audit = latest_audits.get(("MARKER", item["marker_id"]))
                marker["latest_audit"] = audit
                marker["verification_state"] = (
                    audit["decision"] if audit and audit["current"] else
                    "STALE_AUDIT" if audit else "NOT_VERIFIED"
                )
                markers.setdefault(item["field_path"], []).append(marker)
            coverage = [
                {"source_name": item["source_name"], **json.loads(item["row_json"])}
                for item in connection.execute(
                    "SELECT * FROM staging_corpus_paper_coverage WHERE paper_id = ? ORDER BY source_name",
                    (row["paper_id"],),
                )
            ]
            latest_coverage_row = connection.execute(
                """SELECT c.row_json FROM staging_corpus_paper_coverage c
                   JOIN staging_corpus_import_runs r ON r.id = c.import_run_id
                   WHERE c.paper_id = ? ORDER BY r.imported_at DESC LIMIT 1""",
                (row["paper_id"],),
            ).fetchone()
            operational_states = self._operational_states(
                raw_claim_rows, raw_marker_rows,
                json.loads(latest_coverage_row["row_json"]) if latest_coverage_row else None,
                latest_audits, row["paper_id"],
            )
            paper_audits = [
                self._audit_event(item) for item in connection.execute(
                    "SELECT * FROM staging_corpus_audit_events WHERE target_kind = 'PAPER' AND target_id = ? "
                    "ORDER BY julianday(audited_at), created_at, event_id",
                    (row["paper_id"],),
                )
            ]
        record = json.loads(row["record_json"])
        slots = record.get("field_claim_ids", {})
        # Claims from a supplement workbook are not in the stored record's slots;
        # they are placed by their declared field_path, never re-interpreted.
        slotted = {claim_id for fields in slots.values() for ids in fields.values() for claim_id in ids}
        by_path: dict[str, list[str]] = {}
        for claim in claims.values():
            if claim["claim_id"] not in slotted:
                by_path.setdefault(claim["field_path"], []).append(claim["claim_id"])
        contract_paths = {definition["field_path"] for definition in contract}
        fields: list[dict[str, Any]] = []
        for definition in contract:
            claim_ids = [
                *slots.get(definition["field_group"], {}).get(definition["field_name"], []),
                *by_path.get(definition["field_path"], []),
            ]
            field_claims = [claims[claim_id] for claim_id in claim_ids if claim_id in claims]
            field_markers = markers.get(definition["field_path"], [])
            fields.append({
                "field_path": definition["field_path"], "group": definition["field_group"],
                "field_name": definition["field_name"],
                "status": self._field_status(field_claims, field_markers),
                "claim_ids": claim_ids, "claims": field_claims, "markers": field_markers,
            })
        experiments = sorted({claim["experiment_id"] for claim in claims.values() if claim["experiment_id"]})
        return {
            **self._paper_summary(row, len(claims)),
            **operational_states,
            "paper_audits": paper_audits,
            "tags": record.get("tags", []),
            "abstract_status": record.get("abstract_status"),
            "pdf_sha256": record.get("pdf_sha256"),
            "unpopulated_field_policy": record.get("unpopulated_field_policy"),
            "paper_index": json.loads(row["index_json"]),
            "aliases": aliases,
            "experiments": experiments,
            "fields": fields,
            "uncontracted_claims": [
                claims[claim_id] for path, ids in sorted(by_path.items())
                if path not in contract_paths for claim_id in ids
            ],
            "uncontracted_markers": [
                marker for path, items in sorted(markers.items()) if path not in contract_paths for marker in items
            ],
            "coverage": coverage,
            "populated_field_count": sum(1 for item in fields if item["claims"]),
            "not_extracted_field_count": sum(1 for item in fields if item["status"] == NOT_EXTRACTED),
            "import_run_id": row["import_run_id"],
        }

    @staticmethod
    def _field_status(claims: list[dict[str, Any]], markers: list[dict[str, Any]]) -> str:
        """A field's display status. Markers never become values.

        No claim and no marker, or only NOT_EXTRACTED markers: NOT_EXTRACTED
        (nobody found it; an empty slot never means the paper is silent). A
        NOT_REPORTED marker adds NOT_REPORTED_CANDIDATE, an unverified absence
        limited to the marker's scope. Beside an extracted claim both are shown
        (NOT_VERIFIED|NOT_REPORTED_CANDIDATE), not CONFLICT: the two usually
        cover different scopes (OAI-0010: fine-tuning time extracted, total
        training time not found), and CONFLICT is reserved for the paper
        disagreeing with itself.
        """
        reported_absent = any(marker["extraction_status"] == "NOT_REPORTED" for marker in markers)
        # A marker's own non-default status (EXTRACTION_ERROR, CONFLICT) stays visible.
        statuses = {claim["scientific_status"] for claim in claims} | {
            marker["scientific_status"] for marker in markers if marker["scientific_status"] != "NOT_VERIFIED"
        }
        if reported_absent:
            statuses.add(NOT_REPORTED_CANDIDATE)
        if not statuses:
            return NOT_EXTRACTED
        return "|".join(sorted(statuses))

    @staticmethod
    def _marker(row: sqlite3.Row) -> dict[str, Any]:
        source = json.loads(row["row_json"])
        return {
            "marker_id": row["marker_id"], "paper_id": row["paper_id"], "field_path": row["field_path"],
            "extraction_status": row["extraction_status"], "scientific_status": row["scientific_status"],
            "independent_audit": row["independent_audit"], "claim_type": source.get("claim_type"),
            # Section or scope text exactly as supplied; the extractor's own
            # statement of what was searched is usually in ``notes``.
            "section_or_scope": source.get("source_section"),
            "source_url": source.get("evidence_source_url"), "source_edition": source.get("source_edition"),
            "evidence_review": source.get("evidence_review"), "notes": source.get("notes"),
            "batch_id": source.get("batch_id"), "import_run_id": row["import_run_id"],
        }

    @staticmethod
    def _claim(row: sqlite3.Row) -> dict[str, Any]:
        source = json.loads(row["row_json"])
        return {
            "claim_id": row["claim_id"],
            "paper_id": row["paper_id"],
            "source_paper_id": source.get("paper_id"),
            "experiment_id": row["experiment_id"],
            "field_path": row["field_path"],
            "value": parse_claim_value(source.get("value")),
            "value_raw": source.get("value"),
            "subject_scope": source.get("subject_scope"),
            "claim_type": source.get("claim_type"),
            "unit": source.get("unit"),
            "extraction_status": source.get("extraction_status"),
            "extracted_on": source.get("extracted_on"),
            "batch_id": source.get("batch_id"),
            "scientific_status": row["scientific_status"],
            "independent_audit": row["independent_audit"],
            "evidence": {
                "source_url": source.get("evidence_source_url"),
                "source_doi": source.get("source_doi"),
                "source_edition": source.get("source_edition"),
                "section": source.get("source_section"),
                "locator": source.get("source_locator"),
                # Stored exactly as supplied; never synthesised or checked here.
                "verbatim_evidence": source.get("verbatim_evidence"),
                "pdf_page": source.get("pdf_page"),
                "evidence_review": source.get("evidence_review"),
            },
            "notes": source.get("notes"),
            "import_run_id": row["import_run_id"],
        }

    def list_claims(
        self, *, paper_id: str | None = None, field_path: str | None = None,
        experiment_id: str | None = None, limit: int = 200, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        if paper_id is not None:
            with closing(self._ready()) as connection:
                alias = connection.execute(
                    "SELECT paper_id FROM staging_corpus_paper_aliases WHERE alias_id = ?", (paper_id,)
                ).fetchone()
            if alias is not None:
                paper_id = alias["paper_id"]
        clauses, parameters = [], []
        for column, value in (("paper_id", paper_id), ("field_path", field_path), ("experiment_id", experiment_id)):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with closing(self._ready()) as connection:
            total = int(connection.execute(
                f"SELECT COUNT(*) AS n FROM staging_corpus_claims {where}", parameters
            ).fetchone()["n"])
            rows = connection.execute(
                f"SELECT * FROM staging_corpus_claims {where} ORDER BY claim_id LIMIT ? OFFSET ?",
                (*parameters, limit, offset),
            ).fetchall()
            latest = self._latest_audits(connection)
        claims = []
        for row in rows:
            claim = self._claim(row)
            audit = latest.get(("CLAIM", row["claim_id"]))
            claim["latest_audit"] = audit
            claim["verification_state"] = (
                audit["decision"] if audit and audit["current"] else
                "STALE_AUDIT" if audit else "NOT_VERIFIED"
            )
            claims.append(claim)
        return claims, total

    def get_claim(self, claim_id: str) -> dict[str, Any]:
        with closing(self._ready()) as connection:
            row = connection.execute(
                "SELECT * FROM staging_corpus_claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()
            audits = connection.execute(
                "SELECT * FROM staging_corpus_audit_events WHERE target_kind = 'CLAIM' AND target_id = ? "
                "ORDER BY julianday(audited_at), created_at, event_id",
                (claim_id,),
            ).fetchall()
        if row is None:
            raise CorpusNotFoundError(f"staging claim {claim_id} was not found")
        claim = self._claim(row)
        claim["audits"] = [
            {**self._audit_event(item), "current": item["target_fingerprint"] == row["fingerprint"]}
            for item in audits
        ]
        claim["latest_audit"] = claim["audits"][-1] if claim["audits"] else None
        if claim["latest_audit"]:
            claim["latest_audit"]["current"] = claim["latest_audit"]["target_fingerprint"] == row["fingerprint"]
        claim["verification_state"] = (
            claim["latest_audit"]["decision"] if claim["latest_audit"] and claim["latest_audit"]["current"] else
            "STALE_AUDIT" if claim["latest_audit"] else "NOT_VERIFIED"
        )
        return claim

    def research_gaps(self) -> list[dict[str, Any]]:
        with closing(self._ready()) as connection:
            rows = connection.execute("SELECT * FROM staging_corpus_research_gaps ORDER BY gap_key").fetchall()
        gaps = []
        for row in rows:
            source = json.loads(row["row_json"])
            gaps.append({
                "candidate_topic": source.get("candidate_topic"),
                "testable_question": source.get("testable_question"),
                "basis_paper_ids": [
                    item.strip() for item in str(source.get("basis_paper_ids") or "").split(";") if item.strip()
                ],
                "status": source.get("status"),
                "qualification": source.get("qualification"),
                # A research-gap candidate is a team hypothesis or an AI
                # interpretation, as the package labels it; never an
                # author-reported limitation and never established novelty.
                "provenance_type": (
                    "AI_INTERPRETATION" if str(source.get("status") or "").startswith("AI_INTERPRETATION")
                    else "TEAM_NOTE"
                ),
                "realigned_from": source.get("realigned_from"),
                "import_run_id": row["import_run_id"],
            })
        return gaps

    def documents(self) -> dict[str, str]:
        with closing(self._ready()) as connection:
            return {row["name"]: row["text"] for row in connection.execute("SELECT * FROM staging_corpus_documents")}
