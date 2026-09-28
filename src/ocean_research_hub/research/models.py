"""API contracts for the normalized research-intelligence layer."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    StrictInt,
    field_validator,
    model_validator,
)

from ocean_research_hub.schemas.paper_record import PaperRecord, ProvenanceType, SourceOrigin, VerificationStatus


class EntityType(StrEnum):
    DOMAIN = "DOMAIN"
    TASK = "TASK"
    MODEL = "MODEL"
    ARCHITECTURE = "ARCHITECTURE"
    DATASET = "DATASET"
    VARIABLE = "VARIABLE"
    UNIT = "UNIT"
    REGION = "REGION"
    METRIC = "METRIC"
    LOSS = "LOSS"
    OPTIMIZER = "OPTIMIZER"
    LIMITATION_TAXONOMY = "LIMITATION_TAXONOMY"


class SourceEditionType(StrEnum):
    PRIMARY_PDF = "PRIMARY_PDF"
    SUPPLEMENTARY_MATERIAL = "SUPPLEMENTARY_MATERIAL"
    PUBLISHER_METADATA = "PUBLISHER_METADATA"
    CROSSREF_METADATA = "CROSSREF_METADATA"
    CORPUS_MANIFEST = "CORPUS_MANIFEST"
    OTHER = "OTHER"


class SourceEditionCreate(BaseModel):
    """Version-aware source identity usable by the future corpus manifest."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    edition_key: str = Field(min_length=1, max_length=300)
    source_type: SourceEditionType
    uri: HttpUrl | None = None
    content_hash: str | None = Field(default=None, min_length=1, max_length=200)
    version_label: str | None = Field(default=None, min_length=1, max_length=200)
    is_primary: bool = False


class SourceEdition(SourceEditionCreate):
    id: str
    paper_id: str
    created_at: datetime


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    section: str | None = None
    page: StrictInt | None = Field(default=None, ge=1)
    locator: str | None = None
    evidence: str | None = None
    origin: SourceOrigin | None = None
    source_edition_id: str | None = None
    source_edition_key: str | None = None
    claimed_value: JsonValue | None = None

    @field_validator("section", "locator", "evidence", "source_edition_key")
    @classmethod
    def blank_strings_are_none(cls, value: str | None) -> str | None:
        return value or None


class EntitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    entity_type: EntityType
    normalized_key: str
    canonical_name: str
    description: str | None = None
    paper_count: int = 0
    mention_count: int = 0


class EntityMention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    paper_id: str
    source_edition_id: str | None = None
    entity_id: str
    relationship_type: str
    field_path: str
    source_wording: str
    status: VerificationStatus
    provenance_type: ProvenanceType
    confidence: float
    verified_by: str | None = None
    verified_at: datetime | None = None
    alternative_index: int | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)


class EntityFieldState(BaseModel):
    """Edition-scoped bibliography or entity-bearing field state."""

    model_config = ConfigDict(extra="forbid")

    id: str
    paper_id: str
    source_edition_id: str | None = None
    field_path: str
    value: JsonValue | None = None
    conflict_values: list[JsonValue] = Field(default_factory=list)
    status: VerificationStatus
    provenance_type: ProvenanceType
    confidence: float
    verified_by: str | None = None
    verified_at: datetime | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)


class EntityDetail(BaseModel):
    entity: EntitySummary
    mentions: list[EntityMention]


class EntityListResponse(BaseModel):
    items: list[EntitySummary]
    total: int
    limit: int
    offset: int


