import json

import pytest

from ocean_research_hub.ingestion.pdf import ParsedPage, ParsedPdf, ScientificExtractor
from ocean_research_hub.ingestion.semantic import (
    AnthropicClient, GeminiClient, SemanticExtractionError, SemanticExtractor, field_catalog,
)
from ocean_research_hub.schemas.paper_record import PaperRecord, VerificationStatus


class FakeLLMClient:
    """Structural stand-in for SemanticLLMClient: returns a canned JSON payload."""

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.last_prompt: str | None = None

    def propose_claims(self, prompt: str) -> str:
        self.last_prompt = prompt
        return json.dumps(self.payload)


class ExplodingLLMClient:
    def propose_claims(self, prompt: str) -> str:
        raise SemanticExtractionError("simulated transport failure")


def _parsed_pdf() -> ParsedPdf:
    return ParsedPdf(
        pages=[
            ParsedPage(1, "We use a dropout rate of 0.2 throughout the network."),
            ParsedPage(2, "Training used 4 NVIDIA A100 GPUs for 12 hours."),
        ],
        source_name="paper.pdf",
        supplementary_pages=[
            ParsedPage(1, "Ablation: removing the auxiliary loss reduces accuracy by 3 points."),
        ],
    )


def test_field_catalog_includes_readable_bibliography_but_not_identifiers() -> None:
    catalog = dict(field_catalog(PaperRecord()))
    assert catalog["paper.title"] is str
    assert catalog["paper.year"] is int
    assert "paper.doi" not in catalog
    assert "paper.arxiv" not in catalog
    assert "paper.urls" not in catalog
    assert catalog["architecture.dropout"] is float
    assert catalog["training.gpu_count"] is int
    assert catalog["architecture.family"] == list[str]


def test_field_catalog_excludes_ai_interpretation_and_team_note_limitations() -> None:
    # These hold interpretation/human annotation by construction, never a
    # literal author claim - asking the LLM to "quote verbatim PDF evidence"
    # for them is a category error the schema's provenance rules reject.
    catalog = dict(field_catalog(PaperRecord()))
    assert "limitations.ai_interpretation" not in catalog
    assert "limitations.team_note" not in catalog
    assert "limitations.author_reported" in catalog


def test_accepted_claim_requires_verbatim_locatable_evidence() -> None:
    parsed = _parsed_pdf()
    client = FakeLLMClient([
        {
            "path": "architecture.dropout", "value": 0.2, "page": 1,
            "section": None, "evidence": "a dropout rate of 0.2", "origin": "PRIMARY_PAPER",
        },
    ])
    extractor = SemanticExtractor(client=client)
    record = PaperRecord()

    result = extractor.extract(parsed, record)

    assert result.accepted == ["architecture.dropout"]
    assert record.architecture.dropout.status == VerificationStatus.NOT_VERIFIED
    assert record.architecture.dropout.value == 0.2
    assert record.architecture.dropout.source.evidence == "a dropout rate of 0.2"
    assert "architecture.dropout" in client.last_prompt


def test_claim_with_fabricated_evidence_is_rejected_and_marked_extraction_error() -> None:
    parsed = _parsed_pdf()
    client = FakeLLMClient([
        {
            "path": "architecture.dropout", "value": 0.5, "page": 1,
            "section": None, "evidence": "dropout rate of 0.5 is used everywhere",
            "origin": "PRIMARY_PAPER",
        },
    ])
    extractor = SemanticExtractor(client=client)
    record = PaperRecord()

    result = extractor.extract(parsed, record)

    assert result.rejected == ["architecture.dropout"]
    assert record.architecture.dropout.status == VerificationStatus.EXTRACTION_ERROR
    assert record.architecture.dropout.value is None


def test_claim_with_correctly_located_evidence_but_an_inconsistent_value_is_rejected() -> None:
    # The quote is real and genuinely on the cited page, but the claimed
    # value (0.5) does not match what the quote actually supports (0.2). A
    # correctly-located quote alone must not be enough to accept a claim.
    parsed = _parsed_pdf()
    client = FakeLLMClient([
        {
            "path": "architecture.dropout", "value": 0.5, "page": 1,
            "section": None, "evidence": "a dropout rate of 0.2 throughout the network",
            "origin": "PRIMARY_PAPER",
        },
    ])
    extractor = SemanticExtractor(client=client)
    record = PaperRecord()

    result = extractor.extract(parsed, record)

    assert result.rejected == ["architecture.dropout"]
    assert record.architecture.dropout.status == VerificationStatus.EXTRACTION_ERROR
    assert record.architecture.dropout.value is None


