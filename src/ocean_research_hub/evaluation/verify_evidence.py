"""Independent re-verification of stored evidence against the original PDFs.

The extraction artifacts are produced by the same code whose behaviour an
auditor is being asked to trust. This module closes that loop: it re-downloads
or re-reads each pinned PDF, re-hashes it, re-parses it, and re-checks every
stored evidence snippet against the page it claims to come from - without
importing any extraction rule, profile, or provider.

A reviewer can therefore establish, independently of the runner's own report,
whether each populated scientific claim is anchored in real source text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ocean_research_hub.ingestion.pdf import PdfParser, normalize_text

ASSERTED_STATUSES = {"NOT_VERIFIED", "CONFLICT"}


@dataclass(frozen=True)
class EvidenceCheck:
    paper_id: str
    path: str
    origin: str
    page: int | None
    outcome: str
    detail: str


def _page_text(pages: list[Any], page: int) -> str | None:
    found = next((item for item in pages if item.page == page), None)
    return None if found is None else normalize_text(found.text)


def check_paper(
    paper: dict[str, Any], pdf_dir: Path, *, offline: bool = False,
) -> tuple[list[EvidenceCheck], dict[str, Any]]:
    """Re-verify one paper's asserted evidence. Never trusts the artifact's text."""
    target = pdf_dir / f"{paper['id']}.pdf"
    if not target.exists():
        if offline:
            raise FileNotFoundError(f"{target} is missing and --offline was requested")
        with urllib.request.urlopen(paper["primary_pdf_url"], timeout=120) as response:
            target.write_bytes(response.read())
    content = target.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    primary = PdfParser().parse(content, source_name=target.name)

    supplement_pages: list[Any] = []
    supplement_digest: str | None = None
    if paper.get("supplement_url"):
        supplement_target = pdf_dir / f"{paper['id']}-supplement.pdf"
        if not supplement_target.exists():
            if offline:
                raise FileNotFoundError(
                    f"{supplement_target} is missing and --offline was requested"
                )
            with urllib.request.urlopen(paper["supplement_url"], timeout=120) as response:
                supplement_target.write_bytes(response.read())
        supplement_content = supplement_target.read_bytes()
        supplement_digest = hashlib.sha256(supplement_content).hexdigest()
        supplement_pages = PdfParser().parse(
            supplement_content, source_name=supplement_target.name
        ).pages

    checks: list[EvidenceCheck] = []
    for field in paper["fields"]:
        if field["status"] not in ASSERTED_STATUSES:
            continue
        records = [field["source"], *field.get("sources", [])]
        supplied = [record for record in records if record.get("evidence")]
        if not supplied:
            checks.append(EvidenceCheck(
                paper["id"], field["path"], "—", None, "NO_EVIDENCE",
                "an asserted claim carries no evidence snippet at all",
            ))
            continue
        for record in supplied:
            origin = record.get("origin") or "PRIMARY_PAPER"
            pages = supplement_pages if origin == "SUPPLEMENTARY_MATERIAL" else primary.pages
            page_number = record.get("page")
            text = None if page_number is None else _page_text(pages, page_number)
            if text is None:
                checks.append(EvidenceCheck(
                    paper["id"], field["path"], origin, page_number, "PAGE_NOT_FOUND",
                    "the cited page does not exist in the re-parsed source",
                ))
                continue
            snippet = normalize_text(record["evidence"])
            if snippet.lower() in text.lower():
                checks.append(EvidenceCheck(
                    paper["id"], field["path"], origin, page_number, "LOCATED",
                    "snippet found verbatim on the cited page",
                ))
            else:
                checks.append(EvidenceCheck(
                    paper["id"], field["path"], origin, page_number, "NOT_LOCATED",
                    "snippet is not present on the cited page of the re-parsed source",
                ))

    return checks, {
        "id": paper["id"],
        "recorded_primary_sha256": paper.get("primary_pdf_sha256"),
        "recomputed_primary_sha256": digest,
        "primary_sha256_matches": digest == paper.get("primary_pdf_sha256"),
        "recorded_supplement_sha256": paper.get("supplement_sha256"),
        "recomputed_supplement_sha256": supplement_digest,
        "supplement_sha256_matches": (
            supplement_digest == paper.get("supplement_sha256")
            if paper.get("supplement_url") else None
        ),
    }


def render(checks: list[EvidenceCheck], hashes: list[dict[str, Any]]) -> str:
    by_paper: dict[str, list[EvidenceCheck]] = {}
    for check in checks:
        by_paper.setdefault(check.paper_id, []).append(check)
    rows = [
        "# Independent evidence re-verification",
        "",
        "Every asserted claim in the extraction artifact was re-checked against a",
        "freshly parsed copy of the pinned PDF. This tool imports no extraction",
        "rule and no provider: it only asks whether the stored snippet is really",
        "on the page the artifact cites.",
        "",
        "| Paper | Recorded SHA-256 reproduced | Asserted evidence records | Located | Not located | Page missing | No evidence |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    digest_by_paper = {item["id"]: item for item in hashes}
    for paper_id, items in by_paper.items():
        digest = digest_by_paper.get(paper_id, {})
        reproduced = digest.get("primary_sha256_matches")
        if digest.get("supplement_sha256_matches") is False:
            reproduced = False
        rows.append("| " + " | ".join((
            f"`{paper_id}`",
            "yes" if reproduced else "NO",
            str(len(items)),
            str(sum(item.outcome == "LOCATED" for item in items)),
            str(sum(item.outcome == "NOT_LOCATED" for item in items)),
            str(sum(item.outcome == "PAGE_NOT_FOUND" for item in items)),
            str(sum(item.outcome == "NO_EVIDENCE" for item in items)),
        )) + " |")

    failures = [item for item in checks if item.outcome != "LOCATED"]
    rows.extend(("", "## Evidence records that did not re-verify", ""))
    if not failures:
        rows.append("None. Every asserted claim's snippet was relocated in its cited source.")
    else:
        rows.append("| Paper | Field path | Origin | Page | Outcome | Detail |")
        rows.append("|---|---|---|---:|---|---|")
        for item in failures:
            rows.append("| " + " | ".join((
                f"`{item.paper_id}`", item.path, item.origin,
                "—" if item.page is None else str(item.page), item.outcome, item.detail,
            )) + " |")
    rows.extend((
        "",
        "A `LOCATED` result proves only that the quotation is real and correctly",
        "cited. It does not certify that the normalized value is the scientifically",
        "correct reading of that quotation; that remains the independent Scientific",
        "Auditor's decision.",
        "",
    ))
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-verify stored extraction evidence against the pinned source PDFs",
    )
    parser.add_argument("extraction_json", type=Path)
    parser.add_argument("--pdf-dir", type=Path, default=Path(".data/golden-pdfs"))
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument(
        "--offline", action="store_true",
        help="Fail instead of downloading a PDF that is not already cached",
    )
    args = parser.parse_args()

    artifact = json.loads(args.extraction_json.read_text(encoding="utf-8"))
    args.pdf_dir.mkdir(parents=True, exist_ok=True)
    checks: list[EvidenceCheck] = []
    hashes: list[dict[str, Any]] = []
    for paper in artifact["papers"]:
        paper_checks, digest = check_paper(paper, args.pdf_dir, offline=args.offline)
        checks.extend(paper_checks)
        hashes.append(digest)

    report = render(checks, hashes)
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(report, encoding="utf-8")
    payload = {
        "schema_version": 1,
        "source_artifact": str(args.extraction_json),
        "hashes": hashes,
        "checks": [check.__dict__ for check in checks],
        "totals": {
            outcome: sum(check.outcome == outcome for check in checks)
            for outcome in ("LOCATED", "NOT_LOCATED", "PAGE_NOT_FOUND", "NO_EVIDENCE")
        },
    }
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["totals"], indent=2))


if __name__ == "__main__":
    main()
