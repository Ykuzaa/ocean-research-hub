from pathlib import Path

from ocean_research_hub.evaluation.benchmark import load_golden
from ocean_research_hub.evaluation.models import PredictionStatus
from ocean_research_hub.evaluation.real_pdf import (
    AUDIT_PATHS, AuditDecision, AuditDecisionSet, prediction_for, render_audit,
)
from ocean_research_hub.schemas.paper_record import PaperRecord, SourceOrigin, VerificationStatus
from ocean_research_hub.schemas.paper_record import TextField
from ocean_research_hub.ingestion.pdf import EvidenceSelector, EvidenceValidator, ParsedPage, ParsedPdf
from pydantic import ValidationError
import pytest


def test_prediction_conversion_preserves_extraction_error_separately_from_absence() -> None:
    golden = next(
        paper for paper in load_golden(Path("evaluation/golden_dataset"))
        if paper.paper.id == "4dvarnet-ssh-2023"
    )
    record = PaperRecord()
    record.data.datasets.status = VerificationStatus.EXTRACTION_ERROR

    prediction = prediction_for(golden, record)
    by_path = {field.path: field for field in prediction.fields}

    assert by_path["data.datasets"].status is PredictionStatus.EXTRACTION_ERROR
    assert by_path["data.inputs"].status is PredictionStatus.EXTRACTION_ERROR

    record.data.inputs.absence_search_scope = [
        "full primary PDF searched for input variables",
        "publisher supplement index checked; no applicable supplement",
    ]
    scoped = {field.path: field for field in prediction_for(golden, record).fields}
    assert scoped["data.inputs"].status is PredictionStatus.NOT_REPORTED


def test_human_audit_registry_covers_every_issue_19_priority_family() -> None:
    required = {
        "scientific_framing.problem", "data.preprocessing.normalization",
        "architecture.normalization_layers", "training.training_time",
        "objective.auxiliary_losses", "evaluation.ablations",
        "results.headline", "limitations.reproducibility",
    }
    assert required <= set(AUDIT_PATHS)


def test_confident_absence_requires_auditable_search_scope() -> None:
    with pytest.raises(ValidationError, match="absence search scope"):
        TextField(status="NOT_REPORTED", confidence=0.9)

    field = TextField(
        status="NOT_REPORTED",
        confidence=0.9,
        absence_search_scope=["full primary paper", "applicable supplement index"],
    )
    assert field.absence_search_scope == ["full primary paper", "applicable supplement index"]


def test_heading_validated_evidence_rejects_a_mislabeled_section() -> None:
    parsed = ParsedPdf(
        pages=[
            ParsedPage(2121, "3.1 4DVarNet framework\nAn LSTM learns an adaptive gradient update."),
        ],
        source_name="paper.pdf",
    )
    validator = EvidenceValidator()
    wrong = EvidenceSelector(
        2121, "2 4DVarNet framework", "paragraph", r"LSTM learns an adaptive gradient update",
        require_heading=True,
    )
    correct = EvidenceSelector(
        2121, "3.1 4DVarNet framework", "paragraph", r"LSTM learns an adaptive gradient update",
        require_heading=True,
    )

    assert validator.locate(parsed, wrong) is None
    assert validator.locate(parsed, correct) is not None


def test_heading_check_is_scoped_to_the_declared_page_not_the_whole_document() -> None:
    parsed = ParsedPdf(
        pages=[
            ParsedPage(2120, "3.1 4DVarNet framework\nUnrelated page content."),
            ParsedPage(2121, "An LSTM learns an adaptive gradient update."),
        ],
        source_name="paper.pdf",
    )
    validator = EvidenceValidator()
    selector = EvidenceSelector(
        2121, "3.1 4DVarNet framework", "paragraph", r"LSTM learns an adaptive gradient update",
        require_heading=True,
    )

    assert validator.locate(parsed, selector) is None


def test_supplementary_origin_with_no_supplementary_pages_finds_no_evidence() -> None:
    parsed = ParsedPdf(
        pages=[ParsedPage(1, "Ablation study without spectral regularizer.")],
        source_name="paper.pdf",
    )
    validator = EvidenceValidator()
    selector = EvidenceSelector(
        1, "supplement section", "paragraph", r"Ablation study",
        origin=SourceOrigin.SUPPLEMENTARY_MATERIAL,
    )

    assert validator.locate(parsed, selector) is None


def test_audit_report_accepts_only_complete_pdf_bound_auditor_decisions() -> None:
    golden = next(
        paper for paper in load_golden(Path("evaluation/golden_dataset"))
        if paper.paper.id == "4dvarnet-ssh-2023"
    )
    decisions = AuditDecisionSet(
        paper_id=golden.paper.id,
        source_pdf_sha256="a" * 64,
        auditor="scientific-auditor:test",
        decisions=[
            AuditDecision(
                path=path,
                decision="PASS",
                expected_value=None,
                extracted_value=None,
                evidence_location="full primary PDF",
                reason="Test fixture decision.",
            )
            for path in AUDIT_PATHS
        ],
    )

    report = render_audit(golden, PaperRecord(), "a" * 64, decisions)
    assert "PENDING_INDEPENDENT_AUDIT" not in report
    assert "scientific-auditor:test" in report

    decisions.source_pdf_sha256 = "b" * 64
    with pytest.raises(ValueError, match="PDF digest"):
        render_audit(golden, PaperRecord(), "a" * 64, decisions)


def test_audit_report_renders_a_fail_decision_and_rejects_incomplete_or_duplicate_paths() -> None:
    golden = next(
        paper for paper in load_golden(Path("evaluation/golden_dataset"))
        if paper.paper.id == "4dvarnet-ssh-2023"
    )
    base_decisions = [
        AuditDecision(
            path=path, decision="PASS", evidence_location="full primary PDF",
            reason="Test fixture decision.",
        )
        for path in AUDIT_PATHS
    ]
    base_decisions[0] = AuditDecision(
        path=base_decisions[0].path, decision="FAIL",
        expected_value="something else", extracted_value="wrong value",
        evidence_location="full primary PDF", reason="Extracted value does not match the source.",
    )
    decisions = AuditDecisionSet(
        paper_id=golden.paper.id, source_pdf_sha256="a" * 64,
        auditor="scientific-auditor:test", decisions=base_decisions,
    )

    report = render_audit(golden, PaperRecord(), "a" * 64, decisions)
    assert "FAIL" in report
    assert "Extracted value does not match the source." in report

    missing_path = AuditDecisionSet(
        paper_id=golden.paper.id, source_pdf_sha256="a" * 64,
        auditor="scientific-auditor:test", decisions=base_decisions[1:],
    )
    with pytest.raises(ValueError, match="every human-audit field"):
        render_audit(golden, PaperRecord(), "a" * 64, missing_path)

    duplicate_path = AuditDecisionSet(
        paper_id=golden.paper.id, source_pdf_sha256="a" * 64,
        auditor="scientific-auditor:test", decisions=base_decisions + [base_decisions[0]],
    )
    with pytest.raises(ValueError, match="unique"):
        render_audit(golden, PaperRecord(), "a" * 64, duplicate_path)
