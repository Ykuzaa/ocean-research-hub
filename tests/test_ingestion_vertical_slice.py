"""Integration coverage for issue #2's one-paper vertical slice."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

from ocean_research_hub.api import create_app
from ocean_research_hub.ingestion.errors import (
    MetadataProviderError,
    ParserError,
    PersistenceError,
)
from ocean_research_hub.ingestion.models import MetadataPayload, PaperWorkflowStatus
from ocean_research_hub.ingestion.providers import (
    CrossrefMetadataProvider,
    StructuredPayloadParser,
)
from ocean_research_hub.ingestion.repository import SqlitePaperRepository
from ocean_research_hub.schemas.paper_record import PaperRecord, TextField


class StubMetadataProvider:
    def __init__(self, metadata: MetadataPayload | None = None) -> None:
        self.metadata = metadata or MetadataPayload(
            title="Observed ocean dynamics",
            authors=["Ada Researcher"],
            year=2025,
            venue="Journal of Ocean Evidence",
            doi="10.1234/OCEAN.1",
            publisher_url="https://example.org/ocean.1",
        )
        self.calls: list[str] = []

    async def fetch(self, doi: str) -> MetadataPayload:
        self.calls.append(doi)
        return self.metadata


class FailingMetadataProvider:
    async def fetch(self, doi: str) -> MetadataPayload:
        raise MetadataProviderError(f"provider unavailable for {doi}")


class FailingParser:
    def parse(self, payload: object) -> PaperRecord:
        raise ParserError("parser process failed")


class FailingRepository:
    def initialize(self) -> None:
        pass

    def create_or_get(self, **_: object) -> object:
        raise sqlite3.OperationalError("sensitive disk I/O detail")

    def get(self, paper_id: str) -> object:
        raise sqlite3.OperationalError(f"sensitive lock detail for {paper_id}")


@pytest.fixture
def repository(tmp_path: Path) -> SqlitePaperRepository:
    return SqlitePaperRepository(tmp_path / "papers.db")


def make_client(
    repository: SqlitePaperRepository,
    *,
    metadata_provider: object | None = None,
    parser: object | None = None,
) -> TestClient:
    app = create_app(
        repository=repository,
        metadata_provider=metadata_provider or StubMetadataProvider(),
        parsed_paper_provider=parser or StructuredPayloadParser(),
    )
    return TestClient(app)


def verified_title_payload(
    title: str = "Evidence-backed ocean forecast",
) -> dict[str, object]:
    return {
        "paper": {
            "title": {
                "value": title,
                "status": "VERIFIED",
                "provenance_type": "AUTHOR_REPORTED_FACT",
                "confidence": 1.0,
                "source": {
                    "origin": "PRIMARY_PAPER",
                    "page": 1,
                    "locator": "Title",
                    "evidence": title,
                },
            }
        }
    }


def test_local_parsed_paper_round_trips_to_api_and_detail_page(
    repository: SqlitePaperRepository,
) -> None:
    payload = {"parsed_paper": verified_title_payload()}

    with make_client(repository) as client:
        response = client.post("/api/papers/ingest", json=payload)
        assert response.status_code == 201
        result = response.json()
        assert result["created"] is True
        assert result["paper"]["workflow_status"] == "EXTRACTED"
        assert result["paper"]["record"]["paper"]["doi"]["status"] == "NOT_REPORTED"
        paper_id = result["paper"]["id"]

        retrieved = client.get(f"/api/papers/{paper_id}")
        assert retrieved.status_code == 200
        assert retrieved.json()["record"] == result["paper"]["record"]

        page = client.get(f"/papers/{paper_id}")
        assert page.status_code == 200
        assert "Evidence-backed ocean forecast" in page.text
        assert "VERIFIED" in page.text
        assert "PRIMARY_PAPER" in page.text
        assert "NOT_REPORTED" in page.text


def test_detail_page_does_not_render_null_extraction_error_as_not_reported(
    repository: SqlitePaperRepository,
) -> None:
    parsed_paper = verified_title_payload("Synthetic detail extraction failure")
    parsed_paper["training"] = {
        "optimizer": {
            "value": None,
            "status": "EXTRACTION_ERROR",
            "provenance_type": "AUTHOR_REPORTED_FACT",
        }
    }

    with make_client(repository) as client:
        response = client.post(
            "/api/papers/ingest", json={"parsed_paper": parsed_paper}
        )
        assert response.status_code == 201
        paper_id = response.json()["paper"]["id"]

        page = client.get(f"/papers/{paper_id}")

    assert page.status_code == 200
    optimizer = re.search(
        r'<dd data-field="training.optimizer">(.*?)</dd>', page.text
    )
    assert optimizer is not None
    assert "EXTRACTION_ERROR (no extracted value)" in optimizer.group(1)
    assert '<span class="status">EXTRACTION_ERROR</span>' in optimizer.group(1)
    assert "NOT_REPORTED" not in optimizer.group(1)


def test_table_caption_and_appendix_claims_round_trip_without_filling_absent_fields(
    repository: SqlitePaperRepository,
) -> None:
    """Structured parser output must retain locators from non-body paper regions."""
    parsed_paper = {
        "architecture": {
            "family": {
                "value": ["U-Net"],
                "status": "VERIFIED",
                "source": {
                    "origin": "PRIMARY_PAPER",
                    "page": 3,
                    "locator": "Figure 2 caption, right column",
                    "evidence": "Our model uses a U-Net architecture.",
                },
            }
        },
        "training": {
            "batch_size": {
                "value": 64,
                "status": "VERIFIED",
                "source": {
                    "origin": "PRIMARY_PAPER",
                    "page": 6,
                    "locator": "Table 2, batch-size column",
                    "evidence": "Batch size 64.",
                },
            }
        },
        "data": {
            "sample_counts": {
                "value": "12,000 scenes",
                "status": "VERIFIED",
                "source": {
                    "origin": "SUPPLEMENTARY_MATERIAL",
                    "page": 128,
                    "locator": "Appendix C, Table C.1",
                    "evidence": "The data set contains 12,000 scenes.",
                },
            }
        },
    }

    with make_client(repository) as client:
        created = client.post("/api/papers/ingest", json={"parsed_paper": parsed_paper})
        stored = client.get(f"/api/papers/{created.json()['paper']['id']}")

    assert created.status_code == 201
    record = stored.json()["record"]
    assert record["architecture"]["family"]["source"]["locator"] == "Figure 2 caption, right column"
    assert record["training"]["batch_size"]["source"]["locator"] == "Table 2, batch-size column"
    assert record["data"]["sample_counts"]["source"]["page"] == 128
    assert record["architecture"]["activations"] == {
        "value": None,
        "conflict_values": [],
        "status": "NOT_REPORTED",
        "provenance_type": "AUTHOR_REPORTED_FACT",
        "confidence": 0.0,
        "source": {
            "section": None,
            "page": None,
            "locator": None,
            "evidence": None,
            "origin": None,
            "evidence_url": None,
            "claimed_value": None,
        },
            "sources": [],
            "absence_search_scope": [],
            "verified_by": None,
        "verified_at": None,
    }


def test_parsed_paper_doi_is_not_mislabeled_as_crossref_metadata(
    repository: SqlitePaperRepository,
) -> None:
    provider = StubMetadataProvider()

    with make_client(repository, metadata_provider=provider) as client:
        response = client.post(
            "/api/papers/ingest",
            json={
                "doi": "10.1234/ocean.1",
                "parsed_paper": verified_title_payload(),
            },
        )

    doi_field = response.json()["paper"]["record"]["paper"]["doi"]
    assert response.status_code == 201
    assert provider.calls == []
    assert doi_field["status"] == "NOT_VERIFIED"
    assert doi_field["source"]["origin"] == "SECONDARY_SOURCE"


def test_repeated_identical_ingest_is_idempotent(
    repository: SqlitePaperRepository,
) -> None:
    payload = {"parsed_paper": verified_title_payload()}

    with make_client(repository) as client:
        first = client.post("/api/papers/ingest", json=payload)
        second = client.post("/api/papers/ingest", json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["paper"]["id"] == first.json()["paper"]["id"]
    assert repository.count() == 1


def test_case_equivalent_parsed_dois_are_idempotent(
    repository: SqlitePaperRepository,
) -> None:
    """DOIs are case-insensitive identities, including DOI-only parsed records."""
    upper_case = {
        "parsed_paper": {
            "paper": {
                "doi": {
                    "value": "10.1234/OCEAN.1",
                    "status": "NOT_VERIFIED",
                    "source": {
                        "origin": "PRIMARY_PAPER",
                        "page": 1,
                        "locator": "First-page DOI",
                        "evidence": "doi: 10.1234/OCEAN.1",
                    },
                }
            }
        }
    }
    lower_case = {
        "parsed_paper": {
            "paper": {
                "doi": {
                    "value": "10.1234/ocean.1",
                    "status": "NOT_VERIFIED",
                    "source": {
                        "origin": "PRIMARY_PAPER",
                        "page": 1,
                        "locator": "First-page DOI",
                        "evidence": "doi: 10.1234/OCEAN.1",
                    },
                }
            }
        }
    }

    with make_client(repository) as client:
        first = client.post("/api/papers/ingest", json=upper_case)
        second = client.post("/api/papers/ingest", json=lower_case)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["paper"]["id"] == first.json()["paper"]["id"]
    assert first.json()["paper"]["record"]["paper"]["doi"]["source"] == {
        "origin": "PRIMARY_PAPER",
        "page": 1,
        "section": None,
        "locator": "First-page DOI",
        "evidence": "doi: 10.1234/OCEAN.1",
        "evidence_url": None,
        "claimed_value": None,
    }
    assert repository.count() == 1


def test_concurrent_identical_repository_writes_create_one_paper(
    repository: SqlitePaperRepository,
) -> None:
    repository.initialize()
    record = PaperRecord.model_validate(verified_title_payload())

    def ingest_once() -> tuple[str, bool]:
        paper, created = repository.create_or_get(
            identity_key="content:concurrent-paper",
            doi=None,
            record=record,
            workflow_status=PaperWorkflowStatus.EXTRACTED,
            warnings=[],
        )
        return paper.id, created

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: ingest_once(), range(8)))

    assert sum(created for _, created in results) == 1
    assert len({paper_id for paper_id, _ in results}) == 1
    assert repository.count() == 1


def test_doi_metadata_is_normalized_but_never_auto_verified(
    repository: SqlitePaperRepository,
) -> None:
    provider = StubMetadataProvider()
    with make_client(repository, metadata_provider=provider) as client:
        response = client.post(
            "/api/papers/ingest",
            json={"doi": "https://doi.org/10.1234/OCEAN.1"},
        )

    assert response.status_code == 201
    paper = response.json()["paper"]
    assert provider.calls == ["10.1234/ocean.1"]
    assert paper["doi"] == "10.1234/ocean.1"
    assert paper["workflow_status"] == "INGESTED"
    assert paper["record"]["paper"]["title"]["status"] == "NOT_VERIFIED"
    assert paper["record"]["paper"]["doi"]["status"] == "NOT_VERIFIED"
    assert paper["record"]["architecture"]["activations"]["status"] == "NOT_REPORTED"


def test_missing_doi_and_optional_metadata_remain_not_reported(
    repository: SqlitePaperRepository,
) -> None:
    with make_client(repository) as client:
        response = client.post(
            "/api/papers/ingest",
            json={"metadata": {"title": "A DOI-less paper"}},
        )

    assert response.status_code == 201
    paper = response.json()["paper"]
    assert paper["doi"] is None
    assert paper["record"]["paper"]["title"]["status"] == "NOT_VERIFIED"
    assert (
        paper["record"]["paper"]["title"]["source"]["origin"]
        == "SECONDARY_SOURCE"
    )
    assert paper["record"]["paper"]["authors"]["status"] == "NOT_REPORTED"
    assert paper["record"]["paper"]["doi"]["status"] == "NOT_REPORTED"
    assert paper["record"]["training"]["optimizer"]["status"] == "NOT_REPORTED"


def test_parser_failure_is_explicit_and_does_not_persist(
    repository: SqlitePaperRepository,
) -> None:
    with make_client(repository, parser=FailingParser()) as client:
        response = client.post(
            "/api/papers/ingest",
            json={"parsed_paper": verified_title_payload()},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PARSER_ERROR"
    assert "parser process failed" in response.json()["error"]["message"]
    assert repository.count() == 0


def test_invalid_parser_output_is_rejected_without_silent_repair(
    repository: SqlitePaperRepository,
) -> None:
    invalid = {
        "paper": {
            "title": {
                "value": "Unsupported title",
                "status": "VERIFIED",
            }
        }
    }
    with make_client(repository) as client:
        response = client.post("/api/papers/ingest", json={"parsed_paper": invalid})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PARSER_ERROR"
    assert repository.count() == 0


def test_missing_scientific_value_cannot_be_mislabeled_not_verified(
    repository: SqlitePaperRepository,
) -> None:
    invalid = {
        "training": {
            "optimizer": {
                "value": None,
                "status": "NOT_VERIFIED",
            }
        }
    }
    with make_client(repository) as client:
        response = client.post("/api/papers/ingest", json={"parsed_paper": invalid})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PARSER_ERROR"
    assert repository.count() == 0


def test_metadata_provider_failure_is_explicit(
    repository: SqlitePaperRepository,
) -> None:
    with make_client(repository, metadata_provider=FailingMetadataProvider()) as client:
        response = client.post("/api/papers/ingest", json={"doi": "10.1234/ocean.1"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "METADATA_PROVIDER_ERROR"
    assert repository.count() == 0


def test_database_failures_are_structured_and_explicit() -> None:
    app = create_app(
        repository=FailingRepository(),
        metadata_provider=StubMetadataProvider(),
        parsed_paper_provider=StructuredPayloadParser(),
    )
    with TestClient(app) as client:
        write = client.post(
            "/api/papers/ingest",
            json={"parsed_paper": verified_title_payload()},
        )
        read = client.get("/api/papers/example")

    assert write.status_code == 503
    assert write.json()["error"]["code"] == "PERSISTENCE_ERROR"
    assert "sensitive" not in write.text
    assert read.status_code == 503
    assert read.json()["error"]["code"] == "PERSISTENCE_ERROR"
    assert "sensitive" not in read.text


def test_duplicate_doi_with_different_content_never_overwrites(
    repository: SqlitePaperRepository,
) -> None:
    first = {"metadata": {"doi": "10.1234/ocean.1", "title": "Original title"}}
    changed = {"metadata": {"doi": "10.1234/ocean.1", "title": "Changed title"}}

    with make_client(repository) as client:
        created = client.post("/api/papers/ingest", json=first)
        conflict = client.post("/api/papers/ingest", json=changed)
        stored = client.get(f"/api/papers/{created.json()['paper']['id']}")

    assert created.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "INGESTION_CONFLICT"
    assert stored.json()["record"]["paper"]["title"]["value"] == "Original title"
    assert repository.count() == 1


def test_existing_conflict_and_its_evidence_survive_persistence(
    repository: SqlitePaperRepository,
) -> None:
    record = PaperRecord()
    record.training.optimizer = TextField(
        status="CONFLICT",
        conflict_values=["Adam", "SGD"],
        source={
            "origin": "PRIMARY_PAPER",
            "page": 4,
            "section": "Methods",
            "evidence": "Adam was used.",
            "claimed_value": "Adam",
        },
        sources=[
            {
                "origin": "SUPPLEMENTARY_MATERIAL",
                "page": 12,
                "section": "Appendix",
                "evidence": "SGD was used.",
                "claimed_value": "SGD",
            }
        ],
    )

    with make_client(repository) as client:
        response = client.post(
            "/api/papers/ingest",
            json={"parsed_paper": record.model_dump(mode="json")},
        )
        paper_id = response.json()["paper"]["id"]
        stored = client.get(f"/api/papers/{paper_id}").json()

    optimizer = stored["record"]["training"]["optimizer"]
    assert optimizer["status"] == "CONFLICT"
    assert optimizer["value"] is None
    assert optimizer["conflict_values"] == ["Adam", "SGD"]
    assert optimizer["source"]["claimed_value"] == "Adam"
    assert optimizer["sources"][0]["claimed_value"] == "SGD"


def test_parsed_metadata_difference_is_visible_and_primary_record_wins(
    repository: SqlitePaperRepository,
) -> None:
    with make_client(repository) as client:
        response = client.post(
            "/api/papers/ingest",
            json={
                "metadata": {"title": "Secondary metadata title"},
                "parsed_paper": verified_title_payload("Primary paper title"),
            },
        )

    paper = response.json()["paper"]
    assert paper["record"]["paper"]["title"]["value"] == "Primary paper title"
    assert paper["record"]["paper"]["title"]["status"] == "VERIFIED"
    assert paper["warnings"] == [
        "metadata title differed from the parsed record and was not used"
    ]


def test_later_metadata_disagreement_is_added_to_existing_audit_trail(
    repository: SqlitePaperRepository,
) -> None:
    record = PaperRecord.model_validate(verified_title_payload("Primary title"))
    record.paper.doi = TextField(
        value="10.1234/ocean.1",
        status="VERIFIED",
        source={
            "origin": "PRIMARY_PAPER",
            "page": 1,
            "locator": "DOI",
            "evidence": "doi:10.1234/ocean.1",
        },
    )
    parsed = record.model_dump(mode="json")

    provider = StubMetadataProvider()
    with make_client(repository, metadata_provider=provider) as client:
        first = client.post(
            "/api/papers/ingest",
            json={"doi": "10.1234/ocean.1", "parsed_paper": parsed},
        )
        second = client.post(
            "/api/papers/ingest",
            json={
                "doi": "10.1234/ocean.1",
                "metadata": {
                    "doi": "10.1234/ocean.1",
                    "title": "Conflicting secondary title",
                },
                "parsed_paper": parsed,
            },
        )
        stored = client.get(f"/api/papers/{first.json()['paper']['id']}")

    expected_warning = "metadata title differed from the parsed record and was not used"
    assert first.status_code == 201
    assert first.json()["paper"]["warnings"] == []
    assert provider.calls == []
    assert second.status_code == 200
    assert second.json()["paper"]["warnings"] == [expected_warning]
    assert stored.json()["warnings"] == [expected_warning]


def test_identical_record_reingest_advances_workflow_monotonically(
    repository: SqlitePaperRepository,
) -> None:
    metadata = {
        "doi": "10.1234/ocean.1",
        "title": "Metadata title",
    }
    with make_client(repository) as client:
        first = client.post("/api/papers/ingest", json={"metadata": metadata})
        parsed = first.json()["paper"]["record"]
        second = client.post(
            "/api/papers/ingest",
            json={"metadata": metadata, "parsed_paper": parsed},
        )
        stored = client.get(f"/api/papers/{first.json()['paper']['id']}")

    assert first.json()["paper"]["workflow_status"] == "INGESTED"
    assert second.status_code == 200
    assert second.json()["paper"]["workflow_status"] == "EXTRACTED"
    assert stored.json()["workflow_status"] == "EXTRACTED"


def test_missing_paper_returns_structured_not_found(
    repository: SqlitePaperRepository,
) -> None:
    with make_client(repository) as client:
        response = client.get("/api/papers/not-a-real-id")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PAPER_NOT_FOUND"


@pytest.mark.parametrize("payload", [{}, {"doi": ""}, {"doi": "not-a-doi"}])
def test_missing_or_invalid_ingest_identity_is_rejected(
    repository: SqlitePaperRepository,
    payload: dict[str, object],
) -> None:
    with make_client(repository) as client:
        response = client.post("/api/papers/ingest", json=payload)

    assert response.status_code == 422
    assert repository.count() == 0


def test_crossref_mapping_tolerates_missing_or_malformed_optional_dates() -> None:
    missing = CrossrefMetadataProvider._to_metadata({"title": ["No date"]})
    malformed = CrossrefMetadataProvider._to_metadata(
        {"title": ["Malformed date"], "published": {"date-parts": "unknown"}}
    )

    assert missing.year is None
    assert malformed.year is None
    assert missing.source_origin.value == "CROSSREF_METADATA"
