from __future__ import annotations

from pathlib import Path

import pytest

from ocean_research_hub.evaluation.benchmark import benchmark, load_golden
from ocean_research_hub.evaluation.models import (
    BenchmarkField,
    GoldenStatus,
    PaperIdentity,
    PaperPrediction,
    PredictedField,
    PredictionSet,
)
from ocean_research_hub.schemas.paper_record import ProvenanceType, SourceEvidence

GOLDEN_DIR = Path(__file__).parents[1] / "evaluation" / "golden_dataset"


def _perfect_predictions() -> PredictionSet:
    papers = load_golden(GOLDEN_DIR)
    return PredictionSet(
        predictions=[
            PaperPrediction(
                paper_id=paper.paper.id,
                fields=[
                    PredictedField(
                        path=field.path,
                        value=field.value,
                        conflict_values=field.conflict_values,
                        status=(
                            "NOT_VERIFIED"
                            if field.status is GoldenStatus.VERIFIED
                            else field.status.value
                        ),
                        source=(
                            field.source
                            if field.status is not GoldenStatus.NOT_REPORTED
                            else SourceEvidence()
                        ),
                        sources=(
                            field.sources
                            if field.status is not GoldenStatus.NOT_REPORTED
                            else []
                        ),
                    )
                    for field in paper.fields
                ],
            )
            for paper in papers
        ]
    )


def test_golden_corpus_covers_three_required_families_and_compact_subset() -> None:
    papers = load_golden(GOLDEN_DIR)

    assert len(papers) == 3
    assert {paper.paper.category for paper in papers} == {
        "global_ocean_forecasting",
        "reconstruction_data_assimilation",
        "neural_operator_physics_ml",
    }
    assert sorted(len(paper.fields) for paper in papers) == [17, 17, 18]


def test_every_golden_label_has_audited_metadata_and_required_evidence() -> None:
    for paper in load_golden(GOLDEN_DIR):
        assert paper.curation_status == "AUDITED"
        for field in paper.fields:
            expected_audit = {
                "scientific-auditor:issue-3": "2026-09-17T18:01:01+00:00",
                "scientific-auditor:issue-19": "2026-09-18T12:14:43+02:00",
            }
            assert field.verified_by in expected_audit
            assert field.verified_at.isoformat() == expected_audit[field.verified_by]
            if field.status in {GoldenStatus.VERIFIED, GoldenStatus.CONFLICT}:
                assert field.confidence == 1.0
                assert any(
                    source.is_primary_author_source and source.is_locatable
                    for source in [field.source, *field.sources]
                )
                assert field.source_url is not None
                assert not field.absence_search_scope
            else:
                assert field.status is GoldenStatus.NOT_REPORTED
                assert field.confidence == 0.95
                assert field.value is None
                assert field.absence_search_scope
                assert not field.source.is_supplied
                assert field.source_url is None


def test_audited_golden_labels_require_explicit_auditor_identity_and_timestamp() -> None:
    """Defaults cannot let a developer manufacture an apparently audited label."""
    with pytest.raises(ValueError, match="explicit auditor identity and timestamp"):
        BenchmarkField(
            path="training.optimizer",
            family="training",
            value="Adam",
            status="VERIFIED",
            source={
                "page": 4,
                "section": "Methods",
                "locator": "paragraph 2",
                "evidence": "We use Adam.",
                "origin": "PRIMARY_PAPER",
            },
            source_url="https://example.org/paper.pdf",
        )


def test_author_limitations_are_not_collapsed_into_fact_provenance() -> None:
    for paper in load_golden(GOLDEN_DIR):
        for field in paper.fields:
            expected = (
                ProvenanceType.AUTHOR_REPORTED_LIMITATION
                if field.path == "limitations.author_reported"
                else ProvenanceType.AUTHOR_REPORTED_FACT
            )
            assert field.provenance_type is expected


def test_assertions_without_primary_evidence_and_fabricated_absence_evidence_fail() -> None:
    with pytest.raises(ValueError, match="locatable primary-author evidence"):
        BenchmarkField(
            path="training.optimizer",
            family="training",
            value="Adam",
            status="VERIFIED",
            source_url="https://example.org/paper.pdf",
        )
    with pytest.raises(ValueError, match="fabricated point evidence"):
        BenchmarkField(
            path="training.optimizer",
            family="training",
            status="NOT_REPORTED",
            source={"page": 1, "evidence": "not present"},
            absence_search_scope=["full text"],
        )


@pytest.mark.parametrize("status", ["NOT_REPORTED", "EXTRACTION_ERROR"])
def test_non_claim_prediction_cannot_smuggle_point_evidence_or_a_claim_binding(
    status: str,
) -> None:
    """Absence and parser failure are not evidence-backed scientific claims.

    Permitting a quoted source (especially a ``claimed_value`` binding) here
    lets an extractor represent a factual assertion while its status says the
    value is absent/error.  That is silent provenance corruption.
    """
    with pytest.raises(ValueError, match="cannot contain source evidence"):
        PredictedField(
            path="training.optimizer",
            status=status,
            source={
                "page": 4,
                "section": "Methods",
                "locator": "paragraph 2",
                "evidence": "We use Adam.",
                "origin": "PRIMARY_PAPER",
                "claimed_value": "Adam",
            },
        )