def test_illustrative_example_is_not_accepted_as_selected_configuration() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(
            9,
            "Training minimizes a suitable loss function, e.g., mean squared error.",
        )],
        source_name="paper.pdf",
    )
    client = FakeLLMClient([{
        "path": "objective.primary_loss", "value": "mean squared error", "page": 9,
        "section": None,
        "evidence": "a suitable loss function, e.g., mean squared error",
        "origin": "PRIMARY_PAPER",
    }])
    record = PaperRecord()

    result = SemanticExtractor(client=client).extract(parsed, record)

    assert result.rejected == ["objective.primary_loss"]
    assert record.objective.primary_loss.status == VerificationStatus.EXTRACTION_ERROR


def test_composite_claim_requires_evidence_for_every_numeric_component() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(8, "Wind fields have 6 h temporal and 1/4° spatial resolution.")],
        source_name="paper.pdf",
    )
    client = FakeLLMClient([{
        "path": "data.spatial_resolution",
        "value": "4 km SST and chlorophyll, 1/4° winds, and 0.25° altimetry",
        "page": 8, "section": None,
        "evidence": "Wind fields have 6 h temporal and 1/4° spatial resolution",
        "origin": "PRIMARY_PAPER",
    }])

    result = SemanticExtractor(client=client).extract(parsed, PaperRecord())

    assert result.rejected == ["data.spatial_resolution"]


def test_loss_evaluation_scope_is_not_accepted_as_loss_identity() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(8, "The loss function is computed only on tracks from the current date.")],
        source_name="paper.pdf",
    )
    client = FakeLLMClient([{
        "path": "objective.primary_loss",
        "value": "loss function computed only on tracks from the current date",
        "page": 8, "section": None,
        "evidence": "The loss function is computed only on tracks from the current date",
        "origin": "PRIMARY_PAPER",
    }])

    result = SemanticExtractor(client=client).extract(parsed, PaperRecord())

    assert result.rejected == ["objective.primary_loss"]


def test_single_loss_component_is_not_accepted_as_the_primary_objective() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(8, "The first term is the L2 norm of the difference between states.")],
        source_name="paper.pdf",
    )
    client = FakeLLMClient([{
        "path": "objective.primary_loss", "value": "L2 norm of the difference",
        "page": 8, "section": None,
        "evidence": "The first term is the L2 norm of the difference between states",
        "origin": "PRIMARY_PAPER",
    }])

    result = SemanticExtractor(client=client).extract(parsed, PaperRecord())

    assert result.rejected == ["objective.primary_loss"]


def test_full_selected_training_loss_identity_is_accepted() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(8, "The training loss combines reconstruction and regularization losses.")],
        source_name="paper.pdf",
    )
    client = FakeLLMClient([{
        "path": "objective.primary_loss",
        "value": "reconstruction and regularization losses", "page": 8,
        "section": None,
        "evidence": "The training loss combines reconstruction and regularization losses",
        "origin": "PRIMARY_PAPER",
    }])

    result = SemanticExtractor(client=client).extract(parsed, PaperRecord())

    assert result.accepted == ["objective.primary_loss"]


def test_positive_reproducibility_statement_is_not_a_limitation() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(10, "The code is open source to enable reproducibility of all experiments.")],
        source_name="paper.pdf",
    )
    client = FakeLLMClient([{
        "path": "limitations.reproducibility",
        "value": ["code is open source to enable reproducibility"], "page": 10,
        "section": None,
        "evidence": "The code is open source to enable reproducibility of all experiments",
        "origin": "PRIMARY_PAPER",
    }])

    result = SemanticExtractor(client=client).extract(parsed, PaperRecord())

    assert result.rejected == ["limitations.reproducibility"]


def test_reported_limitation_requires_an_explicit_limitation_cue() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(10, "Scaling to the global ocean remains a key challenge for this model.")],
        source_name="paper.pdf",
    )
    client = FakeLLMClient([{
        "path": "limitations.author_reported",
        "value": ["scaling to the global ocean remains a key challenge"], "page": 10,
        "section": None,
        "evidence": "Scaling to the global ocean remains a key challenge for this model",
        "origin": "PRIMARY_PAPER",
    }])

    result = SemanticExtractor(client=client).extract(parsed, PaperRecord())

    assert result.accepted == ["limitations.author_reported"]


def test_metric_acronym_must_appear_literally_in_evidence() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(6, "Metrics include root mean square error and mean absolute error (MAE).")],
        source_name="paper.pdf",
    )
    client = FakeLLMClient([{
        "path": "evaluation.metrics",
        "value": ["root mean square error (RMSE)", "mean absolute error (MAE)"],
        "page": 6, "section": None,
        "evidence": "Metrics include root mean square error and mean absolute error (MAE)",
        "origin": "PRIMARY_PAPER",
    }])

    result = SemanticExtractor(client=client).extract(parsed, PaperRecord())

    assert result.rejected == ["evaluation.metrics"]


