"""Read-only access to the corpus v2 records, claim by claim.

The gate guarantees that every stored quote exists on the page it cites; this module
turns the same nodes into the unit the app and the human auditor work with: one
**claim** — one value, its quote, its page, and enough context to judge it without
opening the record file.

`claims()` enumerates every node `gate.walk()` checks, plus the values the extractors
read off the rendered page without a quotable sentence (`VALUE_READ_NO_SAFE_QUOTE`):
the gate cannot see those, so the human queue is the only place they can be checked.
"""

from __future__ import annotations

import collections
import functools
import hashlib
import json
import pathlib
import re
from typing import Any, Iterator

from .gate import walk

GOLD_DIR = pathlib.Path("evaluation/gold_v2")

#: Training keys the page shows in a fixed order; anything else a paper reports
#: (beta1, framework, gradient clipping) follows, alphabetically.
TRAINING_ORDER = ("loss", "optimizer", "learning_rate", "batch_size", "epochs", "hardware")

_TOKENS = re.compile(r"([A-Za-z_][A-Za-z_0-9]*)|\[(\d+)\]")

#: Quoted nodes that are provenance, not a claim about the science. The gate proves the
#: quote exists and `test_corpus_v2_edition` proves the declared edition follows from it,
#: so there is nothing left for a human verdict to add — and a claim nobody can rule on
#: would sit in the queue for ever.
PROVENANCE_PATHS = frozenset({"source.edition_evidence"})

#: Results carry the measurement, so they are audited first; identity evidence last.
KIND_PRIORITY = {
    "RESULT": 0,
    "TRAINING": 1,
    "TRAINING_EXTRA": 2,
    "CONFLICT": 3,
    "LIMITATION": 4,
    "METHOD": 5,
    "DATASET": 6,
    "EXCLUSION": 7,
}


def _parse(path: str) -> list[str | int]:
    return [name if name else int(index) for name, index in _TOKENS.findall(path)]


