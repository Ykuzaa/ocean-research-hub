"""Integration coverage for issue #4's read-only two-paper comparison.

All paper content in this module is deliberately labelled synthetic. The
fixtures exercise rendering and transport; they are not scientific claims.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest
from fastapi.testclient import TestClient

from ocean_research_hub.api import create_app
from ocean_research_hub.ingestion.repository import SqlitePaperRepository


@pytest.fixture
def repository(tmp_path: Path) -> SqlitePaperRepository:
    return SqlitePaperRepository(tmp_path / "comparison.db")


@pytest.fixture
def client(repository: SqlitePaperRepository) -> TestClient:
    with TestClient(create_app(repository=repository)) as test_client:
        yield test_client


def evidence_field(
    value: object,
    *,
    status: str = "VERIFIED",
    provenance_type: str = "AUTHOR_REPORTED_FACT",
    page: int = 2,
    evidence: str = "The synthetic fixture explicitly reports this value.",
) -> dict[str, object]:
    return {
        "value": value,
        "status": status,
        "provenance_type": provenance_type,
        "source": {
            "origin": "PRIMARY_PAPER",
            "section": "Synthetic fixture",
            "page": page,
            "locator": "comparison test claim",
            "evidence": evidence,
        },
    }


def comparison_payload(
    title: str,
    *,
    family: str,
    task_type: str,
    ai_interpretation: str | None = None,
) -> dict[str, object]:
    limitations: dict[str, object] = {
        "author_reported": evidence_field(
            ["Synthetic author-reported limitation"],
            provenance_type="AUTHOR_REPORTED_LIMITATION",
            page=8,
        )
    }
    if ai_interpretation:
        limitations["ai_interpretation"] = {
            "value": [ai_interpretation],
            "status": "NOT_VERIFIED",
            "provenance_type": "AI_INTERPRETATION",
        }
    return {
        "paper": {"title": evidence_field(title, page=1, evidence=title)},
        "scientific_framing": {
            "task_type": evidence_field([task_type], page=1),
        },
        "data": {
            "datasets": evidence_field([f"Synthetic dataset for {title}"], page=2),
            "variables": evidence_field(
                ["synthetic sea-surface variable"],
                status="PARTIALLY_VERIFIED",
                page=2,
            ),
        },
        "architecture": {"family": evidence_field([family], page=3)},
        "training": {"optimizer": evidence_field("Synthetic optimizer", page=4)},
        "objective": {"primary_loss": evidence_field("Synthetic loss", page=5)},
        "evaluation": {"metrics": evidence_field(["Synthetic metric"], page=6)},
        "results": {"headline": evidence_field(["Synthetic result"], page=7)},
        "limitations": limitations,
    }


def ingest(client: TestClient, payload: dict[str, object]) -> dict[str, object]:
    response = client.post("/api/papers/ingest", json={"parsed_paper": payload})
    assert response.status_code == 201
    return response.json()["paper"]


def test_global_forecasting_pair_has_ordered_api_and_all_comparison_sections(
    client: TestClient,
) -> None:
    left = ingest(
        client,
        comparison_payload(
            "Synthetic global forecast A",
            family="Synthetic transformer",
            task_type="global ocean forecasting",
        ),
    )
    right = ingest(
        client,
        comparison_payload(
            "Synthetic global forecast B",
            family="Synthetic neural operator",
            task_type="global ocean forecasting",
        ),
    )

    api = client.get(
        "/api/papers/compare",
        params={"left_id": left["id"], "right_id": right["id"]},
    )
    page = client.get(
        "/papers/compare",
        params={"left_id": left["id"], "right_id": right["id"]},
    )

    assert api.status_code == 200
    assert api.json()["left"]["id"] == left["id"]
    assert api.json()["right"]["id"] == right["id"]
    assert api.json()["left"]["record"] == left["record"]
    assert page.status_code == 200
    for section_id in (
        "data",
        "architecture",
        "training",
        "objective",
        "evaluation",
        "results",
        "limitations",
    ):
        assert f'<section id="{section_id}">' in page.text
    assert page.text.index("Synthetic global forecast A") < page.text.index(
        "Synthetic global forecast B"
    )


def test_heterogeneous_pair_preserves_status_evidence_absence_and_provenance(
    client: TestClient,
) -> None:
    forecast = ingest(
        client,
        comparison_payload(
            "Synthetic forecast fixture",
            family="Synthetic forecast model",
            task_type="forecasting",
        ),
    )
    reconstruction = ingest(
        client,
        comparison_payload(
            "Synthetic reconstruction fixture",
            family="Synthetic variational model",
            task_type="reconstruction and data assimilation",
            ai_interpretation="Synthetic AI-only research-gap interpretation",
        ),
    )

    page = client.get(
        "/papers/compare",
        params={"left_id": forecast["id"], "right_id": reconstruction["id"]},
    )

    assert page.status_code == 200
    assert 'data-field="data.datasets"' in page.text
    assert 'data-status="VERIFIED"' in page.text
    assert 'data-status="PARTIALLY_VERIFIED"' in page.text
    assert "Inspect source evidence" in page.text
    assert "Synthetic fixture, page 2, comparison test claim" in page.text
    assert "The synthetic fixture explicitly reports this value." in page.text
    assert 'data-status="NOT_REPORTED"' in page.text
    assert ">NOT_REPORTED<br>" in page.text
    assert 'data-provenance="AUTHOR_REPORTED_LIMITATION"' in page.text
    assert 'data-provenance="AI_INTERPRETATION"' in page.text
    assert 'class="comparison-value ai-interpretation"' in page.text
    assert "Synthetic AI-only research-gap interpretation" in page.text
    compared_cells = re.findall(r'<td class="comparison-value.*?</td>', page.text)
    assert compared_cells
    assert all(
        'data-status="' in cell and 'data-provenance="' in cell
        for cell in compared_cells
    )


def test_conflict_alternatives_and_bound_evidence_remain_visible(
    client: TestClient,
) -> None:
    left_payload = comparison_payload(
        "Synthetic conflict fixture",
        family="Synthetic model",
        task_type="forecasting",
    )
    left_payload["training"] = {
        "optimizer": {
            "status": "CONFLICT",
            "conflict_values": ["Synthetic optimizer A", "Synthetic optimizer B"],
            "source": {
                "origin": "PRIMARY_PAPER",
                "page": 4,
                "locator": "synthetic methods",
                "evidence": "The synthetic methods say optimizer A.",
                "claimed_value": "Synthetic optimizer A",
            },
            "sources": [
                {
                    "origin": "SUPPLEMENTARY_MATERIAL",
                    "page": 12,
                    "locator": "synthetic supplement",
                    "evidence": "The synthetic supplement says optimizer B.",
                    "claimed_value": "Synthetic optimizer B",
                }
            ],
        }
    }
    left = ingest(client, left_payload)
    right = ingest(
        client,
        comparison_payload(
            "Synthetic conflict comparator",
            family="Synthetic model",
            task_type="forecasting",
        ),
    )

    page = client.get(
        "/papers/compare",
        params={"left_id": left["id"], "right_id": right["id"]},
    )

    assert page.status_code == 200
    assert 'data-status="CONFLICT"' in page.text
    assert "Synthetic optimizer A" in page.text
    assert "Synthetic optimizer B" in page.text
    assert "Supports:" in page.text
    assert "SUPPLEMENTARY_MATERIAL, page 12, synthetic supplement" in page.text


def test_null_extraction_error_is_not_rendered_as_not_reported(
    client: TestClient,
) -> None:
    failed_payload = comparison_payload(
        "Synthetic extraction failure fixture",
        family="Synthetic model",
        task_type="forecasting",
    )
    failed_payload["training"] = {
        "optimizer": {
            "value": None,
            "status": "EXTRACTION_ERROR",
            "provenance_type": "AUTHOR_REPORTED_FACT",
        }
    }
    failed = ingest(client, failed_payload)
    comparator = ingest(
        client,
        comparison_payload(
            "Synthetic extraction failure comparator",
            family="Synthetic model",
            task_type="forecasting",
        ),
    )

    page = client.get(
        "/papers/compare",
        params={"left_id": failed["id"], "right_id": comparator["id"]},
    )

    assert page.status_code == 200
    optimizer_row = re.search(
        r'<tr data-field="training.optimizer">(.*?)</tr>', page.text
    )
    assert optimizer_row is not None
    left_cell = re.search(r"<td .*?</td>", optimizer_row.group(1))
    assert left_cell is not None
    assert 'data-status="EXTRACTION_ERROR"' in left_cell.group(0)
    assert "EXTRACTION_ERROR (no extracted value)" in left_cell.group(0)
    assert ">NOT_REPORTED<br>" not in left_cell.group(0)


def test_comparison_rejects_same_id_and_reports_missing_papers(
    client: TestClient,
) -> None:
    paper = ingest(
        client,
        comparison_payload(
            "Synthetic request validation fixture",
            family="Synthetic model",
            task_type="forecasting",
        ),
    )

    same = client.get(
        "/api/papers/compare",
        params={"left_id": paper["id"], "right_id": paper["id"]},
    )
    missing = client.get(
        "/papers/compare",
        params={"left_id": paper["id"], "right_id": "missing-paper"},
    )

    assert same.status_code == 422
    assert same.json() == {
        "error": {
            "code": "INVALID_COMPARISON",
            "message": "comparison requires two distinct paper IDs",
        }
    }
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PAPER_NOT_FOUND"


def test_comparison_escapes_scientific_values_and_evidence(client: TestClient) -> None:
    left = ingest(
        client,
        comparison_payload(
            "Synthetic <script>alert(1)</script>",
            family="Synthetic <model>",
            task_type="forecasting",
        ),
    )
    right = ingest(
        client,
        comparison_payload(
            "Synthetic safe comparator",
            family="Synthetic model",
            task_type="forecasting",
        ),
    )

    page = client.get(
        "/papers/compare",
        params={"left_id": left["id"], "right_id": right["id"]},
    )

    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text
    assert "Synthetic &lt;model&gt;" in page.text


def test_comparison_escapes_source_locations_claims_and_evidence(
    client: TestClient,
) -> None:
    payload = comparison_payload(
        "Synthetic escaped source fixture",
        family="Synthetic model",
        task_type="forecasting",
    )
    payload["data"] = {
        "datasets": {
            "value": ["Synthetic safe dataset"],
            "status": "VERIFIED",
            "provenance_type": "AUTHOR_REPORTED_FACT",
            "source": {
                "origin": "PRIMARY_PAPER",
                "section": "<img src=x onerror=alert(1)>",
                "page": 2,
                "locator": "<svg/onload=alert(2)>",
                "evidence": "<script>alert(3)</script>",
            },
        }
    }
    left = ingest(client, payload)
    right = ingest(
        client,
        comparison_payload(
            "Synthetic source comparator",
            family="Synthetic model",
            task_type="forecasting",
        ),
    )

    page = client.get(
        "/papers/compare", params={"left_id": left["id"], "right_id": right["id"]}
    )

    assert page.status_code == 200
    for unsafe_fragment in (
        "<img src=x onerror=alert(1)>",
        "<svg/onload=alert(2)>",
        "<script>alert(3)</script>",
    ):
        assert unsafe_fragment not in page.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in page.text
    assert "&lt;svg/onload=alert(2)&gt;" in page.text
    assert "&lt;script&gt;alert(3)&lt;/script&gt;" in page.text


def test_comparison_is_read_only_and_reversing_ids_reverses_only_order(
    client: TestClient, repository: SqlitePaperRepository
) -> None:
    left = ingest(
        client,
        comparison_payload(
            "Synthetic ordered left",
            family="Synthetic model A",
            task_type="global forecasting",
        ),
    )
    right = ingest(
        client,
        comparison_payload(
            "Synthetic ordered right",
            family="Synthetic model B",
            task_type="global forecasting",
        ),
    )
    before_left = repository.get(left["id"]).model_dump(mode="json")
    before_right = repository.get(right["id"]).model_dump(mode="json")

    forward = client.get(
        "/api/papers/compare", params={"left_id": left["id"], "right_id": right["id"]}
    )
    reverse = client.get(
        "/api/papers/compare", params={"left_id": right["id"], "right_id": left["id"]}
    )

    assert forward.status_code == reverse.status_code == 200
    assert [paper["id"] for paper in (forward.json()["left"], forward.json()["right"])] == [
        left["id"],
        right["id"],
    ]
    assert [paper["id"] for paper in (reverse.json()["left"], reverse.json()["right"])] == [
        right["id"],
        left["id"],
    ]
    assert repository.get(left["id"]).model_dump(mode="json") == before_left
    assert repository.get(right["id"]).model_dump(mode="json") == before_right


def test_comparison_missing_and_malformed_id_queries_fail_without_mutation(
    client: TestClient, repository: SqlitePaperRepository
) -> None:
    paper = ingest(
        client,
        comparison_payload(
            "Synthetic malformed-id fixture",
            family="Synthetic model",
            task_type="forecasting",
        ),
    )
    before = repository.get(paper["id"]).model_dump(mode="json")

    missing_parameter = client.get("/api/papers/compare", params={"left_id": paper["id"]})
    malformed_identifier = client.get(
        "/api/papers/compare", params={"left_id": paper["id"], "right_id": "not/a/stored/id"}
    )

    assert missing_parameter.status_code == 422
    assert malformed_identifier.status_code == 404
    assert malformed_identifier.json()["error"]["code"] == "PAPER_NOT_FOUND"
    assert repository.get(paper["id"]).model_dump(mode="json") == before


def test_static_comparison_routes_take_precedence_and_repository_failures_are_safe(
    client: TestClient, repository: SqlitePaperRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If the static route were shadowed by /{paper_id}, this would return a
    # PAPER_NOT_FOUND error for an ID named "compare", not parameter validation.
    assert client.get("/api/papers/compare").status_code == 422
    assert client.get("/papers/compare").status_code == 422

    def broken_get(_: str) -> object:
        raise OSError("synthetic locked database")

    monkeypatch.setattr(repository, "get", broken_get)
    for endpoint in ("/api/papers/compare", "/papers/compare"):
        response = client.get(endpoint, params={"left_id": "left", "right_id": "right"})
        assert response.status_code == 503
        assert response.json() == {
            "error": {
                "code": "PERSISTENCE_ERROR",
                "message": "paper repository read failed",
            }
        }
