"""Regression coverage for #11 upgrade and source-edition traceability guarantees."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from ocean_research_hub.api import create_app
from ocean_research_hub.ingestion.models import PaperWorkflowStatus
from ocean_research_hub.ingestion.pdf import ParsedPage, ParsedPdf, PdfParser
from ocean_research_hub.ingestion.repository import SqlitePaperRepository
from ocean_research_hub.research.models import SourceEditionCreate, SourceEditionType
from ocean_research_hub.schemas.paper_record import PaperRecord


def _primary_claim(value: object, *, evidence: str) -> dict[str, object]:
    return {
        "value": value,
        "status": "NOT_VERIFIED",
        "provenance_type": "AUTHOR_REPORTED_FACT",
        "confidence": 0.8,
        "source": {
            "origin": "PRIMARY_PAPER",
            "page": 2,
            "section": "Methods",
            "evidence": evidence,
        },
    }


def _record_with_dataset(dataset: str) -> PaperRecord:
    return PaperRecord.model_validate(
        {"data": {"datasets": _primary_claim([dataset], evidence=f"Dataset: {dataset}")}}
    )


class _SinglePagePdfParser(PdfParser):
    def parse(self, content: bytes, *, source_name: str = "paper.pdf") -> ParsedPdf:
        return ParsedPdf(
            pages=[ParsedPage(1, "We use the Adam optimizer.")], source_name=source_name
        )


def test_bibliography_only_doi_record_can_upgrade_in_place_to_primary_record(
    tmp_path: Path,
) -> None:
    """A corpus discovery record must not permanently block later PDF extraction."""
    repository = SqlitePaperRepository(tmp_path / "research.db")
    metadata = {
        "doi": "10.1234/upgrade",
        "title": "Catalog title",
        "authors": ["A. Author"],
        "year": 2024,
        "source_origin": "SECONDARY_SOURCE",
    }
    primary_record = {
        "paper": {
            "title": _primary_claim("Primary-source title", evidence="Primary-source title"),
            "doi": _primary_claim("10.1234/upgrade", evidence="doi: 10.1234/upgrade"),
        },
        "data": {"datasets": _primary_claim(["Argo"], evidence="We use Argo.")},
    }

    with TestClient(create_app(repository=repository)) as client:
        discovery = client.post("/api/papers/ingest", json={"metadata": metadata})
        assert discovery.status_code == 201, discovery.text
        paper_id = discovery.json()["paper"]["id"]

        upgrade = client.post("/api/papers/ingest", json={"parsed_paper": primary_record})

        assert upgrade.status_code == 200, upgrade.text
        assert upgrade.json()["paper"]["id"] == paper_id
        assert upgrade.json()["paper"]["record"]["paper"]["title"]["value"] == "Primary-source title"
        research = client.get(f"/api/research/papers/{paper_id}")
        assert research.status_code == 200, research.text
        assert any(
            mention["source_wording"] == "Argo" for mention in research.json()["entity_mentions"]
        )


def test_upgrade_keeps_superseded_metadata_field_evidence_queryable_by_edition(
    tmp_path: Path,
) -> None:
    """A retained source-edition row is insufficient if its original claim disappears."""
    repository = SqlitePaperRepository(tmp_path / "research.db")
    metadata = {
        "doi": "10.1234/bibliography-history",
        "title": "Catalog title",
        "source_origin": "SECONDARY_SOURCE",
    }
    primary_record = {
        "paper": {
            "title": _primary_claim("Primary title", evidence="Primary title"),
            "doi": _primary_claim(
                "10.1234/bibliography-history",
                evidence="doi: 10.1234/bibliography-history",
            ),
        }
    }

    with TestClient(create_app(repository=repository)) as client:
        discovery = client.post("/api/papers/ingest", json={"metadata": metadata})
        assert discovery.status_code == 201, discovery.text
        paper_id = discovery.json()["paper"]["id"]
        upgraded = client.post("/api/papers/ingest", json={"parsed_paper": primary_record})
        assert upgraded.status_code == 200, upgraded.text
        research = client.get(f"/api/research/papers/{paper_id}")

    assert research.status_code == 200, research.text
    detail = research.json()
    metadata_edition = next(
        edition["id"]
        for edition in detail["source_editions"]
        if edition["edition_key"].startswith("metadata:")
    )
    historical_title = [
        state
        for state in detail["entity_field_states"]
        if state["field_path"] == "paper.title"
        and state["source_edition_id"] == metadata_edition
    ]
    assert historical_title[0]["value"] == "Catalog title"
    assert historical_title[0]["evidence"][0]["evidence"] == "title: Catalog title"


def test_changed_duplicate_arxiv_record_is_not_silently_stored_as_a_second_paper(
    tmp_path: Path,
) -> None:
    """arXiv is a paper identity, not merely an unindexed bibliography field."""
    repository = SqlitePaperRepository(tmp_path / "research.db")
    first = {
        "metadata": {
            "arxiv": "2401.00001",
            "title": "Catalog title v1",
            "source_origin": "SECONDARY_SOURCE",
        }
    }
    changed_duplicate = {
        "metadata": {
            "arxiv": "2401.00001",
            "title": "Catalog title v2",
            "source_origin": "SECONDARY_SOURCE",
        }
    }

    with TestClient(create_app(repository=repository)) as client:
        created = client.post("/api/papers/ingest", json=first)
        assert created.status_code == 201, created.text
        duplicate = client.post("/api/papers/ingest", json=changed_duplicate)

    assert duplicate.status_code == 409, duplicate.text
    assert repository.count() == 1


def test_case_sensitive_units_do_not_normalize_into_the_same_entity(tmp_path: Path) -> None:
    """`m` (metre) and `M` (molar) have distinct scientific meanings."""
    repository = SqlitePaperRepository(tmp_path / "research.db")
    with TestClient(create_app(repository=repository)) as client:
        for unit in ("m", "M"):
            response = client.post(
                "/api/papers/ingest",
                json={"parsed_paper": {"data": {"units": _primary_claim([unit], evidence=f"Unit: {unit}")}}},
            )
            assert response.status_code == 201, response.text
        units = client.get("/api/research/entities", params={"entity_type": "UNIT"})

    assert units.status_code == 200, units.text
    assert {(item["canonical_name"], item["normalized_key"]) for item in units.json()["items"]} == {
        ("m", "m"),
        ("M", "M"),
    }


def test_primary_upgrade_does_not_rebind_inherited_metadata_bibliography_claims(
    tmp_path: Path,
) -> None:
    """A primary edition may supersede metadata, but must not impersonate it."""
    repository = SqlitePaperRepository(tmp_path / "research.db")
    metadata = {
        "doi": "10.1234/metadata-provenance",
        "title": "Catalog title",
        "authors": ["Catalog Author"],
        "source_origin": "SECONDARY_SOURCE",
    }
    primary_record = {
        "paper": {
            "title": _primary_claim("Primary title", evidence="Primary title"),
            "doi": _primary_claim(
                "10.1234/metadata-provenance", evidence="doi: 10.1234/metadata-provenance"
            ),
        }
    }

    with TestClient(create_app(repository=repository)) as client:
        discovery = client.post("/api/papers/ingest", json={"metadata": metadata})
        assert discovery.status_code == 201, discovery.text
        paper_id = discovery.json()["paper"]["id"]
        upgrade = client.post("/api/papers/ingest", json={"parsed_paper": primary_record})
        assert upgrade.status_code == 200, upgrade.text
        detail = client.get(f"/api/research/papers/{paper_id}").json()

    edition_key = {
        edition["id"]: edition["edition_key"] for edition in detail["source_editions"]
    }
    author_states = [
        state for state in detail["entity_field_states"] if state["field_path"] == "paper.authors"
    ]
    metadata_claims = [
        state
        for state in author_states
        if edition_key[state["source_edition_id"]].startswith("metadata:")
        and state["value"] == ["Catalog Author"]
    ]
    assert len(metadata_claims) == 1
    assert metadata_claims[0]["evidence"][0]["origin"] == "SECONDARY_SOURCE"
    primary_states = [
        state
        for state in author_states
        if not edition_key[state["source_edition_id"]].startswith("metadata:")
    ]
    assert primary_states
    assert all(
        state["status"] == "NOT_REPORTED"
        and state["value"] is None
        and state["evidence"] == []
        for state in primary_states
    )


def test_migration_backfills_legacy_arxiv_identity_before_accepting_reingestion(
    tmp_path: Path,
) -> None:
    """An existing database must retain arXiv duplicate protection after migration."""
    database_path = tmp_path / "legacy.db"
    record = _record_with_dataset("Argo").model_copy(deep=True)
    record.paper.arxiv = type(record.paper.arxiv).model_validate(
        _primary_claim("2401.00001", evidence="arXiv:2401.00001")
    )
    record_json = json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    # Simulate the pre-#11 SQLite schema and an already-ingested arXiv paper.
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE papers (
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
            CREATE UNIQUE INDEX papers_unique_doi
                ON papers(doi) WHERE doi IS NOT NULL;
            """
        )
        connection.execute(
            "INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-paper",
                "content:legacy-paper",
                None,
                hashlib.sha256(record_json.encode("utf-8")).hexdigest(),
                "EXTRACTED",
                record_json,
                "[]",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )

    repository = SqlitePaperRepository(database_path)
    with TestClient(create_app(repository=repository)) as client:
        repeated = client.post(
            "/api/papers/ingest", json={"parsed_paper": record.model_dump(mode="json")}
        )

    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["paper"]["id"] == "legacy-paper"
    assert repository.count() == 1