def fingerprint(value: Any, quote: str) -> str:
    """Identity of what a verdict was given on: a re-extraction invalidates it."""
    payload = json.dumps([value, quote], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _page(node: dict) -> int | None:
    return node.get("page_printed") or node.get("page_pdf")


def _status(node: dict) -> str:
    """`QUOTED`, or the contract's status for a value no sentence can carry."""
    return node.get("evidence_status", "QUOTED" if node.get("quote") else "VALUE_READ_NO_SAFE_QUOTE")


def record_slug(path: pathlib.Path) -> str:
    return path.stem


@functools.lru_cache(maxsize=1)
def _load(gold_dir: str, mtime_key: tuple) -> list[tuple[str, dict]]:
    return [
        (record_slug(path), json.loads(path.read_text()))
        for path in sorted(pathlib.Path(gold_dir).glob("*.json"))
    ]


def load_records(gold_dir: pathlib.Path = GOLD_DIR) -> list[tuple[str, dict]]:
    """Every record, cached until a file on disk changes."""
    paths = sorted(gold_dir.glob("*.json"))
    key = tuple((path.name, path.stat().st_mtime_ns) for path in paths)
    return _load(str(gold_dir), key)


def load_record(slug: str, gold_dir: pathlib.Path = GOLD_DIR) -> dict | None:
    for candidate, record in load_records(gold_dir):
        if candidate == slug:
            return record
    return None


def _context(record: dict, path: list[str | int], node: dict) -> tuple[str, str, dict]:
    """Which kind of claim this node is, which field it fills, and what to show with it."""
    methods = {m["method_id"]: m for m in record.get("methods", [])}
    datasets = {d["dataset_id"]: d for d in record.get("datasets", [])}
    head = path[0] if path else ""

    def experiment_context(experiment: dict) -> dict:
        method = methods.get(experiment.get("method_id"), {})
        return {
            "experiment_id": experiment.get("experiment_id"),
            "task": experiment.get("task"),
            "method": method.get("canonical_name"),
            "target": experiment.get("target_variable"),
        }

    if head == "results":
        result = record["results"][path[1]]
        experiments = {e["experiment_id"]: e for e in record.get("experiments", [])}
        experiment = experiments.get(result.get("experiment_id"), {})
        return "RESULT", result.get("metric", "result"), {
            **experiment_context(experiment),
            "metric_raw": result.get("metric_raw"),
            "unit": result.get("unit"),
            "split": result.get("split"),
            "config": result.get("config"),
            "dataset": datasets.get(result.get("dataset_id"), {}).get("canonical_name"),
            "baseline_name": result.get("baseline_name"),
            "baseline_value": result.get("baseline_value"),
            "higher_is_better": result.get("higher_is_better"),
        }

    if head == "experiments":
        experiment = record["experiments"][path[1]]
        field = str(path[3])
        if len(path) > 4:  # experiments[i].training.<field>.extra_evidence[k]
            return "TRAINING_EXTRA", field, {
                **experiment_context(experiment),
                "claim": node.get("claim"),
            }
        return "TRAINING", field, experiment_context(experiment)

    if head == "methods":
        method = record["methods"][path[1]]
        return "METHOD", node.get("field") or "method", {
            "method": method.get("canonical_name"),
            "family": method.get("family"),
            "role": method.get("role"),
            "architecture_note": method.get("architecture_note"),
        }

    if head == "datasets":
        dataset = record["datasets"][path[1]]
        return "DATASET", node.get("field") or "dataset", {
            "dataset": dataset.get("canonical_name"),
            "role": dataset.get("role"),
            "region": dataset.get("region"),
        }

    if head == "limitations":
        return "LIMITATION", record["limitations"][path[1]].get("theme", "limitation"), {}

    if head == "conflicts":
        conflict = record["conflicts"][path[1]]
        return "CONFLICT", conflict.get("field", "conflict"), {
            "values": conflict.get("values", []),
            "chosen": conflict.get("chosen"),
            "reason": conflict.get("reason"),
        }

    if head == "excluded":
        return "EXCLUSION", "excluded", {"reason": record["excluded"].get("reason")}

    return "OTHER", ".".join(str(token) for token in path), {}


def walk_unquoted(node: Any, path: str = "") -> Iterator[tuple[str, dict]]:
    """Yield the valued nodes the gate cannot check, because they carry no quote.

    A value printed as mathematics ("10^-4") survives PDF extraction mangled, so the
    contract says to read it off the page and store no quote rather than a wrong one.
    Those values are the ones a human most needs to confirm, so they are claims too.
    """
    if isinstance(node, dict):
        if (node.get("value") is not None and node.get("page_pdf") is not None
                and not node.get("quote")):
            yield path, node
        for key, value in node.items():
            yield from walk_unquoted(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk_unquoted(value, f"{path}[{index}]")


def claims(slug: str, record: dict) -> Iterator[dict]:
    """One claim per value carrying evidence: every quoted node, plus the unquotable ones."""
    for path, node in list(walk(record)) + list(walk_unquoted(record)):
        if path in PROVENANCE_PATHS:
            continue
        tokens = _parse(path)
        kind, field, context = _context(record, tokens, node)
        value = node.get("value", node.get("claim"))
        yield {
            "claim_id": f"{slug}::{path}",
            "slug": slug,
            "path": path,
            "kind": kind,
            "field": field,
            "value": value,
            "unit": node.get("unit") or context.get("unit"),
            "page_pdf": node.get("page_pdf"),
            "page_printed": node.get("page_printed"),
            "quote": node.get("quote"),
            "note": node.get("note"),
            # A value with a page but no quote is unquotable by construction; the
            # contract's own status for it, whether or not the record spells it out.
            "evidence_status": node.get(
                "evidence_status", "QUOTED" if node.get("quote") else "VALUE_READ_NO_SAFE_QUOTE"
            ),
            "context": context,
            "fingerprint": fingerprint(value, node.get("quote", "")),
            "paper_title": record["paper"]["title"],
            "pdf": record["source"].get("file"),
        }


def all_claims(gold_dir: pathlib.Path = GOLD_DIR) -> list[dict]:
    return [claim for slug, record in load_records(gold_dir) for claim in claims(slug, record)]


def _training_view(training: dict) -> list[dict]:
    keys = [key for key in TRAINING_ORDER if key in training]
    keys += sorted(key for key in training if key not in TRAINING_ORDER and isinstance(training[key], dict))
    return [{
        "field": key,
        "value": training[key].get("value"),
        "unit": training[key].get("unit"),
        "page": _page(training[key]),
        "quote": training[key].get("quote"),
        "evidence_status": _status(training[key]),
        "note": training[key].get("note"),
        "extra_evidence": [
            {"claim": extra.get("claim"), "page": _page(extra), "quote": extra.get("quote")}
            for extra in training[key].get("extra_evidence", [])
        ],
    } for key in keys if training[key].get("value") is not None]


def paper_summary(slug: str, record: dict) -> dict:
    experiments = record.get("experiments", [])
    methods = {m["method_id"]: m for m in record.get("methods", [])}
    return {
        "slug": slug,
        "title": record["paper"]["title"],
        "year": record["paper"].get("year"),
        "venue": record["paper"].get("venue"),
        "doi": record["paper"].get("doi"),
        "domains": record["paper"].get("ocean_domains", []),
        "excluded": record.get("excluded", {}).get("reason") if record.get("excluded") else None,
        "tasks": sorted({e["task"] for e in experiments}),
        "families": sorted({methods[e["method_id"]]["family"] for e in experiments
                            if e.get("method_id") in methods}),
        "proposed": [m["canonical_name"] for m in record.get("methods", []) if m.get("role") == "PROPOSED"],
        "datasets": [d["canonical_name"] for d in record.get("datasets", [])],
        "experiment_count": len(experiments),
        "result_count": len(record.get("results", [])),
        # The denominator the app shows under the audit count, so it must be the number
        # of claims: the gated nodes minus provenance, plus the values no sentence can
        # carry. Counting gated nodes alone overstated it by the edition evidence and
        # understated it by every VALUE_READ_NO_SAFE_QUOTE.
        "claim_count": (
            sum(1 for path, _ in walk(record) if path not in PROVENANCE_PATHS)
            + sum(1 for _ in walk_unquoted(record))
        ),
        "pdf_pages": record["source"].get("pdf_pages"),
        # Which file the claims were read from: half the corpus is not the published
        # article, and a reader has to see that before comparing two papers' numbers.
        "edition": record["source"].get("edition"),
        # The DOI of the published article when the file read prints none, so a search
        # for it still finds the paper. Kept distinct from `doi`, which is the identifier
        # the file itself carries.
        "resolved_from_doi": (record["source"].get("resolved_from") or {}).get("doi"),
    }


def paper_detail(slug: str, record: dict) -> dict:
    methods = {m["method_id"]: m for m in record.get("methods", [])}
    datasets = {d["dataset_id"]: d for d in record.get("datasets", [])}
    by_experiment: dict[str, list[dict]] = collections.defaultdict(list)
    for result in record.get("results", []):
        by_experiment[result.get("experiment_id")].append({
            "metric": result.get("metric"),
            "metric_raw": result.get("metric_raw"),
            "value": result.get("value"),
            "unit": result.get("unit"),
            "split": result.get("split"),
            "config": result.get("config"),
            "dataset": datasets.get(result.get("dataset_id"), {}).get("canonical_name"),
            "baseline_name": result.get("baseline_name"),
            "baseline_value": result.get("baseline_value"),
            "higher_is_better": result.get("higher_is_better"),
            "is_best_in_table": result.get("is_best_in_table", False),
            "page": _page(result),
            "quote": result.get("quote"),
            "evidence_status": _status(result),
            "note": result.get("note"),
        })

    return {
        **paper_summary(slug, record),
        "source": record["source"],
        "methods": [{
            "name": method.get("canonical_name"),
            "family": method.get("family"),
            "family_raw": method.get("family_raw"),
            "role": method.get("role"),
            "is_novel_in_paper": method.get("is_novel_in_paper", False),
            "architecture_note": method.get("architecture_note"),
            "evidence": [{"field": e.get("field"), "page": _page(e), "quote": e.get("quote")}
                         for e in method.get("evidence", [])],
        } for method in record.get("methods", [])],
        "dataset_records": [{
            "name": dataset.get("canonical_name"),
            "role": dataset.get("role"),
            "variables": dataset.get("variables", []),
            "spatial_resolution": dataset.get("spatial_resolution"),
            "temporal_resolution": dataset.get("temporal_resolution"),
            "region": dataset.get("region"),
            "period": [dataset.get("period_start"), dataset.get("period_end")],
            "evidence": [{"field": e.get("field"), "page": _page(e), "quote": e.get("quote")}
                         for e in dataset.get("evidence", [])],
        } for dataset in record.get("datasets", [])],
        "experiments": [{
            "id": experiment["experiment_id"],
            "task": experiment["task"],
            "task_raw": experiment.get("task_raw"),
            "method": methods.get(experiment.get("method_id"), {}).get("canonical_name"),
            "family": methods.get(experiment.get("method_id"), {}).get("family"),
            "datasets": [datasets.get(i, {}).get("canonical_name", i) for i in experiment.get("dataset_ids", [])],
            "target": experiment.get("target_variable"),
            "note": experiment.get("note"),
            "training": _training_view(experiment.get("training", {})),
            "results": by_experiment.get(experiment["experiment_id"], []),
        } for experiment in record.get("experiments", [])],
        "orphan_results": by_experiment.get(None, []),
        "limitations": [{"theme": l.get("theme"), "page": _page(l), "quote": l.get("quote")}
                        for l in record.get("limitations", [])],
        "conflicts": [{"field": c.get("field"), "values": c.get("values", []), "chosen": c.get("chosen"),
                       "reason": c.get("reason"),
                       "sources": [{"page": _page(s), "quote": s.get("quote")} for s in c.get("sources", [])]}
                      for c in record.get("conflicts", [])],
        "not_reported": [{"field": n.get("field"), "searched": n.get("searched", [])}
                         for n in record.get("not_reported", [])],
        "excluded_evidence": record.get("excluded"),
    }


def search(records: list[tuple[str, dict]], query: str | None, task: str | None,
           family: str | None) -> list[dict]:
    """Filter the corpus the way the browser does: free text, then task, then family."""
    summaries = [paper_summary(slug, record) for slug, record in records]
    if query:
        needle = query.casefold()
        summaries = [s for s in summaries if needle in json.dumps(s, ensure_ascii=False).casefold()]
    if task:
        summaries = [s for s in summaries if task in s["tasks"]]
    if family:
        summaries = [s for s in summaries if family in s["families"]]
    return summaries
