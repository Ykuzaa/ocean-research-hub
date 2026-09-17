"""Safe paper-ingestion services and replaceable provider interfaces."""

from .models import (
    IngestPaperRequest,
    IngestPaperResponse,
    MetadataPayload,
    StoredPaper,
)
from .service import PaperIngestionService

__all__ = [
    "IngestPaperRequest",
    "IngestPaperResponse",
    "MetadataPayload",
    "PaperIngestionService",
    "StoredPaper",
]
