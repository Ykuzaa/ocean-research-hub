"""Fetch open-access PDFs for the corpus, free of charge and without an LLM.

Resolves each DOI through OpenAlex, tries every PDF location it advertises, and keeps
the first response that is actually a PDF. Publisher pages that answer a paywall in
HTML are rejected rather than stored, so a blocked paper stays visibly blocked.

    uv run python -m ocean_research_hub.corpus_v2.fetch_oa --limit 20
    uv run python -m ocean_research_hub.corpus_v2.fetch_oa --doi 10.5194/gmd-15-2183-2022
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request

OPENALEX = "https://api.openalex.org/works/doi:"
USER_AGENT = "ocean-research-hub/0.2 (corpus v2 open-access fetcher)"
PDF_MAGIC = b"%PDF"
MIN_BYTES = 20_000
# arXiv and institutional repositories serve the file directly; publisher landing
# pages often answer HTML, so they are tried last.
PREFERRED = ("arxiv.org", "biorxiv", "essoar", "hal.", "archimer", "zenodo", "osti.gov")


def slugify(text: str, limit: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit].strip("-") or "paper"


def fetch(url: str, timeout: int = 45) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def pdf_candidates(work: dict) -> list[str]:
    urls: list[str] = []
    for location in [work.get("best_oa_location"), work.get("primary_location")]:
        if location and location.get("pdf_url"):
            urls.append(location["pdf_url"])
    for location in work.get("locations") or []:
        if location.get("pdf_url"):
            urls.append(location["pdf_url"])
    if (work.get("open_access") or {}).get("oa_url"):
        urls.append(work["open_access"]["oa_url"])

    seen: list[str] = []
    for url in urls:
        if url not in seen:
            seen.append(url)
    seen.sort(key=lambda url: 0 if any(host in url for host in PREFERRED) else 1)
    return seen


def resolve(doi: str) -> dict | None:
    try:
        return json.loads(fetch(OPENALEX + doi.replace("https://doi.org/", "")))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def download(doi: str, title: str, out_dir: pathlib.Path) -> dict:
    entry: dict = {"doi": doi, "title": title, "status": "UNRESOLVED", "tried": []}
    work = resolve(doi)
    if work is None:
        return entry

    entry["title"] = work.get("title") or title
    entry["year"] = work.get("publication_year")
    entry["is_oa"] = (work.get("open_access") or {}).get("is_oa")
    candidates = pdf_candidates(work)
    if not candidates:
        entry["status"] = "NO_OA_PDF"
        return entry

    target = out_dir / f"{slugify(entry['title'])}.pdf"
    if target.exists() and target.stat().st_size > MIN_BYTES:
        entry.update(status="ALREADY_PRESENT", file=str(target))
        return entry

    # The same paper reaches us under several titles (a preprint and its published
    # version), so a name check is not enough: compare the bytes we already hold.
    known = {
        hashlib.sha256(path.read_bytes()).hexdigest(): path
        for path in out_dir.glob("*.pdf")
        if path.stat().st_size > MIN_BYTES
    }

    for url in candidates[:4]:
        entry["tried"].append(url)
        try:
            payload = fetch(url)
        except Exception as error:  # network, TLS, redirect loops, 403...
            entry[url] = type(error).__name__
            continue
        if not payload.startswith(PDF_MAGIC) or len(payload) < MIN_BYTES:
            entry[url] = f"not a pdf ({len(payload)} bytes)"
            continue
        digest = hashlib.sha256(payload).hexdigest()
        if digest in known:
            entry.update(status="DUPLICATE", file=str(known[digest]), url=url)
            return entry
        target.write_bytes(payload)
        entry.update(
            status="DOWNLOADED",
            file=str(target),
            url=url,
            bytes=len(payload),
            sha256_prefix=hashlib.sha256(payload).hexdigest()[:24],
        )
        return entry

    entry["status"] = "BLOCKED"
    return entry


def corpus_dois(database: pathlib.Path, limit: int) -> list[tuple[str, str]]:
    connection = sqlite3.connect(database)
    rows = connection.execute(
        "select doi, record_json from papers where doi is not null and doi != ''"
    ).fetchall()
    papers = []
    for doi, record_json in rows:
        title = ""
        try:
            title = (json.loads(record_json)["paper"]["title"]["value"] or "")[:200]
        except (KeyError, TypeError, json.JSONDecodeError):
            pass
        papers.append((doi, title))
    return papers[:limit] if limit else papers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=".data/ocean-research-hub.db")
    parser.add_argument("--out", default=".data/golden-pdfs")
    parser.add_argument("--manifest", default=".data/oa-manifest.json")
    parser.add_argument("--limit", type=int, default=0, help="0 = tout le corpus")
    parser.add_argument("--doi", action="append", help="DOI explicite, répétable")
    parser.add_argument("--sleep", type=float, default=1.0, help="pause entre requêtes")
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    papers = [(doi, "") for doi in args.doi] if args.doi else corpus_dois(
        pathlib.Path(args.database), args.limit
    )
    print(f"{len(papers)} DOI à résoudre\n")

    manifest = []
    counts: dict[str, int] = {}
    for index, (doi, title) in enumerate(papers, start=1):
        entry = download(doi, title, out_dir)
        manifest.append(entry)
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
        label = (entry.get("title") or doi)[:58]
        print(f"[{index:3d}/{len(papers)}] {entry['status']:15s} {label}")
        time.sleep(args.sleep)

    pathlib.Path(args.manifest).write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print("\nBILAN")
    for status, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {status:15s} {count}")
    print(f"\nmanifeste: {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
