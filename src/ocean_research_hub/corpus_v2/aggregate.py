"""Agrégation du corpus v2: ce que le dataset sait dire, et ce qu'il ne sait pas dire."""

import collections
import json
import pathlib
import statistics
import sys


def load(folder: pathlib.Path) -> list[dict]:
    records = []
    for path in sorted(folder.glob("*.json")):
        record = json.loads(path.read_text())
        record["_file"] = path.name
        records.append(record)
    return records


def training_values(records: list[dict], field: str) -> list[tuple[str, object]]:
    found = []
    for record in records:
        for experiment in record.get("experiments", []):
            entry = experiment.get("training", {}).get(field)
            if isinstance(entry, dict) and entry.get("value") is not None:
                found.append((record["paper"]["paper_id"], entry["value"]))
    return found


def main(folder: str) -> int:
    records = load(pathlib.Path(folder))
    usable = [r for r in records if not r.get("excluded")]
    print(f"PAPIERS: {len(records)} extraits, {len(usable)} retenus\n")

    experiments = [(r, x) for r in usable for x in r.get("experiments", [])]
    results = [(r, res) for r in usable for res in r.get("results", [])]
    print(f"EXPÉRIENCES: {len(experiments)} | RÉSULTATS: {len(results)}\n")

    print("TÂCHES")
    for task, n in collections.Counter(x["task"] for _, x in experiments).most_common():
        print(f"  {task:34s} {n}")

    print("\nFAMILLES D'ARCHITECTURE (méthodes proposées)")
    families = collections.Counter(
        m["family"] for r in usable for m in r.get("methods", [])
        if m.get("role") == "PROPOSED" or m.get("is_novel_in_paper")
    )
    for family, n in families.most_common():
        print(f"  {family:34s} {n}")

    print("\nDATASETS CITÉS")
    datasets = collections.Counter(
        d["canonical_name"][:46] for r in usable for d in r.get("datasets", [])
    )
    for name, n in datasets.most_common(10):
        print(f"  {name:48s} {n}")

    print("\nRÉGLAGES D'ENTRAÎNEMENT RAPPORTÉS")
    for field in ("optimizer", "learning_rate", "batch_size", "epochs", "hardware", "loss"):
        found = training_values(usable, field)
        total = len(experiments)
        line = f"  {field:15s} {len(found)}/{total} expériences"
        numeric = [v for _, v in found if isinstance(v, (int, float))]
        if len(numeric) >= 2:
            line += f" | min {min(numeric)} médiane {statistics.median(numeric)} max {max(numeric)}"
        elif found and not numeric:
            line += " | " + ", ".join(sorted({str(v)[:22] for _, v in found})[:4])
        print(line)

    print("\nMÉTRIQUES RAPPORTÉES")
    for metric, n in collections.Counter(res["metric"] for _, res in results).most_common():
        print(f"  {metric:22s} {n}")

    print("\nMATRICE DE COUVERTURE tâche x famille (nombre de papiers)")
    cells: dict[tuple[str, str], set] = collections.defaultdict(set)
    for record, experiment in experiments:
        method = next(
            (m for m in record.get("methods", []) if m["method_id"] == experiment.get("method_id")),
            None,
        )
        if method:
            cells[(experiment["task"], method["family"])].add(record["paper"]["paper_id"])
    for (task, family), papers in sorted(cells.items(), key=lambda kv: -len(kv[1])):
        print(f"  {task:32s} x {family:22s} {len(papers)}")

    print("\nCOMPARAISONS UTILISABLES (même dataset + même métrique, >= 2 papiers)")
    comparable = collections.defaultdict(set)
    for record, res in results:
        comparable[(res.get("dataset_id"), res["metric"], res.get("unit"))].add(
            record["paper"]["paper_id"]
        )
    shared = {k: v for k, v in comparable.items() if len(v) >= 2}
    print(f"  {len(shared)} cellule(s) comparables entre papiers sur {len(comparable)} au total")
    for (dataset, metric, unit), papers in list(shared.items())[:6]:
        print(f"  {dataset} / {metric} ({unit}): {len(papers)} papiers")

    print("\nCE QUE LA LITTÉRATURE OMET (absences documentées)")
    missing = collections.Counter(
        entry["field"].split(".")[-1] for r in usable for entry in r.get("not_reported", [])
    )
    for field, n in missing.most_common(10):
        print(f"  {field:24s} absent dans {n} cas")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "evaluation/gold_v2"))
