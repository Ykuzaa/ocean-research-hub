"""Build the public one-page report from the corpus v2 records.

The page is a build artifact of the corpus, never a hand-edited file: every figure in
it is recomputed from `evaluation/gold_v2/*.json`, so a new extraction wave changes the
page by rebuilding it.

    uv run python -m ocean_research_hub.corpus_v2.build_poc
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import sys

TRAINING_FIELDS = ("loss", "optimizer", "learning_rate", "batch_size", "epochs", "hardware")


def _paper_view(path: pathlib.Path) -> dict:
    record = json.loads(path.read_text())
    methods = {m["method_id"]: m for m in record.get("methods", [])}
    datasets = {d["dataset_id"]: d for d in record.get("datasets", [])}

    experiments = []
    for experiment in record.get("experiments", []):
        training = experiment.get("training", {})
        found = {
            key: {
                "value": training[key].get("value"),
                "page": training[key].get("page_printed") or training[key].get("page_pdf"),
                "quote": training[key].get("quote"),
            }
            for key in TRAINING_FIELDS
            if key in training and training[key].get("value") is not None
        }
        method = methods.get(experiment.get("method_id"), {})
        experiments.append({
            "id": experiment["experiment_id"],
            "task": experiment["task"],
            "method": method.get("canonical_name", ""),
            "family": method.get("family", ""),
            "datasets": [datasets.get(i, {}).get("canonical_name", "") for i in experiment.get("dataset_ids", [])],
            "target": experiment.get("target_variable", ""),
            "found": found,
            "missing": [key for key in TRAINING_FIELDS if key not in found],
        })

    results = [{
        "metric": r.get("metric"),
        "raw": r.get("metric_raw"),
        "value": r.get("value"),
        "unit": r.get("unit"),
        "config": r.get("config", ""),
        "baseline": r.get("baseline_name"),
        "baseline_value": r.get("baseline_value"),
        "page": r.get("page_printed") or r.get("page_pdf"),
        "quote": r.get("quote"),
        "best": r.get("is_best_in_table", False),
        "dataset": datasets.get(r.get("dataset_id"), {}).get("canonical_name", r.get("dataset_id") or ""),
    } for r in record.get("results", [])]

    return {
        "slug": path.stem,
        "title": record["paper"]["title"],
        "year": record["paper"].get("year"),
        "venue": record["paper"].get("venue"),
        "doi": record["paper"].get("doi"),
        "pdf_pages": record["source"].get("pdf_pages"),
        "sha": record["source"].get("sha256_prefix"),
        "domains": record["paper"].get("ocean_domains", []),
        "excluded": record.get("excluded"),
        "proposed": [m["canonical_name"] for m in record.get("methods", [])
                     if m.get("role") == "PROPOSED" or m.get("is_novel_in_paper")],
        "baselines": [m["canonical_name"] for m in record.get("methods", []) if m.get("role") == "BASELINE"],
        "experiments": experiments,
        "results": results,
        "limitations": [{"theme": l["theme"], "quote": l["quote"],
                         "page": l.get("page_printed") or l.get("page_pdf")}
                        for l in record.get("limitations", [])],
        "conflicts": [{"field": c.get("field"), "values": c.get("values", []),
                       "chosen": c.get("chosen"), "reason": c.get("reason")}
                      for c in record.get("conflicts", [])],
        "quotes": json.dumps(record).count('"quote"'),
    }


def access_report(manifest_path: pathlib.Path) -> dict | None:
    """Combien de papiers indexés sont seulement atteignables, avant toute extraction."""
    if not manifest_path.exists():
        return None
    entries = json.loads(manifest_path.read_text())
    counts = collections.Counter(entry["status"] for entry in entries)
    reachable = counts["DOWNLOADED"] + counts["ALREADY_PRESENT"] + counts["DUPLICATE"]
    unreachable = counts["BLOCKED"] + counts["NO_OA_PDF"] + counts["UNRESOLVED"]
    return {
        "indexed": len(entries),
        "reachable": reachable,
        "blocked": counts["BLOCKED"],
        "no_oa": counts["NO_OA_PDF"],
        "unresolved": counts["UNRESOLVED"],
        "unreachable": unreachable,
    }


def build(gold_dir: pathlib.Path, manifest: pathlib.Path | None = None) -> dict:
    views = [_paper_view(path) for path in sorted(gold_dir.glob("*.json"))]
    usable = [paper for paper in views if not paper["excluded"]]
    experiments = [e for paper in usable for e in paper["experiments"]]
    results = [(paper, r) for paper in usable for r in paper["results"]]

    # A result is comparable across papers only inside one (dataset, metric, unit) cell.
    cells: dict[tuple, set[str]] = collections.defaultdict(set)
    for paper, result in results:
        cells[(result["dataset"], result["metric"], result["unit"])].add(paper["slug"])
    shared = [cell for cell, papers in cells.items() if len(papers) > 1]

    aggregate = {
        "built_on": datetime.date.today().isoformat(),
        "conflicts": sum(len(paper["conflicts"]) for paper in usable),
        "papers": len(usable),
        "excluded": len(views) - len(usable),
        "experiments": len(experiments),
        "results": len(results),
        "quotes": sum(paper["quotes"] for paper in views),
        "reporting": {key: sum(1 for e in experiments if key in e["found"]) for key in TRAINING_FIELDS},
        "tasks": dict(collections.Counter(e["task"] for e in experiments)),
        "families": dict(collections.Counter(e["family"] for e in experiments if e["family"])),
        "metrics": dict(collections.Counter(r["metric"] for _, r in results)),
        "cells": len(cells),
        "shared_cells": len(shared),
        "figures_only": [paper["slug"] for paper in usable if not paper["results"]],
        "access": access_report(manifest) if manifest else None,
    }
    return {"agg": aggregate, "papers": views}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", default="evaluation/gold_v2")
    parser.add_argument("--template", default="evaluation/gold_v2/poc_template.html")
    parser.add_argument("--out", default=".data/poc.html")
    parser.add_argument("--manifest", default=".data/oa-manifest-full.json")
    args = parser.parse_args()

    payload = build(pathlib.Path(args.gold), pathlib.Path(args.manifest))
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = pathlib.Path(args.template).read_text()
    if "__DATA__" not in template:
        print("le gabarit ne contient pas le marqueur __DATA__")
        return 1
    pathlib.Path(args.out).write_text(template.replace("__DATA__", data))

    agg = payload["agg"]
    print(f"{agg['papers']} papiers retenus, {agg['excluded']} exclus")
    print(f"{agg['experiments']} expériences, {agg['results']} résultats, {agg['quotes']} citations")
    print(f"comparabilité: {agg['shared_cells']} cellule(s) partagée(s) sur {agg['cells']}")
    print(f"résultats uniquement en figures: {len(agg['figures_only'])} papier(s)")
    if agg.get("access"):
        a = agg["access"]
        print(f"accès: {a['reachable']}/{a['indexed']} papiers atteignables "
              f"({a['blocked']} bloqués, {a['no_oa']} sans version ouverte)")
    print(f"page: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