class EntityRelationshipCreate(BaseModel):
    """An explicit evidence-backed entity edge; never inferred from co-occurrence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    subject_entity_id: str = Field(min_length=1)
    predicate: str = Field(min_length=1, max_length=200)
    object_entity_id: str = Field(min_length=1)
    source_wording: str = Field(min_length=1)
    status: VerificationStatus = VerificationStatus.NOT_VERIFIED
    provenance_type: ProvenanceType = ProvenanceType.AUTHOR_REPORTED_FACT
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_edition_key: str | None = None
    evidence: list[EvidenceReference] = Field(min_length=1)
    verified_by: str | None = None
    verified_at: datetime | None = None

    @model_validator(mode="after")
    def require_locatable_evidence(self) -> "EntityRelationshipCreate":
        if self.status in {VerificationStatus.NOT_REPORTED, VerificationStatus.EXTRACTION_ERROR}:
            raise ValueError("entity relationships must represent an explicit claim")
        if not all(item.evidence and any((item.section, item.page, item.locator)) for item in self.evidence):
            raise ValueError("entity relationships require locatable evidence")
        if any(item.claimed_value is not None for item in self.evidence):
            raise ValueError("entity relationship evidence cannot bind conflict alternatives")
        if self.status in {
            VerificationStatus.VERIFIED,
            VerificationStatus.PARTIALLY_VERIFIED,
        } and not any(
            item.origin in {
                SourceOrigin.PRIMARY_PAPER,
                SourceOrigin.SUPPLEMENTARY_MATERIAL,
                SourceOrigin.AUTHOR_PROVIDED_MATERIAL,
            }
            for item in self.evidence
        ):
            raise ValueError(
                "VERIFIED and PARTIALLY_VERIFIED relationships require primary-author evidence"
            )
        if self.status in {
            VerificationStatus.VERIFIED,
            VerificationStatus.PARTIALLY_VERIFIED,
        } and self.provenance_type not in {
            ProvenanceType.AUTHOR_REPORTED_FACT,
            ProvenanceType.AUTHOR_REPORTED_LIMITATION,
        }:
            raise ValueError(
                "verified relationships require author-reported provenance"
            )
        return self


class EntityRelationship(EntityRelationshipCreate):
    id: str
    paper_id: str
    source_edition_id: str | None = None


class HyperparameterClaim(BaseModel):
    id: str
    name: str
    value: JsonValue | None = None
    original_wording: str | None = None
    field_path: str
    status: VerificationStatus
    provenance_type: ProvenanceType
    confidence: float
    verified_by: str | None = None
    verified_at: datetime | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)


class TrainingConfiguration(BaseModel):
    id: str
    label: str
    source_edition_id: str | None = None
    hyperparameters: list[HyperparameterClaim] = Field(default_factory=list)


class ReportedResult(BaseModel):
    id: str
    source_edition_id: str | None = None
    metric_entity_id: str | None = None
    dataset_entity_id: str | None = None
    variable_entity_id: str | None = None
    value: JsonValue | None = None
    original_wording: str | None = None
    field_path: str
    status: VerificationStatus
    provenance_type: ProvenanceType
    confidence: float
    verified_by: str | None = None
    verified_at: datetime | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)


class ResearchStatement(BaseModel):
    id: str
    statement_type: str
    source_edition_id: str | None = None
    taxonomy_entity_id: str | None = None
    original_wording: str | None = None
    field_path: str
    status: VerificationStatus
    provenance_type: ProvenanceType
    confidence: float
    verified_by: str | None = None
    verified_at: datetime | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)


class ResearchPaper(BaseModel):
    paper_id: str
    source_editions: list[SourceEdition] = Field(default_factory=list)
    entity_field_states: list[EntityFieldState] = Field(default_factory=list)
    entity_mentions: list[EntityMention] = Field(default_factory=list)
    entity_relationships: list[EntityRelationship] = Field(default_factory=list)
    training_configurations: list[TrainingConfiguration] = Field(default_factory=list)
    reported_results: list[ReportedResult] = Field(default_factory=list)
    statements: list[ResearchStatement] = Field(default_factory=list)


class CorpusManifestEntry(BaseModel):
    """Issue #13 boundary: source identity plus an optional canonical record.

    The discovery pipeline may populate metadata before a PaperRecord exists;
    ingestion can later upgrade the same source edition without inventing
    scientific fields.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    manifest_id: str = Field(min_length=1, max_length=300)
    doi: str | None = None
    arxiv: str | None = None
    title: str | None = None
    source_edition: SourceEditionCreate
    paper_record: PaperRecord | None = None

    @model_validator(mode="after")
    def require_identity(self) -> "CorpusManifestEntry":
        if not any((self.doi, self.arxiv, self.title)):
            raise ValueError("manifest entry requires DOI, arXiv ID, or title")
        return self

    @field_validator("doi", "arxiv", "title")
    @classmethod
    def reject_blank_identity(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("manifest identity values must not be blank")
        return value
