"""Which edition of a paper was actually read.

A corpus that mixes a preprint with the version of record silently changes what its
numbers mean: a preprint's table can differ from the published one, and claiming the
published article while having read the arXiv file would be the same kind of unsourced
assertion this corpus exists to refuse.

So the edition is not declared, it is evidenced. Each record carries

    "edition": "PREPRINT",
    "edition_evidence": {"page_pdf": 1, "quote": "arXiv:2505.08900v6 [physics.ao-ph]"}

The quote is checked by the gate like any other quote — it must exist word for word on
the page it cites — and `classify` must read the declared edition back out of it. The
evidence node carries no `value`, so the gate checks that it locates and does not try to
derive a value from it, and the human audit queue does not grow a claim nobody can rule
on: a reader can see for themselves that the line proves the edition.
"""

from __future__ import annotations

import re

EDITIONS = (
    "VERSION_OF_RECORD",      # the publisher's typeset article
    "ACCEPTED_MANUSCRIPT",    # accepted, not yet final: IEEE early access, a journal proof
    "AUTHOR_MANUSCRIPT",      # the authors' own file, deposited nowhere, not yet published
    "PREPRINT",               # a preprint deposit: arXiv, EarthArXiv, "submitted to"
)

# Ordered: a file that carries an arXiv stamp is the arXiv file, whatever else is on the
# page. The published citation line only settles the edition when nothing contradicts it.
SIGNALS: tuple[tuple[str, str], ...] = (
    (r"arxiv[:\s]*\d{4}\.\d{4,5}", "PREPRINT"),
    (r"arxiv preprint|eartharxiv|essoar|biorxiv", "PREPRINT"),
    (r"manuscript submitted to|submitted to [A-Z]", "PREPRINT"),
    (r"this (?:is a |)preprint|preprint (?:submitted|under|has not|repository)", "PREPRINT"),
    (r"non-?peer reviewed preprint|not (?:yet |)(?:been |)peer[- ]reviewed", "PREPRINT"),
    (r"accepted manuscript|author accepted manuscript", "ACCEPTED_MANUSCRIPT"),
    # IEEE early access: peer review is done, the typesetting is not.
    (r"content may change prior to final publication", "ACCEPTED_MANUSCRIPT"),
    # A publisher's proof still carrying its own placeholders for volume, pages or doi.
    (r"please add (?:article |)doi|\(\(please add", "ACCEPTED_MANUSCRIPT"),
    # An author's file whose running footer names its own revision, with no deposit.
    (r"revised article page \d+ of \d+|submitted article page \d+ of \d+", "AUTHOR_MANUSCRIPT"),
    # The publisher's own typeset header: a journal line with a volume/pages or a DOI.
    (r"https?://doi\.org/10\.\d{4,9}/", "VERSION_OF_RECORD"),
    (r"\bdoi[:\s]*10\.\d{4,9}/", "VERSION_OF_RECORD"),
    (r"received[^.]{0,80}accepted", "VERSION_OF_RECORD"),
    (r"©\s*(?:\d{4}|the author)", "VERSION_OF_RECORD"),
    (r"\b(?:vol(?:ume)?\.?\s*\d+|\d+\s*\(\d+\))\s*[:,]\s*\d+", "VERSION_OF_RECORD"),
    # A journal citation line the publisher prints: "Ocean Sci., 21, 23-45, 2025".
    (r"\b\d{1,3},\s*\d{1,5}\s*[-\u2013]\s*\d{1,5},\s*(?:19|20)\d\d", "VERSION_OF_RECORD"),
)


def classify(quote: str) -> str | None:
    """The edition its own evidence quote proves, or None when it proves nothing."""
    text = re.sub(r"\s+", " ", quote).strip().casefold()
    for pattern, edition in SIGNALS:
        if re.search(pattern, text):
            return edition
    return None
