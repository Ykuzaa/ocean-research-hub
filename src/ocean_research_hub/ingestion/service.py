"""Scientific-integrity-preserving paper ingestion orchestration."""

from __future__ import annotations

import json
import re
import httpx
from hashlib import sha256
from typing import Any

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

from .errors import (
    IngestionConflictError,
    IngestionError,
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
from .semantic import SemanticExtractionError, SemanticExtractor

DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


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


class PaperIngestionService:
    def __init__(
        self,
        *,
        repository: PaperRepository,
        metadata_provider: MetadataProvider,
        parsed_paper_provider: ParsedPaperProvider,
        pdf_parser: PdfParser | None = None,
        scientific_extractor: ScientificExtractor | None = None,
        semantic_extractor: SemanticExtractor | None = None,
    ) -> None:
        self.repository = repository
        self.metadata_provider = metadata_provider
        self.parsed_paper_provider = parsed_paper_provider
        self.pdf_parser = pdf_parser or PdfParser()
        self.scientific_extractor = scientific_extractor or ScientificExtractor()
        self.semantic_extractor = semantic_extractor

    async def ingest(self, request: IngestPaperRequest) -> IngestPaperResponse:
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
        if requested_doi and metadata_doi and requested_doi != metadata_doi:
            raise IngestionConflictError(
                f"requested DOI {requested_doi} does not match metadata DOI {metadata_doi}"
            )
        canonical_doi = requested_doi or metadata_doi

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
            parsed_pdf = self.pdf_parser.parse(content, source_name=source_name)
            extracted = self.scientific_extractor.extract(parsed_pdf)
            record = extracted.record
            extraction_warnings.extend(extracted.warnings)
            extraction_warnings.append("scientific search scope: " + "; ".join(extracted.search_scope))
            if self.semantic_extractor is not None:
                try:
                    semantic_result = self.semantic_extractor.extract(parsed_pdf, record)
                except SemanticExtractionError as exc:
                    extraction_warnings.append(f"semantic extraction unavailable: {exc}")
                else:
                    if semantic_result.accepted:
                        extraction_warnings.append(
                            "semantic extraction populated: " + ", ".join(semantic_result.accepted)
                        )
                    if semantic_result.rejected:
                        extraction_warnings.append(
                            "semantic extraction proposed but could not verify: "
                            + ", ".join(semantic_result.rejected)
                        )
            else:
                extraction_warnings.append("semantic extraction skipped: no LLM client configured")
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

        canonical_json = json.dumps(
            record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        identity_key = (
            f"doi:{canonical_doi}"
            if canonical_doi
            else f"content:{sha256(canonical_json.encode('utf-8')).hexdigest()}"
        )
        try:
            paper, created = self.repository.create_or_get(
                identity_key=identity_key,
                doi=canonical_doi,
                record=record,
                workflow_status=workflow_status,
                warnings=warnings,
            )
        except IngestionError:
            raise
        except Exception as exc:
            raise PersistenceError("paper repository write failed") from exc
        return IngestPaperResponse(created=created, paper=paper)

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
