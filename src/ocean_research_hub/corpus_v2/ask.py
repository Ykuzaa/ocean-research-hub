"""Ask the corpus a question, and get quoted claims back (issue #24).

This is deliberately **not** a chat over PDFs. A question is parsed into filters and
aggregations over the claims, and the answer is the matching claims with the sentence
each value was read from. Three properties follow from that choice:

* it costs nothing to run and needs no model at query time;
* it can always say what it understood, term by term, and what it did not;
* it cannot invent an answer, because every line it returns is a stored claim.

What it will not do is rank methods against each other: no (dataset, metric, unit) cell
is shared by two papers in this corpus, so a ranking is not computable from it. When a
question asks for one, the answer says so instead of producing a number.
"""

from __future__ import annotations

import pathlib
import re
import unicodedata
from typing import Any

from . import entities, store

#: Training fields, by the words a question is likely to use (French and English).
FIELD_WORDS: dict[str, tuple[str, ...]] = {
    "learning_rate": ("learning rate", "taux d apprentissage", "lr", "pas d apprentissage"),
    "batch_size": ("batch size", "batch", "taille de lot", "taille des lots", "lot"),
    "epochs": ("epoch", "epochs", "epoque", "epoques", "iterations"),
    "loss": ("loss", "perte", "fonction de cout", "cout", "objectif d entrainement"),
    "optimizer": ("optimizer", "optimiseur", "adam", "adamw", "sgd"),
    "hardware": ("hardware", "materiel", "gpu", "carte graphique", "machine", "calcul"),
}

LIMITATION_WORDS = ("limite", "limites", "limitation", "limitations", "probleme", "problemes",
                    "faiblesse", "difficulte", "obstacle")
RESULT_WORDS = ("resultat", "resultats", "rmse", "mae", "score", "performance", "precision",
                "erreur", "r2", "correlation", "biais", "accuracy")
RANKING_WORDS = ("meilleur", "meilleure", "meilleurs", "best", "classement", "ranking",
                 "plus performant", "superieur", "comparer", "comparaison", "versus", "vs")

#: Tasks, by the word a French question uses for them.
TASK_WORDS: dict[str, str] = {
    "FORECASTING": "prevision",
    "DATA_ASSIMILATION": "assimilation",
    "GAP_FILLING_RECONSTRUCTION": "reconstruction",
    "SUPER_RESOLUTION": "super resolution",
    "BATHYMETRY_ESTIMATION": "bathymetrie",
    "CLASSIFICATION_SEGMENTATION": "classification",
    "DETECTION": "detection",
    "PARAMETERIZATION": "parametrisation",
    "BIAS_CORRECTION": "correction de biais",
    "EMULATION_SURROGATE": "emulation",
    "INVERSE_INFERENCE": "inversion",
}

#: Limitation themes, by the words a question uses for them.
THEME_WORDS: dict[str, tuple[str, ...]] = {
    "GENERALIZATION": ("generalisation", "generalization", "transfert", "hors domaine"),
    "DATA": ("donnees", "data", "jeu de donnees", "observation"),
    "COMPUTE": ("calcul", "compute", "cout de calcul", "gpu", "memoire"),
    "PHYSICS": ("physique", "physics", "conservation"),
    "UNCERTAINTY": ("incertitude", "uncertainty", "ensemble"),
    "REPRODUCIBILITY": ("reproductibilite", "reproducibility", "code"),
    "EVALUATION": ("evaluation", "validation", "metrique"),
    "FUTURE_WORK": ("travaux futurs", "future work", "suite"),
}


