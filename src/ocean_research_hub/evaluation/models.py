"""Strict schemas for audited golden labels and pre-audit extraction predictions."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue, model_validator

from ocean_research_hub.schemas.paper_record import ProvenanceType, SourceEvidence


class FieldFamily(StrEnum):
    DATA = "data"
    ARCHITECTURE = "architecture"
    TRAINING = "training"
    OBJECTIVE = "objective"
    EVALUATION = "evaluation"
    RESULTS = "results"
    LIMITATIONS = "limitations"


class GoldenStatus(StrEnum):
    """Truth-label states assigned by the independent Scientific Auditor."""

    VERIFIED = "VERIFIED"
    NOT_REPORTED = "NOT_REPORTED"
    CONFLICT = "CONFLICT"


class PredictionStatus(StrEnum):
    """Extraction states allowed before independent scientific audit."""

    NOT_VERIFIED = "NOT_VERIFIED"
    NOT_REPORTED = "NOT_REPORTED"
    CONFLICT = "CONFLICT"
    EXTRACTION_ERROR = "EXTRACTION_ERROR"


class BenchmarkField(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    path: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    family: FieldFamily
    value: JsonValue | None = None
    conflict_values: list[JsonValue] = Field(default_factory=list)
    status: GoldenStatus
    provenance_type: ProvenanceType = ProvenanceType.AUTHOR_REPORTED_FACT
    confidence: float | None = Field(default=None, gt=0.0, le=1.0)
    source: SourceEvidence = Field(default_factory=SourceEvidence)
    sources: list[SourceEvidence] = Field(default_factory=list)
    source_url: HttpUrl | None = None
    # NOT_REPORTED is an audit result, not a paper quotation. Record exactly
    # which primary-source scope was searched instead of manufacturing evidence.
    absence_search_scope: list[str] = Field(default_factory=list)
    verified_by: str | None = None
    verified_at: datetime | None = None

    @model_validator(mode="after")
    def enforce_traceability(self) -> BenchmarkField:
        path_family = self.path.partition(".")[0]
        if path_family != self.family.value:
            raise ValueError("field family must match the first segment of its canonical path")
        evidence_records = [self.source, *self.sources]
        if self.source_url is not None and _is_unpinned_arxiv(self.source_url):
            raise ValueError("mutable arXiv evidence URLs must include an explicit version")
        expected_confidence = 0.95 if self.status is GoldenStatus.NOT_REPORTED else 1.0
        if self.confidence is None:
            self.confidence = expected_confidence
        elif self.confidence != expected_confidence:
            raise ValueError(
                f"{self.status} audited labels require confidence {expected_confidence}"
            )
        if self.status is GoldenStatus.NOT_REPORTED:
            if self.value is not None or self.conflict_values:
                raise ValueError("NOT_REPORTED benchmark fields cannot contain claims")
            if any(record.is_supplied for record in evidence_records) or self.source_url is not None:
                raise ValueError("NOT_REPORTED is not supported by fabricated point evidence")
            if not self.absence_search_scope:
                raise ValueError("NOT_REPORTED fields require an explicit search scope")
        elif self.status is GoldenStatus.VERIFIED:
            if self.value is None:
                raise ValueError("asserted benchmark fields require a value")
            if self.conflict_values:
                raise ValueError("VERIFIED benchmark fields cannot contain conflict alternatives")
            if not any(
                record.is_locatable and record.is_primary_author_source
                for record in evidence_records
            ):
                raise ValueError("asserted fields require locatable primary-author evidence")
            if self.source_url is None:
                raise ValueError("asserted fields require a stable primary-source URL")
            if self.absence_search_scope:
                raise ValueError("asserted fields cannot carry an absence search scope")
            if any(record.claimed_value is not None for record in evidence_records):
                raise ValueError("evidence claim bindings are reserved for CONFLICT fields")
        else:
            if self.value is not None:
                raise ValueError("CONFLICT fields must keep value null")
            alternatives = {_json_key(value) for value in self.conflict_values}
            if len(alternatives) < 2:
                raise ValueError("CONFLICT fields require two distinct alternatives")
            supplied = [record for record in evidence_records if record.is_supplied]
            if any(
                not record.is_locatable
                or not record.is_primary_author_source
                or record.claimed_value is None
                for record in supplied
            ):
                raise ValueError(
                    "every CONFLICT evidence record must be primary, locatable, and bound"
                )
            bound = {
                _json_key(record.claimed_value)
                for record in supplied
                if record.claimed_value is not None
            }
            if bound != alternatives:
                raise ValueError(
                    "CONFLICT fields require primary evidence bound to every alternative"
                )
            if self.source_url is None:
                raise ValueError("CONFLICT fields require a stable primary-source URL")
            if self.absence_search_scope:
                raise ValueError("CONFLICT fields cannot carry an absence search scope")
        if self.family is FieldFamily.LIMITATIONS:
            if self.provenance_type is not ProvenanceType.AUTHOR_REPORTED_LIMITATION:
                raise ValueError("limitation labels require AUTHOR_REPORTED_LIMITATION")
        elif self.provenance_type is not ProvenanceType.AUTHOR_REPORTED_FACT:
            raise ValueError("non-limitation labels require AUTHOR_REPORTED_FACT")
        valid_auditor = self.verified_by is not None and bool(self.verified_by.strip())
        valid_timestamp = (
            self.verified_at is not None
            and self.verified_at.tzinfo is not None
            and self.verified_at.utcoffset() is not None
        )
        if not valid_auditor or not valid_timestamp:
            raise ValueError(
                "audited golden labels require an explicit auditor identity and timestamp"
            )
        return self


class PaperIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=1)
    category: Literal[
        "global_ocean_forecasting",
        "reconstruction_data_assimilation",
        "neural_operator_physics_ml",
    ]
    doi: str | None = None
    arxiv: str | None = None
    primary_source_url: HttpUrl
    pdf_url: HttpUrl

    @model_validator(mode="after")
    def pin_mutable_preprints(self) -> PaperIdentity:
        if self.arxiv is not None and not re.fullmatch(r"\d{4}\.\d{4,5}v\d+", self.arxiv):
            raise ValueError("arXiv identifiers must include an explicit version")
        if _is_unpinned_arxiv(self.primary_source_url) or _is_unpinned_arxiv(self.pdf_url):
            raise ValueError("mutable arXiv URLs must include an explicit version")
        return self


REQUIRED_PATHS = {
    "data.datasets",
    "data.inputs",
    "data.outputs",
    "data.splits.train",
    "data.splits.validation",
    "data.splits.test",
    "data.spatial_resolution",
    "architecture.family",
    "architecture.activations",
    "training.optimizer",
    "training.learning_rate",
    "objective.primary_loss",
    "evaluation.forecast_horizon",
    "evaluation.baselines",
    "evaluation.metrics",
    "results.headline",
    "limitations.author_reported",
}


class GoldenPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    curation_status: Literal["AUDITED"]
    paper: PaperIdentity
    fields: list[BenchmarkField]

    @model_validator(mode="after")
    def require_complete_compact_subset(self) -> GoldenPaper:
        paths = [field.path for field in self.fields]
        if len(paths) != len(set(paths)):
            raise ValueError("golden field paths must be unique")
        missing = REQUIRED_PATHS - set(paths)
        if missing:
            raise ValueError(f"golden paper is missing required paths: {sorted(missing)}")
        if not any(field.status is GoldenStatus.NOT_REPORTED for field in self.fields):
            raise ValueError("each golden paper must include an explicit NOT_REPORTED label")
        return self


class PredictedField(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    path: str
    value: JsonValue | None = None
    conflict_values: list[JsonValue] = Field(default_factory=list)
    status: PredictionStatus
    source: SourceEvidence = Field(default_factory=SourceEvidence)
    sources: list[SourceEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_value_state(self) -> PredictedField:
        non_claim_state = self.status in {
            PredictionStatus.NOT_REPORTED,
            PredictionStatus.EXTRACTION_ERROR,
        }
        if (
            non_claim_state
            and (self.value is not None or self.conflict_values)
        ):
            raise ValueError(f"{self.status} predictions cannot contain claims")
        if non_claim_state and (
            self.source.is_supplied or any(source.is_supplied for source in self.sources)
        ):
            raise ValueError(f"{self.status} predictions cannot contain source evidence")
        if self.status is PredictionStatus.NOT_VERIFIED and self.value is None:
            raise ValueError("claim predictions require a value")
        if self.status is PredictionStatus.NOT_VERIFIED and self.conflict_values:
            raise ValueError("non-conflict predictions cannot contain conflict alternatives")
        if self.status is PredictionStatus.CONFLICT:
            if self.value is not None:
                raise ValueError("CONFLICT predictions must keep value null")
            alternatives = {_json_key(item) for item in self.conflict_values}
            if len(alternatives) < 2:
                raise ValueError("CONFLICT predictions require two distinct alternatives")
        return self


def _json_key(value: JsonValue) -> str:
    """Return a type-preserving stable key for conflict validation."""
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_unpinned_arxiv(url: HttpUrl) -> bool:
    if url.host != "arxiv.org":
        return False
    return re.search(r"v\d+/?$", url.path) is None


class PaperPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: str
    fields: list[PredictedField]

    @model_validator(mode="after")
    def unique_paths(self) -> PaperPrediction:
        paths = [field.path for field in self.fields]
        if len(paths) != len(set(paths)):
            raise ValueError("prediction field paths must be unique")
        return self


class PredictionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    predictions: list[PaperPrediction]
