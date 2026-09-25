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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .workbook import (
    SUPPLEMENT, StagingWorkbook, WorkbookValidationError, normalize_doi, normalize_title,
    parse_claim_value,
)

# States that mean an independent reviewer has attested the row. A row in one
# of these states is never overwritten by an import. Staging workbooks cannot
# introduce them (see ``workbook.REFUSED_CLAIM_STATUSES``); they can only
# arise from an audit recorded after import.
ATTESTED_STATES = frozenset({
    "VERIFIED", "PARTIALLY_VERIFIED", "AUDITED", "INDEPENDENTLY_AUDITED", "AUDIT_PASSED",
})
UNATTESTED_AUDIT_MARKERS = frozenset({
    None, "", "PENDING_INDEPENDENT_AUDIT", "PENDING_PDF_AUDIT", "NOT_AUDITED",
})

NOT_EXTRACTED = "NOT_EXTRACTED"

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
CREATE TABLE IF NOT EXISTS staging_corpus_paper_coverage (
    coverage_key TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES staging_corpus_papers(paper_id),
    source_name TEXT NOT NULL,
    row_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_corpus_documents (
    name TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    import_run_id TEXT NOT NULL
);
"""


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
    aliases_created: list[dict[str, str]] = field(default_factory=list)
    linked_paper_records: int = 0
    absent_from_source: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, Any]:
        return {
            "papers": self.papers.as_dict(), "claims": self.claims.as_dict(),
            "field_contract": self.field_contract.as_dict(),
            "research_gaps": self.research_gaps.as_dict(), "documents": self.documents.as_dict(),
            "coverage": self.coverage.as_dict(),
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

    def import_workbook(self, book: StagingWorkbook) -> ImportReport:
        """Import a validated workbook in one transaction. All or nothing."""
        report = ImportReport(str(uuid4()), book.source_name, book.sha256)
        report.warnings.extend(book.warnings)
        now = datetime.now(UTC).isoformat()
        connection = self._ready()
        try:
            with connection:
                if book.kind == SUPPLEMENT:
                    self._check_supplement(connection, book, report)
                else:
                    self._import_contract(connection, book, report)
                paper_map = self._import_papers(connection, book, report, now)
                self._import_claims(connection, book, report, paper_map, now)
                self._import_gaps(connection, book, report, now)
                self._import_documents(connection, book, report)
                self._import_coverage(connection, book, report, paper_map)
                connection.execute(
                    "INSERT INTO staging_corpus_import_runs VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        report.run_id, book.source_name, book.sha256, now,
                        _canonical(report.counts()), _canonical(report.warnings),
                    ),
                )
        finally:
            connection.close()
        return report

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
        if row is None:
            columns = [key_column, "fingerprint", *values]
            connection.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                (key, fingerprint, *values.values()),
            )
            counts.created += 1
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
        updates = {key: value for key, value in values.items() if key != "created_at"}
        connection.execute(
            f"UPDATE {table} SET fingerprint = ?, {', '.join(f'{column} = ?' for column in updates)} "
            f"WHERE {key_column} = ?",
            (fingerprint, *updates.values(), key),
        )
        counts.updated += 1
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
                report.field_contract,
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
            canonical_id, _ = self._resolve_paper(
                connection, row["paper_id"], normalize_doi(row.get("doi")), normalize_title(row.get("title")),
                None if row.get("year") is None else str(row.get("year")),
            )
            if canonical_id is None:
                errors.append(
                    f"supplement paper {row['paper_id']} is not in the stored corpus; a supplement "
                    f"carries no PAPER_RECORDS and cannot introduce a paper"
                )
        if errors:
            raise WorkbookValidationError(errors)
        outside = sorted(
            f"{row['claim_id']} ({row['field_path']})" for row in book.claims if row["field_path"] not in contract
        )
        if outside:
            report.warnings.append(
                f"claim(s) whose field_path is outside the stored FIELD_CONTRACT are preserved verbatim, "
                f"served as uncontracted_claims and mapped to no field: {outside}"
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
                    "index_json": _canonical(index_row), "record_json": _canonical(record),
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
        for row in book.claims:
            claim_id = row["claim_id"]
            existing = connection.execute(
                "SELECT scientific_status, independent_audit FROM staging_corpus_claims WHERE claim_id = ?",
                (claim_id,),
            ).fetchone()
            protected = existing is not None and is_attested(
                existing["scientific_status"], existing["independent_audit"],
            )
            self._upsert(
                connection, "staging_corpus_claims", "claim_id", claim_id, _fingerprint(row),
                {
                    "paper_id": paper_map[row["paper_id"]], "experiment_id": row.get("experiment_id"),
                    "field_path": row["field_path"], "scientific_status": row["scientific_status"],
                    "independent_audit": row.get("independent_audit"), "row_json": _canonical(row),
                    "import_run_id": report.run_id, "created_at": now, "updated_at": now,
                },
                report.claims, protected=protected, report=report,
            )
        incoming = {row["claim_id"] for row in book.claims}
        stored = {item["claim_id"] for item in connection.execute("SELECT claim_id FROM staging_corpus_claims")}
        absent = sorted(stored - incoming)
        if absent:
            report.absent_from_source["claims"] = absent

    def _import_gaps(
        self, connection: sqlite3.Connection, book: StagingWorkbook, report: ImportReport, now: str,
    ) -> None:
        for row in book.research_gaps:
            key = normalize_title(row["candidate_topic"]) or ""
            self._upsert(
                connection, "staging_corpus_research_gaps", "gap_key", key, _fingerprint(row),
                {
                    "row_json": _canonical(row), "import_run_id": report.run_id,
                    "created_at": now, "updated_at": now,
                },
                report.research_gaps,
            )

    def _import_documents(self, connection: sqlite3.Connection, book: StagingWorkbook, report: ImportReport) -> None:
        documents = {**book.documents, "START_HERE": _canonical(book.start_here)}
        if book.kind == SUPPLEMENT:
            # Keyed by workbook so a supplement never replaces the base package's documents.
            documents = {
                f"{book.source_name}:START_HERE": _canonical(book.start_here),
                f"{book.source_name}:NEW_DETAILED_PAPERS": _canonical(book.new_detailed_papers),
            }
        for name, text in documents.items():
            self._upsert(
                connection, "staging_corpus_documents", "name", name, _fingerprint(text),
                {"text": text, "import_run_id": report.run_id},
                report.documents,
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
                report.coverage,
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

    def field_contract(self) -> list[dict[str, Any]]:
        with closing(self._ready()) as connection:
            return [
                {"field_path": row["field_path"], "group": row["field_group"], "field_name": row["field_name"]}
                for row in connection.execute(
                    "SELECT * FROM staging_corpus_field_contract ORDER BY position"
                )
            ]

    def list_papers(
        self, *, query: str | None = None, domain: str | None = None,
        review_stage: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        with closing(self._ready()) as connection:
            claim_counts = {
                row["paper_id"]: row["n"] for row in connection.execute(
                    "SELECT paper_id, COUNT(*) AS n FROM staging_corpus_claims GROUP BY 1"
                )
            }
            rows = connection.execute("SELECT * FROM staging_corpus_papers ORDER BY paper_id").fetchall()
        papers = [self._paper_summary(row, claim_counts.get(row["paper_id"], 0)) for row in rows]
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
            claims = {
                claim["claim_id"]: self._claim(claim)
                for claim in connection.execute(
                    "SELECT * FROM staging_corpus_claims WHERE paper_id = ? ORDER BY claim_id",
                    (row["paper_id"],),
                )
            }
            contract = connection.execute(
                "SELECT * FROM staging_corpus_field_contract ORDER BY position"
            ).fetchall()
            aliases = [
                {"alias_id": item["alias_id"], "matched_on": item["matched_on"]}
                for item in connection.execute(
                    "SELECT * FROM staging_corpus_paper_aliases WHERE paper_id = ?", (row["paper_id"],)
                )
            ]
            coverage = [
                {"source_name": item["source_name"], **json.loads(item["row_json"])}
                for item in connection.execute(
                    "SELECT * FROM staging_corpus_paper_coverage WHERE paper_id = ? ORDER BY source_name",
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
            statuses = sorted({claim["scientific_status"] for claim in field_claims})
            fields.append({
                "field_path": definition["field_path"], "group": definition["field_group"],
                "field_name": definition["field_name"],
                # An empty slot means nobody looked, not that the paper is silent.
                "status": NOT_EXTRACTED if not field_claims else "|".join(statuses),
                "claim_ids": claim_ids, "claims": field_claims,
            })
        experiments = sorted({claim["experiment_id"] for claim in claims.values() if claim["experiment_id"]})
        return {
            **self._paper_summary(row, len(claims)),
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
            "coverage": coverage,
            "populated_field_count": sum(1 for item in fields if item["claims"]),
            "not_extracted_field_count": sum(1 for item in fields if not item["claims"]),
            "import_run_id": row["import_run_id"],
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
            "scientific_status": row["scientific_status"],
            "independent_audit": row["independent_audit"],
            "evidence": {
                "source_url": source.get("evidence_source_url"),
                "source_doi": source.get("source_doi"),
                "source_edition": source.get("source_edition"),
                "section": source.get("source_section"),
                "locator": source.get("source_locator"),
                # Stored exactly as supplied; never synthesised. Null in the
                # staging package because no PDF alignment was performed.
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
        return [self._claim(row) for row in rows], total

    def get_claim(self, claim_id: str) -> dict[str, Any]:
        with closing(self._ready()) as connection:
            row = connection.execute(
                "SELECT * FROM staging_corpus_claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()
        if row is None:
            raise CorpusNotFoundError(f"staging claim {claim_id} was not found")
        return self._claim(row)

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
                # A research-gap candidate is a team hypothesis, never an
                # author-reported limitation and never established novelty.
                "provenance_type": "TEAM_NOTE",
                "import_run_id": row["import_run_id"],
            })
        return gaps

    def documents(self) -> dict[str, str]:
        with closing(self._ready()) as connection:
            return {row["name"]: row["text"] for row in connection.execute("SELECT * FROM staging_corpus_documents")}
