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
from math import isfinite
from typing import Generic, TypeVar, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue, StrictInt, field_validator, model_validator


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


class SourceOrigin(StrEnum):
    """Constrained identities for evidence sources."""

    PRIMARY_PAPER = "PRIMARY_PAPER"
    SUPPLEMENTARY_MATERIAL = "SUPPLEMENTARY_MATERIAL"
    AUTHOR_PROVIDED_MATERIAL = "AUTHOR_PROVIDED_MATERIAL"
    PUBLISHER_METADATA = "PUBLISHER_METADATA"
    CROSSREF_METADATA = "CROSSREF_METADATA"
    SECONDARY_SOURCE = "SECONDARY_SOURCE"


class SourceEvidence(BaseModel):
    """A precise pointer to the source supporting an extracted field."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    section: str | None = None
    page: StrictInt | None = Field(default=None, ge=1)
    locator: str | None = None
    evidence: str | None = None
    origin: SourceOrigin | None = None
    evidence_url: HttpUrl | None = None
    # Required for each record that supports one side of a CONFLICT field.
    # JsonValue preserves a typed, serializable link to the asserted value.
    claimed_value: JsonValue | None = None

    @field_validator("section", "locator", "evidence")
    @classmethod
    def blank_strings_are_none(cls, value: str | None) -> str | None:
        return value or None

    @property
    def has_textual_evidence(self) -> bool:
        """Whether the source contains the required quoted/cited evidence."""
        return bool(self.evidence)

    @property
    def is_locatable(self) -> bool:
        return self.has_textual_evidence and any((self.section, self.page, self.locator))

    @property
    def is_primary_author_source(self) -> bool:
        return self.origin in {
            SourceOrigin.PRIMARY_PAPER,
            SourceOrigin.SUPPLEMENTARY_MATERIAL,
            SourceOrigin.AUTHOR_PROVIDED_MATERIAL,
        }

    @property
    def is_supplied(self) -> bool:
        """Whether this is an intentional evidence record rather than the default shell."""
        return any((self.section, self.page, self.locator, self.evidence, self.origin, self.evidence_url, self.claimed_value))


T = TypeVar("T")


class EvidenceField(BaseModel, Generic[T]):
    """A scientific value together with its provenance and audit state."""

    model_config = ConfigDict(extra="forbid")

    value: T | None = None
    # Conflicts are not encoded in ``value`` because that breaks the declared
    # type of scalar fields and is ambiguous for fields whose value is already
    # a list. Each alternative retains the field's canonical type instead.
    conflict_values: list[T] = Field(default_factory=list)
    status: VerificationStatus = VerificationStatus.NOT_REPORTED
    provenance_type: ProvenanceType = ProvenanceType.AUTHOR_REPORTED_FACT
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: SourceEvidence = Field(default_factory=SourceEvidence)
    # ``source`` remains the primary evidence object. ``sources`` carries
    # additional independently locatable support, notably for conflicts.
    sources: list[SourceEvidence] = Field(default_factory=list)
    # Absence is an audit result, not the lack of an extraction. A non-empty
    # scope records the field-specific primary/supplement material searched.
    absence_search_scope: list[str] = Field(default_factory=list)
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
        if expected_type is str:
            if not isinstance(value, str):
                raise ValueError("scientific value must be a string")
            if not value.strip():
                raise ValueError("scientific text values must not be blank")
        if expected_type is int and (type(value) is not int):
            raise ValueError("scientific value must be an integer")
        if expected_type is float:
            if type(value) is not float:
                raise ValueError("scientific value must be a float")
            if not isfinite(value):
                raise ValueError("scientific float values must be finite")
        if expected_type is bool and (type(value) is not bool):
            raise ValueError("scientific value must be a boolean")
        if origin is list:
            item_type = get_args(expected_type)[0]
            if not isinstance(value, list) or any(not isinstance(item, item_type) for item in value):
                raise ValueError("scientific value must be a list with correctly typed items")
            if item_type is str and any(not item.strip() for item in value):
                raise ValueError("scientific text lists must not contain blank items")
        return value

    @field_validator("conflict_values", mode="before")
    @classmethod
    def reject_coerced_conflict_values(cls, value: object) -> object:
        """Apply the scientific value's strict typing to every alternative."""
        if not isinstance(value, list):
            raise ValueError("conflict_values must be a list")

        generic_args = cls.__pydantic_generic_metadata__["args"]
        if not generic_args:
            return value
        expected_type = generic_args[0]
        origin = get_origin(expected_type)
        for alternative in value:
            if expected_type is str:
                if not isinstance(alternative, str):
                    raise ValueError("conflict alternative must be a string")
                if not alternative.strip():
                    raise ValueError("conflict text alternatives must not be blank")
            elif expected_type is int and type(alternative) is not int:
                raise ValueError("conflict alternative must be an integer")
            elif expected_type is float:
                if type(alternative) is not float:
                    raise ValueError("conflict alternative must be a float")
                if not isfinite(alternative):
                    raise ValueError("conflict float alternatives must be finite")
            elif expected_type is bool and type(alternative) is not bool:
                raise ValueError("conflict alternative must be a boolean")
            elif origin is list:
                item_type = get_args(expected_type)[0]
                if not isinstance(alternative, list) or any(
                    not isinstance(item, item_type) for item in alternative
                ):
                    raise ValueError(
                        "conflict alternative must be a list with correctly typed items"
                    )
                if item_type is str and any(not item.strip() for item in alternative):
                    raise ValueError("conflict text-list alternatives must not contain blank items")
        return value

    @model_validator(mode="after")
    def enforce_evidence_rules(self) -> "EvidenceField[T]":
        evidence_records = [self.source, *self.sources]
        qualifying_records = [
            record for record in evidence_records
            if record.is_locatable and record.is_primary_author_source
        ]
        claim_bearing_statuses = {
            VerificationStatus.VERIFIED,
            VerificationStatus.PARTIALLY_VERIFIED,
            VerificationStatus.NOT_VERIFIED,
        }
        if self.status in claim_bearing_statuses:
            if (
                self.value is None
                or (isinstance(self.value, str) and not self.value.strip())
                or (isinstance(self.value, (Collection, Mapping)) and not self.value)
            ):
                raise ValueError(f"{self.status} fields require a non-empty claim value")
        if self.status is VerificationStatus.VERIFIED:
            if self.provenance_type not in {
                ProvenanceType.AUTHOR_REPORTED_FACT,
                ProvenanceType.AUTHOR_REPORTED_LIMITATION,
            }:
                raise ValueError("VERIFIED fields require author-reported provenance")
            if not qualifying_records:
                raise ValueError("VERIFIED fields require locatable primary-author source evidence")
        if self.status is VerificationStatus.PARTIALLY_VERIFIED:
            if self.provenance_type not in {
                ProvenanceType.AUTHOR_REPORTED_FACT,
                ProvenanceType.AUTHOR_REPORTED_LIMITATION,
            }:
                raise ValueError("PARTIALLY_VERIFIED fields require author-reported provenance")
            if not qualifying_records:
                raise ValueError("PARTIALLY_VERIFIED fields require locatable primary-author source evidence")
        if self.status is VerificationStatus.CONFLICT:
            if self.provenance_type not in {
                ProvenanceType.AUTHOR_REPORTED_FACT,
                ProvenanceType.AUTHOR_REPORTED_LIMITATION,
            }:
                raise ValueError("CONFLICT fields require author-reported provenance")
            if self.value is not None:
                raise ValueError("CONFLICT fields must keep value null and use conflict_values")

            def typed_key(value: object) -> object:
                """Return a stable, type-preserving key for JSON-like claims."""
                if isinstance(value, BaseModel):
                    return typed_key(
                        value.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
                    )
                if value is None:
                    return ("null",)
                if isinstance(value, bool):
                    return ("boolean", value)
                if type(value) is int:
                    return ("integer", value)
                if type(value) is float:
                    return ("number", repr(value))
                if isinstance(value, str):
                    return ("string", value)
                if isinstance(value, list):
                    return ("array", tuple(typed_key(item) for item in value))
                if isinstance(value, Mapping):
                    return (
                        "object",
                        tuple(sorted((str(key), typed_key(item)) for key, item in value.items())),
                    )
                return (type(value).__name__, repr(value))

            alternatives = {typed_key(value) for value in self.conflict_values}
            if len(alternatives) < 2:
                raise ValueError("CONFLICT fields require at least two distinct competing alternatives")

            generic_args = type(self).__pydantic_generic_metadata__["args"]
            expected_type = generic_args[0] if generic_args else None

            def claimed_value_key(value: JsonValue) -> object:
                # Evidence bindings are JSON, while composite alternatives are
                # parsed models. Validate through the field type so URL
                # normalization and defaults compare semantically.
                if (
                    isinstance(expected_type, type)
                    and issubclass(expected_type, BaseModel)
                ):
                    return typed_key(expected_type.model_validate(value))
                return typed_key(value)

            provided_records = [record for record in evidence_records if record.is_supplied]
            if any(record.claimed_value is None for record in provided_records):
                raise ValueError("CONFLICT evidence records must be explicitly bound to an alternative")
            all_claimed_alternatives = {
                claimed_value_key(record.claimed_value) for record in provided_records
            }
            extra_claims = all_claimed_alternatives - alternatives
            if extra_claims:
                raise ValueError(
                    "CONFLICT evidence claimed values must exactly match the listed alternatives"
                )
            claimed_alternatives = {
                claimed_value_key(record.claimed_value)
                for record in qualifying_records
                if record.claimed_value is not None
            }
            uncovered = alternatives - claimed_alternatives
            if uncovered:
                raise ValueError(
                    "CONFLICT fields require locatable primary-author evidence explicitly bound to every alternative"
                )
        elif self.conflict_values:
            raise ValueError("conflict_values may only be populated when status is CONFLICT")
        elif any(record.claimed_value is not None for record in evidence_records):
            raise ValueError("claimed_value evidence bindings may only be used for CONFLICT fields")
        if self.status is VerificationStatus.NOT_REPORTED and self.value is not None:
            raise ValueError("NOT_REPORTED fields must not contain a value")
        if self.status is VerificationStatus.NOT_REPORTED:
            if any(record.is_supplied for record in evidence_records):
                raise ValueError("NOT_REPORTED fields cannot carry point evidence")
            if self.confidence > 0 and not self.absence_search_scope:
                raise ValueError("confident NOT_REPORTED fields require an explicit absence search scope")
        elif self.absence_search_scope:
            raise ValueError("absence_search_scope is reserved for NOT_REPORTED fields")
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

    @model_validator(mode="after")
    def require_at_least_one_url(self) -> "PaperUrls":
        if not any((self.publisher, self.pdf, self.code, self.datasets)):
            raise ValueError("paper URL values must contain at least one URL")
        return self