def test_multiple_editions_keep_each_edition_claims_and_evidence_inspectable(
    tmp_path: Path,
) -> None:
    """Registering an updated PDF must never erase v1's traceable scientific claims."""
    repository = SqlitePaperRepository(tmp_path / "research.db")
    repository.initialize()
    first_record = _record_with_dataset("Dataset v1")
    paper, _ = repository.create_or_get(
        identity_key="doi:10.1234/edition-history",
        doi="10.1234/edition-history",
        record=first_record,
        workflow_status=PaperWorkflowStatus.EXTRACTED,
        warnings=[],
    )
    repository.sync_research_record(
        paper.id,
        first_record,
        SourceEditionCreate(
            edition_key="publisher-v1",
            source_type=SourceEditionType.PRIMARY_PDF,
            content_hash="sha256:v1",
            version_label="v1",
            is_primary=True,
        ),
    )
    repository.sync_research_record(
        paper.id,
        _record_with_dataset("Dataset v2"),
        SourceEditionCreate(
            edition_key="publisher-v2",
            source_type=SourceEditionType.PRIMARY_PDF,
            content_hash="sha256:v2",
            version_label="v2",
            is_primary=True,
        ),
    )

    research = repository.get_research_paper(paper.id)
    edition_by_id = {edition.id: edition.edition_key for edition in research.source_editions}
    dataset_mentions = [
        mention
        for mention in research.entity_mentions
        if mention.field_path == "data.datasets"
    ]

    assert {
        (edition_by_id[mention.source_edition_id], mention.source_wording)
        for mention in dataset_mentions
    } == {("publisher-v1", "Dataset v1"), ("publisher-v2", "Dataset v2")}
    assert all(mention.evidence[0].evidence == f"Dataset: {mention.source_wording}" for mention in dataset_mentions)


