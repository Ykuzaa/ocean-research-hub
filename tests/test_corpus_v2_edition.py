"""Chaque enregistrement dit quelle édition du papier a été lue, et le prouve.

Le gate vérifie que la citation existe sur la page citée. Ces tests vérifient l'autre
moitié: que l'étiquette déclarée découle de cette citation, et non d'une supposition.
"""

import json
import pathlib

import pytest

from ocean_research_hub.corpus_v2.edition import EDITIONS, classify, publication_markers

GOLD = sorted((pathlib.Path(__file__).resolve().parents[1] / "evaluation" / "gold_v2").glob("*.json"))


@pytest.mark.parametrize("record_path", GOLD, ids=lambda path: path.stem)
def test_every_record_declares_an_evidenced_edition(record_path: pathlib.Path) -> None:
    source = json.loads(record_path.read_text())["source"]

    assert source.get("edition") in EDITIONS, f"édition absente ou hors vocabulaire: {source.get('edition')!r}"
    evidence = source.get("edition_evidence")
    assert isinstance(evidence, dict), "l'édition doit porter sa preuve"
    assert evidence.get("quote"), "une édition sans citation est une affirmation"
    page = evidence.get("page_pdf")
    assert isinstance(page, int) and not isinstance(page, bool) and page >= 1, (
        f"la page de la preuve doit être un numéro de page réel, pas {page!r}"
    )
    assert page <= source["pdf_pages"], (
        f"la preuve cite la page {page} d'un fichier qui en a {source['pdf_pages']}"
    )
    assert "value" not in evidence, (
        "la preuve d'édition ne porte pas de valeur: sinon elle entre dans la file d'audit humain"
    )
    assert classify(evidence["quote"]) == source["edition"], (
        f"la citation ne porte pas l'édition déclarée {source['edition']}: {evidence['quote']!r}"
    )


# Le gate relit les PDF; ils ne sont pas versionnés, donc ce test ne tourne qu'en local.
PDFS = pathlib.Path(__file__).resolve().parents[1] / ".data" / "golden-pdfs"


@pytest.mark.skipif(not PDFS.is_dir(), reason=f"les PDF sources sont absents de {PDFS}")
@pytest.mark.parametrize("record_path", GOLD, ids=lambda path: path.stem)
def test_a_published_label_needs_more_than_a_doi(record_path: pathlib.Path) -> None:
    """Un DOI ne prouve pas qu'un fichier est l'article publié.

    Un manuscrit accepté et une épreuve d'éditeur impriment le DOI de l'article qu'ils
    vont devenir. L'étiquette la plus facile à poser est donc celle qui demande une
    seconde preuve: une marque que seul un article publié porte, sur la page citée.
    """
    import logging

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    from pypdf import PdfReader

    record = json.loads(record_path.read_text())
    source = record["source"]
    if source["edition"] != "VERSION_OF_RECORD":
        pytest.skip("seule la version publiée demande cette seconde preuve")

    page = PdfReader(source["file"]).pages[source["edition_evidence"]["page_pdf"] - 1]
    markers = publication_markers(page.extract_text() or "")
    assert markers, (
        "déclaré comme version publiée, mais la page citée ne porte aucune marque de "
        "publication (ligne de citation, dates éditoriales, copyright, numéro d'article)"
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


@pytest.mark.parametrize("record_path", GOLD, ids=lambda path: path.stem)
def test_the_claim_count_is_the_number_of_claims(record_path: pathlib.Path) -> None:
    """Le dénominateur affiché sous l'audit doit être celui de la file d'audit.

    La preuve d'édition est vérifiée par le gate mais n'est pas une information à
    trancher: la compter gonflerait le dénominateur et ferait paraître l'audit plus
    incomplet qu'il n'est.
    """
    from ocean_research_hub.corpus_v2 import store

    record = json.loads(record_path.read_text())
    summary = store.paper_summary(record_path.stem, record)
    assert summary["claim_count"] == len(list(store.claims(record_path.stem, record)))
