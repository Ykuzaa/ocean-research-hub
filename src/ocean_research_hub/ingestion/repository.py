"""Persistence interface and SQLite development adapter."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel

from ocean_research_hub.schemas.paper_record import EvidenceField, PaperRecord, VerificationStatus
from ocean_research_hub.migrations.runner import apply_migrations
from ocean_research_hub.research.repository import SqliteResearchRepositoryMixin

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
        identifiers: dict[str, str] | None = None,
    ) -> tuple[StoredPaper, bool]: ...

    def get(self, paper_id: str) -> StoredPaper: ...

    def list_all_papers(self) -> tuple[list[StoredPaper], int, int]: ...

    def discard_created(self, paper_id: str) -> None: ...

class SqlitePaperRepository(SqliteResearchRepositoryMixin):
    """Persist canonical records atomically without weakening schema validation."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                apply_migrations(connection)
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
        identifiers: dict[str, str] | None = None,
    ) -> tuple[StoredPaper, bool]:
        record_json = json.dumps(
            record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        fingerprint = sha256(record_json.encode("utf-8")).hexdigest()
        now = datetime.now(UTC).isoformat()
        paper_id = str(uuid4())
        normalized_identifiers = dict(identifiers or {})
        if doi is not None:
            normalized_identifiers["DOI"] = doi

        try:
            with self._connect() as connection:
                # Serialize identity resolution with insertion so concurrent
                # DOI/arXiv/content retries cannot pass the pre-insert check.
                connection.execute("BEGIN IMMEDIATE")
                row = self._find_by_identifiers(connection, normalized_identifiers)
                if row is None:
                    row = connection.execute(
                        "SELECT * FROM papers WHERE identity_key = ? OR doi = ?",
                        (identity_key, doi),
                    ).fetchone()
                if row is None:
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
                    self._insert_identifiers(
                        connection, paper_id, normalized_identifiers, now
                    )
                    row = connection.execute(
                        "SELECT * FROM papers WHERE id = ?", (paper_id,)
                    ).fetchone()
                    if row is None:
                        raise PersistenceError("inserted paper could not be read back")
                    return self._from_row(row), True

                self._insert_identifiers(
                    connection, row["id"], normalized_identifiers, now
                )
                if row["fingerprint"] != fingerprint:
                    existing = self._from_row(row)
                    if self._is_controlled_upgrade(existing, record, workflow_status):
                        record = self._merge_upgrade_record(existing.record, record)
                        record_json = json.dumps(
                            record.model_dump(mode="json"),
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        fingerprint = sha256(record_json.encode("utf-8")).hexdigest()
                        merged_warnings = list(dict.fromkeys([*existing.warnings, *warnings]))
                        connection.execute(
                            """UPDATE papers
                               SET fingerprint = ?, workflow_status = ?, record_json = ?,
                                   warnings_json = ?, updated_at = ?
                               WHERE id = ?""",
                            (
                                fingerprint, workflow_status.value, record_json,
                                json.dumps(merged_warnings), now, existing.id,
                            ),
                        )
                        updated = connection.execute(
                            "SELECT * FROM papers WHERE id = ?", (existing.id,)
                        ).fetchone()
                        if updated is None:
                            raise PersistenceError("upgraded paper could not be read back")
                        return self._from_row(updated), False
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
        except IngestionConflictError:
            raise
        except (sqlite3.Error, ValueError) as exc:
            raise PersistenceError("paper database write failed") from exc

    @staticmethod
    def _find_by_identifiers(
        connection: sqlite3.Connection, identifiers: dict[str, str]
    ) -> sqlite3.Row | None:
        paper_ids: set[str] = set()
        for identifier_type, value in identifiers.items():
            row = connection.execute(
                """SELECT paper_id FROM paper_identifiers
                   WHERE identifier_type = ? AND normalized_value = ?""",
                (identifier_type, value),
            ).fetchone()
            if row is not None:
                paper_ids.add(row["paper_id"])
        if len(paper_ids) > 1:
            raise IngestionConflictError(
                "provided identifiers resolve to different stored papers"
            )
        if not paper_ids:
            return None
        return connection.execute(
            "SELECT * FROM papers WHERE id = ?", (paper_ids.pop(),)
        ).fetchone()

    @staticmethod
    def _insert_identifiers(
        connection: sqlite3.Connection, paper_id: str,
        identifiers: dict[str, str], now: str,
    ) -> None:
        for identifier_type, value in identifiers.items():
            try:
                connection.execute(
                    """INSERT INTO paper_identifiers (
                        id, paper_id, identifier_type, normalized_value, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(paper_id, identifier_type, normalized_value) DO NOTHING""",
                    (str(uuid4()), paper_id, identifier_type, value, now),
                )
            except sqlite3.IntegrityError as exc:
                raise IngestionConflictError(
                    f"{identifier_type} identifier already belongs to another paper"
                ) from exc

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

    def discard_created(self, paper_id: str) -> None:
        """Compensate a failed first-ingest projection without touching prior papers."""
        try:
            with self._connect() as connection:
                connection.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
        except sqlite3.Error as exc:
            raise PersistenceError("failed ingest could not be rolled back") from exc

    def snapshot_for_ingest(
        self, identity_key: str, doi: str | None, identifiers: dict[str, str]
    ) -> dict | None:
        """Capture an existing canonical row before a two-store projection upgrade."""
        with self._connect() as connection:
            row = self._find_by_identifiers(connection, identifiers)
            if row is None:
                row = connection.execute(
                    "SELECT * FROM papers WHERE identity_key = ? OR doi = ?",
                    (identity_key, doi),
                ).fetchone()
            if row is None:
                return None
            paper_id = row["id"]
            return {
                "paper": dict(row),
                "identifier_ids": [item["id"] for item in connection.execute(
                    "SELECT id FROM paper_identifiers WHERE paper_id = ?", (paper_id,)
                )],
                "edition_ids": [item["id"] for item in connection.execute(
                    "SELECT id FROM source_editions WHERE paper_id = ?", (paper_id,)
                )],
            }

    def restore_failed_upgrade(self, snapshot: dict, expected_fingerprint: str) -> None:
        """Compensate only our unchanged upgrade; never clobber a concurrent edit."""
        old = snapshot["paper"]
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT fingerprint FROM papers WHERE id = ?", (old["id"],)
            ).fetchone()
            if current is None or current["fingerprint"] != expected_fingerprint:
                raise PersistenceError("failed upgrade changed concurrently; manual recovery required")
            connection.execute(
                """UPDATE papers SET identity_key = ?, doi = ?, fingerprint = ?,
                   workflow_status = ?, record_json = ?, warnings_json = ?, updated_at = ?
                   WHERE id = ?""",
                (old["identity_key"], old["doi"], old["fingerprint"],
                 old["workflow_status"], old["record_json"], old["warnings_json"],
                 old["updated_at"], old["id"]),
            )
            for table, retained in (
                ("paper_identifiers", snapshot["identifier_ids"]),
                ("source_editions", snapshot["edition_ids"]),
            ):
                for item in connection.execute(
                    f"SELECT id FROM {table} WHERE paper_id = ?", (old["id"],)
                ):
                    if item["id"] not in retained:
                        connection.execute(f"DELETE FROM {table} WHERE id = ?", (item["id"],))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _is_controlled_upgrade(
        existing: StoredPaper, incoming: PaperRecord,
        incoming_status: PaperWorkflowStatus,
    ) -> bool:
        if (
            existing.workflow_status is not PaperWorkflowStatus.INGESTED
            or incoming_status is not PaperWorkflowStatus.EXTRACTED
        ):
            return False

        def fields(model: BaseModel):
            for name in type(model).model_fields:
                value = getattr(model, name)
                if isinstance(value, EvidenceField):
                    yield value
                elif isinstance(value, BaseModel):
                    yield from fields(value)

        non_bibliographic_sections = (
            existing.record.scientific_framing, existing.record.data,
            existing.record.architecture, existing.record.training,
            existing.record.objective, existing.record.evaluation,
            existing.record.results, existing.record.limitations,
        )
        if any(
            field.status is not VerificationStatus.NOT_REPORTED
            for section in non_bibliographic_sections for field in fields(section)
        ):
            return False
        return any(
            evidence.is_primary_author_source
            for field in fields(incoming)
            for evidence in (field.source, *field.sources)
            if evidence.is_supplied
        )

    @staticmethod
    def _merge_upgrade_record(existing: PaperRecord, incoming: PaperRecord) -> PaperRecord:
        """Fill primary extraction gaps from metadata without overriding it arbitrarily."""
        merged = incoming.model_copy(deep=True)

        def merge_models(old: BaseModel, new: BaseModel, path: str = "") -> None:
            for name in type(old).model_fields:
                old_value = getattr(old, name)
                new_value = getattr(new, name)
                field_path = f"{path}.{name}" if path else name
                if isinstance(old_value, EvidenceField) and isinstance(new_value, EvidenceField):
                    if new_value.status is VerificationStatus.NOT_REPORTED:
                        setattr(new, name, old_value.model_copy(deep=True))
                    elif old_value.status is VerificationStatus.NOT_REPORTED:
                        continue
                    elif old_value.model_dump(mode="json") == new_value.model_dump(mode="json"):
                        continue
                    elif field_path.startswith("paper.") and any(
                        evidence.is_primary_author_source
                        for evidence in (new_value.source, *new_value.sources)
                        if evidence.is_supplied
                    ):
                        # Primary-paper bibliography supersedes discovery metadata;
                        # the metadata claim remains inspectable in its source edition.
                        continue
                    else:
                        raise IngestionConflictError(
                            f"controlled upgrade cannot replace existing claim {field_path}"
                        )
                elif isinstance(old_value, BaseModel) and isinstance(new_value, BaseModel):
                    merge_models(old_value, new_value, field_path)

        merge_models(existing, merged)
        return PaperRecord.model_validate(merged.model_dump(mode="json"))

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
