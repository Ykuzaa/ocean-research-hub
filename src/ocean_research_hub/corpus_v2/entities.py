"""Entity views over the corpus: start from a method, a dataset, a variable or a task.

Issues #22 and #23 ask for the literature to be navigable by scientific entity rather
than only by paper, and for the recurring problems and the empty cells of the field to
be visible. Both are answered here, and only from what the corpus actually holds: every
figure on these pages is a count of sourced claims, and every claim keeps its quote.

Two things these views deliberately do not do:

* they never rank methods against each other — the corpus has no shared
  (dataset, metric, unit) cell, so a ranking is not computable from it;
* an empty cell in the coverage matrix is a gap *in this corpus*, which is not the same
  as a research opportunity, and the wording says so wherever it is shown.
"""

from __future__ import annotations

import collections
import pathlib
from typing import Any

from . import store

KINDS = ("family", "task", "dataset", "dataset_group", "variable", "method")

#: Papers name the same source differently ("ERA5 reanalysis (ECMWF)", "ERA5 atmospheric
#: forcing"), so a dataset page keyed on the canonical name is almost always a page about
#: one paper. These keywords group the names by the *source* they come from. This is a
#: navigation aid, not a claim: the canonical name read from each paper is kept intact,
#: and a name matching no rule is grouped under itself.
DATASET_GROUPS: dict[str, tuple[str, ...]] = {
    "ERA5": ("era5",),
    "MODIS": ("modis",),
    "Sentinel-2": ("sentinel-2", "sentinel 2"),
    "Sentinel-1": ("sentinel-1", "sentinel 1"),
    "ICESat-2": ("icesat",),
    "Argo": ("argo",),
    "CMEMS / Copernicus": ("cmems", "copernicus", "glorys", "duacs", "glo12", "medfs"),
    "AVHRR": ("avhrr",),
    "VIIRS": ("viirs",),
    "SST L4 analyses (OSTIA, Reynolds, GHRSST)": ("ostia", "reynolds", "ghrsst", "oisst"),
    "HYCOM": ("hycom",),
    "NEMO-based simulations": ("nemo", "natl60", "eorca", "orca"),
    "LLC / MITgcm simulations": ("llc", "mitgcm"),
    "ROMS simulations": ("roms",),
    "MOM6 / OM4 simulations": ("mom6", "om4"),
    "World Ocean Atlas / Database": ("world ocean atlas", "world ocean database", "woa"),
    "In-situ networks (tide gauges, buoys, gliders)": ("tide gauge", "buoy", "glider", "mooring"),
    "Lidar / airborne surveys": ("lidar", "aerial", "orthoimagery"),
    "LES / idealised simulations": ("large eddy", "les suite", "idealised", "idealized"),
    "CMIP / climate model output": ("cmip",),
}


def dataset_group(name: str | None) -> str | None:
    """Which source a dataset name belongs to, by keyword; the name itself when unmatched."""
    if not name:
        return None
    lowered = name.casefold()
    for group, keywords in DATASET_GROUPS.items():
        if any(keyword in lowered for keyword in keywords):
            return group
    return name

TRAINING_KEYS = ("loss", "optimizer", "learning_rate", "batch_size", "epochs", "hardware")


def _blank() -> dict:
    return {
        "papers": {},
        "experiments": [],
        "tasks": collections.Counter(),
        "families": collections.Counter(),
        "datasets": collections.Counter(),
        "variables": collections.Counter(),
        "methods": collections.Counter(),
        "metrics": collections.Counter(),
        "reporting": collections.Counter(),
        "results": 0,
    }


def _keys_for(kind: str, experiment: dict, method: dict, datasets: list[str]) -> list[str]:
    if kind == "family":
        return [method.get("family")] if method.get("family") else []
    if kind == "task":
        return [experiment["task"]]
    if kind == "variable":
        return [experiment.get("target_variable")] if experiment.get("target_variable") else []
    if kind == "method":
        return [method.get("canonical_name")] if method.get("canonical_name") else []
    if kind == "dataset":
        return [name for name in datasets if name]
    if kind == "dataset_group":
        return sorted({group for group in (dataset_group(name) for name in datasets) if group})
    return []