def test_golden_field_family_must_match_its_canonical_path() -> None:
    """A malformed label must not silently move a data field into training."""
    with pytest.raises(ValueError, match="family must match"):
        BenchmarkField(
            path="data.datasets",
            family="training",
            value=["NATL60"],
            status="VERIFIED",
            source={
                "page": 4,
                "section": "Methods",
                "locator": "paragraph 1",
                "evidence": "NATL60 is used.",
                "origin": "PRIMARY_PAPER",
            },
            source_url="https://example.org/paper.pdf",
        )


def test_xihe_output_conflict_retains_both_primary_source_claims() -> None:
    paper = next(p for p in load_golden(GOLDEN_DIR) if p.paper.id == "xihe-2024")
    field = next(field for field in paper.fields if field.path == "data.outputs")

    assert field.status is GoldenStatus.CONFLICT
    assert field.value is None
    assert len(field.conflict_values) == 2
    assert len(field.sources) == 2
    assert field.conflict_values == [
        "reported output variables: ocean temperature, salinity, zonal and meridional ocean currents at 23 depth levels, plus sea surface height",
        "reported output dimensions: 4320 × 2041 × 94, with two atmospheric variables excluded",
    ]
    assert {
        source.claimed_value for source in [field.source, *field.sources]
    } == set(field.conflict_values)


def test_mutable_preprint_sources_are_version_pinned() -> None:
    for paper in load_golden(GOLDEN_DIR):
        if paper.paper.arxiv:
            assert "v" in paper.paper.arxiv
            assert "v" in str(paper.paper.pdf_url).rsplit("/", 1)[-1]
        for field in paper.fields:
            if field.source_url and "arxiv.org" in str(field.source_url):
                assert "v" in str(field.source_url).rsplit("/", 1)[-1]


def test_arxiv_urls_are_pinned_even_if_the_optional_arxiv_identifier_is_missing() -> None:
    """A missing metadata field cannot turn a mutable source back into valid evidence."""
    with pytest.raises(ValueError, match="mutable arXiv URLs"):
        PaperIdentity(
            id="missing-arxiv-metadata",
            title="Pinned source regression",
            category="global_ocean_forecasting",
            primary_source_url="https://arxiv.org/abs/2402.02995",
            pdf_url="https://arxiv.org/pdf/2402.02995",
        )


def test_supplements_are_included_in_applicable_absence_searches() -> None:
    papers = {paper.paper.id: paper for paper in load_golden(GOLDEN_DIR)}
    applicable = {
        "4dvarnet-ssh-2023": {"training.learning_rate", "evaluation.forecast_horizon"},
        "oceannet-2023": {
            "data.splits.validation", "architecture.activations",
            "training.optimizer", "training.learning_rate",
        },
    }
    for paper_id, paths in applicable.items():
        fields = {field.path: field for field in papers[paper_id].fields}
        for path in paths:
            assert any("supplement" in scope.lower() for scope in fields[path].absence_search_scope)


def test_audited_multisource_claims_retain_all_locations() -> None:
    papers = load_golden(GOLDEN_DIR)
    fields = {
        (paper.paper.id, field.path): field
        for paper in papers
        for field in paper.fields
    }

    assert fields[("4dvarnet-ssh-2023", "data.datasets")].sources
    oceannet_baseline_source = fields[("oceannet-2023", "evaluation.baselines")].sources[0]
    assert (
        oceannet_baseline_source.section,
        oceannet_baseline_source.page,
        oceannet_baseline_source.locator,
    ) == ("1 Introduction", 3, "OceanNet overview paragraph")
    assert fields[("oceannet-2023", "results.headline")].sources


def test_perfect_predictions_score_all_metrics_exactly() -> None:
    report = benchmark(load_golden(GOLDEN_DIR), _perfect_predictions())

    assert report.paper_count == 3
    assert report.field_count == 52
    assert report.overall.precision.value == 1.0
    assert report.overall.recall.value == 1.0
    assert report.overall.exact_match.value == 1.0
    assert report.overall.unsupported_claim_rate.value == 0.0
    assert report.overall.not_reported_accuracy.value == 1.0
    assert report.overall.evidence_location_accuracy.value == 1.0
    assert set(report.by_field_family) == {
        "data", "architecture", "training", "objective",
        "evaluation", "results", "limitations",
    }


