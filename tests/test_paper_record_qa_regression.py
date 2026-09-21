"""Independent QA regression coverage for issue #1's record schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ocean_research_hub.schemas.paper_record import (
    BooleanField,
    IntegerField,
    PaperRecord,
    TextField,
    TextListField,
    VerificationStatus,
)


@pytest.mark.parametrize("evidence", [None, "", " \t "])
def test_qa_verified_claim_never_accepts_missing_or_blank_evidence(evidence: str | None) -> None:
    with pytest.raises(ValidationError, match="source.evidence"):
        TextField(value="AdamW", status="VERIFIED", source={"evidence": evidence})


@pytest.mark.parametrize("value", [None, "", "  "])
def test_qa_verified_scalar_claim_must_be_present_and_non_blank(value: str | None) -> None:
    with pytest.raises(ValidationError):
        TextField(value=value, status="VERIFIED", source={"evidence": "The optimizer is AdamW."})


@pytest.mark.parametrize("value", [[], [""], [" \n "], ["AdamW", " "]])
def test_qa_verified_text_list_claim_cannot_be_empty_or_contain_blank_items(value: list[str]) -> None:
    with pytest.raises(ValidationError):
        TextListField(value=value, status="VERIFIED", source={"evidence": "Table 2."})


def test_qa_false_and_zero_are_valid_verified_claims() -> None:
    evidence = {"page": 1, "evidence": "The paper explicitly reports this value.", "origin": "PRIMARY_PAPER"}

    assert BooleanField(value=False, status="VERIFIED", source=evidence).value is False
    assert IntegerField(value=0, status="VERIFIED", source=evidence).value == 0


def test_qa_partial_record_keeps_missing_metadata_and_fields_unreported() -> None:
    record = PaperRecord.model_validate(
        {
            "paper": {"title": {
                "value": "Partial extraction without a DOI", "status": "NOT_VERIFIED",
                "source": {
                    "page": 1, "locator": "title", "origin": "PRIMARY_PAPER",
                    "evidence": "Partial extraction without a DOI",
                },
            }},
            "architecture": {
                "activations": {
                    "value": ["GELU"],
                    "status": "PARTIALLY_VERIFIED",
                    "source": {"page": 3, "evidence": "GELU follows each layer.", "origin": "PRIMARY_PAPER"},
                }
            },
        }
    )

    assert record.paper.doi.value is None
    assert record.architecture.activations.value == ["GELU"]
    assert record.architecture.dropout.status is VerificationStatus.NOT_REPORTED


def test_qa_conflict_is_retained_and_ai_interpretation_cannot_be_author_claim() -> None:
    conflict = TextField(
        conflict_values=["Adam", "SGD"],
        status="CONFLICT",
        source={"page": 4, "section": "Methods", "evidence": "Adam is used.", "origin": "PRIMARY_PAPER", "claimed_value": "Adam"},
        sources=[{"page": 12, "section": "Appendix", "evidence": "SGD is used.", "origin": "SUPPLEMENTARY_MATERIAL", "claimed_value": "SGD"}],
    )
    assert conflict.status is VerificationStatus.CONFLICT
    assert conflict.conflict_values == ["Adam", "SGD"]

    with pytest.raises(ValidationError, match="limitations.ai_interpretation"):
        PaperRecord.model_validate(
            {
                "limitations": {
                    "ai_interpretation": {
                        "value": ["Possible OOD limitation."],
                        "status": "NOT_VERIFIED",
                        "provenance_type": "AUTHOR_REPORTED_FACT",
                    }
                }
            }
        )


def test_qa_rejects_coerced_scientific_values_and_source_page() -> None:
    with pytest.raises(ValidationError):
        IntegerField(value="32", status="NOT_VERIFIED")
    with pytest.raises(ValidationError):
        TextField(value="AdamW", status="NOT_VERIFIED", source={"page": True})
