"""SQLite repository for normalized, evidence-backed research intelligence."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel

from ocean_research_hub.ingestion.errors import (
    IngestionConflictError,
    PaperNotFoundError,
    ResearchEntityNotFoundError,
)
from ocean_research_hub.schemas.paper_record import (
    EvidenceField,
    PaperRecord,
    ProvenanceType,
    SourceEvidence,
)

from .models import (
    EntityDetail,
    EntityFieldState,
    EntityListResponse,
    EntityMention,
    EntityRelationship,
    EntityRelationshipCreate,
    EntitySummary,
    EntityType,
    EvidenceReference,
    HyperparameterClaim,
    ReportedResult,
    ResearchPaper,
    ResearchStatement,
    SourceEdition,
    SourceEditionCreate,
    TrainingConfiguration,
)


ENTITY_FIELDS: tuple[tuple[str, EntityType, str], ...] = (
    ("scientific_framing.domain", EntityType.DOMAIN, "STUDIES_DOMAIN"),
    ("scientific_framing.task_type", EntityType.TASK, "ADDRESSES_TASK"),
    ("scientific_framing.region", EntityType.REGION, "STUDIES_REGION"),
    ("architecture.named_models", EntityType.MODEL, "USES_MODEL"),
    ("architecture.family", EntityType.ARCHITECTURE, "USES_ARCHITECTURE"),
    ("data.datasets", EntityType.DATASET, "USES_DATASET"),
    ("data.variables", EntityType.VARIABLE, "USES_VARIABLE"),
    ("data.units", EntityType.UNIT, "REPORTS_UNIT"),
    ("training.optimizer", EntityType.OPTIMIZER, "USES_OPTIMIZER"),
    ("objective.primary_loss", EntityType.LOSS, "OPTIMIZES_LOSS"),
    ("objective.auxiliary_losses", EntityType.LOSS, "OPTIMIZES_LOSS"),
    ("objective.physics_constraints", EntityType.LOSS, "USES_PHYSICAL_CONSTRAINT"),
    ("objective.spectral_losses", EntityType.LOSS, "OPTIMIZES_LOSS"),
    ("objective.gradient_front_losses", EntityType.LOSS, "OPTIMIZES_LOSS"),
    ("objective.probabilistic_losses", EntityType.LOSS, "OPTIMIZES_LOSS"),
    ("evaluation.metrics", EntityType.METRIC, "EVALUATED_WITH"),
)

class ResearchRepository(Protocol):
    def sync_research_record(
        self,
        paper_id: str,
        record: PaperRecord,
        source_edition: SourceEditionCreate | None = None,
        *,
        include_missing_bibliography: bool = True,
    ) -> None: ...

    def add_source_edition(self, paper_id: str, edition: SourceEditionCreate) -> SourceEdition: ...

    def list_entities(
        self, *, entity_type: EntityType | None, query: str | None, limit: int, offset: int
    ) -> EntityListResponse: ...

    def get_entity(self, entity_id: str) -> EntityDetail: ...

    def get_research_paper(self, paper_id: str) -> ResearchPaper: ...

    def add_entity_relationship(
        self, paper_id: str, relationship: EntityRelationshipCreate
    ) -> EntityRelationship: ...


def normalize_entity_key(value: str) -> str:
    """Conservative deduplication: Unicode and whitespace only.

    Case is scientific data for values such as units, and aliases are not
    guessed (for example, SST is not silently merged with sea-surface
    temperature).
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).strip())


def _stable_id(namespace: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"ocean-research-hub:{namespace}:{key}"))


def _claim_key(*parts: object) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _field(record: PaperRecord, path: str) -> EvidenceField[object]:
    value: object = record
    for part in path.split("."):
        value = getattr(value, part)
    assert isinstance(value, EvidenceField)
    return value


