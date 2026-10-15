"""Asking the corpus a question (issue #24).

The answer is built from stored claims, so these tests check the two things that could
make it dishonest: answering a question it did not understand, and answering a question
the corpus cannot answer at all.
"""

from __future__ import annotations

import pathlib

from ocean_research_hub.corpus_v2 import ask

GOLD = pathlib.Path("evaluation/gold_v2")


def test_it_understands_an_objective_and_a_setting() -> None:
    parsed = ask.parse("quel taux d'apprentissage pour la bathymétrie ?", GOLD)
    assert parsed["fields"] == ["learning_rate"]
    assert parsed["tasks"] == ["BATHYMETRY_ESTIMATION"]


def test_it_understands_a_data_source_under_any_of_its_names() -> None:
    assert ask.parse("qui utilise ERA5 ?", GOLD)["dataset_groups"] == ["ERA5"]
    assert "Sentinel-2" in ask.parse("papiers avec Sentinel-2", GOLD)["dataset_groups"]


def test_a_question_it_cannot_parse_gets_no_answer() -> None:
    """Returning the whole corpus would look like an answer to a question nobody read."""
    result = ask.answer("bonjour", GOLD)
    assert result["understood_nothing"] is True
    assert result["answers"] == []
    assert result["experiments_matched"] == 0
    assert "Aucun terme" in result["caveats"][0]


def test_a_ranking_question_is_answered_with_why_it_cannot_be_ranked() -> None:
    result = ask.answer("quelle architecture est la meilleure pour la prévision ?", GOLD)
    assert any("aucun classement" in caveat for caveat in result["caveats"])
    assert all(block["kind"] != "ranking" for block in result["answers"])


def test_a_setting_answer_states_how_many_experiments_omit_it() -> None:
    result = ask.answer("quel taux d'apprentissage pour la bathymétrie ?", GOLD)
    block = next(b for b in result["answers"] if b["kind"] == "training")
    assert block["field"] == "learning_rate"
    assert 0 < block["reported"] < block["of"]
    assert block["reported"] == len([v for v in block["values"] if v["value"] is not None])
    assert any("ne rapportent pas ce réglage" in caveat for caveat in result["caveats"])


def test_every_value_returned_carries_its_source() -> None:
    result = ask.answer("quelle fonction de coût pour la reconstruction ?", GOLD)
    block = next(b for b in result["answers"] if b["kind"] == "training")
    for value in block["values"]:
        assert value["page"], value
        assert value["quote"] or value["note"], value  # unquotable values keep their reason


def test_limitations_can_be_asked_by_theme() -> None:
    result = ask.answer("quelles limites de généralisation ?", GOLD)
    block = next(b for b in result["answers"] if b["kind"] == "limitations")
    assert block["count"] > 5
    assert {item["theme"] for item in block["values"]} == {"GENERALIZATION"}
    assert all(item["quote"] for item in block["values"])


def test_results_are_returned_with_the_warning_that_they_do_not_compare() -> None:
    result = ask.answer("quels résultats RMSE en bathymétrie ?", GOLD)
    block = next(b for b in result["answers"] if b["kind"] == "results")
    assert block["count"] > 0
    assert any("ne se comparent pas" in caveat for caveat in result["caveats"])


def test_one_word_naming_both_a_family_and_a_method_widens_rather_than_narrows() -> None:
    """'U-Net' is a family and, in one paper, a method name: the answer must not collapse."""
    narrow = ask.answer("combien d'époques pour un U-Net ?", GOLD)
    assert narrow["experiments_matched"] > 1
