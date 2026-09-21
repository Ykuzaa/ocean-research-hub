"""Independent QA regressions for issue #19 extraction safety.

These fixtures intentionally use non-golden prose.  They protect the public
extractor contract rather than a paper title, a pre-computed page number, or a
known expected-value registry.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from ocean_research_hub.ingestion.pdf import (
    ParsedPage,
    ParsedPdf,
    ScientificExtractor,
    set_extracted_field,
)
from ocean_research_hub.ingestion.semantic import SemanticExtractor
from ocean_research_hub.schemas.paper_record import (
    PaperRecord,
    SourceEvidence,
    SourceOrigin,
    TextField,
    VerificationStatus,
)


class _FakeSemanticClient:
    def __init__(self, claims: object) -> None:
        self.claims = claims

    def propose_claims(self, prompt: str) -> str:
        return json.dumps(self.claims)


@pytest.mark.parametrize(
    ("source_name", "text", "optimizer", "batch_size"),
    [
        (
            "unseen-regional-forecast.pdf",
            "A convolutional neural network forecasts coastal SSH. "
            "Training used an SGD optimizer with batch size of 7. "
            "The spatial resolution is 0.25 degrees.",
            "SGD",
            7,
        ),
        (
            "unseen-assimilation-study.pdf",
            "A graph neural network is evaluated for ocean reconstruction. "
            "We used an AdamW optimizer and batch size was 16. "
            "The horizontal resolution was 4 km.",
            "AdamW",
            16,
        ),
    ],
)
def test_two_non_golden_documents_use_the_shared_extractor_path(
    source_name: str, text: str, optimizer: str, batch_size: int,
) -> None:
    """Common explicit phrasing must not depend on a golden-paper profile."""
    record = ScientificExtractor().extract(
        ParsedPdf(pages=[ParsedPage(7, text)], source_name=source_name)
    ).record

    assert record.training.optimizer.value == optimizer
    assert record.training.batch_size.value == batch_size
    for field in (record.training.optimizer, record.training.batch_size):
        assert field.status is VerificationStatus.NOT_VERIFIED
        assert field.source.is_locatable
        assert field.source.origin is SourceOrigin.PRIMARY_PAPER


def test_profile_like_title_cannot_disable_or_replace_shared_source_extraction() -> None:
    """A title formerly used as a golden profile must not select fixed facts."""
    record = ScientificExtractor().extract(
        ParsedPdf(
            pages=[ParsedPage(
                1,
                "4DVarNet-SSH: end-to-end learning. "
                "This independent reproduction used an SGD optimizer with batch size of 9.",
            )],
            source_name="independent-reproduction.pdf",
        )
    ).record

    assert record.training.optimizer.value == "SGD"
    assert record.training.batch_size.value == 9
    assert record.training.optimizer.source.evidence == "SGD optimizer"


def test_architecture_conventions_are_not_inferred_when_the_source_is_silent() -> None:
    record = ScientificExtractor().extract(
        ParsedPdf(
            pages=[ParsedPage(
                3,
                "Our Transformer uses attention blocks for sea-level forecasting. "
                "No activation or normalization implementation detail is specified here.",
            )],
            source_name="no-conventions.pdf",
        )
    ).record

    assert record.architecture.activations.status is VerificationStatus.NOT_REPORTED
    assert record.architecture.activations.value is None
    assert record.architecture.normalization_layers.status is VerificationStatus.NOT_REPORTED
    assert record.architecture.normalization_layers.value is None


def test_unverified_claims_require_locatable_evidence() -> None:
    with pytest.raises(ValidationError, match="locatable source evidence"):
        TextField(value="Adam", status="NOT_VERIFIED")
    with pytest.raises(ValidationError, match="locatable source evidence"):
        TextField(
            value="Adam",
            status="NOT_VERIFIED",
            source={"evidence": "Adam optimizer"},
        )


@pytest.mark.parametrize("origin", ["SECONDARY_SOURCE", "NOT_A_SOURCE"])
def test_semantic_claims_with_invalid_or_secondary_origin_fail_closed(origin: str) -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(1, "The architecture uses a dropout rate of 0.2.")],
        source_name="semantic-origin.pdf",
    )
    record = PaperRecord()
    result = SemanticExtractor(client=_FakeSemanticClient([
        {
            "path": "architecture.dropout",
            "value": 0.2,
            "page": 1,
            "section": None,
            "evidence": "dropout rate of 0.2",
            "origin": origin,
        },
    ])).extract(parsed, record)

    assert result.accepted == []
    assert result.rejected == ["architecture.dropout"]
    assert record.architecture.dropout.status is VerificationStatus.EXTRACTION_ERROR
    assert record.architecture.dropout.value is None


def test_semantic_example_language_cannot_become_a_reported_configuration() -> None:
    """An illustrative loss option is not evidence that the authors used it."""
    parsed = ParsedPdf(
        pages=[ParsedPage(
            5,
            "For a deployment-specific objective, a suitable loss function "
            "(e.g., mean squared error) may be selected by a future user.",
        )],
        source_name="illustrative-loss-only.pdf",
    )
    record = PaperRecord()
    result = SemanticExtractor(client=_FakeSemanticClient([
        {
            "path": "objective.primary_loss",
            "value": "mean squared error",
            "page": 5,
            "section": None,
            "evidence": "a suitable loss function (e.g., mean squared error) may be selected",
            "origin": "PRIMARY_PAPER",
        },
    ])).extract(parsed, record)

    assert result.accepted == []
    assert result.rejected == ["objective.primary_loss"]
    assert record.objective.primary_loss.status is VerificationStatus.EXTRACTION_ERROR
    assert record.objective.primary_loss.value is None


def test_third_distinct_claim_extends_conflict_instead_of_overwriting_it() -> None:
    record = PaperRecord()
    for page, optimizer in enumerate(("Adam", "SGD", "AdamW"), start=1):
        set_extracted_field(
            record,
            "training.optimizer",
            optimizer,
            [SourceEvidence(
                page=page,
                section="Methods",
                locator=f"paragraph {page}",
                evidence=f"We used {optimizer} optimizer.",
                origin=SourceOrigin.PRIMARY_PAPER,
            )],
        )

    field = record.training.optimizer
    assert field.status is VerificationStatus.CONFLICT
    assert field.value is None
    assert field.conflict_values == ["Adam", "SGD", "AdamW"]
    assert [source.claimed_value for source in [field.source, *field.sources]] == [
        "Adam", "SGD", "AdamW",
    ]