class Bibliography(BaseModel):
    """Evidence-backed bibliographic metadata; bare metadata is not canonical."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: TextField = Field(default_factory=TextField)
    authors: TextListField = Field(default_factory=TextListField)
    year: IntegerField = Field(default_factory=IntegerField)
    venue: TextField = Field(default_factory=TextField)
    doi: TextField = Field(default_factory=TextField)
    arxiv: TextField = Field(default_factory=TextField)
    urls: EvidenceField[PaperUrls] = Field(default_factory=lambda: EvidenceField[PaperUrls]())


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
    origins: TextListField = Field(default_factory=TextListField)
    variables: TextListField = Field(default_factory=TextListField)
    units: TextListField = Field(default_factory=TextListField)
    inputs: TextListField = Field(default_factory=TextListField)
    outputs: TextListField = Field(default_factory=TextListField)
    depth_levels: TextField = Field(default_factory=TextField)
    spatial_resolution: TextField = Field(default_factory=TextField)
    temporal_resolution: TextField = Field(default_factory=TextField)
    time_coverage: TextField = Field(default_factory=TextField)
    sample_counts: TextField = Field(default_factory=TextField)
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
    gpu_count: IntegerField = Field(default_factory=IntegerField)
    gpu_types: TextListField = Field(default_factory=TextListField)
    training_time: TextField = Field(default_factory=TextField)


class Objective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_loss: TextField = Field(default_factory=TextField)
    auxiliary_losses: TextListField = Field(default_factory=TextListField)
    physics_constraints: TextListField = Field(default_factory=TextListField)
    spectral_losses: TextListField = Field(default_factory=TextListField)
    gradient_front_losses: TextListField = Field(default_factory=TextListField)
    probabilistic_losses: TextListField = Field(default_factory=TextListField)
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
    team_note: TextListField = Field(default_factory=lambda: TextListField(provenance_type=ProvenanceType.TEAM_NOTE))

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
        if self.team_note.provenance_type is not ProvenanceType.TEAM_NOTE:
            raise ValueError("limitations.team_note requires TEAM_NOTE provenance")
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

    @model_validator(mode="after")
    def enforce_fact_provenance_outside_limitations(self) -> "PaperRecord":
        """Only author-reported facts may be verified in fact-valued sections."""

        def evidence_fields(model: BaseModel):
            for name in type(model).model_fields:
                value = getattr(model, name)
                if isinstance(value, EvidenceField):
                    yield value
                elif isinstance(value, BaseModel):
                    yield from evidence_fields(value)

        fact_sections = (
            self.paper, self.scientific_framing, self.data, self.architecture,
            self.training, self.objective, self.evaluation, self.results,
        )
        for section in fact_sections:
            for field in evidence_fields(section):
                if (
                    field.status in {
                        VerificationStatus.VERIFIED,
                        VerificationStatus.PARTIALLY_VERIFIED,
                        VerificationStatus.CONFLICT,
                    }
                    and field.provenance_type is not ProvenanceType.AUTHOR_REPORTED_FACT
                ):
                    raise ValueError(
                        "verified or conflicting fact fields require AUTHOR_REPORTED_FACT provenance"
                    )
        return self
