"""Deterministic gate for corpus v2 records.

Two independent checks, reported separately because they answer different questions:

* **locate** — does the stored quote exist, word for word, on the page it cites?
* **support** — does the stored value actually follow from that quote?

A record passes the gate only when every quote locates. Support failures are reported
as warnings, because a value may legitimately be a normalisation of its quote
("Adam optimizer" -> "adam"); they are the queue a human auditor should review first.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unicodedata
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Iterator

import logging

from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)

LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
DASHES = {"−": "-", "–": "-", "—": "-"}
QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"'}


def normalise(text: str) -> str:
    """Collapse a PDF page or a stored quote to a comparable form."""
    text = unicodedata.normalize("NFKC", text)
    for mapping in (LIGATURES, DASHES, QUOTES):
        for bad, good in mapping.items():
            text = text.replace(bad, good)
    # PDF line-break hyphenation ("parame-\nter") reaches stored quotes as
    # "parame- ter"; joining both forms keeps the two sides comparable.
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    text = re.sub(r"[^0-9a-zA-Z]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _numbers(text: str) -> set[str]:
    """Numeric tokens of a text, normalised so 0.50 and .5 compare equal.

    Papers print exponents with a Unicode minus ("5e−5") and thousands separators,
    so both are folded before the numbers are read.
    """
    for bad, good in DASHES.items():
        text = text.replace(bad, good)
    found = set()
    # The leading minus counts as a sign unless a digit precedes it, so "log(-2.498)"
    # yields -2.498 while a hyphenated "10-5" still yields 10 and 5. The lookbehind must
    # not exclude letters: PDF extraction glues numbers to words ("MLDRMSE3.83").
    for raw in re.findall(r"(?<![\d.])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", text.replace(",", "")):
        try:
            value = float(raw)
        except ValueError:
            continue
        found.add(f"{value:g}")
    return found


def supports(value: Any, quote: str) -> bool:
    """Is `value` derivable from `quote` without outside knowledge?"""
    if isinstance(value, bool) or value is None:
        return True
    if isinstance(value, (int, float)):
        return f"{float(value):g}" in _numbers(quote)
    if isinstance(value, (list, tuple)):
        return all(supports(item, quote) for item in value)
    if not isinstance(value, str):
        return True

    haystack = normalise(quote)
    if not haystack:
        return False
    needle = normalise(value)
    if needle and needle in haystack:
        return True
    # A normalised value ("weighted reconstruction losses plus gradient terms") is a
    # rewording of its quote: require most of its content words to be present.
    words = [w for w in needle.split() if len(w) > 3]
    if not words:
        return needle in haystack
    hits = sum(1 for word in words if word in haystack)
    return hits / len(words) >= 0.5


@dataclass
class Report:
    checked: int = 0
    locate_failures: list[str] = dataclass_field(default_factory=list)
    support_warnings: list[str] = dataclass_field(default_factory=list)
    pagination_warnings: list[str] = dataclass_field(default_factory=list)

    @property
    def located(self) -> int:
        return self.checked - len(self.locate_failures)

    @property
    def ok(self) -> bool:
        return not self.locate_failures


def walk(node: Any, path: str = "") -> Iterator[tuple[str, dict]]:
    """Yield every node carrying a quote and the PDF page it cites."""
    if isinstance(node, dict):
        if node.get("quote") and node.get("page_pdf") is not None:
            yield path, node
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")


def check(record: dict, repo_root: pathlib.Path) -> Report:
    pdf = repo_root / record["source"]["file"]
    pages = [normalise(page.extract_text() or "") for page in PdfReader(str(pdf)).pages]
    offset = record["source"].get("printed_page_offset", 0)
    report = Report()

    for path, claim in walk(record):
        report.checked += 1
        index = claim["page_pdf"] - 1
        needle = normalise(claim["quote"])

        if not (0 <= index < len(pages) and needle in pages[index]):
            elsewhere = [i + 1 for i, text in enumerate(pages) if needle in text]
            report.locate_failures.append(
                f"{path}: cited p{claim['page_pdf']}, found on {elsewhere or 'nowhere'}"
                f"\n    quote: {claim['quote'][:100]}"
            )
            continue

        if "value" in claim and not supports(claim["value"], claim["quote"]):
            report.support_warnings.append(
                f"{path}: value {claim['value']!r} is not derivable from its quote"
            )

        printed = claim.get("page_printed")
        if printed is not None and printed - offset != claim["page_pdf"]:
            report.pagination_warnings.append(
                f"{path}: printed p{printed} vs pdf p{claim['page_pdf']} at offset {offset}"
            )

    return report


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m ocean_research_hub.corpus_v2.gate <record.json> [...]")
        return 2

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    worst = 0
    for target in argv:
        record = json.loads(pathlib.Path(target).read_text())
        report = check(record, repo_root)
        name = pathlib.Path(target).stem

        for failure in report.locate_failures:
            print(f"FAIL {name} {failure}")
        for warning in report.support_warnings:
            print(f"WARN {name} {warning}")
        for warning in report.pagination_warnings:
            print(f"PAGE {name} {warning}")

        status = "ok" if report.ok else "FAILED"
        print(
            f"{name}: {report.located}/{report.checked} quotes located, "
            f"{len(report.support_warnings)} support warning(s) — {status}"
        )
        worst = max(worst, 0 if report.ok else 1)
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
