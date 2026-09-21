import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from ocean_research_hub.api import create_app
from ocean_research_hub.ingestion.errors import PersistenceError
from ocean_research_hub.ingestion.models import PaperWorkflowStatus
from ocean_research_hub.ingestion.repository import SqlitePaperRepository
from ocean_research_hub.schemas.paper_record import PaperRecord


def _source(evidence: str) -> dict[str, object]:
    return {
        "origin": "PRIMARY_PAPER",
        "page": 12,
        "section": "3 Methods",
        "locator": "paragraph 4",
        "evidence": evidence,
    }


def _record(index: int, *, scientific: bool = False) -> PaperRecord:
    record: dict[str, object] = {
        "paper": {
            "title": {"value": f"Paper {index}", "status": "NOT_VERIFIED"},
            "year": {"value": 2020 + index % 3, "status": "NOT_VERIFIED"},
        }
    }
    if scientific:
        exact = (
            "The study trains an encoder-decoder with Adam using the complete, "
            "author-reported configuration and retains this exact long source sentence."
        )
        record.update(
            {
                "architecture": {
                    "family": {
                        "value": ["Encoder-decoder"],
                        "status": "NOT_VERIFIED",
                        "provenance_type": "AUTHOR_REPORTED_FACT",
                        "confidence": 0.81,
                        "source": _source(exact),
                    }
                },
                "data": {
                    "datasets": {
                        "value": ["NATL60"],
                        "status": "NOT_VERIFIED",
                        "provenance_type": "AUTHOR_REPORTED_FACT",
                        "source": _source("Experiments use the NATL60 nature run as the training dataset."),
                    }
                },
                "training": {
                    "optimizer": {
                        "value": "Adam",
                        "status": "NOT_VERIFIED",
                        "provenance_type": "AUTHOR_REPORTED_FACT",
                        "confidence": 0.75,
                        "source": _source(exact),
                    },
                    "learning_rate": {
                        "value": "1e-4",
                        "status": "NOT_VERIFIED",
                        "provenance_type": "AUTHOR_REPORTED_FACT",
                        "source": _source("The initial learning rate is 1e-4 for every experiment."),
                    },
                    "batch_size": {
                        "value": 8,
                        "status": "NOT_VERIFIED",
                        "provenance_type": "AUTHOR_REPORTED_FACT",
                        "source": _source("Each optimization step uses a batch size of eight samples."),
                    },
                },
                "limitations": {
                    "data": {
                        "value": ["Restricted spatial coverage"],
                        "status": "NOT_VERIFIED",
                        "provenance_type": "AUTHOR_REPORTED_LIMITATION",
                        "source": _source("The authors note that the observations cover only one region."),
                    }
                },
            }
        )
    return PaperRecord.model_validate(record)


def _insert(
    repository: SqlitePaperRepository, index: int, *, scientific: bool = False
) -> str:
    paper, _ = repository.create_or_get(
        identity_key=f"paper-{index}",
        doi=f"10.1000/{index}",
        record=_record(index, scientific=scientific),
        workflow_status=(
            PaperWorkflowStatus.EXTRACTED if scientific else PaperWorkflowStatus.INGESTED
        ),
        warnings=[],
    )
    return paper.id


def test_landing_empty_is_distinct_from_unavailable(tmp_path: Path) -> None:
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    app = create_app(repository=repository)

    with TestClient(app) as client:
        response = client.get("/api/landing")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "empty"
    assert body["totals"]["papers"] == 0
    assert body["completeness"] == {"missing_records": 0, "message": None}
    assert body["gap_preview"]["label"] == "Product Preview"
    assert body["gap_preview"]["analytics_state"] == "NOT_COMPUTED"
    assert body["gap_preview"]["is_live_analytic"] is False


def test_landing_repository_failure_is_unavailable_not_empty(tmp_path: Path) -> None:
    class FailingLandingRepository(SqlitePaperRepository):
        def list_all_papers(self):
            raise PersistenceError("aggregate read failed")

    app = create_app(repository=FailingLandingRepository(tmp_path / "papers.db"))

    with TestClient(app) as client:
        response = client.get("/api/landing")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PERSISTENCE_ERROR"