def test_audited_verified_gold_matches_pre_audit_not_verified_prediction() -> None:
    papers = load_golden(GOLDEN_DIR)
    gold = next(field for field in papers[0].fields if field.status is GoldenStatus.VERIFIED)
    prediction = PredictionSet(
        predictions=[
            PaperPrediction(
                paper_id=papers[0].paper.id,
                fields=[
                    PredictedField(
                        path=gold.path,
                        value=gold.value,
                        status="NOT_VERIFIED",
                        source=gold.source,
                        sources=gold.sources,
                    )
                ],
            )
        ]
    )

    report = benchmark(papers, prediction)
    assert report.overall.precision.value == 1.0
    assert report.overall.precision.numerator == 1


def test_missing_predictions_are_reproducible_misses_not_implicit_not_reported() -> None:
    report = benchmark(
        load_golden(GOLDEN_DIR), PredictionSet(predictions=[])
    )

    assert report.overall.precision.value is None
    assert report.overall.recall.value == 0.0
    assert report.overall.exact_match.value == 0.0
    assert report.overall.unsupported_claim_rate.value is None
    assert report.overall.not_reported_accuracy.value == 0.0
    assert report.overall.evidence_location_accuracy.value == 0.0


def test_wrong_value_is_unsupported_and_wrong_location_is_scored_separately() -> None:
    papers = load_golden(GOLDEN_DIR)
    first, second = papers[0].fields[:2]
    prediction = PredictionSet(
        predictions=[
            PaperPrediction(
                paper_id=papers[0].paper.id,
                fields=[
                    PredictedField(
                        path=first.path,
                        value="unsupported replacement",
                        status="NOT_VERIFIED",
                        source=first.source,
                    ),
                    PredictedField(
                        path=second.path,
                        value=second.value,
                        status="NOT_VERIFIED",
                        source=SourceEvidence(
                            section=second.source.section,
                            page=second.source.page,
                            locator="wrong locator",
                            evidence=second.source.evidence,
                            origin=second.source.origin,
                        ),
                    ),
                ],
            )
        ]
    )

    report = benchmark(papers, prediction)
    assert report.overall.precision.numerator == 1
    assert report.overall.precision.denominator == 2
    assert report.overall.unsupported_claim_rate.numerator == 1
    assert report.overall.unsupported_claim_rate.denominator == 2
    assert report.overall.evidence_location_accuracy.numerator == 0


def test_claim_on_not_reported_field_counts_as_unsupported() -> None:
    papers = load_golden(GOLDEN_DIR)
    paper = next(
        paper for paper in papers
        if any(field.status is GoldenStatus.NOT_REPORTED for field in paper.fields)
    )
    absent = next(field for field in paper.fields if field.status is GoldenStatus.NOT_REPORTED)
    report = benchmark(
        papers,
        PredictionSet(
            predictions=[
                PaperPrediction(
                    paper_id=paper.paper.id,
                    fields=[
                        PredictedField(
                            path=absent.path,
                            value="invented conventional value",
                            status="NOT_VERIFIED",
                        )
                    ],
                )
            ]
        ),
    )

    assert report.overall.unsupported_claim_rate.value == 1.0
    assert report.overall.not_reported_accuracy.numerator == 0


def test_conflict_prediction_is_preserved_and_counted_as_unsupported() -> None:
    papers = load_golden(GOLDEN_DIR)
    field = papers[0].fields[0]
    report = benchmark(
        papers,
        PredictionSet(
            predictions=[
                PaperPrediction(
                    paper_id=papers[0].paper.id,
                    fields=[
                        PredictedField(
                            path=field.path,
                            status="CONFLICT",
                            conflict_values=["Adam", "AdamW"],
                        )
                    ],
                )
            ]
        ),
    )

    assert report.overall.unsupported_claim_rate.value == 1.0


@pytest.mark.parametrize("kind", ["paper", "path"])
def test_unknown_prediction_identifiers_fail_visibly(kind: str) -> None:
    papers = load_golden(GOLDEN_DIR)
    paper_id = "not-in-golden" if kind == "paper" else papers[0].paper.id
    path = "data.datasets" if kind == "paper" else "data.typo"
    predictions = PredictionSet(
        predictions=[
            PaperPrediction(
                paper_id=paper_id,
                fields=[PredictedField(path=path, status="NOT_REPORTED")],
            )
        ]
    )

    with pytest.raises(ValueError, match="unknown"):
        benchmark(papers, predictions)


def test_benchmark_rejects_duplicate_golden_papers_even_when_called_as_library() -> None:
    """Do not rely on the CLI loader alone to preserve benchmark denominators."""
    paper = load_golden(GOLDEN_DIR)[0]

    with pytest.raises(ValueError, match="golden paper IDs must be unique"):
        benchmark([paper, paper], PredictionSet(predictions=[]))


def test_report_serialization_is_deterministic() -> None:
    golden = load_golden(GOLDEN_DIR)
    predictions = _perfect_predictions()

    assert benchmark(golden, predictions).model_dump_json() == benchmark(
        golden, predictions
    ).model_dump_json()
