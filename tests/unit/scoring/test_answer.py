"""Tests de la forme des Réponses de référence (story 3.1)."""

import pytest

from wavelibrarian.scoring.answer import exact_match, is_short_form


@pytest.mark.parametrize(
    "texte",
    [
        "1412",
        "la guilde d'Orvane",
        "un deux trois quatre cinq",
        "1 234 567 890 123",
        "12,5 %",
        "1412-03-05",
        "05/03/1412",
        "3 kg",
    ],
)
def test_forme_courte(texte):
    assert is_short_form(texte)


@pytest.mark.parametrize(
    "texte",
    ["", "la guilde a été fondée en mille quatre cent douze", "environ 3 fois plus long que prévu"],
)
def test_forme_longue(texte):
    assert not is_short_form(texte)


# --- exact_match (story 3.4) -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reference", "reponse"),
    [
        ("1 412", "La guilde fut fondée en 1412."),
        ("1412", "Fondée en 1 412 ."),
        ("Élodie Varn", "elodie varn"),
        ("elodie varn", "C'est ÉLODIE VARN, sans doute."),
        ("3,5", "3.5"),
        ("3.50", "environ 3,5 mètres"),
        ("1 412", "en 1412"),
        ("05/03/1412", "le 5/3/1412"),
        ("-3", "il fait −3 °C"),
        ("1412000", "1.412.000 habitants"),
        ("1 412 000", "1,412,000"),
        ("1412,5", "1 412,5"),
        ("oeuvre", "Une Œuvre"),
        ("1412-1413", "de 1412 à 1413, soit 1412-1413"),
    ],
)
def test_exact_match_vrai(reference: str, reponse: str) -> None:
    assert exact_match(reference, reponse)


@pytest.mark.parametrize(
    ("reference", "reponse"),
    [
        ("1412", "1413"),
        ("1412", "14120 habitants"),
        ("1412", "en 141"),
        ("3,5", "35"),
        ("Élodie Varn", "Varn Élodie"),
        ("Varn", "Varnish"),
        ("", "quelque chose"),
        ("   ", ""),
        ("long mot de la référence", "mot"),
        ("-3", "3"),
        ("3", "-3"),
        ("1412", "code A1412"),
        ("1412", "1412-1413"),
        ("1412", "1412–1413"),
        ("5", "le 5e siècle"),
        ("1412000", "1.412"),
    ],
)
def test_exact_match_faux(reference: str, reponse: str) -> None:
    assert not exact_match(reference, reponse)


# --- Story 4.9, AC 2 : Critères automatiques ----------------------------------------------------


def test_citation_correctness() -> None:
    from wavelibrarian.scoring.answer import citation_correctness as cc

    ref, corpus = {"d#a"}, {"d#a", "d#b"}
    assert cc(["d#a"], ref, corpus, unanswerable=False)
    assert cc(["d#b", "d#a"], ref, corpus, unanswerable=False)
    assert not cc(["d#b"], ref, corpus, unanswerable=False)  # aucun Ancrage de référence
    assert not cc(["d#a", "x#hors"], ref, corpus, unanswerable=False)  # une hors du Corpus
    assert not cc([], ref, corpus, unanswerable=False)
    assert cc([], set(), corpus, unanswerable=True)
    assert not cc(["d#a"], set(), corpus, unanswerable=True)


def test_abstention_correctness() -> None:
    from wavelibrarian.scoring.answer import abstention_correctness as ac

    assert ac(True, unanswerable=True) and ac(False, unanswerable=False)
    assert not ac(False, unanswerable=True) and not ac(True, unanswerable=False)
