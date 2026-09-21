"""QA regressions for the independent evidence re-verification tool.

The tool exists so an auditor does not have to trust the extractor. These tests
therefore check that it actually fails when the artifact is wrong, not only
that it passes when the artifact is right.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ocean_research_hub.evaluation.verify_evidence import check_paper, render

PDF_DIR = Path(".data/golden-pdfs")
PDF_NAME = "4dvarnet-ssh-2023"


def _artifact(evidence: str, page: int, status: str = "NOT_VERIFIED") -> dict[str, object]:
    content = (PDF_DIR / f"{PDF_NAME}.pdf").read_bytes()
    return {
        "id": PDF_NAME,
        "primary_pdf_url": "https://example.test/unused-when-cached.pdf",
        "primary_pdf_sha256": hashlib.sha256(content).hexdigest(),
        "supplement_url": None,
        "supplement_sha256": None,
        "fields": [{
            "path": "training.optimizer",
            "status": status,
            "source": {
                "origin": "PRIMARY_PAPER", "page": page,
                "section": None, "locator": "test", "evidence": evidence,
            },
            "sources": [],
        }],
    }


pytestmark = pytest.mark.skipif(
    not (PDF_DIR / f"{PDF_NAME}.pdf").exists(),
    reason="pinned source PDF is not cached in this environment",
)


def test_real_snippet_on_its_real_page_reverifies() -> None:
    checks, digest = check_paper(_artifact("Adam optimizer", 2124), PDF_DIR, offline=True)

    assert [check.outcome for check in checks] == ["LOCATED"]
    assert digest["primary_sha256_matches"] is True


def test_real_snippet_attributed_to_the_wrong_page_fails() -> None:
    """Citing a real sentence to a page it is not on must not re-verify."""
    checks, _ = check_paper(_artifact("Adam optimizer", 2120), PDF_DIR, offline=True)

    assert [check.outcome for check in checks] == ["NOT_LOCATED"]


def test_invented_snippet_fails() -> None:
    checks, _ = check_paper(
        _artifact("We trained with the Shampoo optimizer for 4000 epochs", 2124),
        PDF_DIR, offline=True,
    )

    assert [check.outcome for check in checks] == ["NOT_LOCATED"]


def test_page_absent_from_the_source_is_reported_distinctly() -> None:
    checks, _ = check_paper(_artifact("Adam optimizer", 99999), PDF_DIR, offline=True)

    assert [check.outcome for check in checks] == ["PAGE_NOT_FOUND"]


def test_a_tampered_hash_is_surfaced_rather_than_ignored() -> None:
    artifact = _artifact("Adam optimizer", 2124)
    artifact["primary_pdf_sha256"] = "0" * 64
    checks, digest = check_paper(artifact, PDF_DIR, offline=True)

    assert digest["primary_sha256_matches"] is False
    assert "NO" in render(checks, [digest])


def test_absent_and_errored_fields_are_not_evidence_checked() -> None:
    """Only asserted claims owe evidence; absence must not be counted as a failure."""
    for status in ("NOT_REPORTED", "EXTRACTION_ERROR"):
        artifact = _artifact("Adam optimizer", 2124, status=status)
        checks, _ = check_paper(artifact, PDF_DIR, offline=True)
        assert checks == []


def test_missing_pdf_is_a_visible_failure_under_offline() -> None:
    artifact = _artifact("Adam optimizer", 2124)
    artifact["id"] = "not-a-cached-paper"
    with pytest.raises(FileNotFoundError):
        check_paper(artifact, PDF_DIR, offline=True)


def test_report_lists_every_failing_record() -> None:
    checks, digest = check_paper(_artifact("not in this paper at all", 2124), PDF_DIR, offline=True)
    report = render(checks, [digest])

    assert "training.optimizer" in report
    assert "NOT_LOCATED" in report
    assert "None. Every asserted claim" not in report


def test_json_round_trips_for_the_audit_package() -> None:
    checks, digest = check_paper(_artifact("Adam optimizer", 2124), PDF_DIR, offline=True)
    payload = json.dumps({"hashes": [digest], "checks": [check.__dict__ for check in checks]})

    assert json.loads(payload)["checks"][0]["outcome"] == "LOCATED"
