import json
from pathlib import Path

from fastapi.testclient import TestClient

from ocean_research_hub.api import create_app
from ocean_research_hub.ingestion.models import MetadataPayload
from ocean_research_hub.ingestion.pdf import (
    EvidenceSelector, EvidenceValidator, ParsedPage, ParsedPdf, PdfParser, ScientificExtractor,
)
from ocean_research_hub.ingestion.repository import SqlitePaperRepository
from ocean_research_hub.ingestion.semantic import SemanticExtractionError, SemanticExtractor


class StubPdfParser(PdfParser):
    def parse(self, content: bytes, *, source_name: str = "paper.pdf") -> ParsedPdf:
        return ParsedPdf(
            pages=[
                ParsedPage(1, "4.1 Data. We used GLORYS12 reanalysis for training. Input variables include sea surface temperature and sea surface height. The spatial resolution is 1/12 degree."),
                ParsedPage(2, "4.6 Optimization Details. We use the AdamW optimizer with a learning rate of 5e-5 and batch size of 16. The loss function is mean square error (MSE). XiHe is a hierarchical transformer-based framework."),
            ],
            source_name=source_name,
        )


def test_pdf_path_populates_claims_with_page_evidence_and_explicit_absence_scope(tmp_path: Path) -> None:
    pdf = tmp_path / "xihe.pdf"
    pdf.write_bytes(b"%PDF-1.7 fixture")
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    app = create_app(repository=repository, pdf_parser=StubPdfParser())

    with TestClient(app) as client:
        response = client.post("/api/papers/ingest", json={"pdf_path": str(pdf)})

    assert response.status_code == 201
    result = response.json()["paper"]
    assert result["workflow_status"] == "EXTRACTED"
    assert result["record"]["data"]["spatial_resolution"]["value"] is None
    assert result["record"]["data"]["spatial_resolution"]["status"] == "EXTRACTION_ERROR"
    assert result["record"]["training"]["optimizer"]["value"] == "AdamW"
    assert result["record"]["training"]["batch_size"]["value"] == 16
    assert result["record"]["architecture"]["family"]["value"] is None
    assert any("scientific search scope" in warning for warning in result["warnings"])


def test_paper_identity_never_activates_paper_specific_claims() -> None:
    parsed = ParsedPdf(
        pages=[
            ParsedPage(1, "OceanNet: A principled neural operator-based forecasting model."),
        ],
        source_name="oceannet.pdf",
    )

    result = ScientificExtractor().extract(parsed)

    assert result.record.evaluation.baselines.status == "NOT_REPORTED"
    assert result.record.evaluation.ablations.status == "NOT_REPORTED"
    assert result.record.evaluation.baselines.value is None
    assert any("no explicit supported claims" in warning for warning in result.warnings)


def test_repeated_explicit_values_are_retained_as_conflict() -> None:
    parsed = ParsedPdf(
        pages=[
            ParsedPage(1, "We use the Adam optimizer."),
            ParsedPage(2, "We use the AdamW optimizer."),
        ],
        source_name="conflict.pdf",
    )
    record = ScientificExtractor().extract(parsed).record
    field = record.training.optimizer
    assert field.status == "CONFLICT"
    assert field.value is None
    assert field.conflict_values == ["Adam", "AdamW"]
    assert len(field.sources) == 1
    assert field.source.claimed_value == "Adam"
    assert field.sources[0].claimed_value == "AdamW"


def test_third_explicit_value_extends_conflict_instead_of_overwriting_it() -> None:
    parsed = ParsedPdf(
        pages=[
            ParsedPage(1, "We use the Adam optimizer."),
            ParsedPage(2, "We use the AdamW optimizer."),
            ParsedPage(3, "We use the SGD optimizer."),
        ],
        source_name="conflict.pdf",
    )

    field = ScientificExtractor().extract(parsed).record.training.optimizer

    assert field.status == "CONFLICT"
    assert field.value is None
    assert field.conflict_values == ["Adam", "AdamW", "SGD"]
    assert {source.claimed_value for source in [field.source, *field.sources]} == {
        "Adam", "AdamW", "SGD",
    }


def test_generic_fallback_leaves_entity_scoped_resolution_to_semantic_extraction() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(1, "The spatial resolution is 0.25° × 0.25° on a global grid. Other text.")],
        source_name="paper.pdf",
    )

    field = ScientificExtractor().extract(parsed).record.data.spatial_resolution

    assert field.value is None
    assert field.status == "NOT_REPORTED"


def test_malformed_pdf_is_not_reported_as_an_empty_scientific_record(tmp_path: Path) -> None:
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"not a pdf")
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    app = create_app(repository=repository)
    with TestClient(app) as client:
        response = client.post("/api/papers/ingest", json={"pdf_path": str(pdf)})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PARSER_ERROR"


def test_evidence_validator_rejects_wrong_page_and_unlocatable_text() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(2124, "We use a single GPU and Adam optimizer.")],
        source_name="paper.pdf",
    )
    validator = EvidenceValidator()

    assert validator.locate(parsed, EvidenceSelector(2123, "3.3", "paragraph", r"Adam")) is None
    assert validator.locate(parsed, EvidenceSelector(2124, "3.3", "paragraph", r"AdamW")) is None
    evidence = validator.locate(parsed, EvidenceSelector(2124, "3.3", "paragraph", r"Adam optimizer"))
    assert evidence is not None
    assert evidence.page == 2124
    assert evidence.evidence == "Adam optimizer"


