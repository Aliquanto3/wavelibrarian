"""Aide commune de fenêtre, neutre (sans dépendance de couche) : raccourcir un texte."""

from typing import Any


def couper(texte: str, tokenizer: Any, limite: int) -> str:
    """Raccourcit `texte` (par pas de 20 %) jusqu'à tenir dans `limite` tokens."""
    coupe = texte
    while coupe and tokenizer.count(coupe) > limite:
        coupe = coupe[: int(len(coupe) * 0.8)]
    return coupe
