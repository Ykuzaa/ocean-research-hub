from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ocean_research_hub.api import create_app
from ocean_research_hub.ingestion.models import PaperWorkflowStatus
from ocean_research_hub.ingestion.repository import SqlitePaperRepository
from ocean_research_hub.research.models import CorpusManifestEntry, SourceEditionCreate
from ocean_research_hub.schemas.paper_record import PaperRecord


def claim(value: object, *, evidence: str = "Reported by the authors.") -> dict[str, object]:
    return {
        "value": value,
        "status": "NOT_VERIFIED",
        "provenance_type": "AUTHOR_REPORTED_FACT",
        "confidence": 0.8,
        "source": {
            "origin": "PRIMARY_PAPER",
            "page": 3,
            "section": "Methods",
            "locator": "paragraph 2",
            "evidence": evidence,
        },
    }


def ingest(client: TestClient, title: str, dataset: str) -> dict[str, object]:
    response = client.post(
        "/api/papers/ingest",
        json={
            "parsed_paper": {
                "paper": {"title": claim(title)},
                "scientific_framing": {
                    "domain": claim(["Physical Oceanography", "Machine Learning"]),
                    "task_type": claim(["Forecasting"]),
                },
                "data": {
                    "datasets": claim([dataset]),
                    "variables": claim(["sea surface height"]),
                    "units": claim(["m"]),
                },
                "architecture": {
                    "named_models": claim(["OceanNet"]),
                    "family": claim(["Transformer"]),
                },
                "training": {
                    "optimizer": claim("AdamW"),
                    "batch_size": claim(16),
                    "scheduler": {"status": "EXTRACTION_ERROR"},
                },
                "evaluation": {"metrics": claim(["RMSE"])},
                "results": {"headline": claim(["RMSE was 0.12 m."])},
                "limitations": {
                    "author_reported": {
                        **claim(["Limited to one basin."]),
                        "provenance_type": "AUTHOR_REPORTED_LIMITATION",
                    },
                    "future_work": {
                        **claim(["Extend to global coverage."]),
                        "provenance_type": "AUTHOR_REPORTED_LIMITATION",
                    },
                },
            }
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["paper"]


def test_migrations_are_repeatable_and_recorded(tmp_path: Path) -> None:
    repository = SqlitePaperRepository(tmp_path / "research.db")
    repository.initialize()
    repository.initialize()

    with sqlite3.connect(repository.database_path) as connection:
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert versions == [
        ("0001_paper_records",), ("0002_research_intelligence",),
        ("0003_staging_corpus",),
    ]
    assert {
        "source_editions",
        "research_entities",
        "entity_mentions",
        "training_configurations",
        "hyperparameters",
        "reported_results",
        "research_statements",
    } <= tables


def test_normalized_entities_deduplicate_across_heterogeneous_papers_and_keep_wording(
    tmp_path: Path,
) -> None:
    repository = SqlitePaperRepository(tmp_path / "research.db")
    with TestClient(create_app(repository=repository)) as client:
        first = ingest(client, "Paper A", "GLORYS12")
        ingest(client, "Paper B", "Argo")

        domains = client.get(
            "/api/research/entities", params={"entity_type": "DOMAIN"}
        ).json()
        detail = client.get(
            f"/api/research/papers/{first['id']}"
        ).json()

    physical = next(item for item in domains["items"] if item["canonical_name"] == "Physical Oceanography")
    assert physical["paper_count"] == 2
    assert domains["total"] == 2
    dataset_mentions = [
        item for item in detail["entity_mentions"] if item["field_path"] == "data.datasets"
    ]
    assert dataset_mentions[0]["source_wording"] == "GLORYS12"
    assert dataset_mentions[0]["evidence"][0]["page"] == 3
    assert {item["status"] for item in dataset_mentions} == {"NOT_VERIFIED"}


def test_research_projection_preserves_missing_errors_results_and_statements(
    tmp_path: Path,
) -> None:
    repository = SqlitePaperRepository(tmp_path / "research.db")
    with TestClient(create_app(repository=repository)) as client:
        paper = ingest(client, "Claims", "Argo")
        detail = client.get(f"/api/research/papers/{paper['id']}").json()

    parameters = {
        item["field_path"]: item
        for item in detail["training_configurations"][0]["hyperparameters"]
    }
    assert parameters["training.scheduler"]["status"] == "EXTRACTION_ERROR"
    assert parameters["training.scheduler"]["value"] is None
    assert parameters["training.learning_rate"]["status"] == "NOT_REPORTED"
    assert parameters["training.learning_rate"]["value"] is None
    assert any(item["value"] == "RMSE was 0.12 m." for item in detail["reported_results"])
    assert {item["statement_type"] for item in detail["statements"] if item["original_wording"]} == {
        "LIMITATION",
        "FUTURE_WORK",
    }


def test_source_editions_are_exact_idempotent_and_changed_identity_conflicts(
    tmp_path: Path,
) -> None:
    repository = SqlitePaperRepository(tmp_path / "research.db")
    repository.initialize()
    paper, _ = repository.create_or_get(
        identity_key="content:edition-test",
        doi=None,
        record=PaperRecord(),
        workflow_status=PaperWorkflowStatus.INGESTED,
        warnings=[],
    )
    edition = {
        "edition_key": "publisher-v1",
        "source_type": "PRIMARY_PDF",
        "uri": "https://example.org/paper-v1.pdf",
        "content_hash": "sha256:abc",
        "version_label": "version 1",
        "is_primary": True,
    }
    with TestClient(create_app(repository=repository)) as client:
        first = client.post(f"/api/research/papers/{paper.id}/source-editions", json=edition)
        second = client.post(f"/api/research/papers/{paper.id}/source-editions", json=edition)
        changed = client.post(
            f"/api/research/papers/{paper.id}/source-editions",
            json={**edition, "uri": "https://example.org/changed.pdf"},
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "INGESTION_CONFLICT"


def test_manifest_contract_validates_paper_record_and_source_identity() -> None:
    entry = CorpusManifestEntry.model_validate(
        {
            "manifest_id": "corpus-13:item-1",
            "doi": "10.1234/example",
            "source_edition": {
                "edition_key": "doi:10.1234/example:metadata",
                "source_type": "CORPUS_MANIFEST",
            },
            "paper_record": {},
        }
    )
    assert isinstance(entry.paper_record, PaperRecord)
    assert entry.paper_record.training.optimizer.status.value == "NOT_REPORTED"

    with pytest.raises(ValidationError):
        CorpusManifestEntry.model_validate(
            {
                "manifest_id": "bad",
                "title": "Paper",
                "source_edition": {"edition_key": "bad", "source_type": "CORPUS_MANIFEST"},
                "paper_record": {"training": {"optimizer": {"value": "AdamW", "status": "NOT_REPORTED"}}},
            }
        )


def test_reingesting_same_evidence_replaces_only_same_edition_projection(
    tmp_path: Path,
) -> None:
    repository = SqlitePaperRepository(tmp_path / "research.db")
    payload = {
        "parsed_paper": {
            "data": {"datasets": claim(["Argo"], evidence="We use Argo.")}
        }
    }
    with TestClient(create_app(repository=repository)) as client:
        first = client.post("/api/papers/ingest", json=payload)
        second = client.post("/api/papers/ingest", json=payload)
        detail = client.get(
            f"/api/research/papers/{first.json()['paper']['id']}"
        ).json()

    assert first.status_code == 201
    assert second.status_code == 200
    mentions = [item for item in detail["entity_mentions"] if item["field_path"] == "data.datasets"]
    assert len(mentions) == 1
    assert mentions[0]["evidence"][0]["evidence"] == "We use Argo."


def test_entity_field_states_expose_absence_error_and_audit_metadata(tmp_path: Path) -> None:
    repository = SqlitePaperRepository(tmp_path / "research.db")
    record = {
        "scientific_framing": {"domain": {"status": "EXTRACTION_ERROR"}},
        "data": {
            "datasets": {
                **claim(["Argo"]),
                "status": "VERIFIED",
                "verified_by": "scientific-auditor",
                "verified_at": "2026-09-22T10:00:00Z",
            },
        },
    }
    with TestClient(create_app(repository=repository)) as client:
        created = client.post("/api/papers/ingest", json={"parsed_paper": record})
        detail = client.get(
            f"/api/research/papers/{created.json()['paper']['id']}"
        ).json()

    states = {item["field_path"]: item for item in detail["entity_field_states"]}
    assert states["scientific_framing.domain"]["status"] == "EXTRACTION_ERROR"
    assert states["scientific_framing.domain"]["value"] is None
    assert states["scientific_framing.task_type"]["status"] == "NOT_REPORTED"
    assert states["data.datasets"]["verified_by"] == "scientific-auditor"
    assert states["data.datasets"]["verified_at"] == "2026-09-22T10:00:00Z"
    assert states["data.datasets"]["evidence"][0]["source_edition_id"] is not None
    assert states["data.datasets"]["evidence"][0]["source_edition_key"] is not None
    assert not any(
        mention["field_path"] == "scientific_framing.domain"
        for mention in detail["entity_mentions"]
    )


def test_explicit_entity_relationship_api_never_infers_parallel_list_edges(
    tmp_path: Path,
) -> None:
    repository = SqlitePaperRepository(tmp_path / "research.db")
    with TestClient(create_app(repository=repository)) as client:
        paper = ingest(client, "Relations", "Argo")
        detail = client.get(f"/api/research/papers/{paper['id']}").json()
        assert detail["entity_relationships"] == []
        entities = {
            item["source_wording"]: item["entity_id"]
            for item in detail["entity_mentions"]
        }
        edition_key = detail["source_editions"][0]["edition_key"]
        created = client.post(
            f"/api/research/papers/{paper['id']}/relationships",
            json={
                "subject_entity_id": entities["OceanNet"],
                "predicate": "EVALUATED_ON",
                "object_entity_id": entities["Argo"],
                "source_wording": "OceanNet was evaluated on Argo.",
                "status": "NOT_VERIFIED",
                "provenance_type": "AUTHOR_REPORTED_FACT",
                "confidence": 0.8,
                "source_edition_key": edition_key,
                "evidence": [{
                    "origin": "PRIMARY_PAPER",
                    "page": 5,
                    "locator": "Evaluation, paragraph 1",
                    "evidence": "OceanNet was evaluated on Argo.",
                }],
            },
        )
        rejected = client.post(
            f"/api/research/papers/{paper['id']}/relationships",
            json={
                "subject_entity_id": entities["OceanNet"],
                "predicate": "EVALUATED_ON",
                "object_entity_id": entities["Argo"],
                "source_wording": "Unsupported edge",
                "status": "NOT_VERIFIED",
                "evidence": [],
            },
        )
        refreshed = client.get(f"/api/research/papers/{paper['id']}").json()

    assert created.status_code == 201, created.text
    assert rejected.status_code == 422
    assert refreshed["entity_relationships"][0]["predicate"] == "EVALUATED_ON"
    assert refreshed["entity_relationships"][0]["evidence"][0]["source_edition_key"] == edition_key


def test_verified_entity_relationship_rejects_interpretive_provenance() -> None:
    from ocean_research_hub.research.models import EntityRelationshipCreate

    with pytest.raises(ValidationError, match="author-reported provenance"):
        EntityRelationshipCreate.model_validate({
            "subject_entity_id": "model-id",
            "predicate": "EVALUATED_ON",
            "object_entity_id": "dataset-id",
            "source_wording": "The model was evaluated on the dataset.",
            "status": "VERIFIED",
            "provenance_type": "AI_INTERPRETATION",
            "evidence": [{
                "origin": "PRIMARY_PAPER",
                "page": 4,
                "evidence": "The model was evaluated on the dataset.",
            }],
        })


def test_cross_identifier_alias_prevents_doi_arxiv_duplicate(tmp_path: Path) -> None:
    repository = SqlitePaperRepository(tmp_path / "research.db")
    with TestClient(create_app(repository=repository)) as client:
        first = client.post("/api/papers/ingest", json={"metadata": {
            "doi": "10.1234/cross-id",
            "arxiv": "2401.00001v2",
            "title": "Cross-identified paper",
        }})
        duplicate = client.post("/api/papers/ingest", json={"metadata": {
            "arxiv": "https://arxiv.org/abs/2401.00001",
            "title": "Cross-identified paper",
        }})

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert repository.count() == 1


def test_numbered_staging_migration_preserves_imported_corpus(tmp_path: Path) -> None:
    from ocean_research_hub.corpus.repository import CorpusRepository
    from ocean_research_hub.corpus.workbook import read_workbook

    database = tmp_path / "research.db"
    corpus = CorpusRepository(database)
    workbook = Path(__file__).resolve().parents[1] / "import_staging" / "Ocean_Research_Hub_COMPLET.xlsx"
    corpus.import_workbook(read_workbook(workbook))
    assert corpus.summary()["papers"] == 115

    canonical = SqlitePaperRepository(database)
    canonical.initialize()
    canonical.initialize()
    with sqlite3.connect(database) as connection:
        versions = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        assert "0003_staging_corpus" in versions
        assert connection.execute("SELECT COUNT(*) FROM staging_corpus_papers").fetchone()[0] == 115
        assert connection.execute("SELECT COUNT(*) FROM staging_corpus_claims").fetchone()[0] == 144
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'staging_corpus_audit_events'"
        ).fetchone() is not None
