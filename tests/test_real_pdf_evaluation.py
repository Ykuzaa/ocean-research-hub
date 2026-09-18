from pathlib import Path

from ocean_research_hub.evaluation.benchmark import load_golden
from ocean_research_hub.evaluation.models import PredictionStatus
from ocean_research_hub.evaluation.real_pdf import AUDIT_PATHS, prediction_for
from ocean_research_hub.schemas.paper_record import PaperRecord, VerificationStatus
from ocean_research_hub.schemas.paper_record import TextField
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
