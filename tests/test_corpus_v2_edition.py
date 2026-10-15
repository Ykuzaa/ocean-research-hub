"""Chaque enregistrement dit quelle édition du papier a été lue, et le prouve.

Le gate vérifie que la citation existe sur la page citée. Ces tests vérifient l'autre
moitié: que l'étiquette déclarée découle de cette citation, et non d'une supposition.
"""

import json
import pathlib

import pytest

from ocean_research_hub.corpus_v2.edition import EDITIONS, classify

GOLD = sorted((pathlib.Path(__file__).resolve().parents[1] / "evaluation" / "gold_v2").glob("*.json"))


@pytest.mark.parametrize("record_path", GOLD, ids=lambda path: path.stem)
def test_every_record_declares_an_evidenced_edition(record_path: pathlib.Path) -> None:
    source = json.loads(record_path.read_text())["source"]

    assert source.get("edition") in EDITIONS, f"édition absente ou hors vocabulaire: {source.get('edition')!r}"
    evidence = source.get("edition_evidence")
    assert isinstance(evidence, dict), "l'édition doit porter sa preuve"
    assert evidence.get("quote"), "une édition sans citation est une affirmation"
    assert evidence.get("page_pdf"), "la citation doit dire sur quelle page elle se trouve"
    assert "value" not in evidence, (
        "la preuve d'édition ne porte pas de valeur: sinon elle entre dans la file d'audit humain"
    )
    assert classify(evidence["quote"]) == source["edition"], (
        f"la citation ne porte pas l'édition déclarée {source['edition']}: {evidence['quote']!r}"
    )


def test_an_arxiv_stamp_wins_over_a_published_doi_on_the_same_line() -> None:
    # Un fichier arXiv reste un fichier arXiv, même quand la page affiche le DOI publié.
    assert classify("arXiv:2505.08900v6 [physics.ao-ph] https://doi.org/10.1029/2025GL117046") == "PREPRINT"


def test_a_quote_that_proves_nothing_is_refused() -> None:
    assert classify("We train a neural network on reanalysis data.") is None


def test_an_early_access_page_is_not_the_version_of_record() -> None:
    quote = "content may change prior to final publication. Citation information: DOI 10.1109/JSTARS.2022.3140281"
    assert classify(quote) == "ACCEPTED_MANUSCRIPT"


def test_the_edition_evidence_is_not_a_claim_to_audit() -> None:
    from ocean_research_hub.corpus_v2 import store

    paths = {claim["path"] for claim in store.all_claims()}
    assert not any(path.startswith("source.edition") for path in paths)
