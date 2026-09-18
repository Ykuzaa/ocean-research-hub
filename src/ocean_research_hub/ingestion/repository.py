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

    def list_papers(self, *, limit: int, offset: int) -> tuple[list[StoredPaper], int]: ...


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
    ) -> tuple[StoredPaper, bool]:
        record_json = json.dumps(
            record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        fingerprint = sha256(record_json.encode("utf-8")).hexdigest()
        now = datetime.now(UTC).isoformat()
        paper_id = str(uuid4())

        try:
            with self._connect() as connection:
                try:
                    connection.execute(
                        """
                        INSERT INTO papers (
                            id, identity_key, doi, fingerprint, workflow_status,
                            record_json, warnings_json, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        ),
                    )
                except sqlite3.IntegrityError:
                    row = connection.execute(
                        "SELECT * FROM papers WHERE identity_key = ? OR doi = ?",
                        (identity_key, doi),
                    ).fetchone()
                    if row is None:
                        raise
                    if row["fingerprint"] != fingerprint:
                        raise IngestionConflictError(
                            "this paper identity already exists with different content; "
                            "the stored scientific record was not overwritten"
                        )
                    existing = self._from_row(row)
                    merged_warnings = list(dict.fromkeys([*existing.warnings, *warnings]))
                    merged_status = max(
                        (existing.workflow_status, workflow_status),
                        key=WORKFLOW_ORDER.__getitem__,
                    )
                    if (
                        merged_warnings != existing.warnings
                        or merged_status is not existing.workflow_status
                    ):
                        connection.execute(
                            """
                            UPDATE papers
                            SET warnings_json = ?, workflow_status = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (
                                json.dumps(merged_warnings),
                                merged_status.value,
                                now,
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

    def list_papers(self, *, limit: int, offset: int) -> tuple[list[StoredPaper], int]:
        """Most-recently-updated first, for a simple list/browse view."""
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM papers ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
                total_row = connection.execute("SELECT COUNT(*) AS count FROM papers").fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError("paper database list failed") from exc
        assert total_row is not None
        try:
            papers = [self._from_row(row) for row in rows]
        except (ValueError, KeyError, TypeError) as exc:
            raise PersistenceError("stored paper could not be validated") from exc
        return papers, int(total_row["count"])

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
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
