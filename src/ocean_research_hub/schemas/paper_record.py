"""Canonical, evidence-backed schema for an Ocean Research Hub paper record.

Scientific fields are deliberately represented by :class:`EvidenceField`, rather
than bare values.  This makes an absent value distinguishable from an unverified
claim and prevents a field from being marked VERIFIED without quoted source
evidence.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime
from enum import StrEnum
from typing import Generic, TypeVar, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    NOT_REPORTED = "NOT_REPORTED"
    CONFLICT = "CONFLICT"
    EXTRACTION_ERROR = "EXTRACTION_ERROR"


class ProvenanceType(StrEnum):
    AUTHOR_REPORTED_FACT = "AUTHOR_REPORTED_FACT"
    AUTHOR_REPORTED_LIMITATION = "AUTHOR_REPORTED_LIMITATION"
    AI_INTERPRETATION = "AI_INTERPRETATION"
    TEAM_NOTE = "TEAM_NOTE"


class SourceEvidence(BaseModel):
    """A precise pointer to the source supporting an extracted field."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)

    section: str | None = None
    page: int | None = Field(default=None, ge=1)
    locator: str | None = None
    evidence: str | None = None

    @field_validator("section", "locator", "evidence")
    @classmethod
    def blank_strings_are_none(cls, value: str | None) -> str | None:
        return value or None

    @property
    def has_textual_evidence(self) -> bool:
        """Whether the source contains the required quoted/cited evidence."""
        return bool(self.evidence)


T = TypeVar("T")


class EvidenceField(BaseModel, Generic[T]):
    """A scientific value together with its provenance and audit state."""

    model_config = ConfigDict(extra="forbid")

    value: T | None = None
    status: VerificationStatus = VerificationStatus.NOT_REPORTED
    provenance_type: ProvenanceType = ProvenanceType.AUTHOR_REPORTED_FACT
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: SourceEvidence = Field(default_factory=SourceEvidence)
    verified_by: str | None = None
    verified_at: datetime | None = None

    @field_validator("value", mode="before")
    @classmethod
    def reject_coerced_scientific_values(cls, value: object) -> object:
        """Reject type coercion while retaining JSON string enum inputs.

        Status and provenance are deliberate string-valued API enums.  Values
        instead are generated scientific claims and must arrive in their
        declared type so malformed extraction cannot be silently repaired.
        """
        if value is None:
            return value

        generic_args = cls.__pydantic_generic_metadata__["args"]
        if not generic_args:
            return value
        expected_type = generic_args[0]
        origin = get_origin(expected_type)
        if expected_type is str and not isinstance(value, str):
            raise ValueError("scientific value must be a string")
        if expected_type is int and (type(value) is not int):
            raise ValueError("scientific value must be an integer")
        if expected_type is float and (type(value) is not float):
            raise ValueError("scientific value must be a float")
        if expected_type is bool and (type(value) is not bool):
            raise ValueError("scientific value must be a boolean")
        if origin is list:
            item_type = get_args(expected_type)[0]
            if not isinstance(value, list) or any(not isinstance(item, item_type) for item in value):
                raise ValueError("scientific value must be a list with correctly typed items")
        return value

    @model_validator(mode="after")
    def enforce_evidence_rules(self) -> "EvidenceField[T]":
        if self.status is VerificationStatus.VERIFIED:
            if (
                self.value is None
                or (isinstance(self.value, str) and not self.value.strip())
                or (isinstance(self.value, (Collection, Mapping)) and not self.value)
            ):
                raise ValueError("VERIFIED fields require a non-empty claim value")
            if not self.source.has_textual_evidence:
                raise ValueError("VERIFIED fields require non-empty source.evidence")
        if self.status is VerificationStatus.NOT_REPORTED and self.value is not None:
            raise ValueError("NOT_REPORTED fields must not contain a value")
        return self


TextField = EvidenceField[str]
TextListField = EvidenceField[list[str]]
IntegerField = EvidenceField[int]
DecimalField = EvidenceField[float]
BooleanField = EvidenceField[bool]


