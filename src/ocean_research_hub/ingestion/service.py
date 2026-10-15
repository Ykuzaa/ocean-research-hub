"""Scientific-integrity-preserving paper ingestion orchestration."""

from __future__ import annotations

import json
import re
import httpx
from hashlib import sha256
from typing import Any

from pydantic import BaseModel

from ocean_research_hub.schemas.paper_record import (
    Bibliography,
    EvidenceField,
    IntegerField,
    PaperRecord,
    PaperUrls,
    ProvenanceType,
    SourceEvidence,
    SourceOrigin,
    TextField,
    TextListField,
    VerificationStatus,
)
from ocean_research_hub.research.models import SourceEditionCreate, SourceEditionType

from .errors import (
    IngestionConflictError,
    IngestionError,
    InvalidArxivError,
    InvalidDoiError,
    MetadataProviderError,
    ParserError,
    PersistenceError,
)
from .models import (
    IngestPaperRequest,
    IngestPaperResponse,
    MetadataPayload,
    PaperWorkflowStatus,
)
from .providers import MetadataProvider, ParsedPaperProvider
from .pdf import PdfParser, ScientificExtractor, read_pdf_path
from .repository import PaperRepository

DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
ARXIV_PATTERN = re.compile(
    r"^(?:\d{4}\.\d{4,5}|[a-z][a-z.\-]+/\d{7})(?:v\d+)?$", re.IGNORECASE
)


def normalize_doi(value: str) -> str:
    normalized = value.strip()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ):
        if normalized.lower().startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    normalized = normalized.strip().lower()
    if not DOI_PATTERN.fullmatch(normalized):
        raise InvalidDoiError(f"invalid DOI: {value}")
    return normalized


def normalize_arxiv(value: str) -> str:
    normalized = value.strip()
    for prefix in ("https://arxiv.org/abs/", "http://arxiv.org/abs/", "arxiv:"):
        if normalized.lower().startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    normalized = normalized.strip().lower()
    if not ARXIV_PATTERN.fullmatch(normalized):
        raise InvalidArxivError(f"invalid arXiv identifier: {value}")
    return re.sub(r"v\d+$", "", normalized)


