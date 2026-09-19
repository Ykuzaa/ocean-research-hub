"""FastAPI application for the trustworthy one-paper vertical slice."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

# Loaded here (not just __main__) so GEMINI_API_KEY is present before
# `app = create_app()` runs below, regardless of entry point (uvicorn's
# import-string launch, `uv run ocean-research-hub`, or direct import in
# tests). Never overrides a variable already set in the real environment.
load_dotenv()

from ocean_research_hub.ingestion.errors import (
    IngestionConflictError,
    IngestionError,
    InvalidComparisonError,
    InvalidDoiError,
    MetadataProviderError,
    PaperNotFoundError,
    ParserError,
    PersistenceError,
)
from ocean_research_hub.corpus import domain_ids, load_seed
from ocean_research_hub.ingestion.models import (
    DomainSummary,
    IngestPaperRequest,
    IngestPaperResponse,
    PaperComparisonResponse,
    PaperListResponse,
    PaperSummary,
    StoredPaper,
)
from ocean_research_hub.ingestion.providers import (
    CrossrefMetadataProvider,
    MetadataProvider,
    ParsedPaperProvider,
    StructuredPayloadParser,
)
from ocean_research_hub.ingestion.pdf import PdfParser, ScientificExtractor, iter_evidence_fields
from ocean_research_hub.ingestion.repository import (
    PaperRepository,
    SqlitePaperRepository,
)
from ocean_research_hub.ingestion.semantic import AnthropicClient, GeminiClient, SemanticExtractor
from ocean_research_hub.ingestion.service import PaperIngestionService
from ocean_research_hub.rendering import render_paper_comparison, render_paper_detail


def summarize(paper: StoredPaper) -> PaperSummary:
    record = paper.record
    scientific_sections = (
        record.scientific_framing, record.data, record.architecture, record.training,
        record.objective, record.evaluation, record.results, record.limitations,
    )
    extracted = sum(
        1
        for section in scientific_sections
        for field in iter_evidence_fields(section)
        if field.value is not None or field.conflict_values
    )
    headline = record.results.headline.value
    return PaperSummary(
        id=paper.id,
        title=record.paper.title.value,
        authors=record.paper.authors.value or [],
        year=record.paper.year.value,
        venue=record.paper.venue.value,
        doi=paper.doi,
        architecture=record.architecture.family.value or [],
        headline=headline[0] if headline else None,
        extracted_field_count=extracted,
        domains=paper.domains,
        workflow_status=paper.workflow_status,
        created_at=paper.created_at,
        updated_at=paper.updated_at,
    )


def create_app(
    *,
    repository: PaperRepository | None = None,
    metadata_provider: MetadataProvider | None = None,
    parsed_paper_provider: ParsedPaperProvider | None = None,
    pdf_parser: PdfParser | None = None,
    scientific_extractor: ScientificExtractor | None = None,
    semantic_extractor: SemanticExtractor | None | bool = None,
) -> FastAPI:
    database_path = Path(os.getenv("OCEAN_HUB_DB_PATH", ".data/ocean-research-hub.db"))
    paper_repository = repository or SqlitePaperRepository(database_path)
    # `semantic_extractor=False` explicitly disables the LLM step even when a
    # key is configured; leaving the parameter out auto-enables it from the
    # environment so `uv run ocean-research-hub` picks up a configured key
    # without extra wiring, while tests that never set either env var stay
    # network-free by default. ANTHROPIC_API_KEY takes priority when both are
    # set - Claude is the preferred provider; Gemini remains a cheaper option
    # for callers who only configure that key.
    resolved_semantic_extractor: SemanticExtractor | None
    if semantic_extractor is False:
        resolved_semantic_extractor = None
    elif isinstance(semantic_extractor, SemanticExtractor):
        resolved_semantic_extractor = semantic_extractor
    elif os.environ.get("ANTHROPIC_API_KEY"):
        resolved_semantic_extractor = SemanticExtractor(client=AnthropicClient())
    elif os.environ.get("GEMINI_API_KEY"):
        resolved_semantic_extractor = SemanticExtractor(client=GeminiClient())
    else:
        resolved_semantic_extractor = None
    service = PaperIngestionService(
        repository=paper_repository,
        metadata_provider=metadata_provider or CrossrefMetadataProvider(),
        parsed_paper_provider=parsed_paper_provider or StructuredPayloadParser(),
        pdf_parser=pdf_parser,
        scientific_extractor=scientific_extractor,
        semantic_extractor=resolved_semantic_extractor,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        paper_repository.initialize()
        yield

    app = FastAPI(
        title="Ocean Research Hub",
        version="0.1.0",
        lifespan=lifespan,
    )
    # Local-only MVP: the frontend runs on a different origin/port (Next.js
    # dev server) and calls this API directly from the browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv(
            "OCEAN_HUB_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(","),
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )

    def error_response(status_code: int, error: Exception) -> JSONResponse:
        code = getattr(error, "code", "INGESTION_ERROR")
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": code, "message": str(error)}},
        )

    @app.exception_handler(InvalidDoiError)
    async def invalid_doi_handler(_: Request, error: InvalidDoiError) -> JSONResponse:
        return error_response(422, error)

    @app.exception_handler(ParserError)
    async def parser_error_handler(_: Request, error: ParserError) -> JSONResponse:
        return error_response(422, error)

    @app.exception_handler(MetadataProviderError)
    async def metadata_error_handler(
        _: Request, error: MetadataProviderError
    ) -> JSONResponse:
        return error_response(502, error)

    @app.exception_handler(IngestionConflictError)
    async def conflict_handler(
        _: Request, error: IngestionConflictError
    ) -> JSONResponse:
        return error_response(409, error)

    @app.exception_handler(PaperNotFoundError)
    async def not_found_handler(_: Request, error: PaperNotFoundError) -> JSONResponse:
        return error_response(404, error)

    @app.exception_handler(InvalidComparisonError)
    async def invalid_comparison_handler(
        _: Request, error: InvalidComparisonError
    ) -> JSONResponse:
        return error_response(422, error)

    @app.exception_handler(PersistenceError)
    async def persistence_error_handler(
        _: Request, error: PersistenceError
    ) -> JSONResponse:
        return error_response(503, error)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/papers/ingest",
        response_model=IngestPaperResponse,
        status_code=201,
    )
    async def ingest_paper(
        request: IngestPaperRequest,
        response: Response,
    ) -> IngestPaperResponse:
        result = await service.ingest(request)
        if not result.created:
            response.status_code = 200
        return result

    @app.get("/api/papers", response_model=PaperListResponse)
    async def list_papers_api(
        limit: int = Query(default=20, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        domain: str | None = Query(default=None),
    ) -> PaperListResponse:
        if domain is not None and domain not in domain_ids():
            raise PaperNotFoundError(f"domain {domain} does not exist")
        papers, total = paper_repository.list_papers(limit=limit, offset=offset, domain=domain)
        return PaperListResponse(papers=[summarize(paper) for paper in papers], total=total)

    @app.get("/api/domains", response_model=list[DomainSummary])
    async def list_domains_api() -> list[DomainSummary]:
        counts = paper_repository.domain_counts()
        return [
            DomainSummary(
                id=domain["id"], name=domain["name"], description=domain["description"],
                paper_count=counts.get(domain["id"], 0),
            )
            for domain in load_seed()["domains"]
        ]

    @app.get("/api/papers/compare", response_model=PaperComparisonResponse)
    async def compare_papers_api(
        left_id: str,
        right_id: str,
    ) -> PaperComparisonResponse:
        left, right = get_comparison_pair(left_id, right_id)
        return PaperComparisonResponse(left=left, right=right)

    @app.get("/api/papers/{paper_id}", response_model=StoredPaper)
    async def get_paper(paper_id: str) -> StoredPaper:
        return get_stored_paper(paper_id)

    @app.get("/papers/compare", response_class=HTMLResponse)
    async def compare_papers_view(left_id: str, right_id: str) -> HTMLResponse:
        left, right = get_comparison_pair(left_id, right_id)
        return HTMLResponse(render_paper_comparison(left, right))

    @app.get("/papers/{paper_id}", response_class=HTMLResponse)
    async def paper_detail(paper_id: str) -> HTMLResponse:
        paper = get_stored_paper(paper_id)
        return HTMLResponse(render_paper_detail(paper))

    def get_stored_paper(paper_id: str) -> StoredPaper:
        try:
            return paper_repository.get(paper_id)
        except IngestionError:
            raise
        except Exception as exc:
            raise PersistenceError("paper repository read failed") from exc

    def get_comparison_pair(
        left_id: str, right_id: str
    ) -> tuple[StoredPaper, StoredPaper]:
        if left_id == right_id:
            raise InvalidComparisonError("comparison requires two distinct paper IDs")
        # Lookups intentionally follow request order so both the API and view
        # retain stable left/right semantics.
        return get_stored_paper(left_id), get_stored_paper(right_id)

    return app


app = create_app()
