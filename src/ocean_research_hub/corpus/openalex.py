"""Resolve seed paper titles to DOIs and open-access PDF links through OpenAlex."""

from __future__ import annotations

import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

import httpx

OPENALEX_WORKS = "https://api.openalex.org/works"
SELECT = "id,doi,title,publication_year,authorships,primary_location,best_oa_location,locations"
# Titles are matched, not trusted: OpenAlex search returns *related* works too,
# and ingesting the wrong paper under a curated title would be worse than
# ingesting nothing.
MATCH_THRESHOLD = 0.9
ARXIV_DOI_PREFIX = "10.48550/"


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKC", title).lower()
    return re.sub(r"[^\w]+", " ", text).strip()


def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def pdf_candidates(work: dict[str, Any]) -> list[str]:
    """Downloadable PDF links, arXiv first: publishers often block scripted downloads."""
    locations = work.get("locations") or []
    urls: list[str] = []
    for location in locations:
        landing = location.get("landing_page_url") or ""
        match = re.search(r"arxiv\.org/abs/([^\s?#]+)", landing)
        if match:
            urls.append(f"https://arxiv.org/pdf/{match.group(1)}")
    best = work.get("best_oa_location") or {}
    if best.get("pdf_url"):
        urls.append(best["pdf_url"])
    urls.extend(location["pdf_url"] for location in locations if location.get("pdf_url"))
    return list(dict.fromkeys(urls))


@dataclass
class Resolution:
    query_title: str
    openalex_id: str | None = None
    doi: str | None = None
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    similarity: float = 0.0
    pdf_candidates: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.openalex_id is not None


def _doi(work: dict[str, Any]) -> str | None:
    doi = work.get("doi")
    return doi.removeprefix("https://doi.org/").lower() if doi else None


def _from_works(query_title: str, works: list[tuple[dict[str, Any], float]]) -> Resolution:
    # A preprint and its journal version are separate OpenAlex works: keep the
    # journal DOI as identity but pool every version's downloadable PDFs.
    works = sorted(
        works,
        key=lambda item: ((_doi(item[0]) or "").startswith(ARXIV_DOI_PREFIX), -item[1]),
    )
    primary, similarity = works[0]
    source = ((primary.get("primary_location") or {}).get("source") or {})
    candidates: list[str] = []
    for work, _ in works:
        candidates.extend(pdf_candidates(work))
    return Resolution(
        query_title=query_title,
        openalex_id=primary.get("id"),
        doi=_doi(primary),
        title=primary.get("title"),
        authors=[
            name for authorship in primary.get("authorships") or []
            if (name := (authorship.get("author") or {}).get("display_name"))
        ],
        year=primary.get("publication_year"),
        venue=source.get("display_name"),
        similarity=round(similarity, 3),
        pdf_candidates=sorted(dict.fromkeys(candidates), key=lambda url: "arxiv.org" not in url),
    )


class OpenAlexBudgetExhausted(RuntimeError):
    """OpenAlex refused the request for lack of budget (not a transient error)."""


def _get(client: httpx.Client, url: str, params: dict[str, Any]) -> httpx.Response:
    api_key = os.environ.get("OPENALEX_API_KEY")
    if api_key:
        params = {**params, "api_key": api_key}
    for attempt in range(4):
        response = client.get(url, params=params)
        if response.status_code != 429:
            return response
        wait = float(response.headers.get("retry-after", "2"))
        if wait > 60:
            # The anonymous daily budget is shared per IP and resets at
            # midnight UTC: retrying for hours would just hang the run.
            raise OpenAlexBudgetExhausted(
                "OpenAlex daily budget used up; set OPENALEX_API_KEY (free at openalex.org) or retry after midnight UTC"
            )
        time.sleep(max(wait, 2.0 ** attempt))
    return response


def _title_matches(client: httpx.Client, title: str) -> list[tuple[dict[str, Any], float]]:
    query = normalize_title(title)
    for params in ({"filter": f"title.search:{query}"}, {"search": query}):
        response = _get(client, OPENALEX_WORKS, {**params, "per-page": 10, "select": SELECT})
        response.raise_for_status()
        matches = [
            (work, title_similarity(title, work.get("title") or ""))
            for work in response.json().get("results", [])
        ]
        matches = [(work, score) for work, score in matches if score >= MATCH_THRESHOLD]
        if matches:
            return matches
    return []


def resolve(client: httpx.Client, title: str, doi: str | None = None) -> Resolution:
    works = _title_matches(client, title)
    if doi:
        response = _get(client, f"{OPENALEX_WORKS}/doi:{doi}", {"select": SELECT})
        if response.status_code == 200:
            # The curated DOI decides identity, but other versions of the same
            # paper found by title (e.g. its arXiv preprint when the publisher
            # blocks downloads) still contribute their PDF links.
            known = response.json()
            others = [(work, score) for work, score in works if _doi(work) != _doi(known)]
            resolution = _from_works(title, [(known, 1.0), *others])
            return resolution
    return _from_works(title, works) if works else Resolution(query_title=title)