def test_partially_verified_relationship_requires_locatable_primary_author_evidence(
    tmp_path: Path,
) -> None:
    """Normalized edges must retain the field-level evidence threshold for audits."""
    repository = SqlitePaperRepository(tmp_path / "research.db")
    with TestClient(create_app(repository=repository)) as client:
        paper = client.post(
            "/api/papers/ingest",
            json={
                "parsed_paper": {
                    "architecture": {"named_models": _primary_claim(["OceanNet"], evidence="OceanNet")},
                    "data": {"datasets": _primary_claim(["Argo"], evidence="Argo")},
                }
            },
        ).json()["paper"]
        entities = {
            item["source_wording"]: item["entity_id"]
            for item in client.get(f"/api/research/papers/{paper['id']}").json()["entity_mentions"]
        }
        response = client.post(
            f"/api/research/papers/{paper['id']}/relationships",
            json={
                "subject_entity_id": entities["OceanNet"],
                "predicate": "EVALUATED_ON",
                "object_entity_id": entities["Argo"],
                "source_wording": "OceanNet was evaluated on Argo.",
                "status": "PARTIALLY_VERIFIED",
                "provenance_type": "AUTHOR_REPORTED_FACT",
                "evidence": [{
                    "origin": "SECONDARY_SOURCE",
                    "page": 3,
                    "evidence": "A catalog says OceanNet was evaluated on Argo.",
                }],
            },
        )

    assert response.status_code == 422, response.text


