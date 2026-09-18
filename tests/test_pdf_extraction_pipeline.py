from pathlib import Path

from fastapi.testclient import TestClient

from ocean_research_hub.api import create_app
from ocean_research_hub.ingestion.models import MetadataPayload
from ocean_research_hub.ingestion.pdf import (
    EvidenceSelector, EvidenceValidator, ParsedPage, ParsedPdf, PdfParser, ScientificExtractor,
)
from ocean_research_hub.ingestion.repository import SqlitePaperRepository


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
    assert result["record"]["data"]["spatial_resolution"]["value"] == "1/12 degree"
    assert result["record"]["data"]["spatial_resolution"]["status"] == "NOT_VERIFIED"
    assert result["record"]["data"]["spatial_resolution"]["source"]["page"] == 1
    assert result["record"]["training"]["optimizer"]["value"] == "AdamW"
    assert result["record"]["training"]["batch_size"]["value"] == 16
    assert result["record"]["architecture"]["family"]["value"] == ["hierarchical transformer"]
    assert any("scientific search scope" in warning for warning in result["warnings"])


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

    assert field.status.name == "EXTRACTION_ERROR"
    assert field.value is None