def fold(text: str) -> str:
    """Lowercase, strip accents and punctuation, so 'époques' matches 'epoques'."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-zA-Z]+", " ", text)).strip().casefold()


def _match_words(question: str, words: tuple[str, ...]) -> list[str]:
    return [word for word in words if fold(word) in question]


def _vocabulary(gold_dir: pathlib.Path) -> dict[str, dict[str, str]]:
    """Every entity name the corpus holds, keyed by its folded form."""
    overview = entities.overview(gold_dir)
    vocabulary: dict[str, dict[str, str]] = {}
    for kind in ("task", "family", "dataset_group", "variable", "method"):
        vocabulary[kind] = {fold(row["name"]): row["name"]
                            for row in overview["entities"][kind]}
    # The vocabularies are machine identifiers; a question uses words.
    for identifier, word in TASK_WORDS.items():
        vocabulary["task"][fold(word)] = identifier
    vocabulary["family"].update({
        fold("u-net"): "CNN_UNET", fold("unet"): "CNN_UNET",
        fold("transformeur"): "TRANSFORMER", fold("transformer"): "TRANSFORMER",
        fold("autoencodeur"): "CNN_AUTOENCODER", fold("auto-encodeur"): "CNN_AUTOENCODER",
        fold("convolutif"): "CNN_GENERIC", fold("cnn"): "CNN_GENERIC",
        fold("perceptron"): "MLP_DNN", fold("mlp"): "MLP_DNN",
        fold("operateur neuronal"): "FNO_NEURAL_OPERATOR", fold("fourier"): "FNO_NEURAL_OPERATOR",
        fold("graphe"): "GNN", fold("gnn"): "GNN",
        fold("recurrent"): "RNN_LSTM_GRU", fold("lstm"): "RNN_LSTM_GRU",
        fold("hybride"): "HYBRID_PHYSICS_ML",
        fold("regression symbolique"): "SYMBOLIC_REGRESSION",
    })
    return vocabulary


def parse(question: str, gold_dir: pathlib.Path = store.GOLD_DIR) -> dict[str, Any]:
    """What the corpus understood of a question, term by term."""
    folded = fold(question)
    vocabulary = _vocabulary(gold_dir)

    found: dict[str, list[str]] = {kind: [] for kind in vocabulary}
    for kind, names in vocabulary.items():
        for key, name in names.items():
            # Short keys would match inside other words ("lot" in "pilote").
            if len(key) >= 3 and re.search(rf"\b{re.escape(key)}\b", folded):
                if name not in found[kind]:
                    found[kind].append(name)

    fields = [field for field, words in FIELD_WORDS.items() if _match_words(folded, words)]
    themes = [theme for theme, words in THEME_WORDS.items() if _match_words(folded, words)]
    return {
        "question": question,
        "fields": fields,
        "themes": themes,
        "tasks": found["task"],
        "families": found["family"],
        "dataset_groups": found["dataset_group"],
        "variables": found["variable"],
        "methods": found["method"],
        "asks_for_limitations": bool(_match_words(folded, LIMITATION_WORDS)) or bool(themes),
        "asks_for_results": bool(_match_words(folded, RESULT_WORDS)),
        "asks_for_ranking": bool(_match_words(folded, RANKING_WORDS)),
    }


def _experiment_rows(gold_dir: pathlib.Path) -> list[dict]:
    """Every experiment, flattened with what a question can filter on."""
    rows = []
    for slug, record in store.load_records(gold_dir):
        if record.get("excluded"):
            continue
        methods = {m["method_id"]: m for m in record.get("methods", [])}
        names = {d["dataset_id"]: d.get("canonical_name") for d in record.get("datasets", [])}
        results = [r for r in record.get("results", [])]
        for experiment in record.get("experiments", []):
            method = methods.get(experiment.get("method_id"), {})
            datasets = [names.get(i) for i in experiment.get("dataset_ids", [])]
            rows.append({
                "slug": slug, "title": record["paper"]["title"],
                "id": experiment["experiment_id"], "task": experiment["task"],
                "family": method.get("family"), "method": method.get("canonical_name"),
                "datasets": [d for d in datasets if d],
                "dataset_groups": sorted({g for g in (entities.dataset_group(d) for d in datasets) if g}),
                "variable": experiment.get("target_variable"),
                "training": experiment.get("training", {}),
                "results": [r for r in results if r.get("experiment_id") == experiment["experiment_id"]],
            })
    return rows


def _matches(row: dict, query: dict) -> bool:
    if query["tasks"] and row["task"] not in query["tasks"]:
        return False
    # One word can name both a family and a method ("U-Net"); requiring both would
    # narrow the answer to the single paper whose method carries that exact name.
    if query["families"] or query["methods"]:
        if not (row["family"] in query["families"] or row["method"] in query["methods"]):
            return False
    if query["dataset_groups"] and not set(query["dataset_groups"]) & set(row["dataset_groups"]):
        return False
    if query["variables"] and row["variable"] not in query["variables"]:
        return False
    return True


def answer(question: str, gold_dir: pathlib.Path = store.GOLD_DIR, limit: int = 40) -> dict[str, Any]:
    query = parse(question, gold_dir)
    understood = {key: query[key] for key in
                  ("fields", "themes", "tasks", "families", "dataset_groups", "variables", "methods")}
    if not any(understood.values()) and not query["asks_for_limitations"] and not query["asks_for_results"]:
        # Returning the whole corpus to a question nobody parsed would look like an answer.
        return {
            "question": question, "understood": understood, "understood_nothing": True,
            "experiments_matched": 0, "papers_matched": 0, "answers": [],
            "caveats": ["Aucun terme de cette question ne correspond à ce que le corpus "
                        "contient. Essaie un objectif (bathymétrie, prévision, "
                        "reconstruction), une architecture (U-Net, transformeur, "
                        "opérateur neuronal de Fourier), une source (ERA5, Sentinel-2, "
                        "CMEMS), un réglage (taux d'apprentissage, taille de lot, "
                        "matériel) ou le mot « limites »."],
        }
    rows = [row for row in _experiment_rows(gold_dir) if _matches(row, query)]
    filtered = any(query[key] for key in ("tasks", "families", "dataset_groups", "variables", "methods"))

    caveats: list[str] = []
    answers: list[dict] = []

    if query["asks_for_ranking"]:
        caveats.append(
            "Cette littérature ne permet aucun classement: sur 117 combinaisons "
            "(jeu de données, métrique, unité), aucune n'est partagée par deux papiers. "
            "La question « laquelle est la meilleure » n'a pas de réponse calculable ici."
        )

    for field in query["fields"]:
        values = []
        for row in rows:
            node = row["training"].get(field)
            if node and node.get("value") is not None:
                values.append({
                    "slug": row["slug"], "title": row["title"], "experiment": row["id"],
                    "task": row["task"], "family": row["family"], "method": row["method"],
                    "value": node.get("value"), "unit": node.get("unit"),
                    "page": node.get("page_printed") or node.get("page_pdf"),
                    "quote": node.get("quote"), "note": node.get("note"),
                })
        answers.append({
            "kind": "training", "field": field,
            "reported": len(values), "of": len(rows), "values": values[:limit],
        })
        if len(values) < len(rows):
            caveats.append(
                f"{len(rows) - len(values)} des {len(rows)} expériences concernées ne "
                f"rapportent pas ce réglage: l'absence est enregistrée avec le périmètre cherché."
            )

    if query["asks_for_results"]:
        measured = [{
            "slug": row["slug"], "title": row["title"], "experiment": row["id"],
            "metric": result.get("metric"), "metric_raw": result.get("metric_raw"),
            "value": result.get("value"), "unit": result.get("unit"),
            "split": result.get("split"), "config": result.get("config"),
            "baseline_name": result.get("baseline_name"), "baseline_value": result.get("baseline_value"),
            "page": result.get("page_printed") or result.get("page_pdf"), "quote": result.get("quote"),
        } for row in rows for result in row["results"]]
        answers.append({"kind": "results", "count": len(measured), "values": measured[:limit]})
        caveats.append("Chaque résultat vaut pour son propre jeu de données et sa propre "
                       "métrique: ces lignes ne se comparent pas entre elles.")

    if query["asks_for_limitations"]:
        slugs = {row["slug"] for row in rows} if filtered else None
        items = []
        for slug, record in store.load_records(gold_dir):
            if slugs is not None and slug not in slugs:
                continue
            for limitation in record.get("limitations", []):
                if query["themes"] and limitation.get("theme") not in query["themes"]:
                    continue
                items.append({
                    "slug": slug, "title": record["paper"]["title"],
                    "theme": limitation.get("theme"), "quote": limitation.get("quote"),
                    "page": limitation.get("page_printed") or limitation.get("page_pdf"),
                })
        answers.append({"kind": "limitations", "count": len(items), "values": items[:limit]})
        caveats.append("Seules les limites que les auteurs énoncent eux-mêmes sont "
                       "enregistrées: ni promesse de travaux futurs, ni mesure de performance.")

    if not answers:
        answers.append({
            "kind": "experiments", "count": len(rows),
            "values": [{"slug": row["slug"], "title": row["title"], "experiment": row["id"],
                        "task": row["task"], "family": row["family"], "method": row["method"],
                        "datasets": row["datasets"], "variable": row["variable"],
                        "reported": [f for f in FIELD_WORDS if row["training"].get(f, {}).get("value") is not None]}
                       for row in rows[:limit]],
        })

    return {
        "question": question,
        "understood": understood,
        "understood_nothing": False,
        "experiments_matched": len(rows),
        "papers_matched": len({row["slug"] for row in rows}),
        "answers": answers,
        "caveats": caveats,
    }


def main(argv: list[str]) -> int:
    if not argv:
        print('usage: python -m ocean_research_hub.corpus_v2.ask "votre question"')
        return 2
    result = answer(" ".join(argv))
    print(f"compris: {result['understood']}")
    print(f"{result['experiments_matched']} expériences, {result['papers_matched']} papiers")
    for block in result["answers"]:
        if block["kind"] == "training":
            print(f"\n{block['field']}: {block['reported']}/{block['of']} expériences le rapportent")
            for value in block["values"][:6]:
                print(f"  {value['value']} — {value['slug']} p.{value['page']}")
        else:
            print(f"\n{block['kind']}: {block.get('count', len(block['values']))}")
            for value in block["values"][:6]:
                label = value.get("quote") or value.get("title")
                print(f"  {value['slug']}: {str(label)[:90]}")
    for caveat in result["caveats"]:
        print(f"\n! {caveat}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