def _source_wording(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _evidence_records(field: EvidenceField[object]) -> list[SourceEvidence]:
    return [record for record in (field.source, *field.sources) if record.is_supplied]


def _evidence_fields(model: BaseModel, path: str = ""):
    """Yield every evidence-bearing leaf without dropping nested scientific fields."""
    for name in type(model).model_fields:
        value = getattr(model, name)
        field_path = f"{path}.{name}" if path else name
        if isinstance(value, EvidenceField):
            yield field_path, value
        elif isinstance(value, BaseModel):
            yield from _evidence_fields(value, field_path)


def _json_key(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class SqliteResearchRepositoryMixin:
    """Research methods mixed into the existing SQLite paper repository."""

    database_path: object

    def _connect(self) -> sqlite3.Connection: ...

    def add_source_edition(self, paper_id: str, edition: SourceEditionCreate) -> SourceEdition:
        now = datetime.now(UTC).isoformat()
        edition_id = _stable_id("source-edition", f"{paper_id}:{edition.edition_key}")
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM papers WHERE id = ?", (paper_id,)).fetchone() is None:
                raise PaperNotFoundError(f"paper {paper_id} was not found")
            existing = connection.execute(
                "SELECT * FROM source_editions WHERE paper_id = ? AND edition_key = ?",
                (paper_id, edition.edition_key),
            ).fetchone()
            incoming_identity = (
                edition.source_type.value, str(edition.uri) if edition.uri else None,
                edition.content_hash, edition.version_label, int(edition.is_primary),
            )
            if existing is not None:
                stored_identity = (
                    existing["source_type"], existing["uri"], existing["content_hash"],
                    existing["version_label"], existing["is_primary"],
                )
                if stored_identity != incoming_identity:
                    raise IngestionConflictError(
                        "source edition key already exists with different identity; "
                        "use a distinct edition_key for a new version"
                    )
                return self._source_edition_from_row(existing)
            try:
                connection.execute(
                """
                INSERT INTO source_editions (
                    id, paper_id, edition_key, source_type, uri, content_hash,
                    version_label, is_primary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edition_id, paper_id, edition.edition_key, edition.source_type.value,
                    str(edition.uri) if edition.uri else None, edition.content_hash,
                    edition.version_label, int(edition.is_primary), now,
                ),
                )
            except sqlite3.IntegrityError as exc:
                raise IngestionConflictError(
                    "source edition content hash is already assigned to another paper"
                ) from exc
            row = connection.execute("SELECT * FROM source_editions WHERE id = ?", (edition_id,)).fetchone()
        assert row is not None
        return self._source_edition_from_row(row)

    def sync_research_record(
        self,
        paper_id: str,
        record: PaperRecord,
        source_edition: SourceEditionCreate | None = None,
        *,
        include_missing_bibliography: bool = True,
    ) -> None:
        stored_edition = self.add_source_edition(paper_id, source_edition) if source_edition else None
        edition_id = stored_edition.id if stored_edition else None
        edition_key = stored_edition.edition_key if stored_edition else None
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            self._delete_edition_projection(connection, paper_id, edition_id)

            # The generic state ledger covers every canonical field, including
            # nested preprocessing, split, architecture, objective, evaluation,
            # availability, and reproducibility claims. Specialized tables below
            # are query indexes, not replacements for the lossless field states.
            for path, field in _evidence_fields(record):
                if (
                    not include_missing_bibliography
                    and path.startswith("paper.")
                    and field.status.value == "NOT_REPORTED"
                ):
                    continue
                self._store_entity_field_state(
                    connection, paper_id, edition_id, edition_key,
                    path, field, now,
                )

            for path, entity_type, relationship in ENTITY_FIELDS:
                field = _field(record, path)
                self._store_entity_field(
                    connection, paper_id, edition_id, edition_key, path,
                    entity_type, relationship, field, now
                )

            self._store_training(connection, paper_id, edition_id, edition_key, record, now)
            self._store_results(connection, paper_id, edition_id, edition_key, record, now)
            self._store_statements(connection, paper_id, edition_id, edition_key, record, now)

    @staticmethod
    def _edition_scope(edition_id: str | None) -> tuple[str, tuple[object, ...]]:
        if edition_id is None:
            return "source_edition_id IS NULL", ()
        return "source_edition_id = ?", (edition_id,)

    def _delete_edition_projection(
        self, connection: sqlite3.Connection, paper_id: str, edition_id: str | None
    ) -> None:
        scope, scope_parameters = self._edition_scope(edition_id)

        def claim_ids(table: str) -> list[str]:
            return [
                row["id"] for row in connection.execute(
                    f"SELECT id FROM {table} WHERE paper_id = ? AND {scope}",
                    (paper_id, *scope_parameters),
                ).fetchall()
            ]

        field_state_ids = claim_ids("entity_field_states")
        result_ids = claim_ids("reported_results")
        statement_ids = claim_ids("research_statements")
        configuration_ids = claim_ids("training_configurations")
        hyperparameter_ids: list[str] = []
        for configuration_id in configuration_ids:
            hyperparameter_ids.extend(
                row["id"] for row in connection.execute(
                    "SELECT id FROM hyperparameters WHERE training_configuration_id = ?",
                    (configuration_id,),
                ).fetchall()
            )
        for claim_table, ids in (
            ("entity_field_states", field_state_ids),
            ("hyperparameters", hyperparameter_ids),
            ("reported_results", result_ids),
            ("research_statements", statement_ids),
        ):
            for claim_id in ids:
                connection.execute(
                    "DELETE FROM claim_evidence WHERE claim_table = ? AND claim_id = ?",
                    (claim_table, claim_id),
                )
        for table in (
            "entity_mentions", "entity_field_states", "training_configurations",
            "reported_results", "research_statements",
        ):
            connection.execute(
                f"DELETE FROM {table} WHERE paper_id = ? AND {scope}",
                (paper_id, *scope_parameters),
            )

    def _store_entity_field_state(
        self, connection: sqlite3.Connection, paper_id: str, edition_id: str | None,
        edition_key: str | None, path: str, field: EvidenceField[object], now: str,
    ) -> None:
        edition_scope = edition_id or "unversioned"
        claim_key = _claim_key(path, field.value, field.conflict_values, field.status.value)
        claim_id = _stable_id("entity-field-state", f"{paper_id}:{edition_scope}:{path}")
        serialized = field.model_dump(mode="json")
        connection.execute(
            """INSERT INTO entity_field_states (
                id, paper_id, source_edition_id, field_path, value_json,
                conflict_values_json, status, provenance_type, confidence,
                verified_by, verified_at, claim_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                claim_id, paper_id, edition_id, path,
                json.dumps(serialized["value"], ensure_ascii=False)
                if serialized["value"] is not None else None,
                json.dumps(serialized["conflict_values"], ensure_ascii=False), field.status.value,
                field.provenance_type.value, field.confidence, field.verified_by,
                field.verified_at.isoformat() if field.verified_at else None, claim_key, now,
            ),
        )
        self._insert_evidence(
            connection, "claim_evidence", "claim_id", claim_id, field,
            paper_id, edition_id, edition_key, "entity_field_states"
        )

    def _store_entity_field(
        self, connection: sqlite3.Connection, paper_id: str, edition_id: str | None,
        edition_key: str | None, path: str, entity_type: EntityType, relationship: str,
        field: EvidenceField[object], now: str,
    ) -> None:
        if (
            field.status.value == "EXTRACTION_ERROR"
            or field.provenance_type not in {
                ProvenanceType.AUTHOR_REPORTED_FACT,
                ProvenanceType.AUTHOR_REPORTED_LIMITATION,
            }
        ):
            return
        alternatives: list[tuple[object, int | None]]
        if field.status.value == "CONFLICT":
            alternatives = [(item, index) for index, item in enumerate(field.conflict_values)]
        elif field.value is None:
            alternatives = []
        else:
            alternatives = [(field.value, None)]

        flattened: list[tuple[object, int | None, object | None]] = []
        for value, alternative_index in alternatives:
            if isinstance(value, list):
                flattened.extend((item, alternative_index, value) for item in value)
            else:
                flattened.append((value, alternative_index, value))

        for value, alternative_index, claimed_alternative in flattened:
            if not isinstance(value, str) or not value.strip():
                continue
            normalized_key = normalize_entity_key(value)
            entity_key = f"{entity_type.value}:{normalized_key}"
            entity_id = _stable_id("entity", entity_key)
            connection.execute(
                """
                INSERT INTO research_entities (
                    id, entity_type, normalized_key, canonical_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, normalized_key) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (entity_id, entity_type.value, normalized_key, value.strip(), now, now),
            )
            claim_key = _claim_key(path, entity_type.value, normalized_key, alternative_index)
            mention_id = _stable_id(
                "mention", f"{paper_id}:{edition_id or 'unversioned'}:{claim_key}"
            )
            connection.execute(
                """
                INSERT INTO entity_mentions (
                    id, paper_id, source_edition_id, entity_id, relationship_type,
                    field_path, source_wording, status, provenance_type, confidence,
                    verified_by, verified_at, alternative_index, claim_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mention_id, paper_id, edition_id, entity_id, relationship, path, value.strip(),
                    field.status.value, field.provenance_type.value, field.confidence,
                    field.verified_by, field.verified_at.isoformat() if field.verified_at else None,
                    alternative_index, claim_key, now,
                ),
            )
            self._insert_evidence(
                connection, "mention_evidence", "mention_id", mention_id, field,
                paper_id, edition_id, edition_key,
                evidence_records=(
                    [
                        evidence for evidence in _evidence_records(field)
                        if evidence.claimed_value is not None
                        and _json_key(evidence.claimed_value) == _json_key(claimed_alternative)
                    ]
                    if field.status.value == "CONFLICT"
                    else None
                ),
            )

    def _store_training(
        self, connection: sqlite3.Connection, paper_id: str, edition_id: str | None,
        edition_key: str | None, record: PaperRecord, now: str,
    ) -> None:
        configuration_key = "paper-default"
        configuration_id = _stable_id(
            "training", f"{paper_id}:{edition_id or 'unversioned'}:{configuration_key}"
        )
        connection.execute(
            """INSERT INTO training_configurations
               (id, paper_id, source_edition_id, label, configuration_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (configuration_id, paper_id, edition_id, "Reported training configuration", configuration_key, now),
        )
        for name in type(record.training).model_fields:
            field = getattr(record.training, name)
            assert isinstance(field, EvidenceField)
            path = f"training.{name}"
            value = field.conflict_values if field.status.value == "CONFLICT" else field.value
            claim_key = _claim_key(path, value, field.status.value)
            claim_id = _stable_id("hyperparameter", f"{configuration_id}:{claim_key}")
            connection.execute(
                """INSERT INTO hyperparameters (
                    id, training_configuration_id, name, normalized_value_json,
                    original_wording, field_path, status, provenance_type,
                    confidence, verified_by, verified_at, claim_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    claim_id, configuration_id, name,
                    json.dumps(value, ensure_ascii=False) if value is not None else None,
                    self._best_wording(field), path, field.status.value,
                    field.provenance_type.value, field.confidence, field.verified_by,
                    field.verified_at.isoformat() if field.verified_at else None, claim_key,
                ),
            )
            self._insert_evidence(
                connection, "claim_evidence", "claim_id", claim_id, field,
                paper_id, edition_id, edition_key, "hyperparameters"
            )

    def _store_results(
        self, connection: sqlite3.Connection, paper_id: str, edition_id: str | None,
        edition_key: str | None, record: PaperRecord, now: str,
    ) -> None:
        for name in type(record.results).model_fields:
            field = getattr(record.results, name)
            assert isinstance(field, EvidenceField)
            path = f"results.{name}"
            values: list[object | None]
            if field.status.value == "CONFLICT":
                values = list(field.conflict_values)
            elif isinstance(field.value, list):
                values = list(field.value) or [None]
            else:
                values = [field.value]
            for index, value in enumerate(values):
                claim_key = _claim_key(path, index, value, field.status.value)
                claim_id = _stable_id(
                    "reported-result", f"{paper_id}:{edition_id or 'unversioned'}:{claim_key}"
                )
                connection.execute(
                    """INSERT INTO reported_results (
                        id, paper_id, source_edition_id, normalized_value_json,
                        original_wording, field_path, status, provenance_type,
                        confidence, verified_by, verified_at, claim_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        claim_id, paper_id, edition_id,
                        json.dumps(value, ensure_ascii=False) if value is not None else None,
                        _source_wording(value) if value is not None else self._best_wording(field),
                        path, field.status.value, field.provenance_type.value,
                        field.confidence, field.verified_by,
                        field.verified_at.isoformat() if field.verified_at else None, claim_key,
                    ),
                )
                self._insert_evidence(
                    connection, "claim_evidence", "claim_id", claim_id, field,
                    paper_id, edition_id, edition_key, "reported_results",
                    evidence_records=(
                        [
                            evidence for evidence in _evidence_records(field)
                            if evidence.claimed_value is not None
                            and _json_key(evidence.claimed_value) == _json_key(value)
                        ]
                        if field.status.value == "CONFLICT"
                        else None
                    ),
                )

    def _store_statements(
        self, connection: sqlite3.Connection, paper_id: str, edition_id: str | None,
        edition_key: str | None, record: PaperRecord, now: str,
    ) -> None:
        for name in type(record.limitations).model_fields:
            field = getattr(record.limitations, name)
            assert isinstance(field, EvidenceField)
            path = f"limitations.{name}"
            statement_type = "FUTURE_WORK" if name == "future_work" else "LIMITATION"
            values: list[object | None]
            if field.status.value == "CONFLICT":
                values = list(field.conflict_values)
            elif isinstance(field.value, list):
                values = list(field.value) or [None]
            else:
                values = [field.value]
            for index, value in enumerate(values):
                claim_key = _claim_key(path, index, value, field.status.value)
                claim_id = _stable_id(
                    "research-statement", f"{paper_id}:{edition_id or 'unversioned'}:{claim_key}"
                )
                connection.execute(
                    """INSERT INTO research_statements (
                        id, paper_id, source_edition_id, statement_type,
                        original_wording, field_path, status, provenance_type,
                        confidence, verified_by, verified_at, claim_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        claim_id, paper_id, edition_id, statement_type,
                        _source_wording(value) if value is not None else self._best_wording(field),
                        path, field.status.value, field.provenance_type.value,
                        field.confidence, field.verified_by,
                        field.verified_at.isoformat() if field.verified_at else None, claim_key,
                    ),
                )
                self._insert_evidence(
                    connection, "claim_evidence", "claim_id", claim_id, field,
                    paper_id, edition_id, edition_key, "research_statements",
                    evidence_records=(
                        [
                            evidence for evidence in _evidence_records(field)
                            if evidence.claimed_value is not None
                            and _json_key(evidence.claimed_value) == _json_key(value)
                        ]
                        if field.status.value == "CONFLICT"
                        else None
                    ),
                )

    @staticmethod
    def _best_wording(field: EvidenceField[object]) -> str | None:
        records = _evidence_records(field)
        return next((record.evidence for record in records if record.evidence), None)

    def _insert_evidence(
        self, connection: sqlite3.Connection, table: str, foreign_key: str, claim_id: str,
        field: EvidenceField[object], paper_id: str, fallback_edition_id: str | None,
        fallback_edition_key: str | None, claim_table: str | None = None,
        evidence_records: list[SourceEvidence] | None = None,
    ) -> None:
        records = _evidence_records(field) if evidence_records is None else evidence_records
        for order, evidence in enumerate(records):
            evidence_edition_id = fallback_edition_id
            evidence_edition_key = evidence.source_edition_key or fallback_edition_key
            if evidence.source_edition_key is not None:
                edition_row = connection.execute(
                    "SELECT id FROM source_editions WHERE paper_id = ? AND edition_key = ?",
                    (paper_id, evidence.source_edition_key),
                ).fetchone()
                if edition_row is None:
                    raise IngestionConflictError(
                        f"evidence references unknown source edition {evidence.source_edition_key}"
                    )
                evidence_edition_id = edition_row["id"]
            values = (
                str(uuid4()), claim_id, order, evidence.section, evidence.page,
                evidence.locator, evidence.evidence,
                evidence.origin.value if evidence.origin else None,
                evidence_edition_id, evidence_edition_key,
                json.dumps(evidence.claimed_value, ensure_ascii=False) if evidence.claimed_value is not None else None,
            )
            if table == "mention_evidence":
                connection.execute(
                    """INSERT INTO mention_evidence (
                        id, mention_id, evidence_order, section, page, locator,
                        evidence_text, origin, source_edition_id, source_edition_key,
                        claimed_value_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
            else:
                connection.execute(
                    """INSERT INTO claim_evidence (
                        id, claim_id, evidence_order, section, page, locator,
                        evidence_text, origin, source_edition_id, source_edition_key,
                        claimed_value_json, claim_table
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (*values, claim_table),
                )

    def list_entities(
        self, *, entity_type: EntityType | None = None, query: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> EntityListResponse:
        clauses: list[str] = []
        parameters: list[object] = []
        if entity_type is not None:
            clauses.append("e.entity_type = ?")
            parameters.append(entity_type.value)
        if query:
            clauses.append("(e.canonical_name LIKE ? ESCAPE '\\' OR e.normalized_key LIKE ? ESCAPE '\\')")
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.extend((f"%{escaped}%", f"%{normalize_entity_key(escaped)}%"))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            total_row = connection.execute(
                f"SELECT COUNT(*) AS count FROM research_entities e {where}", parameters
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT e.*, COUNT(DISTINCT m.paper_id) AS paper_count,
                       COUNT(m.id) AS mention_count
                FROM research_entities e
                LEFT JOIN entity_mentions m ON m.entity_id = e.id
                {where}
                GROUP BY e.id
                ORDER BY e.canonical_name COLLATE NOCASE, e.id
                LIMIT ? OFFSET ?
                """,
                (*parameters, limit, offset),
            ).fetchall()
        return EntityListResponse(
            items=[self._entity_from_row(row) for row in rows],
            total=int(total_row["count"] if total_row else 0), limit=limit, offset=offset,
        )

    def add_entity_relationship(
        self, paper_id: str, relationship: EntityRelationshipCreate
    ) -> EntityRelationship:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM papers WHERE id = ?", (paper_id,)).fetchone() is None:
                raise PaperNotFoundError(f"paper {paper_id} was not found")
            for entity_id in (relationship.subject_entity_id, relationship.object_entity_id):
                if connection.execute(
                    "SELECT 1 FROM research_entities WHERE id = ?", (entity_id,)
                ).fetchone() is None:
                    raise ResearchEntityNotFoundError(
                        f"research entity {entity_id} was not found"
                    )
            edition_id = None
            if relationship.source_edition_key:
                edition_row = connection.execute(
                    "SELECT id FROM source_editions WHERE paper_id = ? AND edition_key = ?",
                    (paper_id, relationship.source_edition_key),
                ).fetchone()
                if edition_row is None:
                    raise IngestionConflictError(
                        f"relationship references unknown source edition {relationship.source_edition_key}"
                    )
                edition_id = edition_row["id"]
            claim_key = _claim_key(
                relationship.subject_entity_id, relationship.predicate,
                relationship.object_entity_id, relationship.source_wording,
                relationship.status.value,
            )
            relationship_id = _stable_id(
                "entity-relationship",
                f"{paper_id}:{edition_id or 'unversioned'}:{claim_key}",
            )
            existing = connection.execute(
                "SELECT * FROM entity_relationships WHERE id = ?", (relationship_id,)
            ).fetchone()
            if existing is not None:
                stored = self._relationship_from_row(connection, existing)
                incoming_identity = relationship.model_dump(mode="json", exclude={"evidence"})
                stored_identity = stored.model_dump(
                    mode="json",
                    exclude={"id", "paper_id", "source_edition_id", "evidence"},
                )
                incoming_identity["evidence"] = [
                    {
                        **item.model_dump(mode="json", exclude={"source_edition_id"}),
                        "source_edition_key": (
                            item.source_edition_key or relationship.source_edition_key
                        ),
                    }
                    for item in relationship.evidence
                ]
                stored_identity["evidence"] = [
                    item.model_dump(mode="json", exclude={"source_edition_id"})
                    for item in stored.evidence
                ]
                if stored_identity != incoming_identity:
                    raise IngestionConflictError(
                        "entity relationship already exists with different evidence or audit metadata"
                    )
            else:
                connection.execute(
                    """INSERT INTO entity_relationships (
                        id, paper_id, source_edition_id, subject_entity_id, predicate,
                        object_entity_id, source_wording, status, provenance_type,
                        confidence, verified_by, verified_at, claim_key, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        relationship_id, paper_id, edition_id,
                        relationship.subject_entity_id, relationship.predicate,
                        relationship.object_entity_id, relationship.source_wording,
                        relationship.status.value, relationship.provenance_type.value,
                        relationship.confidence, relationship.verified_by,
                        relationship.verified_at.isoformat() if relationship.verified_at else None,
                        claim_key, now,
                    ),
                )
                for order, evidence in enumerate(relationship.evidence):
                    evidence_edition_id = edition_id
                    evidence_edition_key = evidence.source_edition_key or relationship.source_edition_key
                    if evidence.source_edition_key:
                        evidence_row = connection.execute(
                            "SELECT id FROM source_editions WHERE paper_id = ? AND edition_key = ?",
                            (paper_id, evidence.source_edition_key),
                        ).fetchone()
                        if evidence_row is None:
                            raise IngestionConflictError(
                                f"relationship evidence references unknown source edition {evidence.source_edition_key}"
                            )
                        evidence_edition_id = evidence_row["id"]
                    connection.execute(
                        """INSERT INTO relationship_evidence (
                            id, relationship_id, evidence_order, section, page, locator,
                            evidence_text, origin, source_edition_id, source_edition_key
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            str(uuid4()), relationship_id, order, evidence.section, evidence.page,
                            evidence.locator, evidence.evidence,
                            evidence.origin.value if evidence.origin else None,
                            evidence_edition_id, evidence_edition_key,
                        ),
                    )
            row = connection.execute(
                "SELECT * FROM entity_relationships WHERE id = ?", (relationship_id,)
            ).fetchone()
            assert row is not None
            return self._relationship_from_row(connection, row)

    def get_entity(self, entity_id: str) -> EntityDetail:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT e.*, COUNT(DISTINCT m.paper_id) AS paper_count,
                          COUNT(m.id) AS mention_count
                   FROM research_entities e LEFT JOIN entity_mentions m ON m.entity_id = e.id
                   WHERE e.id = ? GROUP BY e.id""",
                (entity_id,),
            ).fetchone()
            if row is None:
                raise ResearchEntityNotFoundError(f"research entity {entity_id} was not found")
            mention_rows = connection.execute(
                "SELECT * FROM entity_mentions WHERE entity_id = ? ORDER BY paper_id, field_path, id",
                (entity_id,),
            ).fetchall()
            mentions = [self._mention_from_row(connection, mention) for mention in mention_rows]
        return EntityDetail(entity=self._entity_from_row(row), mentions=mentions)

    def get_research_paper(self, paper_id: str) -> ResearchPaper:
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM papers WHERE id = ?", (paper_id,)).fetchone() is None:
                raise PaperNotFoundError(f"paper {paper_id} was not found")
            editions = [
                self._source_edition_from_row(row) for row in connection.execute(
                    "SELECT * FROM source_editions WHERE paper_id = ? ORDER BY created_at, id", (paper_id,)
                ).fetchall()
            ]
            mentions = [
                self._mention_from_row(connection, row) for row in connection.execute(
                    "SELECT * FROM entity_mentions WHERE paper_id = ? ORDER BY field_path, id", (paper_id,)
                ).fetchall()
            ]
            field_states = [
                self._field_state_from_row(connection, row) for row in connection.execute(
                    "SELECT * FROM entity_field_states WHERE paper_id = ? ORDER BY field_path, id",
                    (paper_id,),
                ).fetchall()
            ]
            configurations: list[TrainingConfiguration] = []
            for row in connection.execute(
                "SELECT * FROM training_configurations WHERE paper_id = ? ORDER BY created_at, id", (paper_id,)
            ).fetchall():
                claims = [self._hyperparameter_from_row(connection, item) for item in connection.execute(
                    "SELECT * FROM hyperparameters WHERE training_configuration_id = ? ORDER BY field_path, id",
                    (row["id"],),
                ).fetchall()]
                configurations.append(TrainingConfiguration(
                    id=row["id"], label=row["label"], source_edition_id=row["source_edition_id"],
                    hyperparameters=claims,
                ))
            results = [self._result_from_row(connection, row) for row in connection.execute(
                "SELECT * FROM reported_results WHERE paper_id = ? ORDER BY field_path, id", (paper_id,)
            ).fetchall()]
            statements = [self._statement_from_row(connection, row) for row in connection.execute(
                "SELECT * FROM research_statements WHERE paper_id = ? ORDER BY field_path, id", (paper_id,)
            ).fetchall()]
            relationships = [
                self._relationship_from_row(connection, row) for row in connection.execute(
                    "SELECT * FROM entity_relationships WHERE paper_id = ? ORDER BY predicate, id",
                    (paper_id,),
                ).fetchall()
            ]
        return ResearchPaper(
            paper_id=paper_id, source_editions=editions, entity_field_states=field_states,
            entity_mentions=mentions,
            entity_relationships=relationships,
            training_configurations=configurations, reported_results=results, statements=statements,
        )

    @staticmethod
    def _entity_from_row(row: sqlite3.Row) -> EntitySummary:
        return EntitySummary(
            id=row["id"], entity_type=row["entity_type"], normalized_key=row["normalized_key"],
            canonical_name=row["canonical_name"], description=row["description"],
            paper_count=row["paper_count"], mention_count=row["mention_count"],
        )

    def _mention_from_row(self, connection: sqlite3.Connection, row: sqlite3.Row) -> EntityMention:
        return EntityMention(
            id=row["id"], paper_id=row["paper_id"], source_edition_id=row["source_edition_id"],
            entity_id=row["entity_id"], relationship_type=row["relationship_type"],
            field_path=row["field_path"], source_wording=row["source_wording"], status=row["status"],
            provenance_type=row["provenance_type"], confidence=row["confidence"],
            verified_by=row["verified_by"], verified_at=row["verified_at"],
            alternative_index=row["alternative_index"],
            evidence=self._read_evidence(connection, "mention_evidence", "mention_id", row["id"]),
        )

    def _field_state_from_row(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> EntityFieldState:
        return EntityFieldState(
            id=row["id"], paper_id=row["paper_id"],
            source_edition_id=row["source_edition_id"], field_path=row["field_path"],
            value=self._json(row["value_json"]),
            conflict_values=self._json(row["conflict_values_json"]) or [],
            status=row["status"], provenance_type=row["provenance_type"],
            confidence=row["confidence"],
            verified_by=row["verified_by"], verified_at=row["verified_at"],
            evidence=self._read_evidence(
                connection, "claim_evidence", "claim_id", row["id"], "entity_field_states"
            ),
        )

    def _hyperparameter_from_row(self, connection: sqlite3.Connection, row: sqlite3.Row) -> HyperparameterClaim:
        return HyperparameterClaim(
            id=row["id"], name=row["name"], value=self._json(row["normalized_value_json"]),
            original_wording=row["original_wording"], field_path=row["field_path"],
            status=row["status"], provenance_type=row["provenance_type"], confidence=row["confidence"],
            verified_by=row["verified_by"], verified_at=row["verified_at"],
            evidence=self._read_evidence(connection, "claim_evidence", "claim_id", row["id"], "hyperparameters"),
        )

    def _result_from_row(self, connection: sqlite3.Connection, row: sqlite3.Row) -> ReportedResult:
        return ReportedResult(
            id=row["id"], source_edition_id=row["source_edition_id"],
            metric_entity_id=row["metric_entity_id"], dataset_entity_id=row["dataset_entity_id"],
            variable_entity_id=row["variable_entity_id"], value=self._json(row["normalized_value_json"]),
            original_wording=row["original_wording"], field_path=row["field_path"], status=row["status"],
            provenance_type=row["provenance_type"], confidence=row["confidence"],
            verified_by=row["verified_by"], verified_at=row["verified_at"],
            evidence=self._read_evidence(connection, "claim_evidence", "claim_id", row["id"], "reported_results"),
        )

    def _statement_from_row(self, connection: sqlite3.Connection, row: sqlite3.Row) -> ResearchStatement:
        return ResearchStatement(
            id=row["id"], statement_type=row["statement_type"], source_edition_id=row["source_edition_id"],
            taxonomy_entity_id=row["taxonomy_entity_id"], original_wording=row["original_wording"],
            field_path=row["field_path"], status=row["status"], provenance_type=row["provenance_type"],
            confidence=row["confidence"],
            verified_by=row["verified_by"], verified_at=row["verified_at"],
            evidence=self._read_evidence(connection, "claim_evidence", "claim_id", row["id"], "research_statements"),
        )

    def _relationship_from_row(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> EntityRelationship:
        edition_key = None
        if row["source_edition_id"] is not None:
            edition_row = connection.execute(
                "SELECT edition_key FROM source_editions WHERE id = ?",
                (row["source_edition_id"],),
            ).fetchone()
            edition_key = edition_row["edition_key"] if edition_row is not None else None
        evidence_rows = connection.execute(
            "SELECT * FROM relationship_evidence WHERE relationship_id = ? ORDER BY evidence_order",
            (row["id"],),
        ).fetchall()
        evidence = [EvidenceReference(
            section=item["section"], page=item["page"], locator=item["locator"],
            evidence=item["evidence_text"], origin=item["origin"],
            source_edition_id=item["source_edition_id"],
            source_edition_key=item["source_edition_key"],
        ) for item in evidence_rows]
        return EntityRelationship(
            id=row["id"], paper_id=row["paper_id"], source_edition_id=row["source_edition_id"],
            subject_entity_id=row["subject_entity_id"], predicate=row["predicate"],
            object_entity_id=row["object_entity_id"], source_wording=row["source_wording"],
            status=row["status"], provenance_type=row["provenance_type"],
            confidence=row["confidence"], verified_by=row["verified_by"],
            verified_at=row["verified_at"],
            source_edition_key=edition_key,
            evidence=evidence,
        )

    @staticmethod
    def _read_evidence(
        connection: sqlite3.Connection, table: str, foreign_key: str, claim_id: str,
        claim_table: str | None = None,
    ) -> list[EvidenceReference]:
        where = f"{foreign_key} = ?"
        parameters: tuple[object, ...] = (claim_id,)
        if claim_table is not None:
            where += " AND claim_table = ?"
            parameters = (claim_id, claim_table)
        rows = connection.execute(
            f"SELECT * FROM {table} WHERE {where} ORDER BY evidence_order", parameters
        ).fetchall()
        return [EvidenceReference(
            section=row["section"], page=row["page"], locator=row["locator"],
            evidence=row["evidence_text"], origin=row["origin"],
            source_edition_id=row["source_edition_id"],
            source_edition_key=row["source_edition_key"],
            claimed_value=SqliteResearchRepositoryMixin._json(row["claimed_value_json"]),
        ) for row in rows]

    @staticmethod
    def _source_edition_from_row(row: sqlite3.Row) -> SourceEdition:
        return SourceEdition(
            id=row["id"], paper_id=row["paper_id"], edition_key=row["edition_key"],
            source_type=row["source_type"], uri=row["uri"], content_hash=row["content_hash"],
            version_label=row["version_label"], is_primary=bool(row["is_primary"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _json(value: str | None) -> object | None:
        return json.loads(value) if value is not None else None
