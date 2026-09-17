"""Deterministic field-level benchmark metrics for scientific extraction."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ocean_research_hub.evaluation.models import (
    BenchmarkField,
    FieldFamily,
    GoldenPaper,
    GoldenStatus,
    PaperPrediction,
    PredictedField,
    PredictionSet,
    PredictionStatus,
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _same_claim(gold: BenchmarkField, predicted: PredictedField | None) -> bool:
    if predicted is None:
        return False
    if gold.status is GoldenStatus.VERIFIED:
        return bool(
            predicted.status is PredictionStatus.NOT_VERIFIED
            and _canonical(gold.value) == _canonical(predicted.value)
        )
    if gold.status is GoldenStatus.CONFLICT:
        return bool(
            predicted.status is PredictionStatus.CONFLICT
            and {_canonical(value) for value in gold.conflict_values}
            == {_canonical(value) for value in predicted.conflict_values}
        )
    return False


def _same_location(gold: BenchmarkField, predicted: PredictedField | None) -> bool:
    if not _same_claim(gold, predicted):
        return False
    assert predicted is not None
    def locations(source: Any, sources: list[Any]) -> list[tuple[Any, Any, Any]]:
        return sorted(
            (
                (record.page, record.section, record.locator)
                for record in [source, *sources]
                if record.is_supplied
            ),
            key=lambda location: tuple(
                "" if component is None else str(component) for component in location
            ),
        )

    return locations(gold.source, gold.sources) == locations(
        predicted.source, predicted.sources
    )


@dataclass
class _Counts:
    gold_claims: int = 0
    predicted_claims: int = 0
    exact_claims: int = 0
    fields: int = 0
    exact_fields: int = 0
    unsupported_claims: int = 0
    not_reported: int = 0
    correct_not_reported: int = 0
    located_claims: int = 0
    correct_locations: int = 0

    def add(self, gold: BenchmarkField, predicted: PredictedField | None) -> None:
        gold_claim = gold.status in {GoldenStatus.VERIFIED, GoldenStatus.CONFLICT}
        predicted_claim = bool(
            predicted
            and predicted.status in {PredictionStatus.NOT_VERIFIED, PredictionStatus.CONFLICT}
        )
        claim_match = _same_claim(gold, predicted)
        self.fields += 1
        self.gold_claims += int(gold_claim)
        self.predicted_claims += int(predicted_claim)
        self.exact_claims += int(claim_match)
        self.unsupported_claims += int(predicted_claim and not claim_match)
        self.not_reported += int(not gold_claim)
        self.correct_not_reported += int(
            not gold_claim and predicted is not None
            and predicted.status is PredictionStatus.NOT_REPORTED
        )
        self.located_claims += int(gold_claim)
        self.correct_locations += int(_same_location(gold, predicted))
        self.exact_fields += int(
            claim_match
            or (
                not gold_claim and predicted is not None
                and predicted.status is PredictionStatus.NOT_REPORTED
            )
        )


class Metric(BaseModel):
    numerator: int
    denominator: int
    value: float | None


class MetricGroup(BaseModel):
    precision: Metric
    recall: Metric
    exact_match: Metric
    unsupported_claim_rate: Metric
    not_reported_accuracy: Metric
    evidence_location_accuracy: Metric


class BenchmarkReport(BaseModel):
    schema_version: int = 1
    paper_count: int
    field_count: int
    overall: MetricGroup
    by_field_family: dict[str, MetricGroup]


def _ratio(numerator: int, denominator: int) -> Metric:
    return Metric(
        numerator=numerator,
        denominator=denominator,
        value=round(numerator / denominator, 6) if denominator else None,
    )


def _metrics(counts: _Counts) -> MetricGroup:
    return MetricGroup(
        precision=_ratio(counts.exact_claims, counts.predicted_claims),
        recall=_ratio(counts.exact_claims, counts.gold_claims),
        exact_match=_ratio(counts.exact_fields, counts.fields),
        unsupported_claim_rate=_ratio(counts.unsupported_claims, counts.predicted_claims),
        not_reported_accuracy=_ratio(counts.correct_not_reported, counts.not_reported),
        evidence_location_accuracy=_ratio(counts.correct_locations, counts.located_claims),
    )


def benchmark(golden: list[GoldenPaper], prediction_set: PredictionSet) -> BenchmarkReport:
    golden_id_list = [paper.paper.id for paper in golden]
    if len(golden_id_list) != len(set(golden_id_list)):
        raise ValueError("golden paper IDs must be unique")
    predictions_by_paper: dict[str, PaperPrediction] = {
        item.paper_id: item for item in prediction_set.predictions
    }
    if len(predictions_by_paper) != len(prediction_set.predictions):
        raise ValueError("prediction paper IDs must be unique")
    golden_ids = set(golden_id_list)
    extra_ids = set(predictions_by_paper) - golden_ids
    if extra_ids:
        raise ValueError(f"predictions contain unknown paper IDs: {sorted(extra_ids)}")

    overall = _Counts()
    families: dict[FieldFamily, _Counts] = defaultdict(_Counts)
    for paper in golden:
        prediction = predictions_by_paper.get(paper.paper.id)
        predicted_fields = {field.path: field for field in prediction.fields} if prediction else {}
        gold_paths = {field.path for field in paper.fields}
        extra_paths = set(predicted_fields) - gold_paths
        if extra_paths:
            raise ValueError(
                f"prediction for {paper.paper.id} contains unknown paths: {sorted(extra_paths)}"
            )
        for field in paper.fields:
            predicted = predicted_fields.get(field.path)
            overall.add(field, predicted)
            families[field.family].add(field, predicted)

    return BenchmarkReport(
        paper_count=len(golden),
        field_count=overall.fields,
        overall=_metrics(overall),
        by_field_family={family.value: _metrics(families[family]) for family in FieldFamily},
    )


def load_golden(directory: Path) -> list[GoldenPaper]:
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise ValueError(f"no golden JSON files found in {directory}")
    papers = [GoldenPaper.model_validate_json(path.read_text(encoding="utf-8")) for path in paths]
    ids = [paper.paper.id for paper in papers]
    if len(ids) != len(set(ids)):
        raise ValueError("golden paper IDs must be unique")
    return papers
