from __future__ import annotations

import pytest
from pydantic import ValidationError

from ocean_research_hub.schemas.paper_record import (
    EvidenceField,
    PaperRecord,
    ProvenanceType,
    VerificationStatus,
)


def test_empty_record_preserves_not_reported_defaults() -> None:
    record = PaperRecord()

    assert record.paper.doi is None
    assert record.training.optimizer.value is None
    assert record.training.optimizer.status is VerificationStatus.NOT_REPORTED
    assert record.architecture.activations.value is None


def test_verified_field_requires_textual_source_evidence() -> None:
    with pytest.raises(ValidationError, match="source.evidence"):
        EvidenceField[str](value="AdamW", status="VERIFIED")


def test_verified_field_with_evidence_is_valid() -> None:
    field = EvidenceField[str](
        value="AdamW",
        status="VERIFIED",
        provenance_type="AUTHOR_REPORTED_FACT",
        confidence=0.99,
        source={
            "section": "Training details",
            "page": 12,
            "locator": "Appendix A, paragraph 2",
            "evidence": "Models were optimized using AdamW.",
        },
    )

    assert field.source.page == 12
    assert field.status is VerificationStatus.VERIFIED


def test_not_reported_cannot_hide_a_value() -> None:
    with pytest.raises(ValidationError, match="NOT_REPORTED"):
        EvidenceField[str](value="GELU", status="NOT_REPORTED")


def test_conflict_is_retained_as_an_explicit_status() -> None:
    field = EvidenceField[list[str]](
        value=["Adam", "SGD"],
        status="CONFLICT",
        provenance_type="AUTHOR_REPORTED_FACT",
        source={"evidence": "Methods reports Adam; appendix reports SGD."},
    )

    assert field.status is VerificationStatus.CONFLICT
    assert field.value == ["Adam", "SGD"]


@pytest.mark.parametrize("key", ["INFERRED", "AUTHOR_GUESS", ""])
def test_invalid_provenance_is_rejected(key: str) -> None:
    with pytest.raises(ValidationError):
        EvidenceField[str](provenance_type=key)


@pytest.mark.parametrize("status", ["APPROVED", "MISSING", ""])
def test_invalid_verification_status_is_rejected(status: str) -> None:
    with pytest.raises(ValidationError):
        EvidenceField[str](status=status)


def test_extra_fields_are_rejected_to_prevent_untracked_claims() -> None:
    with pytest.raises(ValidationError):
        PaperRecord.model_validate({"training": {"optimizer": {"value": "Adam"}, "secret": "x"}})
