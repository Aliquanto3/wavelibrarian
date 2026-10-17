"""Tests de la forme des Réponses de référence (story 3.1)."""

import pytest

from wavelibrarian.scoring.answer import is_short_form


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
