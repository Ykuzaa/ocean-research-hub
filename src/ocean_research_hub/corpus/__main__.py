"""Seed corpus CLI: resolve the curated titles, then ingest them through the API.

    uv run ocean-research-hub-seed resolve
    uv run ocean-research-hub-seed ingest --select GLONET --select XiHe
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx

from ocean_research_hub.corpus import load_seed
from ocean_research_hub.corpus.openalex import (
    ARXIV_DOI_PREFIX,
    MATCH_THRESHOLD,
    OpenAlexBudgetExhausted,
    Resolution,
    resolve,
    title_similarity,
)

RESOLVED_PATH = Path(__file__).with_name("resolved.json")


def run_resolve() -> None:
    papers = load_seed()["papers"]
    previous = {}
    if RESOLVED_PATH.exists():
        previous = {item["title"]: item for item in json.loads(RESOLVED_PATH.read_text(encoding="utf-8"))}
    resolved: list[dict[str, Any]] = []
    with httpx.Client(timeout=30.0, headers={"user-agent": "ocean-research-hub"}) as client:
        for index, paper in enumerate(papers):
            try:
                resolution = asdict(resolve(client, paper["title"], paper.get("doi")))
            except OpenAlexBudgetExhausted as exc:
                # Keep what was already resolved rather than losing the run.
                print(f"\nStopped: {exc}", flush=True)
                resolved.extend(
                    previous[p["title"]] if p["title"] in previous else {**p, "resolution": asdict(Resolution(p["title"]))}
                    for p in papers[index:]
                )
                break
            resolved.append({**paper, "resolution": resolution})
            status = "PDF" if resolution["pdf_candidates"] else ("meta" if resolution["openalex_id"] else "NOT FOUND")
            print(f"{status:9} {paper['title'][:90]}", flush=True)
            time.sleep(0.15)
    RESOLVED_PATH.write_text(json.dumps(resolved, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    found = sum(1 for item in resolved if item["resolution"]["openalex_id"])
    with_pdf = sum(1 for item in resolved if item["resolution"]["pdf_candidates"])
    print(f"\n{len(resolved)} papers: {found} found, {with_pdf} with an open-access PDF link")


def metadata_for(item: dict[str, Any]) -> dict[str, Any]:
    """Bibliographic metadata from OpenAlex, sent as a secondary source.

    It only fills fields the PDF pass could not verify (primary source wins),
    and its DOI — arXiv DOIs included — gives the paper a stable identity so a
    later PDF extraction upgrades the same record instead of duplicating it.
    """
    resolution = item["resolution"]
    metadata: dict[str, Any] = {
        "title": resolution["title"] or item["title"],
        "authors": resolution.get("authors", []),
        "year": resolution["year"],
        "venue": resolution["venue"],
        "doi": resolution["doi"] or item.get("doi"),
        "source_origin": "SECONDARY_SOURCE",
    }
    return {key: value for key, value in metadata.items() if value not in (None, [], "")}


def ingest_one(api: str, item: dict[str, Any], *, metadata_only: bool) -> str:
    resolution = item["resolution"]
    base: dict[str, Any] = {"domains": item["domains"]}
    if resolution["openalex_id"]:
        base["metadata"] = metadata_for(item)
    # A curated link from seed.json beats OpenAlex's guesses.
    urls = [] if metadata_only else list(
        dict.fromkeys([*filter(None, [item.get("pdf_url")]), *resolution["pdf_candidates"]])
    )
    attempts = [{**base, "pdf_url": url} for url in urls]
    # Without a PDF, Crossref gives the fullest notice (authors included) for
    # publisher DOIs; OpenAlex's is the fallback (and the only option for arXiv).
    doi = (base.get("metadata") or {}).get("doi")
    if doi and not doi.startswith(ARXIV_DOI_PREFIX):
        attempts.append({"doi": doi, "domains": item["domains"], "extract": False})
    if "metadata" in base:
        attempts.append({**base, "extract": False})
    started = time.monotonic()
    last_error = "not found in OpenAlex and no PDF link"
    with httpx.Client(timeout=900.0) as client:
        for body in attempts:
            response = client.post(f"{api}/api/papers/ingest", json=body)
            if response.status_code in (200, 201):
                title = response.json()["paper"]["record"]["paper"]["title"]["value"]
                how = "PDF" if "pdf_url" in body else "metadata only"
                return f"OK   {how:13} {time.monotonic() - started:5.0f}s  {title or item['title']}"
            last_error = response.text[:160]
    return f"FAIL {item['title'][:80]}  ({last_error})"


def already_extracted(api: str) -> list[str]:
    with httpx.Client(timeout=30.0) as client:
        papers = client.get(f"{api}/api/papers", params={"limit": 200}).json()["papers"]
    return [paper["title"] for paper in papers if paper["title"] and paper["extracted_field_count"] > 0]


def run_ingest(api: str, selectors: list[str], concurrency: int, metadata_only: bool) -> None:
    items = json.loads(RESOLVED_PATH.read_text(encoding="utf-8"))
    if selectors:
        wanted = [s.lower() for s in selectors]
        items = [
            item for item in items
            if any(s in f"{item['title']} {item.get('alias', '')}".lower() for s in wanted)
        ]
    # Never pay twice, and never let a metadata-only pass shadow an extraction
    # stored under another identity (e.g. a PDF ingested before its DOI was known).
    done = already_extracted(api)
    items = [
        item for item in items
        if not any(title_similarity(item["title"], title) >= MATCH_THRESHOLD for title in done)
    ]
    mode = "metadata only" if metadata_only else "with PDF extraction"
    print(f"Ingesting {len(items)} papers {mode} ({concurrency} at a time)", flush=True)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for line in pool.map(lambda item: ingest_one(api, item, metadata_only=metadata_only), items):
            print(line, flush=True)
    print("ALL_DONE", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("resolve", help="look every seed title up in OpenAlex")
    ingest = sub.add_parser("ingest", help="ingest resolved papers through the running API")
    ingest.add_argument("--api", default="http://127.0.0.1:8000")
    ingest.add_argument("--select", action="append", default=[], help="title/alias substring (repeatable)")
    ingest.add_argument("--concurrency", type=int, default=3)
    ingest.add_argument(
        "--metadata-only", action="store_true",
        help="store title/authors/year/venue from OpenAlex without PDF extraction (no LLM cost)",
    )
    args = parser.parse_args()
    if args.command == "resolve":
        run_resolve()
    else:
        run_ingest(args.api, args.select, args.concurrency, args.metadata_only)


if __name__ == "__main__":
    sys.exit(main())