class PaperIngestionService:
    def __init__(
        self,
        *,
        repository: PaperRepository,
        metadata_provider: MetadataProvider,
        parsed_paper_provider: ParsedPaperProvider,
        pdf_parser: PdfParser | None = None,
        scientific_extractor: ScientificExtractor | None = None,
    ) -> None:
        self.repository = repository
        self.metadata_provider = metadata_provider
        self.parsed_paper_provider = parsed_paper_provider
        self.pdf_parser = pdf_parser or PdfParser()
        self.scientific_extractor = scientific_extractor or ScientificExtractor()

    async def ingest(self, request: IngestPaperRequest) -> IngestPaperResponse:
        source_edition: SourceEditionCreate | None = None
        requested_doi = normalize_doi(request.doi) if request.doi else None
        metadata = request.metadata
        # A DOI can identify a caller-supplied parsed record without authorizing a
        # secondary metadata lookup. Fetch metadata only for a DOI-only import;
        # otherwise preserve the parsed primary-source record unless metadata was
        # explicitly supplied alongside it.
        if (
            metadata is None
            and requested_doi is not None
            and request.parsed_paper is None
        ):
            try:
                metadata = await self.metadata_provider.fetch(requested_doi)
            except IngestionError:
                raise
            except Exception as exc:
                raise MetadataProviderError("metadata provider failed") from exc

        metadata_doi = (
            normalize_doi(metadata.doi) if metadata and metadata.doi else None
        )
        metadata_arxiv = (
            normalize_arxiv(metadata.arxiv) if metadata and metadata.arxiv else None
        )
        if metadata is not None and metadata_arxiv is not None:
            metadata = metadata.model_copy(update={"arxiv": metadata_arxiv})
        if requested_doi and metadata_doi and requested_doi != metadata_doi:
            raise IngestionConflictError(
                f"requested DOI {requested_doi} does not match metadata DOI {metadata_doi}"
            )
        canonical_doi = requested_doi or metadata_doi
        canonical_arxiv = metadata_arxiv

        extraction_warnings: list[str] = []
        if request.parsed_paper is None and (request.pdf_path is not None or request.pdf_url is not None or (metadata and metadata.pdf_url)):
            pdf_url = request.pdf_url or (metadata.pdf_url if metadata else None)
            if request.pdf_path:
                content, source_name = read_pdf_path(request.pdf_path)
            else:
                assert pdf_url is not None
                try:
                    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                        response = await client.get(str(pdf_url))
                        response.raise_for_status()
                        content, source_name = response.content, str(pdf_url).rsplit("/", 1)[-1] or "paper.pdf"
                except (httpx.HTTPError, OSError) as exc:
                    raise ParserError(f"could not download PDF source: {pdf_url}") from exc
            content_hash = sha256(content).hexdigest()
            source_edition = SourceEditionCreate(
                edition_key=f"pdf-sha256:{content_hash}",
                source_type=SourceEditionType.PRIMARY_PDF,
                uri=pdf_url,
                content_hash=content_hash,
                version_label=source_name,
                is_primary=True,
            )
            parsed_pdf = self.pdf_parser.parse(content, source_name=source_name)
            extracted = self.scientific_extractor.extract(parsed_pdf)
            record = extracted.record
            extraction_warnings.extend(extracted.warnings)
            extraction_warnings.append("scientific search scope: " + "; ".join(extracted.search_scope))
            workflow_status = PaperWorkflowStatus.EXTRACTED
        elif request.parsed_paper is None:
            record = PaperRecord()
            workflow_status = PaperWorkflowStatus.INGESTED
        else:
            try:
                record = self.parsed_paper_provider.parse(request.parsed_paper)
            except IngestionError:
                raise
            except Exception as exc:
                raise ParserError("parsed paper provider failed") from exc
            workflow_status = PaperWorkflowStatus.EXTRACTED

        record = record.model_copy(deep=True)
        # Keep the source's claims separate from bibliography subsequently filled
        # from a metadata provider. The latter must not acquire primary provenance.
        source_record = record.model_copy(deep=True)
        source_json = json.dumps(
            source_record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        source_hash = sha256(source_json.encode("utf-8")).hexdigest()
        warnings: list[str] = extraction_warnings
        if metadata is not None:
            self._merge_metadata(record.paper, metadata, canonical_doi, warnings)
        elif canonical_doi is not None:
            self._merge_doi(record.paper, canonical_doi, warnings)

        record_doi = record.paper.doi.value
        if record_doi is not None:
            normalized_record_doi = normalize_doi(record_doi)
            if canonical_doi and normalized_record_doi != canonical_doi:
                raise IngestionConflictError(
                    f"parsed paper DOI {normalized_record_doi} does not match ingest DOI {canonical_doi}"
                )
            # DOI identity is case-insensitive. Persist the same canonical value
            # used for identity and fingerprinting while leaving the field's
            # evidence, provenance, confidence, and audit state unchanged.
            doi_field = record.paper.doi.model_dump()
            doi_field["value"] = normalized_record_doi
            record.paper.doi = TextField.model_validate(doi_field)
            canonical_doi = canonical_doi or normalized_record_doi

        record_arxiv = record.paper.arxiv.value
        if record_arxiv is not None:
            normalized_record_arxiv = normalize_arxiv(record_arxiv)
            if canonical_arxiv and normalized_record_arxiv != canonical_arxiv:
                raise IngestionConflictError(
                    f"parsed paper arXiv ID {normalized_record_arxiv} does not match "
                    f"metadata arXiv ID {canonical_arxiv}"
                )
            arxiv_field = record.paper.arxiv.model_dump()
            arxiv_field["value"] = normalized_record_arxiv
            record.paper.arxiv = TextField.model_validate(arxiv_field)
            canonical_arxiv = canonical_arxiv or normalized_record_arxiv

        canonical_json = json.dumps(
            record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        record_hash = sha256(canonical_json.encode("utf-8")).hexdigest()
        if source_edition is None:
            if request.parsed_paper is not None:
                source_edition = SourceEditionCreate(
                    edition_key=f"paper-record-sha256:{source_hash}",
                    source_type=SourceEditionType.OTHER,
                    content_hash=f"paper-record:{source_hash}",
                    version_label="canonical PaperRecord import",
                    is_primary=self._has_primary_source_evidence(record),
                )
            elif metadata is not None:
                source_type = (
                    SourceEditionType.CROSSREF_METADATA
                    if metadata.source_origin is SourceOrigin.CROSSREF_METADATA
                    else SourceEditionType.PUBLISHER_METADATA
                    if metadata.source_origin is SourceOrigin.PUBLISHER_METADATA
                    else SourceEditionType.OTHER
                )
                source_edition = SourceEditionCreate(
                    edition_key=f"metadata:{metadata.source_origin.value}:{canonical_doi or record_hash}",
                    source_type=source_type,
                    uri=metadata.publisher_url,
                    version_label=metadata.source_origin.value,
                )
        identity_key = (
            f"doi:{canonical_doi}"
            if canonical_doi
            else f"arxiv:{canonical_arxiv}"
            if canonical_arxiv
            else f"content:{sha256(canonical_json.encode('utf-8')).hexdigest()}"
        )
        identifiers = {
            key: value for key, value in {
                "DOI": canonical_doi, "ARXIV": canonical_arxiv,
            }.items() if value is not None
        }
        snapshot_for_ingest = getattr(self.repository, "snapshot_for_ingest", None)
        previous = (
            snapshot_for_ingest(identity_key, canonical_doi, identifiers)
            if snapshot_for_ingest is not None else None
        )
        try:
            paper, created = self.repository.create_or_get(
                identity_key=identity_key,
                doi=canonical_doi,
                record=record,
                workflow_status=workflow_status,
                warnings=warnings,
                identifiers=identifiers,
            )
            sync_research_record = getattr(self.repository, "sync_research_record", None)
            if sync_research_record is not None:
                try:
                    # Project only claims supplied by this edition. Bibliography
                    # filled from secondary metadata is not a claim of the PDF or
                    # parsed primary record; explicit missing fields remain visible.
                    sync_research_record(
                        paper.id,
                        source_record if source_edition and source_edition.is_primary else record,
                        source_edition,
                        include_missing_bibliography=True,
                    )
                except Exception:
                    if created:
                        discard_created = getattr(self.repository, "discard_created", None)
                        if discard_created is not None:
                            discard_created(paper.id)
                    elif previous is not None:
                        restore = getattr(self.repository, "restore_failed_upgrade", None)
                        if restore is not None:
                            current_json = json.dumps(
                                paper.record.model_dump(mode="json"),
                                sort_keys=True, separators=(",", ":"),
                            )
                            restore(previous, sha256(current_json.encode("utf-8")).hexdigest())
                    raise
        except IngestionError:
            raise
        except Exception as exc:
            raise PersistenceError("paper repository write failed") from exc
        return IngestPaperResponse(created=created, paper=paper)

    @staticmethod
    def _has_primary_source_evidence(record: PaperRecord) -> bool:
        """Do not label a structured import primary unless its evidence says so."""
        def fields(model: BaseModel):
            for name in type(model).model_fields:
                value = getattr(model, name)
                if isinstance(value, EvidenceField):
                    yield value
                elif isinstance(value, BaseModel):
                    yield from fields(value)

        return any(
            evidence.is_primary_author_source
            for field in fields(record)
            for evidence in (field.source, *field.sources)
            if evidence.is_supplied
        )

    @staticmethod
    def _merge_metadata(
        bibliography: Bibliography,
        metadata: MetadataPayload,
        canonical_doi: str | None,
        warnings: list[str],
    ) -> None:
        origin = metadata.source_origin

        def evidence(label: str, value: object) -> SourceEvidence:
            locator = (
                f"DOI {canonical_doi}" if canonical_doi else "Imported metadata payload"
            )
            return SourceEvidence(
                origin=origin,
                locator=locator,
                evidence=f"{label}: {value}",
            )

        def merge(
            field_name: str, incoming: object | None, field: EvidenceField[Any]
        ) -> None:
            if incoming is None or incoming == []:
                return
            if field.status is VerificationStatus.NOT_REPORTED:
                replacement: EvidenceField[Any]
                source = evidence(field_name, incoming)
                if isinstance(incoming, list):
                    replacement = TextListField(
                        value=incoming,
                        status=VerificationStatus.NOT_VERIFIED,
                        provenance_type=ProvenanceType.AUTHOR_REPORTED_FACT,
                        confidence=0.5,
                        source=source,
                    )
                elif type(incoming) is int:
                    replacement = IntegerField(
                        value=incoming,
                        status=VerificationStatus.NOT_VERIFIED,
                        provenance_type=ProvenanceType.AUTHOR_REPORTED_FACT,
                        confidence=0.5,
                        source=source,
                    )
                else:
                    replacement = TextField(
                        value=str(incoming),
                        status=VerificationStatus.NOT_VERIFIED,
                        provenance_type=ProvenanceType.AUTHOR_REPORTED_FACT,
                        confidence=0.5,
                        source=source,
                    )
                setattr(bibliography, field_name, replacement)
            elif field.value != incoming:
                warnings.append(
                    f"metadata {field_name} differed from the parsed record and was not used"
                )

        merge("title", metadata.title, bibliography.title)
        merge("authors", metadata.authors, bibliography.authors)
        merge("year", metadata.year, bibliography.year)
        merge("venue", metadata.venue, bibliography.venue)
        merge("arxiv", metadata.arxiv, bibliography.arxiv)
        if canonical_doi:
            PaperIngestionService._merge_doi(
                bibliography, canonical_doi, warnings, origin
            )

        urls = (
            PaperUrls(
                publisher=metadata.publisher_url,
                pdf=metadata.pdf_url,
                code=metadata.code_url,
                datasets=metadata.dataset_urls,
            )
            if any(
                (
                    metadata.publisher_url,
                    metadata.pdf_url,
                    metadata.code_url,
                    metadata.dataset_urls,
                )
            )
            else None
        )
        if urls is not None:
            if bibliography.urls.status is VerificationStatus.NOT_REPORTED:
                bibliography.urls = EvidenceField[PaperUrls](
                    value=urls,
                    status=VerificationStatus.NOT_VERIFIED,
                    provenance_type=ProvenanceType.AUTHOR_REPORTED_FACT,
                    confidence=0.5,
                    source=evidence("urls", urls.model_dump(mode="json")),
                )
            elif bibliography.urls.value != urls:
                warnings.append(
                    "metadata urls differed from the parsed record and were not used"
                )

    @staticmethod
    def _merge_doi(
        bibliography: Bibliography,
        doi: str,
        warnings: list[str],
        origin: SourceOrigin | None = None,
    ) -> None:
        source_origin = origin or SourceOrigin.SECONDARY_SOURCE
        if bibliography.doi.status is VerificationStatus.NOT_REPORTED:
            bibliography.doi = TextField(
                value=doi,
                status=VerificationStatus.NOT_VERIFIED,
                provenance_type=ProvenanceType.AUTHOR_REPORTED_FACT,
                confidence=0.5,
                source=SourceEvidence(
                    origin=source_origin,
                    locator=f"DOI {doi}",
                    evidence=f"DOI: {doi}",
                ),
            )
        elif bibliography.doi.value is not None:
            existing = normalize_doi(bibliography.doi.value)
            if existing != doi:
                warnings.append(
                    "metadata DOI differed from the parsed record and was not used"
                )
