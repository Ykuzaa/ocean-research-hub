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

    # Neither convention may be invented. The two fields then diverge on
    # whether absence is *provable*: the page uses the word "activation", so
    # absence of an activation function cannot be certified and the honest
    # outcome is a failure to extract. It names no normalization layer from
    # the closed vocabulary at all, so that absence is assertable and must
    # carry the search scope that establishes it.
    assert record.architecture.activations.value is None
    assert record.architecture.activations.status is VerificationStatus.EXTRACTION_ERROR
    assert record.architecture.activations.absence_search_scope == []
    assert record.architecture.normalization_layers.value is None
    assert record.architecture.normalization_layers.status is VerificationStatus.NOT_REPORTED
    assert record.architecture.normalization_layers.absence_search_scope


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


@pytest.mark.parametrize(
    "text",
    [
        "The training loss is used in Sect. 4.2 for all experiments.",
        "The loss function was also tested (Fig. 3) under noisy observations.",
        "The loss function is computed only on tracks from the current date.",
    ],
)
def test_deterministic_loss_capture_rejects_usage_or_evaluation_context_not_loss_identity(
    text: str,
) -> None:
    """Mentioning a loss is not evidence of which loss the authors selected.

    This protects the deterministic path too: it must not bypass the semantic
    provider's contextual guards merely because a broad regular expression can
    capture words following ``loss ... is/was``.
    """
    record = ScientificExtractor().extract(
        ParsedPdf(pages=[ParsedPage(4, text)], source_name="loss-context.pdf")
    ).record

    assert record.objective.primary_loss.status is VerificationStatus.NOT_REPORTED
    assert record.objective.primary_loss.value is None


def test_supplementary_semantic_claim_carries_the_pinned_supplement_url() -> None:
    """Supplement provenance needs a retrievable origin, not only an enum."""
    supplement_url = "https://example.test/paper-supplement.pdf"
    parsed = ParsedPdf(
        pages=[ParsedPage(1, "Primary paper.")],
        supplementary_pages=[ParsedPage(
            3, "The ablation removes the auxiliary loss during training."
        )],
        supplementary_search_scope=[supplement_url],
        source_name="primary.pdf",
    )
    record = PaperRecord()
    result = SemanticExtractor(client=_FakeSemanticClient([{
        "path": "evaluation.ablations",
        "value": ["removes the auxiliary loss"],
        "page": 3,
        "section": None,
        "evidence": "The ablation removes the auxiliary loss during training",
        "origin": "SUPPLEMENTARY_MATERIAL",
    }])).extract(parsed, record)

    assert result.accepted == ["evaluation.ablations"]
    assert record.evaluation.ablations.source.origin is SourceOrigin.SUPPLEMENTARY_MATERIAL
    assert str(record.evaluation.ablations.source.evidence_url) == supplement_url


def test_deterministic_architecture_family_rejects_a_baseline_or_related_work_mention() -> None:
    """A model named as a baseline is not necessarily the paper's architecture."""
    record = ScientificExtractor().extract(
        ParsedPdf(
            pages=[ParsedPage(
                6,
                "For comparison, we evaluate a Fourier neural operator baseline "
                "alongside the proposed regional method.",
            )],
            source_name="baseline-mention.pdf",
        )
    ).record

    assert record.architecture.family.status is VerificationStatus.NOT_REPORTED
    assert record.architecture.family.value is None


@pytest.mark.parametrize(
    ("text", "section", "field"),
    [
        (
            "For comparison, the baseline learning rate was 0.001.",
            "training", "learning_rate",
        ),
        (
            "Prior work reports a baseline batch size of 32.",
            "training", "batch_size",
        ),
        (
            "The related-work U-Net uses a dropout rate of 0.2.",
            "architecture", "dropout",
        ),
    ],
)
def test_deterministic_hyperparameters_reject_related_work_or_baseline_context(
    text: str, section: str, field: str,
) -> None:
    """A literal number is insufficient without binding it to this paper's run."""
    record = ScientificExtractor().extract(
        ParsedPdf(pages=[ParsedPage(6, text)], source_name="related-work.pdf")
    ).record
    extracted = getattr(getattr(record, section), field)

    assert extracted.value is None
    # Either non-claim state is acceptable here; what must never happen is the
    # other paper's number being stored as this paper's configuration.
    assert extracted.status in {
        VerificationStatus.NOT_REPORTED, VerificationStatus.EXTRACTION_ERROR,
    }


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


def test_absence_probe_asserts_absence_only_with_a_recorded_search_scope() -> None:
    """A provable absence is a finding and must carry the scope proving it."""
    field = ScientificExtractor().extract(ParsedPdf(
        pages=[ParsedPage(2, "We train a regional operator on reanalysis fields.")],
        source_name="silent-on-optimizer.pdf",
    )).record.training.optimizer

    assert field.status is VerificationStatus.NOT_REPORTED
    assert field.value is None
    assert any("silent-on-optimizer.pdf" in entry for entry in field.absence_search_scope)
    assert any("absence probe" in entry for entry in field.absence_search_scope)
    assert any(
        "no supplementary material was supplied" in entry
        for entry in field.absence_search_scope
    )


