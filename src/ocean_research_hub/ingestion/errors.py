"""Explicit domain failures surfaced by the ingestion API."""


class IngestionError(Exception):
    code = "INGESTION_ERROR"


class InvalidDoiError(IngestionError):
    code = "INVALID_DOI"


class MetadataProviderError(IngestionError):
    code = "METADATA_PROVIDER_ERROR"


class ParserError(IngestionError):
    code = "PARSER_ERROR"


class IngestionConflictError(IngestionError):
    code = "INGESTION_CONFLICT"


class PaperNotFoundError(IngestionError):
    code = "PAPER_NOT_FOUND"


class PersistenceError(IngestionError):
    code = "PERSISTENCE_ERROR"
