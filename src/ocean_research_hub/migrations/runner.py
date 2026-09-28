"""Small migration runner used by the local SQLite adapter."""

from __future__ import annotations

import json
import re
import sqlite3
from importlib.resources import files
from uuid import NAMESPACE_URL, uuid5


_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_ARXIV_PATTERN = re.compile(
    r"^(?:\d{4}\.\d{4,5}|[a-z][a-z.\-]+/\d{7})(?:v\d+)?$", re.IGNORECASE
)


def _normalize_doi(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    for prefix in (
        "https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
        "http://dx.doi.org/", "doi:",
    ):
        if normalized.lower().startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    normalized = normalized.strip().lower()
    return normalized if _DOI_PATTERN.fullmatch(normalized) else None


def _normalize_arxiv(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    for prefix in ("https://arxiv.org/abs/", "http://arxiv.org/abs/", "arxiv:"):
        if normalized.lower().startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    normalized = normalized.strip().lower()
    if not _ARXIV_PATTERN.fullmatch(normalized):
        return None
    return re.sub(r"v\d+$", "", normalized)


def _backfill_paper_identifiers(connection: sqlite3.Connection) -> None:
    """Index identities from databases created before normalized identifiers existed.

    This runs after every migration check so installations that already recorded
    the original 0002 migration also receive the compatibility backfill.
    """
    tables = {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if not {"papers", "paper_identifiers"}.issubset(tables):
        return
    for row in connection.execute(
        "SELECT id, identity_key, doi, record_json FROM papers ORDER BY created_at, id"
    ).fetchall():
        paper_id, identity_key, stored_doi, record_json = row
        try:
            record = json.loads(record_json)
        except (TypeError, ValueError):
            record = {}
        bibliography = record.get("paper", {}) if isinstance(record, dict) else {}

        def record_value(name: str) -> object:
            field = bibliography.get(name, {}) if isinstance(bibliography, dict) else {}
            return field.get("value") if isinstance(field, dict) else None

        identity_doi = identity_key[4:] if identity_key.startswith("doi:") else None
        identity_arxiv = identity_key[6:] if identity_key.startswith("arxiv:") else None
        identifiers = {
            "DOI": _normalize_doi(stored_doi or record_value("doi") or identity_doi),
            "ARXIV": _normalize_arxiv(record_value("arxiv") or identity_arxiv),
        }
        for identifier_type, normalized_value in identifiers.items():
            if normalized_value is None:
                continue
            existing = connection.execute(
                """SELECT paper_id FROM paper_identifiers
                   WHERE identifier_type = ? AND normalized_value = ?""",
                (identifier_type, normalized_value),
            ).fetchone()
            if existing is not None and existing[0] != paper_id:
                raise sqlite3.IntegrityError(
                    f"legacy {identifier_type} identity belongs to multiple papers"
                )
            identifier_id = str(uuid5(
                NAMESPACE_URL,
                f"ocean-research-hub:paper-identifier:{identifier_type}:{normalized_value}",
            ))
            connection.execute(
                """INSERT INTO paper_identifiers (
                       id, paper_id, identifier_type, normalized_value, created_at
                   ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(paper_id, identifier_type, normalized_value) DO NOTHING""",
                (identifier_id, paper_id, identifier_type, normalized_value),
            )


def apply_migrations(connection: sqlite3.Connection) -> None:
    """Apply packaged migrations exactly once, in lexical order."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    applied = {
        row[0] for row in connection.execute("SELECT version FROM schema_migrations")
    }
    migration_root = files("ocean_research_hub.migrations")
    migrations = sorted(
        item for item in migration_root.iterdir()
        if item.name.endswith(".sql") and item.name[:4].isdigit()
    )
    for migration in migrations:
        version = migration.name.removesuffix(".sql")
        if version in applied:
            continue
        sql = migration.read_text(encoding="utf-8")
        # executescript commits any open transaction, so transaction control is
        # included in the script passed to SQLite.
        safe_version = version.replace("'", "''")
        connection.executescript(
            f"BEGIN IMMEDIATE;\n{sql}\n"
            f"INSERT INTO schema_migrations(version) VALUES ('{safe_version}');\nCOMMIT;"
        )
    _backfill_paper_identifiers(connection)
