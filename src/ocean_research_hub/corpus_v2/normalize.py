"""Normalisation séparée de l'extraction.

L'extracteur lit ce que le papier dit ; la normalisation range ce qu'il a lu dans le
vocabulaire de l'application. Les deux étapes restent distinctes pour qu'une erreur de
rangement se corrige sans relire le PDF : la valeur telle qu'extraite est conservée
dans `*_raw`.

    uv run python -m ocean_research_hub.corpus_v2.normalize --check
    uv run python -m ocean_research_hub.corpus_v2.normalize --write
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

# Les 19 domaines de l'application, tels qu'ils existent déjà en base.
DOMAINS = {
    "forecasting", "data-assimilation", "subsurface", "sst", "ssh-altimetry", "currents",
    "eddies-fronts", "marine-heatwaves", "sea-ice", "waves", "biogeochemistry",
    "bathymetry", "parameterization", "neural-operators", "foundation-models",
    "llm-agents", "marine-ecology", "benchmarks", "reviews",
}

# Premier motif trouvé dans le libellé brut, dans cet ordre.
DOMAIN_RULES: tuple[tuple[str, str], ...] = (
    ("heatwave", "marine-heatwaves"),
    ("sea ice", "sea-ice"), ("sea-ice", "sea-ice"),
    ("bathymetr", "bathymetry"), ("seabed", "bathymetry"), ("seafloor", "bathymetry"),
    ("eddy", "eddies-fronts"), ("eddies", "eddies-fronts"), ("front", "eddies-fronts"),
    ("altimetr", "ssh-altimetry"), ("sea surface height", "ssh-altimetry"),
    ("ssh", "ssh-altimetry"), ("swot", "ssh-altimetry"),
    ("sea surface temperature", "sst"), ("sst", "sst"),
    ("chlorophyll", "biogeochemistry"), ("biogeochem", "biogeochemistry"),
    ("ocean colour", "biogeochemistry"), ("ocean color", "biogeochemistry"),
    ("algal", "biogeochemistry"), ("plankton", "biogeochemistry"),
    ("ecolog", "marine-ecology"), ("fisher", "marine-ecology"), ("species", "marine-ecology"),
    ("wave", "waves"), ("sea state", "waves"),
    ("parameteri", "parameterization"), ("mixing", "parameterization"),
    ("closure", "parameterization"), ("boundary layer", "parameterization"),
    ("mesoscale", "parameterization"), ("mixed layer", "parameterization"),
    ("marine geology", "bathymetry"),
    ("temperature and salinity", "subsurface"),
    ("neural operator", "neural-operators"), ("fourier neural", "neural-operators"),
    ("foundation model", "foundation-models"),
    ("llm", "llm-agents"), ("language model", "llm-agents"), ("agent", "llm-agents"),
    ("review", "reviews"), ("overview", "reviews"), ("survey", "reviews"),
    ("tutorial", "reviews"),
    ("assimilation", "data-assimilation"), ("interpolation", "data-assimilation"),
    ("reconstruct", "data-assimilation"), ("gap filling", "data-assimilation"),
    ("super-resolution", "data-assimilation"), ("super resolution", "data-assimilation"),
    ("downscal", "data-assimilation"),
    ("subsurface", "subsurface"), ("depth profile", "subsurface"), ("argo", "subsurface"),
    ("current", "currents"), ("circulation", "currents"), ("throughflow", "currents"),
    ("transport", "currents"), ("geostroph", "currents"),
    ("benchmark", "benchmarks"), ("dataset suite", "benchmarks"),
    ("forecast", "forecasting"), ("prediction", "forecasting"), ("digital twin", "forecasting"),
)


def normalise_domains(raw: list[str]) -> tuple[list[str], list[str]]:
    """Renvoie (domaines normalisés, libellés non rangés)."""
    kept: list[str] = []
    unmatched: list[str] = []
    for label in raw:
        token = str(label).strip()
        if token in DOMAINS:
            if token not in kept:
                kept.append(token)
            continue
        needle = token.lower().replace("_", " ")
        for pattern, domain in DOMAIN_RULES:
            if pattern in needle:
                if domain not in kept:
                    kept.append(domain)
                break
        else:
            unmatched.append(token)
    return kept, unmatched


def process(path: pathlib.Path, write: bool) -> dict:
    record = json.loads(path.read_text())
    raw = record["paper"].get("ocean_domains_raw") or record["paper"].get("ocean_domains") or []
    normalised, unmatched = normalise_domains(list(raw))

    changed = normalised != list(record["paper"].get("ocean_domains") or [])
    if write and changed:
        record["paper"]["ocean_domains_raw"] = list(raw)
        record["paper"]["ocean_domains"] = normalised
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False))

    return {"slug": path.stem, "raw": list(raw), "normalised": normalised,
            "unmatched": unmatched, "changed": changed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", default="evaluation/gold_v2")
    parser.add_argument("--write", action="store_true", help="écrit les fichiers")
    args = parser.parse_args()

    reports = [process(path, args.write) for path in sorted(pathlib.Path(args.gold).glob("*.json"))]
    changed = [r for r in reports if r["changed"]]
    unmatched = {label for r in reports for label in r["unmatched"]}

    for report in changed:
        print(f"{report['slug']}: {report['raw']} -> {report['normalised']}")
    print(f"\n{len(changed)}/{len(reports)} enregistrement(s) {'écrits' if args.write else 'à normaliser'}")
    if unmatched:
        print("libellés non rangés (à arbitrer ou à ajouter aux règles):")
        for label in sorted(unmatched):
            print(f"  {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
