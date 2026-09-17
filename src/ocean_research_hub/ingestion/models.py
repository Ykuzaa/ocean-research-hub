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

    @field_validator("doi")
    @classmethod
    def reject_blank_doi(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("DOI must not be blank")
        return value

    @model_validator(mode="after")
    def require_an_ingestion_source(self) -> IngestPaperRequest:
        if self.doi is None and self.metadata is None and self.parsed_paper is None:
            raise ValueError("provide a DOI, metadata, or parsed_paper")
        return self


class StoredPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    identity_key: str
    doi: str | None
    workflow_status: PaperWorkflowStatus
    record: PaperRecord
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class IngestPaperResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: bool
    paper: StoredPaper
