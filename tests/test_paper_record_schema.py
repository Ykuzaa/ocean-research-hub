from __future__ import annotations

import pytest
from pydantic import ValidationError

from ocean_research_hub.schemas.paper_record import (
    EvidenceField,
    PaperRecord,
    ProvenanceType,
    TextField,
    TextListField,
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


@pytest.mark.parametrize("value", [None, "", "   "])
def test_verified_field_requires_a_non_empty_claim_value(value: str | None) -> None:
    with pytest.raises(ValidationError, match="non-empty claim value|scientific text values must not be blank"):
        EvidenceField[str](value=value, status="VERIFIED", source={"evidence": "AdamW was used."})


@pytest.mark.parametrize("value", [[], {}, set()])
def test_verified_field_requires_a_non_empty_collection_or_mapping_claim(value: object) -> None:
    with pytest.raises(ValidationError, match="non-empty claim value"):
        EvidenceField[object](
            value=value,
            status="VERIFIED",
            source={"evidence": "No activation functions are used."},
        )


@pytest.mark.parametrize("value", [False, 0])
def test_verified_field_permits_meaningful_false_and_zero_values(value: bool | int) -> None:
    field = EvidenceField[bool | int](
        value=value,
        status="VERIFIED",
        source={"evidence": "The reported value is explicitly false or zero."},
    )

    assert field.value == value


@pytest.mark.parametrize("value", [["   "], [""], ["reported value", " \t "]])
@pytest.mark.parametrize("status", ["NOT_VERIFIED", "VERIFIED"])
def test_text_list_fields_reject_blank_items_for_every_status(
    value: list[str], status: str
) -> None:
    kwargs: dict[str, object] = {"value": value, "status": status}
    if status == "VERIFIED":
        kwargs["source"] = {"evidence": "The reported list is documented."}

    with pytest.raises(ValidationError, match="must not contain blank items"):
        TextListField(**kwargs)


@pytest.mark.parametrize("value", ["", "   ", "\t"])
@pytest.mark.parametrize("status", ["NOT_VERIFIED", "PARTIALLY_VERIFIED", "VERIFIED"])
def test_text_fields_reject_blank_values_for_every_status(value: str, status: str) -> None:
    kwargs: dict[str, object] = {"value": value, "status": status}
    if status == "VERIFIED":
        kwargs["source"] = {"evidence": "The field is reported in the paper."}

    with pytest.raises(ValidationError, match="scientific text values must not be blank"):
        TextField(**kwargs)


def test_text_field_retains_none_as_an_absent_not_reported_value() -> None:
    field = TextField(value=None, status="NOT_REPORTED")

    assert field.value is None


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


def test_limitations_keep_ai_interpretation_separate_from_author_reported_limitations() -> None:
    record = PaperRecord()

    assert record.limitations.author_reported.provenance_type is ProvenanceType.AUTHOR_REPORTED_LIMITATION
    assert record.limitations.ai_interpretation.provenance_type is ProvenanceType.AI_INTERPRETATION

    with pytest.raises(ValidationError, match="limitations.ai_interpretation"):
        PaperRecord.model_validate({"limitations": {"ai_interpretation": {
            "value": ["The evidence may not support OOD performance."],
            "status": "NOT_VERIFIED", "provenance_type": "AUTHOR_REPORTED_FACT",
        }}})

    with pytest.raises(ValidationError, match="limitations.author_reported"):
        PaperRecord.model_validate({"limitations": {"author_reported": {
            "value": ["The authors report limited temporal coverage."],
            "status": "NOT_VERIFIED", "provenance_type": "AI_INTERPRETATION",
        }}})


def test_scientific_field_types_are_strict_and_do_not_coerce_malformed_inputs() -> None:
    with pytest.raises(ValidationError):
        EvidenceField[int](value="32")

    with pytest.raises(ValidationError):
        EvidenceField[str](source={"page": True})