class PaperUrls(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publisher: HttpUrl | None = None
    pdf: HttpUrl | None = None
    code: HttpUrl | None = None
    datasets: list[HttpUrl] = Field(default_factory=list)


class Bibliography(BaseModel):
    """Imported bibliographic metadata; scientific claims live in EvidenceField."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None, ge=1)
    venue: str | None = None
    doi: str | None = None
    arxiv: str | None = None
    urls: PaperUrls = Field(default_factory=PaperUrls)


class ScientificFraming(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem: TextField = Field(default_factory=TextField)
    motivation: TextField = Field(default_factory=TextField)
    objective: TextField = Field(default_factory=TextField)
    task_type: TextListField = Field(default_factory=TextListField)
    domain: TextListField = Field(default_factory=TextListField)
    region: TextListField = Field(default_factory=TextListField)
    ocean_regime: TextListField = Field(default_factory=TextListField)


class DataSplits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    train: TextField = Field(default_factory=TextField)
    validation: TextField = Field(default_factory=TextField)
    test: TextField = Field(default_factory=TextField)


class Preprocessing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missing_data: TextField = Field(default_factory=TextField)
    masking: TextField = Field(default_factory=TextField)
    regridding: TextField = Field(default_factory=TextField)
    interpolation: TextField = Field(default_factory=TextField)
    normalization: TextField = Field(default_factory=TextField)
    anomalies: TextField = Field(default_factory=TextField)
    filtering: TextField = Field(default_factory=TextField)
    augmentation: TextField = Field(default_factory=TextField)
    derived_features: TextListField = Field(default_factory=TextListField)


class DataDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasets: TextListField = Field(default_factory=TextListField)
    inputs: TextListField = Field(default_factory=TextListField)
    outputs: TextListField = Field(default_factory=TextListField)
    depth_levels: TextField = Field(default_factory=TextField)
    spatial_resolution: TextField = Field(default_factory=TextField)
    temporal_resolution: TextField = Field(default_factory=TextField)
    time_coverage: TextField = Field(default_factory=TextField)
    splits: DataSplits = Field(default_factory=DataSplits)
    preprocessing: Preprocessing = Field(default_factory=Preprocessing)


class Architecture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: TextListField = Field(default_factory=TextListField)
    summary: TextField = Field(default_factory=TextField)
    encoder: TextField = Field(default_factory=TextField)
    decoder: TextField = Field(default_factory=TextField)
    blocks: TextListField = Field(default_factory=TextListField)
    layer_count: IntegerField = Field(default_factory=IntegerField)
    hidden_dimensions: TextListField = Field(default_factory=TextListField)
    channels: TextListField = Field(default_factory=TextListField)
    patch_or_window: TextField = Field(default_factory=TextField)
    attention: TextField = Field(default_factory=TextField)
    positional_encoding: TextField = Field(default_factory=TextField)
    skip_connections: BooleanField = Field(default_factory=BooleanField)
    activations: TextListField = Field(default_factory=TextListField)
    normalization_layers: TextListField = Field(default_factory=TextListField)
    dropout: DecimalField = Field(default_factory=DecimalField)
    parameter_count: IntegerField = Field(default_factory=IntegerField)
    forecasting_mode: TextField = Field(default_factory=TextField)
    probabilistic_mode: TextField = Field(default_factory=TextField)
    physical_components: TextListField = Field(default_factory=TextListField)


class Training(BaseModel):
    model_config = ConfigDict(extra="forbid")

    optimizer: TextField = Field(default_factory=TextField)
    learning_rate: TextField = Field(default_factory=TextField)
    scheduler: TextField = Field(default_factory=TextField)
    batch_size: IntegerField = Field(default_factory=IntegerField)
    epochs_or_steps: TextField = Field(default_factory=TextField)
    early_stopping: TextField = Field(default_factory=TextField)
    weight_decay: TextField = Field(default_factory=TextField)
    gradient_clipping: TextField = Field(default_factory=TextField)
    initialization: TextField = Field(default_factory=TextField)
    mixed_precision: BooleanField = Field(default_factory=BooleanField)
    random_seeds: TextListField = Field(default_factory=TextListField)
    hardware: TextListField = Field(default_factory=TextListField)
    training_time: TextField = Field(default_factory=TextField)


class Objective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_loss: TextField = Field(default_factory=TextField)
    auxiliary_losses: TextListField = Field(default_factory=TextListField)
    physics_constraints: TextListField = Field(default_factory=TextListField)
    loss_weights: TextListField = Field(default_factory=TextListField)


class Evaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baselines: TextListField = Field(default_factory=TextListField)
    metrics: TextListField = Field(default_factory=TextListField)
    forecast_horizon: TextField = Field(default_factory=TextField)
    evaluation_datasets: TextListField = Field(default_factory=TextListField)
    observation_space_validation: TextField = Field(default_factory=TextField)
    uncertainty_calibration: TextField = Field(default_factory=TextField)
    ablations: TextListField = Field(default_factory=TextListField)
    ood_tests: TextListField = Field(default_factory=TextListField)
    statistical_significance: TextField = Field(default_factory=TextField)


class Results(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: TextListField = Field(default_factory=TextListField)
    by_variable: TextListField = Field(default_factory=TextListField)
    by_region: TextListField = Field(default_factory=TextListField)
    by_depth: TextListField = Field(default_factory=TextListField)
    by_horizon: TextListField = Field(default_factory=TextListField)
    qualitative: TextListField = Field(default_factory=TextListField)
    compute_cost: TextField = Field(default_factory=TextField)


class Limitations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_reported: TextListField = Field(default_factory=lambda: TextListField(provenance_type=ProvenanceType.AUTHOR_REPORTED_LIMITATION))
    future_work: TextListField = Field(default_factory=lambda: TextListField(provenance_type=ProvenanceType.AUTHOR_REPORTED_LIMITATION))
    reproducibility: TextListField = Field(default_factory=lambda: TextListField(provenance_type=ProvenanceType.AUTHOR_REPORTED_LIMITATION))
    data: TextListField = Field(default_factory=lambda: TextListField(provenance_type=ProvenanceType.AUTHOR_REPORTED_LIMITATION))
    physics: TextListField = Field(default_factory=lambda: TextListField(provenance_type=ProvenanceType.AUTHOR_REPORTED_LIMITATION))
    generalization: TextListField = Field(default_factory=lambda: TextListField(provenance_type=ProvenanceType.AUTHOR_REPORTED_LIMITATION))
    uncertainty: TextListField = Field(default_factory=lambda: TextListField(provenance_type=ProvenanceType.AUTHOR_REPORTED_LIMITATION))
    compute: TextListField = Field(default_factory=lambda: TextListField(provenance_type=ProvenanceType.AUTHOR_REPORTED_LIMITATION))
    ai_interpretation: TextListField = Field(default_factory=lambda: TextListField(provenance_type=ProvenanceType.AI_INTERPRETATION))

    @model_validator(mode="after")
    def enforce_limitation_provenance(self) -> "Limitations":
        author_reported_fields = (
            "author_reported", "future_work", "reproducibility", "data", "physics",
            "generalization", "uncertainty", "compute",
        )
        for name in author_reported_fields:
            field = getattr(self, name)
            if field.provenance_type is not ProvenanceType.AUTHOR_REPORTED_LIMITATION:
                raise ValueError(f"limitations.{name} requires AUTHOR_REPORTED_LIMITATION provenance")
        if self.ai_interpretation.provenance_type is not ProvenanceType.AI_INTERPRETATION:
            raise ValueError("limitations.ai_interpretation requires AI_INTERPRETATION provenance")
        return self


class PaperRecord(BaseModel):
    """The canonical fully structured record for one scientific paper."""

    model_config = ConfigDict(extra="forbid")

    paper: Bibliography = Field(default_factory=Bibliography)
    scientific_framing: ScientificFraming = Field(default_factory=ScientificFraming)
    data: DataDescription = Field(default_factory=DataDescription)
    architecture: Architecture = Field(default_factory=Architecture)
    training: Training = Field(default_factory=Training)
    objective: Objective = Field(default_factory=Objective)
    evaluation: Evaluation = Field(default_factory=Evaluation)
    results: Results = Field(default_factory=Results)
    limitations: Limitations = Field(default_factory=Limitations)