def test_absence_scope_names_the_supplement_when_one_was_searched() -> None:
    """Absence asserted over a supplement must say which supplement was read."""
    supplement_url = "https://example.test/supplement.pdf"
    field = ScientificExtractor().extract(ParsedPdf(
        pages=[ParsedPage(1, "We train a regional operator on reanalysis fields.")],
        supplementary_pages=[ParsedPage(1, "Additional forecast skill figures.")],
        supplementary_search_scope=[supplement_url],
        source_name="primary.pdf",
    )).record.training.optimizer

    assert field.status is VerificationStatus.NOT_REPORTED
    assert any(supplement_url in entry for entry in field.absence_search_scope)


@pytest.mark.parametrize(
    ("text", "section", "field"),
    [
        ("Training used the Adam optimiser described by prior work.", "training", "optimizer"),
        ("The learning rate follows the reference implementation.", "training", "learning_rate"),
        ("Each batch is assembled from consecutive daily fields.", "training", "batch_size"),
        ("A cosine schedule was considered during development.", "training", "scheduler"),
        ("The non-linearity is inherited from the operator block.", "architecture", "activations"),
    ],
)
def test_mentioned_but_ungroundable_field_is_an_extraction_error_not_an_absence(
    text: str, section: str, field: str,
) -> None:
    """Discussing a concept without a bindable value is a failure, not absence.

    This is the guard that keeps the absence probe scientifically honest: it may
    only certify absence when none of the field's vocabulary occurs at all.
    """
    extracted = getattr(getattr(ScientificExtractor().extract(ParsedPdf(
        pages=[ParsedPage(5, text)], source_name="mentioned.pdf",
    )).record, section), field)

    assert extracted.value is None
    assert extracted.status is VerificationStatus.EXTRACTION_ERROR
    assert extracted.absence_search_scope == []


def test_narrative_fields_never_receive_a_lexical_absence_assertion() -> None:
    """Open-vocabulary fields cannot be proven absent by keyword silence.

    The OceanNet supplement reports two ablation experiments without ever
    writing "ablation"; a lexical probe on such a field would manufacture a
    false scientific absence, so these paths are deliberately unprobed.
    """
    from ocean_research_hub.ingestion.pdf import ABSENCE_PROBES

    for path in (
        "scientific_framing.problem", "data.datasets", "architecture.family",
        "evaluation.ablations", "evaluation.baselines", "results.headline",
        "limitations.author_reported",
    ):
        assert path not in ABSENCE_PROBES

    record = ScientificExtractor().extract(ParsedPdf(
        pages=[ParsedPage(1, "A short note with no scientific detail at all.")],
        source_name="empty.pdf",
    )).record
    assert record.evaluation.ablations.absence_search_scope == []


def test_semantic_silence_cannot_overwrite_an_established_absence() -> None:
    """The model declining to propose a value is agreement, not a new failure."""
    parsed = ParsedPdf(
        pages=[ParsedPage(1, "We train a regional operator on reanalysis fields.")],
        source_name="silent.pdf",
    )
    record = ScientificExtractor().extract(parsed).record
    assert record.training.optimizer.status is VerificationStatus.NOT_REPORTED

    result = SemanticExtractor(client=_FakeSemanticClient([])).extract(parsed, record)

    assert record.training.optimizer.status is VerificationStatus.NOT_REPORTED
    assert record.training.optimizer.absence_search_scope
    assert "training.optimizer" not in result.errored


def test_located_semantic_evidence_overrides_a_probed_absence() -> None:
    """Absence is a default of last resort, not a lock against real evidence.

    The probe vocabulary is finite, so a paper can report a field in wording it
    does not contain. When the semantic pass then grounds a real quote, the
    claim must win and the now-false absence scope must be cleared.
    """
    parsed = ParsedPdf(
        pages=[ParsedPage(
            1,
            "Every reported experiment was executed on a single Grace Hopper "
            "accelerator provided by our institute.",
        )],
        source_name="unusual-hardware.pdf",
    )
    record = ScientificExtractor().extract(parsed).record
    assert record.training.hardware.status is VerificationStatus.NOT_REPORTED

    SemanticExtractor(client=_FakeSemanticClient([{
        "path": "training.hardware",
        "value": "a single Grace Hopper accelerator",
        "page": 1,
        "section": None,
        "evidence": "executed on a single Grace Hopper accelerator provided by our institute",
        "origin": "PRIMARY_PAPER",
    }])).extract(parsed, record)

    assert record.training.hardware.status is VerificationStatus.NOT_VERIFIED
    assert record.training.hardware.value == ["a single Grace Hopper accelerator"]
    assert record.training.hardware.absence_search_scope == []
