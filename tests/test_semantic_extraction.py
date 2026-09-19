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


def test_field_catalog_covers_readable_bibliography_but_not_identifiers() -> None:
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