def build(gold_dir: pathlib.Path = store.GOLD_DIR) -> dict:
    """Index every experiment under each entity it belongs to."""
    index: dict[str, dict[str, dict]] = {kind: {} for kind in KINDS}
    limitations: dict[str, list[dict]] = collections.defaultdict(list)
    coverage: dict[tuple[str, str], set[str]] = collections.defaultdict(set)

    for slug, record in store.load_records(gold_dir):
        if record.get("excluded"):
            continue
        methods = {m["method_id"]: m for m in record.get("methods", [])}
        names = {d["dataset_id"]: d.get("canonical_name") for d in record.get("datasets", [])}
        results_by_experiment: dict[str, list[dict]] = collections.defaultdict(list)
        for result in record.get("results", []):
            results_by_experiment[result.get("experiment_id")].append(result)

        for limitation in record.get("limitations", []):
            limitations[limitation.get("theme", "OTHER")].append({
                "slug": slug, "title": record["paper"]["title"],
                "quote": limitation.get("quote"),
                "page": limitation.get("page_printed") or limitation.get("page_pdf"),
            })

        for experiment in record.get("experiments", []):
            method = methods.get(experiment.get("method_id"), {})
            datasets = [names.get(i) for i in experiment.get("dataset_ids", [])]
            training = experiment.get("training", {})
            reported = [key for key in TRAINING_KEYS
                        if key in training and training[key].get("value") is not None]
            rows = results_by_experiment.get(experiment["experiment_id"], [])
            if method.get("family"):
                coverage[(experiment["task"], method["family"])].add(slug)

            for kind in KINDS:
                for key in _keys_for(kind, experiment, method, datasets):
                    bucket = index[kind].setdefault(key, _blank())
                    bucket["papers"][slug] = {"slug": slug, "title": record["paper"]["title"],
                                              "year": record["paper"].get("year")}
                    bucket["experiments"].append({
                        "slug": slug, "id": experiment["experiment_id"], "task": experiment["task"],
                        "method": method.get("canonical_name"), "family": method.get("family"),
                        "datasets": [d for d in datasets if d],
                        "variable": experiment.get("target_variable"),
                        "reported": reported,
                        "missing": [key for key in TRAINING_KEYS if key not in reported],
                        "results": len(rows),
                    })
                    bucket["tasks"][experiment["task"]] += 1
                    if method.get("family"):
                        bucket["families"][method["family"]] += 1
                    if method.get("canonical_name"):
                        bucket["methods"][method["canonical_name"]] += 1
                    for name in datasets:
                        if name:
                            bucket["datasets"][name] += 1
                    if experiment.get("target_variable"):
                        bucket["variables"][experiment["target_variable"]] += 1
                    for row in rows:
                        bucket["metrics"][row.get("metric")] += 1
                    bucket["results"] += len(rows)
                    for key in reported:
                        bucket["reporting"][key] += 1

    return {"index": index, "limitations": dict(limitations), "coverage": coverage}


def _summary(name: str, bucket: dict) -> dict:
    experiments = len(bucket["experiments"])
    return {
        "name": name,
        "papers": len(bucket["papers"]),
        "experiments": experiments,
        "results": bucket["results"],
        "tasks": dict(bucket["tasks"].most_common()),
        "families": dict(bucket["families"].most_common()),
        "datasets": dict(bucket["datasets"].most_common(8)),
        "variables": dict(bucket["variables"].most_common(8)),
        "methods": dict(bucket["methods"].most_common(8)),
        "metrics": dict(bucket["metrics"].most_common(8)),
        # The reporting rate is the point of the corpus: it is always given as a share of
        # the experiments this entity covers, never as a bare count.
        "reporting": {key: {"reported": bucket["reporting"].get(key, 0), "of": experiments}
                      for key in TRAINING_KEYS},
    }


def overview(gold_dir: pathlib.Path = store.GOLD_DIR) -> dict:
    data = build(gold_dir)
    index = data["index"]
    tasks = sorted({task for task, _ in data["coverage"]})
    families = sorted({family for _, family in data["coverage"]})
    matrix = [{"task": task, "cells": [
        {"family": family, "papers": len(data["coverage"].get((task, family), set()))}
        for family in families]} for task in tasks]
    empty = [(task, family) for task in tasks for family in families
             if not data["coverage"].get((task, family))]

    return {
        "entities": {kind: [_summary(name, bucket)
                            for name, bucket in sorted(index[kind].items(),
                                                       key=lambda kv: -len(kv[1]["papers"]))]
                     for kind in KINDS},
        "coverage": {"tasks": tasks, "families": families, "matrix": matrix,
                     "empty_cells": [{"task": t, "family": f} for t, f in empty],
                     "caveat": ("Une case vide est un trou dans ce corpus, pas une opportunité "
                                "de recherche démontrée: elle peut aussi signifier que la "
                                "combinaison n'a pas de sens, ou que le papier qui la traite "
                                "n'est pas accessible.")},
        "problems": {theme: {"papers": len({item["slug"] for item in items}), "items": items}
                     for theme, items in sorted(data["limitations"].items(),
                                                key=lambda kv: -len(kv[1]))},
    }


def detail(kind: str, name: str, gold_dir: pathlib.Path = store.GOLD_DIR) -> dict | None:
    if kind not in KINDS:
        return None
    data = build(gold_dir)
    bucket = data["index"][kind].get(name)
    if bucket is None:
        return None
    slugs = set(bucket["papers"])
    problems = [{"theme": theme, **item}
                for theme, items in data["limitations"].items()
                for item in items if item["slug"] in slugs]
    return {
        "kind": kind,
        **_summary(name, bucket),
        "paper_list": sorted(bucket["papers"].values(), key=lambda p: (p["year"] or 0), reverse=True),
        "experiment_list": bucket["experiments"],
        "problems": problems,
        "comparability": ("Les valeurs de ces papiers ne sont pas comparables entre elles: "
                          "aucune combinaison (jeu de données, métrique, unité) n'est partagée "
                          "par deux d'entre eux. Cette page décrit des pratiques, pas un classement."),
    }


def main(argv: list[str]) -> int:
    data = overview()
    for kind in KINDS:
        rows = data["entities"][kind][:6]
        print(f"\n== {kind} ==")
        for row in rows:
            reported = row["reporting"]["learning_rate"]
            print(f"  {row['name'][:46]:46s} {row['papers']:3d} papiers "
                  f"{row['experiments']:3d} expériences  lr {reported['reported']}/{reported['of']}")
    shared = [row for row in data["entities"]["dataset_group"] if row["papers"] > 1]
    print(f"\nsources de données présentes dans plus d'un papier: {len(shared)} sur "
          f"{len(data['entities']['dataset_group'])}")
    print(f"cases vides de la matrice: {len(data['coverage']['empty_cells'])} sur "
          f"{len(data['coverage']['tasks']) * len(data['coverage']['families'])}")
    print("problèmes récurrents:", {k: v["papers"] for k, v in list(data["problems"].items())[:6]})
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
