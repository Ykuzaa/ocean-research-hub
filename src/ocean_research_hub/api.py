"""FastAPI application for the trustworthy one-paper vertical slice."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from ocean_research_hub.ingestion.errors import (
    IngestionConflictError,
    IngestionError,
    InvalidDoiError,
    MetadataProviderError,
    PaperNotFoundError,
    ParserError,
    PersistenceError,
)
from ocean_research_hub.ingestion.models import (
    IngestPaperRequest,
    IngestPaperResponse,
    StoredPaper,
)
from ocean_research_hub.ingestion.providers import (
    CrossrefMetadataProvider,
    MetadataProvider,
    ParsedPaperProvider,
    StructuredPayloadParser,
)
from ocean_research_hub.ingestion.repository import (
    PaperRepository,
    SqlitePaperRepository,
)
from ocean_research_hub.ingestion.service import PaperIngestionService
from ocean_research_hub.rendering import render_paper_detail


def create_app(
    *,
    repository: PaperRepository | None = None,
    metadata_provider: MetadataProvider | None = None,
    parsed_paper_provider: ParsedPaperProvider | None = None,
) -> FastAPI:
    database_path = Path(os.getenv("OCEAN_HUB_DB_PATH", ".data/ocean-research-hub.db"))
    paper_repository = repository or SqlitePaperRepository(database_path)
    service = PaperIngestionService(
        repository=paper_repository,
        metadata_provider=metadata_provider or CrossrefMetadataProvider(),
        parsed_paper_provider=parsed_paper_provider or StructuredPayloadParser(),
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

    @app.get("/api/papers/{paper_id}", response_model=StoredPaper)
    async def get_paper(paper_id: str) -> StoredPaper:
        return get_stored_paper(paper_id)

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

    return app


app = create_app()