def test_evaluation_dataset_requires_a_data_or_evaluation_relation() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(7, "We use BOOST-SWOT DC metrics for comparison with prior methods.")],
        source_name="paper.pdf",
    )
    client = FakeLLMClient([{
        "path": "evaluation.evaluation_datasets", "value": ["BOOST-SWOT DC"],
        "page": 7, "section": None,
        "evidence": "We use BOOST-SWOT DC metrics for comparison with prior methods",
        "origin": "PRIMARY_PAPER",
    }])

    result = SemanticExtractor(client=client).extract(parsed, PaperRecord())

    assert result.rejected == ["evaluation.evaluation_datasets"]


def test_unicode_scientific_minus_is_normalized_in_accepted_string_values() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(7, "We train the model with a learning rate of 5e−5 throughout.")],
        source_name="paper.pdf",
    )
    client = FakeLLMClient([{
        "path": "training.learning_rate", "value": "5e−5", "page": 7,
        "section": None, "evidence": "a learning rate of 5e−5 throughout",
        "origin": "PRIMARY_PAPER",
    }])
    record = PaperRecord()

    result = SemanticExtractor(client=client).extract(parsed, record)

    assert result.accepted == ["training.learning_rate"]
    assert record.training.learning_rate.value == "5e-5"


def test_claim_citing_the_wrong_page_is_rejected() -> None:
    parsed = _parsed_pdf()
    client = FakeLLMClient([
        {
            # This text is really on page 1, not page 2.
            "path": "architecture.dropout", "value": 0.2, "page": 2,
            "section": None, "evidence": "a dropout rate of 0.2", "origin": "PRIMARY_PAPER",
        },
    ])
    extractor = SemanticExtractor(client=client)
    record = PaperRecord()

    result = extractor.extract(parsed, record)

    assert result.rejected == ["architecture.dropout"]
    assert record.architecture.dropout.status == VerificationStatus.EXTRACTION_ERROR


@pytest.mark.parametrize("origin", ["SECONDARY_SOURCE", "NOT_A_REAL_ORIGIN"])
def test_claim_with_non_author_source_origin_is_rejected(origin: str) -> None:
    client = FakeLLMClient([
        {
            "path": "architecture.dropout", "value": 0.2, "page": 1,
            "section": None, "evidence": "a dropout rate of 0.2 throughout the network",
            "origin": origin,
        },
    ])
    record = PaperRecord()

    result = SemanticExtractor(client=client).extract(_parsed_pdf(), record)

    assert result.rejected == ["architecture.dropout"]
    assert record.architecture.dropout.status == VerificationStatus.EXTRACTION_ERROR


def test_type_mismatched_value_is_rejected_rather_than_coerced() -> None:
    parsed = _parsed_pdf()
    client = FakeLLMClient([
        {
            "path": "training.gpu_count", "value": "four", "page": 2,
            "section": None, "evidence": "4 NVIDIA A100 GPUs for 12 hours",
            "origin": "PRIMARY_PAPER",
        },
    ])
    extractor = SemanticExtractor(client=client)
    record = PaperRecord()

    result = extractor.extract(parsed, record)

    assert result.rejected == ["training.gpu_count"]
    assert record.training.gpu_count.value is None


def test_claim_for_a_path_outside_the_requested_catalog_is_ignored() -> None:
    parsed = _parsed_pdf()
    client = FakeLLMClient([
        {
            "path": "paper.title", "value": "Injected Title", "page": 1,
            "section": None, "evidence": "a dropout rate of 0.2", "origin": "PRIMARY_PAPER",
        },
        {
            "path": "not.a.real.path", "value": "x", "page": 1,
            "section": None, "evidence": "a dropout rate of 0.2", "origin": "PRIMARY_PAPER",
        },
    ])
    extractor = SemanticExtractor(client=client)
    record = PaperRecord()

    result = extractor.extract(parsed, record)

    assert result.accepted == []
    assert record.paper.title.value is None


def test_already_resolved_field_is_never_included_in_the_prompt_or_overwritten() -> None:
    parsed = _parsed_pdf()
    record = PaperRecord()
    record.architecture.dropout.status = VerificationStatus.NOT_VERIFIED
    record.architecture.dropout.value = 0.9
    client = FakeLLMClient([
        {
            "path": "architecture.dropout", "value": 0.2, "page": 1,
            "section": None, "evidence": "a dropout rate of 0.2", "origin": "PRIMARY_PAPER",
        },
    ])
    extractor = SemanticExtractor(client=client)

    extractor.extract(parsed, record)

    assert "architecture.dropout" not in client.last_prompt
    assert record.architecture.dropout.value == 0.9


