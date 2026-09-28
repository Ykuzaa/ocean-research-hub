"""Invariants of the #29 field-path mapping pre-review (AI_INTERPRETATION, not validated)."""

import csv
import json
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
PREREVIEW = ROOT / "evaluation/field_mapping/b16-field-path-map-prereview.json"
B16 = ROOT / "import_staging/Ocean_Research_Intelligence_ENRICHED_B16.xlsx"
BASE = ROOT / "import_staging/Ocean_Research_Hub_COMPLET.xlsx"  # holds FIELD_CONTRACT


def _load():
    return json.loads(PREREVIEW.read_text(encoding="utf-8"))


def _sheet_column(name, column, workbook=B16):
    book = openpyxl.load_workbook(workbook, read_only=True)
    rows = book[name].iter_rows(values_only=True)
    header = next(rows)
    index = header.index(column)
    return [row[index] for row in rows if row[index] is not None]


def test_prereview_is_pending_ai_interpretation_only():
    doc = _load()
    assert doc["status"] == "PROPOSAL_PENDING_HUMAN_VALIDATION"
    for rule in doc["rules"]:
        assert rule["provenance_type"] == "AI_INTERPRETATION"
        assert rule["review_status"] == "PENDING"
        assert rule["human_validation_required"] is True


def test_prereview_covers_exactly_the_b16_map():
    doc = _load()
    assert sorted(r["original_path"] for r in doc["rules"]) == sorted(
        _sheet_column("FIELD_PATH_MAP", "field_path")
    )


def test_mapped_targets_are_contract_fields_and_independently_concurred():
    contract = set(_sheet_column("FIELD_CONTRACT", "field_path", BASE))
    for rule in _load()["rules"]:
        if rule["proposed_decision"] != "MAPPED":
            assert rule["proposed_canonical_path"] is None
            continue
        assert rule["proposed_canonical_path"] in contract
        if rule["source_decision"] == "MAPPED":
            assert rule["proposed_canonical_path"] == rule["original_path"]
        else:
            assert rule.get("auditor_verdict") == "CONCUR", rule["original_path"]


def test_csv_matches_json():
    doc = _load()
    with open(PREREVIEW.with_suffix(".csv"), newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [(r["original_path"], r["proposed_decision"]) for r in rows] == [
        (r["original_path"], r["proposed_decision"]) for r in doc["rules"]
    ]
    assert all(not r["human_decision"] for r in rows)
