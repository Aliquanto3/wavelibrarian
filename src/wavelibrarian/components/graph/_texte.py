"""Contrôle de fenêtre pour les appels de graphe (pas de troncature silencieuse)."""

import logging
from typing import Any

from wavelibrarian.core.errors import ConfigError

_log = logging.getLogger(__name__)

# Réserve pour le system et l'habillage du message.
MARGE = 128


def couper(texte: str, tokenizer: Any, limite: int) -> str:
    """Raccourcit `texte` (par pas de 20 %) jusqu'à tenir dans `limite` tokens."""
    coupe = texte
    while coupe and tokenizer.count(coupe) > limite:
        coupe = coupe[: int(len(coupe) * 0.8)]
    return coupe


def borner(ctx: Any, model_id: str, system: str, texte: str, max_tokens: int, nom: str) -> str:
    """`texte` tronqué avec avertissement s'il ne tient pas dans la fenêtre du modèle ;
    `ConfigError` si même le system et la sortie réservée n'y tiennent pas."""
    fenetre = ctx.catalog.get(model_id).context_window
    if fenetre is None:
        return texte
    tokenizer = ctx.tokenizer_for(model_id)
    libre = fenetre - int(tokenizer.count(system)) - max_tokens - MARGE
    if libre <= 0:
        raise ConfigError(
            "graph",
            f"`{nom}` : le system et la sortie réservée ne laissent aucune place dans la "
            f"fenêtre de {fenetre} tokens de `{model_id}`",
        )
    if tokenizer.count(texte) <= libre:
        return texte
    coupe = couper(texte, tokenizer, libre)
    _log.warning("%s : texte tronqué avant l'appel (fenêtre de %d tokens)", nom, fenetre)
    return coupe
