"""Scientific-audit safety regressions for the canonical paper record."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ocean_research_hub.schemas.paper_record import EvidenceField, PaperRecord, TextField, TextListField


PRIMARY_EVIDENCE = {
    "origin": "PRIMARY_PAPER",
    "page": 5,
    "section": "Methods",
    "evidence": "The optimizer is AdamW.",
}

SECONDARY_PRIMARY_EVIDENCE = {
    "origin": "SUPPLEMENTARY_MATERIAL",
    "page": 12,
    "section": "Appendix",
    "evidence": "The conflicting optimizer is SGD.",
    "claimed_value": "SGD",
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


@pytest.mark.parametrize("status", ["PARTIALLY_VERIFIED", "CONFLICT"])
@pytest.mark.parametrize("value", [None, "", [], {}])
def test_claim_bearing_non_verified_statuses_require_meaningful_values(
    status: str, value: object
) -> None:
    kwargs: dict[str, object] = {"value": value, "status": status, "source": PRIMARY_EVIDENCE}
    if status == "CONFLICT":
        kwargs["sources"] = [SECONDARY_PRIMARY_EVIDENCE]

    with pytest.raises(ValidationError, match="require a non-empty claim value|must not be blank"):
        EvidenceField[object](**kwargs)


@pytest.mark.parametrize("value", [False, 0])
def test_partially_verified_claims_retain_false_and_zero(value: bool | int) -> None:
    assert EvidenceField[bool | int](
        value=value, status="PARTIALLY_VERIFIED", source=PRIMARY_EVIDENCE
    ).value == value


def test_conflict_requires_evidence_bound_to_every_side() -> None:
    with pytest.raises(ValidationError, match="explicitly bound to every alternative"):
        TextListField(
            value=["Adam", "SGD"],
            status="CONFLICT",
            source={**PRIMARY_EVIDENCE, "claimed_value": "Adam"},
            sources=[{**SECONDARY_PRIMARY_EVIDENCE, "claimed_value": "Adam"}],
        )


def test_conflict_preserves_false_and_zero_as_explicit_alternatives() -> None:
    field = EvidenceField[list[int]](
        value=[0, 1],
        status="CONFLICT",
        source={**PRIMARY_EVIDENCE, "claimed_value": 0},
        sources=[{**SECONDARY_PRIMARY_EVIDENCE, "claimed_value": 1}],
    )

    assert field.value == [0, 1]


def test_team_notes_are_separate_from_author_limitations_and_ai_interpretation() -> None:
    record = PaperRecord.model_validate(
        {"limitations": {"team_note": {
            "value": ["Replicate this result on an independent basin."],
            "status": "NOT_VERIFIED",
            "provenance_type": "TEAM_NOTE",
        }}}
    )
    assert record.limitations.team_note.provenance_type.value == "TEAM_NOTE"

    with pytest.raises(ValidationError, match="limitations.team_note"):
        PaperRecord.model_validate(
            {"limitations": {"team_note": {
                "value": ["This must not be presented as author reported."],
                "status": "NOT_VERIFIED",
                "provenance_type": "AUTHOR_REPORTED_LIMITATION",
            }}}
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
