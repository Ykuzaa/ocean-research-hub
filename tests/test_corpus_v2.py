"""Le corpus v2 ne contient que des enregistrements qui passent le gate déterministe."""

import json
import pathlib

import pytest

from ocean_research_hub.corpus_v2.gate import check, normalise, supports

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GOLD = sorted((REPO_ROOT / "evaluation" / "gold_v2").glob("*.json"))

# Le gate relit les PDF eux-mêmes. Ils ne sont pas versionnés (369 Mo, fichiers d'éditeurs),
# donc il ne tourne que là où ils sont: en local, et jamais en CI. Un test sauté se voit
# dans le rapport; le faire passer sans les PDF reviendrait à affirmer une vérification
# qui n'a pas eu lieu.
PDFS = REPO_ROOT / ".data" / "golden-pdfs"
needs_pdfs = pytest.mark.skipif(
    not PDFS.is_dir(),
    reason=f"les PDF sources sont absents de {PDFS}; le gate ne peut pas relocaliser les citations",
)


def test_gold_corpus_is_not_empty() -> None:
    assert GOLD, "aucun enregistrement dans evaluation/gold_v2"


@needs_pdfs
@pytest.mark.parametrize("record_path", GOLD, ids=lambda path: path.stem)
def test_every_quote_is_relocatable(record_path: pathlib.Path) -> None:
    record = json.loads(record_path.read_text())
    report = check(record, REPO_ROOT)

    assert report.checked > 0, "un enregistrement sans citation n'a pas sa place dans le corpus"
    assert not report.locate_failures, "\n".join(report.locate_failures)
    assert not report.support_warnings, "\n".join(report.support_warnings)


def test_hyphenation_across_a_line_break_still_matches() -> None:
    # Le texte PDF coupe les mots en fin de ligne; les deux formes doivent se comparer.
    assert normalise("regularization parame-\nter") == normalise("regularization parame- ter")


def test_support_reads_a_unicode_minus_exponent() -> None:
    # Les papiers impriment "5e−5" avec un moins Unicode.
    assert supports(5e-05, "and a learning rate 5e−5.")
    assert not supports(0.7514, "The best performance was recorded at epoch 37, where")


def test_support_accepts_a_normalised_wording_but_not_an_invention() -> None:
    assert supports("adam", "All numerical experiments used the Adam optimizer")
    assert not supports("AdamW with cosine schedule", "All numerical experiments used the Adam optimizer")
