"""Transport and persistence models for the first ingestion vertical slice."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictInt,
    field_validator,
    model_validator,
)

from ocean_research_hub.corpus import domain_ids
from ocean_research_hub.schemas.paper_record import PaperRecord, SourceOrigin


class PaperWorkflowStatus(StrEnum):
    INGESTED = "INGESTED"
    PARSED = "PARSED"
    EXTRACTED = "EXTRACTED"
    SCIENTIFIC_AUDIT = "SCIENTIFIC_AUDIT"
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"


class MetadataPayload(BaseModel):
    """Bibliographic metadata returned by a DOI provider or supplied import."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: StrictInt | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv: str | None = None
    publisher_url: HttpUrl | None = None
    pdf_url: HttpUrl | None = None
    code_url: HttpUrl | None = None
    dataset_urls: list[HttpUrl] = Field(default_factory=list)
    source_origin: SourceOrigin = SourceOrigin.SECONDARY_SOURCE

    @field_validator("title", "venue", "doi", "arxiv")
    @classmethod
    def reject_blank_scalar_metadata(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("metadata text must not be blank")
        return value

    @field_validator("authors")
    @classmethod
    def reject_blank_authors(cls, value: list[str]) -> list[str]:
        if any(not author.strip() for author in value):
            raise ValueError("metadata authors must not be blank")
        return value

    @field_validator("source_origin")
    @classmethod
    def require_metadata_origin(cls, value: SourceOrigin) -> SourceOrigin:
        if value not in {
            SourceOrigin.CROSSREF_METADATA,
            SourceOrigin.PUBLISHER_METADATA,
            SourceOrigin.SECONDARY_SOURCE,
        }:
            raise ValueError(
                "metadata origin must be CROSSREF_METADATA, PUBLISHER_METADATA, "
                "or SECONDARY_SOURCE"
            )
        return value


class IngestPaperRequest(BaseModel):
    """One DOI import, direct metadata import, local parsed payload, or a combination."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    doi: str | None = None
    metadata: MetadataPayload | None = None
    parsed_paper: dict[str, Any] | None = None
    pdf_path: str | None = None
    pdf_url: HttpUrl | None = None
    domains: list[str] = Field(default_factory=list)
    # False stores bibliography only, even when the metadata carries a PDF link
    # (Crossref often does): no download, no LLM call, no cost.
    extract: bool = True

    @field_validator("doi")
    @classmethod
    def reject_blank_doi(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("DOI must not be blank")
        return value

    @field_validator("domains")
    @classmethod
    def require_known_domains(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(domain_ids()))
        if unknown:
            raise ValueError(f"unknown domains: {', '.join(unknown)}")
        return value

    @model_validator(mode="after")
    def require_an_ingestion_source(self) -> IngestPaperRequest:
        if self.doi is None and self.metadata is None and self.parsed_paper is None and self.pdf_path is None and self.pdf_url is None:
            raise ValueError("provide a DOI, metadata, parsed_paper, pdf_path, or pdf_url")
        if self.parsed_paper is not None and (self.pdf_path is not None or self.pdf_url is not None):
            raise ValueError("parsed_paper cannot be combined with a PDF source")
        return self


class StoredPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    identity_key: str
    doi: str | None
    workflow_status: PaperWorkflowStatus
    record: PaperRecord
    warnings: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class IngestPaperResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: bool
    paper: StoredPaper


class PaperSummary(BaseModel):
    """A light-weight row for list views; full evidence lives at GET /api/papers/{id}."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str | None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None
    architecture: list[str] = Field(default_factory=list)
    headline: str | None = None
    extracted_field_count: int = 0
    domains: list[str] = Field(default_factory=list)
    workflow_status: PaperWorkflowStatus
    created_at: datetime
    updated_at: datetime


class PaperListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    papers: list[PaperSummary]
    total: int


class DomainSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    paper_count: int


class PaperComparisonResponse(BaseModel):
    """An ordered pair of canonical records for deterministic comparison."""

    model_config = ConfigDict(extra="forbid")

    left: StoredPaper
    right: StoredPaper