def test_landing_aggregates_all_rows_beyond_public_page_limit(tmp_path: Path) -> None:
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    repository.initialize()
    for index in range(205):
        _insert(repository, index)
    app = create_app(repository=repository)

    with TestClient(app) as client:
        landing = client.get("/api/landing").json()
        year_drilldown = client.get(
            "/api/landing/drilldown",
            params={"dimension": "year_bibliographic", "key": "2020", "limit": 200},
        ).json()

    # The landing aggregation must not truncate to a presentation-page cap.
    assert repository.list_all_papers()[1] == 205
    assert landing["state"] == "ready"
    assert landing["totals"]["papers"] == 205
    assert landing["totals"]["readable_papers"] == 205
    assert sum(item["bibliography_only"] for item in landing["years"]) == 205
    assert all(len(item["bibliographic_papers"]) <= 3 for item in landing["years"])
    assert year_drilldown["total"] > 3
    assert len(year_drilldown["paper_items"]) == year_drilldown["total"]
    assert len(landing["workflows"]) == 1
    assert landing["workflows"][0]["status"] == "INGESTED"
    assert landing["workflows"][0]["papers"] == 205
    assert len(landing["workflows"][0]["items"]) == 3


def test_landing_keeps_value_evidence_provenance_and_audit_state_separate(
    tmp_path: Path,
) -> None:
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    repository.initialize()
    _insert(repository, 1, scientific=True)
    app = create_app(repository=repository)

    with TestClient(app) as client:
        body = client.get("/api/landing").json()

    architecture = body["architecture_families"][0]
    field = architecture["items"][0]["field"]
    assert architecture["label"] == "Encoder-decoder"
    assert field["value"] == ["Encoder-decoder"]
    assert field["source"]["evidence"].endswith("exact long source sentence.")
    assert field["source"]["locator"] == "paragraph 4"
    assert field["status"] == "NOT_VERIFIED"
    assert field["provenance_type"] == "AUTHOR_REPORTED_FACT"
    assert field["verified_by"] is None and field["verified_at"] is None
    assert body["totals"]["audited_fields"] == 0

    limitation = body["limitations"][0]
    assert limitation["key"] == "data"
    limitation_field = limitation["items"][0]["field"]
    assert limitation_field["value"] == ["Restricted spatial coverage"]
    assert limitation_field["source"]["evidence"] == (
        "The authors note that the observations cover only one region."
    )
    assert limitation_field["provenance_type"] == "AUTHOR_REPORTED_LIMITATION"


