"""Replaceable Crossref-compatible metadata and parsed-payload providers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from ocean_research_hub.schemas.paper_record import PaperRecord

from .errors import MetadataProviderError, ParserError
from .models import MetadataPayload


class MetadataProvider(Protocol):
    async def fetch(self, doi: str) -> MetadataPayload: ...


class ParsedPaperProvider(Protocol):
    def parse(self, payload: Mapping[str, Any]) -> PaperRecord: ...


class StructuredPayloadParser:
    """Validates a local parser's structured JSON output as a canonical record."""

    def parse(self, payload: Mapping[str, Any]) -> PaperRecord:
        try:
            return PaperRecord.model_validate(payload)
        except ValidationError as exc:
            raise ParserError(f"parsed paper payload is invalid: {exc}") from exc


class CrossrefMetadataProvider:
    """Small Crossref REST adapter; network failures remain explicit."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def fetch(self, doi: str) -> MetadataPayload:
        url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
        headers = {
            "User-Agent": "OceanResearchHub/0.1 (mailto:research@example.invalid)"
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, headers=headers
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                message = response.json()["message"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise MetadataProviderError(
                f"Crossref lookup failed for DOI {doi}: {exc}"
            ) from exc

        try:
            return self._to_metadata(message)
        except (KeyError, TypeError, ValidationError) as exc:
            raise MetadataProviderError(
                f"Crossref returned malformed metadata for DOI {doi}: {exc}"
            ) from exc

    @staticmethod
    def _to_metadata(message: Mapping[str, Any]) -> MetadataPayload:
        if not isinstance(message, Mapping):
            raise TypeError("Crossref message must be an object")

        def first_text(key: str) -> str | None:
            value = message.get(key)
            if isinstance(value, list) and value and isinstance(value[0], str):
                return value[0]
            return value if isinstance(value, str) else None

        authors: list[str] = []
        raw_authors = message.get("author", [])
        if isinstance(raw_authors, list):
            for author in raw_authors:
                if not isinstance(author, Mapping):
                    continue
                name = " ".join(
                    part.strip()
                    for part in (author.get("given"), author.get("family"))
                    if isinstance(part, str) and part.strip()
                )
                if name:
                    authors.append(name)

        year = None
        published = message.get("published")
        date_parts = (
            published.get("date-parts", []) if isinstance(published, Mapping) else []
        )
        if (
            isinstance(date_parts, list)
            and date_parts
            and isinstance(date_parts[0], list)
            and date_parts[0]
            and type(date_parts[0][0]) is int
        ):
            year = date_parts[0][0]

        pdf_url = None
        links = message.get("link", [])
        if isinstance(links, list):
            for link in links:
                if (
                    isinstance(link, Mapping)
                    and link.get("content-type") == "application/pdf"
                    and isinstance(link.get("URL"), str)
                ):
                    pdf_url = link["URL"]
                    break

        return MetadataPayload(
            title=first_text("title"),
            authors=authors,
            year=year,
            venue=first_text("container-title"),
            doi=message.get("DOI") if isinstance(message.get("DOI"), str) else None,
            publisher_url=message.get("URL")
            if isinstance(message.get("URL"), str)
            else None,
            pdf_url=pdf_url,
            source_origin="CROSSREF_METADATA",
        )
