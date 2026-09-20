"""Persistence interface and SQLite development adapter."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from ocean_research_hub.schemas.paper_record import PaperRecord

from .errors import IngestionConflictError, PaperNotFoundError, PersistenceError
from .models import PaperWorkflowStatus, StoredPaper


WORKFLOW_ORDER = {
    PaperWorkflowStatus.INGESTED: 0,
    PaperWorkflowStatus.PARSED: 1,
    PaperWorkflowStatus.EXTRACTED: 2,
    PaperWorkflowStatus.SCIENTIFIC_AUDIT: 3,
    PaperWorkflowStatus.PARTIAL: 4,
    PaperWorkflowStatus.VERIFIED: 5,
    PaperWorkflowStatus.REJECTED: 5,
}


class PaperRepository(Protocol):
    def initialize(self) -> None: ...

    def create_or_get(
        self,
        *,
        identity_key: str,
        doi: str | None,
        record: PaperRecord,
        workflow_status: PaperWorkflowStatus,
        warnings: list[str],
    ) -> tuple[StoredPaper, bool]: ...

    def get(self, paper_id: str) -> StoredPaper: ...

    def find_by_identity(self, identity_key: str) -> StoredPaper | None: ...

    def add_domains(self, paper_id: str, domains: list[str]) -> StoredPaper: ...

    def list_papers(
        self, *, limit: int, offset: int, domain: str | None = None,
    ) -> tuple[list[StoredPaper], int]: ...

    def domain_counts(self) -> dict[str, int]: ...

    def list_all_papers(self) -> tuple[list[StoredPaper], int, int]: ...


class SqlitePaperRepository:
    """Persist canonical records atomically without weakening schema validation."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS papers (
                        id TEXT PRIMARY KEY,
                        identity_key TEXT NOT NULL UNIQUE,
                        doi TEXT,
                        fingerprint TEXT NOT NULL,
                        workflow_status TEXT NOT NULL,
                        record_json TEXT NOT NULL,
                        warnings_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE UNIQUE INDEX IF NOT EXISTS papers_unique_doi
                        ON papers(doi) WHERE doi IS NOT NULL;
                    """
                )
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(papers)")}
                if "domains_json" not in columns:
                    connection.execute(
                        "ALTER TABLE papers ADD COLUMN domains_json TEXT NOT NULL DEFAULT '[]'"
                    )
        except (OSError, sqlite3.Error) as exc:
            raise PersistenceError("paper database initialization failed") from exc

    def create_or_get(
        self,
        *,
        identity_key: str,
        doi: str | None,
        record: PaperRecord,
        workflow_status: PaperWorkflowStatus,
        warnings: list[str],
        domains: list[str] | None = None,
    ) -> tuple[StoredPaper, bool]:
        record_json = json.dumps(
            record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        fingerprint = sha256(record_json.encode("utf-8")).hexdigest()
        now = datetime.now(UTC).isoformat()
        paper_id = str(uuid4())
        domains = list(dict.fromkeys(domains or []))

        try:
            with self._connect() as connection:
                try:
                    connection.execute(
                        """
                        INSERT INTO papers (
                            id, identity_key, doi, fingerprint, workflow_status,
                            record_json, warnings_json, created_at, updated_at, domains_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            paper_id,
                            identity_key,
                            doi,
                            fingerprint,
                            workflow_status.value,
                            record_json,
                            json.dumps(warnings),
                            now,
                            now,
                            json.dumps(domains),
                        ),
                    )
                except sqlite3.IntegrityError:
                    row = connection.execute(
                        "SELECT * FROM papers WHERE identity_key = ? OR doi = ?",
                        (identity_key, doi),
                    ).fetchone()
                    if row is None:
                        raise
                    existing = self._from_row(row)
                    if row["fingerprint"] != fingerprint:
                        # A metadata-only record holds no scientific claims, so
                        # replacing it with a full PDF extraction loses nothing.
                        # Anything else (including conflicting metadata for the
                        # same DOI) is refused rather than silently overwritten.
                        upgrade = (
                            existing.workflow_status is PaperWorkflowStatus.INGESTED
                            and WORKFLOW_ORDER[workflow_status] > WORKFLOW_ORDER[PaperWorkflowStatus.INGESTED]
                        )
                        if not upgrade:
                            raise IngestionConflictError(
                                "this paper identity already exists with different content; "
                                "the stored scientific record was not overwritten"
                            )
                        connection.execute(
                            """
                            UPDATE papers
                            SET record_json = ?, fingerprint = ?, workflow_status = ?,
                                warnings_json = ?, domains_json = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (
                                record_json, fingerprint, workflow_status.value,
                                json.dumps(list(dict.fromkeys([*existing.warnings, *warnings]))),
                                json.dumps(list(dict.fromkeys([*existing.domains, *domains]))),
                                now, existing.id,
                            ),
                        )
                        row = connection.execute(
                            "SELECT * FROM papers WHERE id = ?", (existing.id,)
                        ).fetchone()
                        return self._from_row(row), False
                    merged_warnings = list(dict.fromkeys([*existing.warnings, *warnings]))
                    merged_domains = list(dict.fromkeys([*existing.domains, *domains]))
                    merged_status = max(
                        (existing.workflow_status, workflow_status),
                        key=WORKFLOW_ORDER.__getitem__,
                    )
                    if (
                        merged_warnings != existing.warnings
                        or merged_domains != existing.domains
                        or merged_status is not existing.workflow_status
                    ):
                        connection.execute(
                            """
                            UPDATE papers
                            SET warnings_json = ?, workflow_status = ?, updated_at = ?,
                                domains_json = ?
                            WHERE id = ?
                            """,
                            (
                                json.dumps(merged_warnings),
                                merged_status.value,
                                now,
                                json.dumps(merged_domains),
                                existing.id,
                            ),
                        )
                        row = connection.execute(
                            "SELECT * FROM papers WHERE id = ?", (existing.id,)
                        ).fetchone()
                        if row is None:
                            raise PersistenceError("updated paper could not be read back")
                    return self._from_row(row), False

                row = connection.execute(
                    "SELECT * FROM papers WHERE id = ?", (paper_id,)
                ).fetchone()
                if row is None:
                    raise PersistenceError("inserted paper could not be read back")
                return self._from_row(row), True
        except IngestionConflictError:
            raise
        except (sqlite3.Error, ValueError) as exc:
            raise PersistenceError("paper database write failed") from exc

    def get(self, paper_id: str) -> StoredPaper:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM papers WHERE id = ?", (paper_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError("paper database read failed") from exc
        if row is None:
            raise PaperNotFoundError(f"paper {paper_id} was not found")
        try:
            return self._from_row(row)
        except (ValueError, KeyError, TypeError) as exc:
            raise PersistenceError("stored paper could not be validated") from exc

    def find_by_identity(self, identity_key: str) -> StoredPaper | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM papers WHERE identity_key = ?", (identity_key,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError("paper database read failed") from exc
        if row is None:
            return None
        try:
            return self._from_row(row)
        except (ValueError, KeyError, TypeError) as exc:
            raise PersistenceError("stored paper could not be validated") from exc

    def add_domains(self, paper_id: str, domains: list[str]) -> StoredPaper:
        paper = self.get(paper_id)
        merged = list(dict.fromkeys([*paper.domains, *domains]))
        if merged == paper.domains:
            return paper
        try:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE papers SET domains_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(merged), datetime.now(UTC).isoformat(), paper_id),
                )
        except sqlite3.Error as exc:
            raise PersistenceError("paper database write failed") from exc
        return self.get(paper_id)

    def list_papers(
        self, *, limit: int, offset: int, domain: str | None = None,
    ) -> tuple[list[StoredPaper], int]:
        """Most-recently-updated first, optionally restricted to one domain."""
        # Domain ids are slugs (no quotes), so matching the quoted id inside
        # the JSON array text is exact.
        where, params = ("WHERE domains_json LIKE ?", [f'%"{domain}"%']) if domain else ("", [])
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"SELECT * FROM papers {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (*params, limit, offset),
                ).fetchall()
                total_row = connection.execute(
                    f"SELECT COUNT(*) AS count FROM papers {where}", params
                ).fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError("paper database list failed") from exc
        assert total_row is not None
        try:
            papers = [self._from_row(row) for row in rows]
        except (ValueError, KeyError, TypeError) as exc:
            raise PersistenceError("stored paper could not be validated") from exc
        return papers, int(total_row["count"])

    def domain_counts(self) -> dict[str, int]:
        try:
            with self._connect() as connection:
                rows = connection.execute("SELECT domains_json FROM papers").fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError("paper database read failed") from exc
        counts: dict[str, int] = {}
        for row in rows:
            for domain in json.loads(row["domains_json"]):
                counts[domain] = counts.get(domain, 0) + 1
        return counts

    def list_all_papers(self) -> tuple[list[StoredPaper], int, int]:
        """Return the complete corpus for server-side aggregation.

        Unlike the paginated public listing, this maintenance-oriented read has
        no presentation cap. Invalid persisted rows are counted rather than
        making a valid remainder look unavailable; callers can surface a
        truthful PARTIAL state while repository I/O failures still raise.
        """
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM papers ORDER BY updated_at DESC"
                ).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError("paper database read failed") from exc

        papers: list[StoredPaper] = []
        invalid = 0
        for row in rows:
            try:
                papers.append(self._from_row(row))
            except (ValueError, KeyError, TypeError):
                invalid += 1
        return papers, len(rows), invalid

    def count(self) -> int:
        """Expose a deterministic integration-test and maintenance probe."""
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM papers"
                ).fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError("paper database count failed") from exc
        assert row is not None
        return int(row["count"])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> StoredPaper:
        return StoredPaper(
            id=row["id"],
            identity_key=row["identity_key"],
            doi=row["doi"],
            workflow_status=row["workflow_status"],
            record=PaperRecord.model_validate_json(row["record_json"]),
            warnings=json.loads(row["warnings_json"]),
            domains=json.loads(row["domains_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
