"""Scientific-audit safety regressions for the canonical paper record."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ocean_research_hub.schemas.paper_record import PaperRecord, TextField, TextListField


PRIMARY_EVIDENCE = {
    "origin": "PRIMARY_PAPER",
    "page": 5,
    "section": "Methods",
    "evidence": "The optimizer is AdamW.",
}


@pytest.mark.parametrize("provenance", ["AI_INTERPRETATION", "TEAM_NOTE"])
def test_verified_claim_rejects_interpretive_or_team_provenance(provenance: str) -> None:
    with pytest.raises(ValidationError, match="author-reported provenance"):
        TextField(value="AdamW", status="VERIFIED", provenance_type=provenance, source=PRIMARY_EVIDENCE)


@pytest.mark.parametrize(
    "source",
    [
        {"origin": "PRIMARY_PAPER", "evidence": "AdamW is used."},
        {"origin": "SECONDARY_SOURCE", "page": 5, "evidence": "AdamW is used."},
    ],
)
def test_verified_claim_requires_locatable_primary_author_evidence(source: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="locatable primary-author"):
        TextField(value="AdamW", status="VERIFIED", source=source)


def test_partially_verified_claim_requires_locatable_primary_author_evidence() -> None:
    with pytest.raises(ValidationError, match="PARTIALLY_VERIFIED.*locatable primary-author"):
        TextField(value="AdamW", status="PARTIALLY_VERIFIED", source={"evidence": "AdamW is used."})


def test_conflict_requires_distinct_evidence_for_each_side() -> None:
    with pytest.raises(ValidationError, match="at least two distinct"):
        TextListField(
            value=["Adam", "SGD"],
            status="CONFLICT",
            source=PRIMARY_EVIDENCE,
            sources=[PRIMARY_EVIDENCE],
        )


def test_verified_author_reported_limitation_is_valid() -> None:
    record = PaperRecord.model_validate(
        {
            "limitations": {
                "author_reported": {
                    "value": ["The study covers only one basin."],
                    "status": "VERIFIED",
                    "provenance_type": "AUTHOR_REPORTED_LIMITATION",
                    "source": {
                        "origin": "PRIMARY_PAPER",
                        "page": 14,
                        "section": "Limitations",
                        "evidence": "Our analysis is limited to one basin.",
                    },
                }
            }
        }
    )

    assert record.limitations.author_reported.value == ["The study covers only one basin."]


def test_verified_fact_field_cannot_use_limitation_provenance() -> None:
    with pytest.raises(ValidationError, match="VERIFIED fact fields require AUTHOR_REPORTED_FACT"):
        PaperRecord.model_validate(
            {"training": {"optimizer": {
                "value": "AdamW", "status": "VERIFIED",
                "provenance_type": "AUTHOR_REPORTED_LIMITATION", "source": PRIMARY_EVIDENCE,
            }}}
        )


def test_bibliography_uses_evidence_envelopes_and_cannot_silently_verify_bare_metadata() -> None:
    with pytest.raises(ValidationError):
        PaperRecord.model_validate({"paper": {"title": "Bare title"}})

    record = PaperRecord.model_validate(
        {"paper": {"title": {
            "value": "Evidence-backed ocean study", "status": "VERIFIED",
            "provenance_type": "AUTHOR_REPORTED_FACT", "source": PRIMARY_EVIDENCE,
        }}}
    )

    assert record.paper.title.value == "Evidence-backed ocean study"