def test_rejected_duplicate_source_hash_does_not_leave_an_unprojected_paper(
    tmp_path: Path,
) -> None:
    """A source-edition collision must roll back the preceding paper insert."""
    pdf_path = tmp_path / "same.pdf"
    pdf_path.write_bytes(b"%PDF same content")
    repository = SqlitePaperRepository(tmp_path / "research.db")
    with TestClient(create_app(repository=repository, pdf_parser=_SinglePagePdfParser())) as client:
        first = client.post(
            "/api/papers/ingest",
            json={"pdf_path": str(pdf_path), "metadata": {"doi": "10.1234/first", "title": "First"}},
        )
        collision = client.post(
            "/api/papers/ingest",
            json={"pdf_path": str(pdf_path), "metadata": {"doi": "10.1234/second", "title": "Second"}},
        )

    assert first.status_code == 201, first.text
    assert collision.status_code == 409, collision.text
    assert repository.count() == 1


def test_failed_source_collision_does_not_mutate_a_controlled_upgrade(
    tmp_path: Path,
) -> None:
    """Compensation must also protect an existing record being upgraded in place."""
    pdf_path = tmp_path / "same.pdf"
    pdf_path.write_bytes(b"%PDF same content")
    repository = SqlitePaperRepository(tmp_path / "research.db")
    with TestClient(create_app(repository=repository, pdf_parser=_SinglePagePdfParser())) as client:
        occupied = client.post(
            "/api/papers/ingest",
            json={"pdf_path": str(pdf_path), "metadata": {"doi": "10.1234/occupied", "title": "Occupied"}},
        )
        discovery = client.post(
            "/api/papers/ingest",
            json={"metadata": {"doi": "10.1234/upgrade-target", "title": "Catalog target"}},
        )
        target_id = discovery.json()["paper"]["id"]
        failed_upgrade = client.post(
            "/api/papers/ingest",
            json={
                "pdf_path": str(pdf_path),
                "metadata": {"doi": "10.1234/upgrade-target", "title": "Catalog target"},
            },
        )
        target_after_failure = client.get(f"/api/papers/{target_id}")

    assert occupied.status_code == 201, occupied.text
    assert discovery.status_code == 201, discovery.text
    assert failed_upgrade.status_code == 409, failed_upgrade.text
    assert target_after_failure.status_code == 200, target_after_failure.text
    assert target_after_failure.json()["workflow_status"] == "INGESTED"
    assert target_after_failure.json()["record"]["paper"]["title"]["value"] == "Catalog target"