def test_landing_marks_invalid_persisted_rows_partial(tmp_path: Path) -> None:
    database = tmp_path / "papers.db"
    repository = SqlitePaperRepository(database)
    repository.initialize()
    good_id = _insert(repository, 1, scientific=True)
    bad_id = _insert(repository, 2)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE papers SET record_json = ? WHERE id = ?", ("not-json", bad_id))
    app = create_app(repository=repository)

    with TestClient(app) as client:
        response = client.get("/api/landing")
        drilldown = client.get(
            "/api/landing/drilldown",
            params={"dimension": "architecture", "key": "Encoder-decoder"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "partial"
    assert body["totals"]["papers"] == 2
    assert body["totals"]["readable_papers"] == 1
    assert body["completeness"]["missing_records"] == 1
    assert body["architecture_families"][0]["items"][0]["paper"]["id"] == good_id
    assert drilldown.status_code == 200
    assert drilldown.json()["state"] == "partial"
    assert drilldown.json()["completeness"]["missing_records"] == 1


def test_named_intelligence_excludes_unsourced_and_error_fields(tmp_path: Path) -> None:
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    repository.initialize()
    record = PaperRecord.model_validate(
        {
            "paper": {"title": {"value": "Unsafe summary", "status": "NOT_VERIFIED"}},
            "architecture": {
                "family": {
                    "value": ["Transformer"],
                    "status": "NOT_VERIFIED",
                    "provenance_type": "AI_INTERPRETATION",
                    "source": _source("The source mentions a Transformer but this stored value is interpretation."),
                }
            },
            "data": {
                "datasets": {
                    "value": ["Guessed dataset"],
                    "status": "NOT_VERIFIED",
                    "provenance_type": "TEAM_NOTE",
                    "source": _source("A team member added a dataset note that must not become an author fact."),
                }
            },
            "training": {
                "optimizer": {
                    "value": "unusable extractor output",
                    "status": "EXTRACTION_ERROR",
                    "provenance_type": "AUTHOR_REPORTED_FACT",
                }
            },
        }
    )
    repository.create_or_get(
        identity_key="unsafe",
        doi=None,
        record=record,
        workflow_status=PaperWorkflowStatus.EXTRACTED,
        warnings=[],
    )
    app = create_app(repository=repository)

    with TestClient(app) as client:
        body = client.get("/api/landing").json()
        not_reported = client.get(
            "/api/landing/drilldown",
            params={"dimension": "status", "key": "NOT_REPORTED", "limit": 1},
        ).json()

    assert body["architecture_families"] == []
    assert body["datasets"] == []
    statuses = {item["status"]: item["fields"] for item in body["statuses"]}
    assert statuses["EXTRACTION_ERROR"] == 1
    assert statuses["NOT_REPORTED"] > 0
    missing = not_reported["evidence_items"][0]["field"]
    assert missing["value"] is None
    assert missing["source"]["evidence"] is None
    assert missing["display_source"] is None


def test_named_intelligence_never_binds_one_list_excerpt_to_every_value(
    tmp_path: Path,
) -> None:
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    repository.initialize()
    record = PaperRecord.model_validate(
        {
            "paper": {"title": {"value": "Several datasets", "status": "NOT_VERIFIED"}},
            "data": {
                "datasets": {
                    "value": ["NATL60", "OSTIA", "Argo"],
                    "status": "NOT_VERIFIED",
                    "provenance_type": "AUTHOR_REPORTED_FACT",
                    "sources": [
                        _source("The simulations use NATL60."),
                        _source("Additional observations are also used."),
                    ],
                }
            },
        }
    )
    repository.create_or_get(
        identity_key="multi-dataset",
        doi=None,
        record=record,
        workflow_status=PaperWorkflowStatus.EXTRACTED,
        warnings=[],
    )
    app = create_app(repository=repository)

    with TestClient(app) as client:
        body = client.get("/api/landing").json()

    assert body["datasets"] == []


def test_display_source_uses_qualifying_additional_source(tmp_path: Path) -> None:
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    repository.initialize()
    evidence = "The paper explicitly states that the model uses the Adam optimizer."
    record = PaperRecord.model_validate(
        {
            "paper": {"title": {"value": "Additional evidence", "status": "NOT_VERIFIED"}},
            "training": {
                "optimizer": {
                    "value": "Adam",
                    "status": "NOT_VERIFIED",
                    "provenance_type": "AUTHOR_REPORTED_FACT",
                    "sources": [_source(evidence)],
                },
                "learning_rate": {
                    "value": "1e-4",
                    "status": "NOT_VERIFIED",
                    "provenance_type": "AUTHOR_REPORTED_FACT",
                    "sources": [_source("The initial learning rate is explicitly given as 1e-4.")],
                },
                "batch_size": {
                    "value": 4,
                    "status": "NOT_VERIFIED",
                    "provenance_type": "AUTHOR_REPORTED_FACT",
                    "sources": [_source("The paper explicitly reports a batch size of four samples.")],
                },
            },
        }
    )
    repository.create_or_get(
        identity_key="additional-source",
        doi=None,
        record=record,
        workflow_status=PaperWorkflowStatus.EXTRACTED,
        warnings=[],
    )
    app = create_app(repository=repository)

    with TestClient(app) as client:
        body = client.get("/api/landing").json()

    optimizer = next(
        field for field in body["extraction_demo"]["fields"] if field["path"] == "training.optimizer"
    )
    assert optimizer["source"]["evidence"] is None
    assert optimizer["display_source"]["evidence"] == evidence


def test_verification_ledger_only_counts_extraction_attempted_papers(tmp_path: Path) -> None:
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    repository.initialize()
    _insert(repository, 1, scientific=True)
    bibliography_only_id = _insert(repository, 2, scientific=False)
    app = create_app(repository=repository)

    with TestClient(app) as client:
        body = client.get("/api/landing").json()
        missing = client.get(
            "/api/landing/drilldown",
            params={"dimension": "status", "key": "NOT_REPORTED", "limit": 200},
        ).json()

    assert body["totals"]["processed_papers"] == 1
    assert body["totals"]["indexed_not_processed"] == 1
    assert sum(item["fields"] for item in body["statuses"]) == body["totals"]["scientific_record_fields"]
    assert all(item["paper"]["id"] != bibliography_only_id for item in missing["evidence_items"])


def test_named_intelligence_excludes_unprocessed_source_linked_claims(tmp_path: Path) -> None:
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    repository.initialize()
    record = _record(3, scientific=True)
    repository.create_or_get(
        identity_key="unprocessed-source-linked",
        doi=None,
        record=record,
        workflow_status=PaperWorkflowStatus.INGESTED,
        warnings=[],
    )
    app = create_app(repository=repository)

    with TestClient(app) as client:
        landing = client.get("/api/landing").json()
        drilldown = client.get(
            "/api/landing/drilldown",
            params={"dimension": "architecture", "key": "Encoder-decoder"},
        ).json()

    assert landing["totals"]["processed_papers"] == 0
    assert landing["architecture_families"] == []
    assert landing["limitations"] == []
    assert drilldown["total"] == 0


def test_future_dated_records_are_flagged_and_excluded_from_year_chart(tmp_path: Path) -> None:
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    repository.initialize()
    record = PaperRecord.model_validate(
        {
            "paper": {
                "title": {"value": "Future metadata", "status": "NOT_VERIFIED"},
                "year": {"value": datetime.now().year + 1, "status": "NOT_VERIFIED"},
            }
        }
    )
    repository.create_or_get(
        identity_key="future-year",
        doi=None,
        record=record,
        workflow_status=PaperWorkflowStatus.INGESTED,
        warnings=[],
    )
    app = create_app(repository=repository)

    with TestClient(app) as client:
        body = client.get("/api/landing").json()

    assert body["totals"]["future_dated_papers"] == 1
    assert body["years"] == []


def test_conflict_demo_rejects_sentence_fragments_and_uses_plausible_bound_values(
    tmp_path: Path,
) -> None:
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    repository.initialize()
    bad_values = [
        "the grid is described in a long methods sentence",
        "another excerpt discussing resolution without a compact value",
    ]
    good_values = ["1/12°", "0.25°"]

    def conflict_record(title: str, values: list[str]) -> PaperRecord:
        return PaperRecord.model_validate(
            {
                "paper": {"title": {"value": title, "status": "NOT_VERIFIED"}},
                "data": {
                    "spatial_resolution": {
                        "status": "CONFLICT",
                        "provenance_type": "AUTHOR_REPORTED_FACT",
                        "conflict_values": values,
                        "source": {**_source(f"First excerpt for {values[0]}"), "claimed_value": values[0]},
                        "sources": [{**_source(f"Second excerpt for {values[1]}"), "claimed_value": values[1]}],
                    }
                },
            }
        )

    for key, record in (("bad-conflict", conflict_record("Bad", bad_values)), ("good-conflict", conflict_record("Good", good_values))):
        repository.create_or_get(
            identity_key=key,
            doi=None,
            record=record,
            workflow_status=PaperWorkflowStatus.EXTRACTED,
            warnings=[],
        )
    app = create_app(repository=repository)

    with TestClient(app) as client:
        demo = client.get("/api/landing").json()["conflict_demo"]

    assert demo["paper"]["title"] == "Good"
    assert demo["field"]["conflict_values"] == good_values