def test_profile_cannot_emit_hard_coded_hardware_roles_when_source_reverses_them() -> None:
    """A literal match alone cannot justify a normalized semantic claim.

    This is an adversarial profile fixture: it retains the words matched by the
    4DVarNet hardware selector while reversing which domain size uses each GPU
    configuration.  An evidence-grounded extractor must reject the stale
    normalized registry value rather than label it as a supported claim.
    """
    parsed = ParsedPdf(
        pages=[
            ParsedPage(1, "4DVarNet-SSH: end-to-end learning"),
            ParsedPage(
                2124,
                "We use a single GPU for the large domain. The same set of "
                "parameters holds for small domains, but we use the "
                "4DVarNet-distributed version of the code over 4 GPUs.",
            ),
        ],
        source_name="adversarial-4dvarnet.pdf",
    )

    field = ScientificExtractor().extract(parsed).record.training.hardware

    assert field.status.name == "NOT_REPORTED"
    assert field.value is None


def test_profile_cannot_emit_hardware_claim_when_large_domain_gpu_is_negated() -> None:
    """Negation must not satisfy an evidence contract for an asserted relation."""
    parsed = ParsedPdf(
        pages=[
            ParsedPage(1, "4DVarNet-SSH: end-to-end learning"),
            ParsedPage(
                2124,
                "When the domain is small, we use a single GPU. The same "
                "parameters hold for larger domains, but we do not use the "
                "4DVarNet-distributed version of the code over 4 GPUs.",
            ),
        ],
        source_name="negated-hardware-4dvarnet.pdf",
    )

    field = ScientificExtractor().extract(parsed).record.training.hardware

    assert field.status.name == "NOT_REPORTED"
    assert field.value is None


def test_profile_cannot_emit_training_time_when_domain_duration_roles_reverse() -> None:
    """The duration numbers alone do not support their normalized domain roles."""
    parsed = ParsedPdf(
        pages=[
            ParsedPage(1, "4DVarNet-SSH: end-to-end learning"),
            ParsedPage(
                2124,
                "The computational time of the training procedure lies between "
                "4 and 5 h for the large-domain setup and between 7 and 8 h "
                "for the small-domain setup.",
            ),
        ],
        source_name="reversed-time-4dvarnet.pdf",
    )

    field = ScientificExtractor().extract(parsed).record.training.training_time

    assert field.status.name == "NOT_REPORTED"
    assert field.value is None


def test_profile_cannot_emit_specific_loss_components_from_generic_loss_phrase() -> None:
    """Generic reconstruction/regularization wording cannot prove L2/count terms."""
    parsed = ParsedPdf(
        pages=[
            ParsedPage(1, "4DVarNet-SSH: end-to-end learning"),
            ParsedPage(
                2123,
                "The training loss L combines reconstruction losses and "
                "additional regularization terms as follows: one non-L2 "
                "penalty only.",
            ),
        ],
        source_name="generic-loss-4dvarnet.pdf",
    )

    field = ScientificExtractor().extract(parsed).record.objective.primary_loss

    assert field.status.name == "NOT_REPORTED"
    assert field.value is None


class _FakeSemanticLLMClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def propose_claims(self, prompt: str) -> str:
        return json.dumps(self.payload)


class _ExplodingSemanticLLMClient:
    def propose_claims(self, prompt: str) -> str:
        raise SemanticExtractionError("simulated Gemini outage")


def test_ingestion_reports_fields_populated_by_the_configured_semantic_extractor(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "xihe.pdf"
    pdf.write_bytes(b"%PDF-1.7 fixture")
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    client = _FakeSemanticLLMClient([
        {
            # data.time_coverage is untouched by ScientificExtractor's generic
            # pass, so this exercises the semantic path specifically rather
            # than the deterministic one.
            "path": "data.time_coverage", "value": "1/12 degree", "page": 1, "section": None,
            "evidence": "The spatial resolution is 1/12 degree.", "origin": "PRIMARY_PAPER",
        },
    ])
    app = create_app(
        repository=repository, pdf_parser=StubPdfParser(),
        semantic_extractor=SemanticExtractor(client=client),
    )

    with TestClient(app) as test_client:
        response = test_client.post("/api/papers/ingest", json={"pdf_path": str(pdf)})

    result = response.json()["paper"]
    assert result["record"]["data"]["time_coverage"]["value"] == "1/12 degree"
    assert any(
        "semantic extraction populated" in warning and "data.time_coverage" in warning
        for warning in result["warnings"]
    )


def test_ingestion_survives_a_semantic_extractor_failure_with_a_visible_warning(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "xihe.pdf"
    pdf.write_bytes(b"%PDF-1.7 fixture")
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    app = create_app(
        repository=repository, pdf_parser=StubPdfParser(),
        semantic_extractor=SemanticExtractor(client=_ExplodingSemanticLLMClient()),
    )

    with TestClient(app) as test_client:
        response = test_client.post("/api/papers/ingest", json={"pdf_path": str(pdf)})

    assert response.status_code == 201
    result = response.json()["paper"]
    assert any(
        "semantic extraction unavailable" in warning and "simulated Gemini outage" in warning
        for warning in result["warnings"]
    )


def test_ingestion_notes_when_no_semantic_extractor_is_configured(tmp_path: Path) -> None:
    pdf = tmp_path / "xihe.pdf"
    pdf.write_bytes(b"%PDF-1.7 fixture")
    repository = SqlitePaperRepository(tmp_path / "papers.db")
    app = create_app(repository=repository, pdf_parser=StubPdfParser())

    with TestClient(app) as test_client:
        response = test_client.post("/api/papers/ingest", json={"pdf_path": str(pdf)})

    result = response.json()["paper"]
    assert any("semantic extraction skipped" in warning for warning in result["warnings"])