def test_supplementary_material_claim_is_validated_against_supplementary_pages() -> None:
    parsed = _parsed_pdf()
    client = FakeLLMClient([
        {
            "path": "evaluation.ablations", "value": ["removing the auxiliary loss"], "page": 1,
            "section": None, "evidence": "removing the auxiliary loss reduces accuracy by 3 points",
            "origin": "SUPPLEMENTARY_MATERIAL",
        },
    ])
    extractor = SemanticExtractor(client=client)
    record = PaperRecord()

    result = extractor.extract(parsed, record)

    assert result.accepted == ["evaluation.ablations"]
    assert record.evaluation.ablations.source.origin == "SUPPLEMENTARY_MATERIAL"


def test_llm_transport_failure_raises_rather_than_being_treated_as_absence() -> None:
    extractor = SemanticExtractor(client=ExplodingLLMClient())

    with pytest.raises(SemanticExtractionError):
        extractor.extract(_parsed_pdf(), PaperRecord())


def test_gemini_client_fails_closed_without_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(SemanticExtractionError, match="GEMINI_API_KEY"):
        GeminiClient(api_key=None)


def test_anthropic_client_fails_closed_without_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SemanticExtractionError, match="ANTHROPIC_API_KEY"):
        AnthropicClient(api_key=None)


def test_claims_wrapped_in_a_markdown_fence_are_still_parsed() -> None:
    # Some providers wrap JSON in ```json ... ``` despite instructions not to.
    parsed = _parsed_pdf()

    class FencedClient:
        def propose_claims(self, prompt: str) -> str:
            return (
                "```json\n"
                '[{"path": "architecture.dropout", "value": 0.2, "page": 1, '
                '"section": null, "evidence": "a dropout rate of 0.2", '
                '"origin": "PRIMARY_PAPER"}]\n'
                "```"
            )

    extractor = SemanticExtractor(client=FencedClient())
    result = extractor.extract(parsed, PaperRecord())

    assert result.accepted == ["architecture.dropout"]


def test_invalid_page_rejects_only_that_claim() -> None:
    parsed = ParsedPdf(
        pages=[
            ParsedPage(0, "Cover page. We use a dropout rate of 0.2 throughout the network."),
            ParsedPage(1, "Training used 4 NVIDIA A100 GPUs for 12 hours."),
        ],
        source_name="paper.pdf",
    )
    client = FakeLLMClient([
        {
            "path": "architecture.dropout", "value": 0.2, "page": 0,
            "section": None, "evidence": "a dropout rate of 0.2 throughout the network",
            "origin": "PRIMARY_PAPER",
        },
        {
            "path": "training.gpu_count", "value": 4, "page": 1,
            "section": None, "evidence": "Training used 4 NVIDIA A100 GPUs for 12 hours",
            "origin": "PRIMARY_PAPER",
        },
    ])
    record = PaperRecord()

    result = SemanticExtractor(client=client).extract(parsed, record)

    assert result.rejected == ["architecture.dropout"]
    assert result.accepted == ["training.gpu_count"]


def test_malformed_response_shape_yields_zero_claims_not_a_crash() -> None:
    client = FakeLLMClient({"error": "the model refused to answer"})
    extractor = SemanticExtractor(client=client)
    record = PaperRecord()

    result = extractor.extract(_parsed_pdf(), record)

    assert result.accepted == []
    assert record.architecture.dropout.status == VerificationStatus.EXTRACTION_ERROR


def test_field_already_matched_by_the_real_deterministic_pipeline_is_skipped() -> None:
    parsed = ParsedPdf(
        pages=[
            ParsedPage(1, "4DVarNet-SSH: end-to-end learning"),
            ParsedPage(2124, "3.3 Learning setting. We use a single GPU and Adam optimizer with a batch size of 2 over 200 epochs."),
        ],
        source_name="4dvarnet.pdf",
    )
    record = ScientificExtractor().extract(parsed).record
    assert record.training.optimizer.status == VerificationStatus.NOT_VERIFIED  # sanity: deterministic pass matched it

    client = FakeLLMClient([
        {
            "path": "training.optimizer", "value": "SGD", "page": 2124, "section": None,
            "evidence": "We use a single GPU and Adam optimizer with a batch size of 2",
            "origin": "PRIMARY_PAPER",
        },
    ])
    extractor = SemanticExtractor(client=client)

    extractor.extract(parsed, record)

    assert "training.optimizer" not in client.last_prompt
    assert record.training.optimizer.value == "Adam"  # untouched by the conflicting LLM proposal
