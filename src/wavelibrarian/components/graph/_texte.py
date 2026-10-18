"""Contrôle de fenêtre pour les appels de graphe (pas de troncature silencieuse)."""

import json
import logging
from typing import Any

from pydantic import BaseModel

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.fenetre import couper

_log = logging.getLogger(__name__)

# Réserve pour le system et l'habillage du message.
MARGE = 128
# Majorant des tokens fixes qu'un provider `schema_in_prompt` ajoute au prompt en plus du schéma
# (`schema_prompt_overhead` d'Anthropic) ; les providers ne sont pas visibles des Composants.
SURCOUT_SCHEMA = 400

__all__ = ["MARGE", "SURCOUT_SCHEMA", "borner", "couper", "reserve_schema"]


def reserve_schema(ctx: Any, model_id: str, schema: type[BaseModel]) -> int:
    """Tokens à réserver pour un appel structuré : le schéma JSON et son habillage."""
    texte = json.dumps(schema.model_json_schema(), ensure_ascii=False, sort_keys=True)
    return int(ctx.tokenizer_for(model_id).count(texte)) + SURCOUT_SCHEMA


def borner(
    ctx: Any,
    model_id: str,
    system: str,
    texte: str,
    max_tokens: int,
    nom: str,
    reserve: int = 0,
) -> str:
    """`texte` tronqué avec avertissement s'il ne tient pas dans la fenêtre du modèle ;
    `ConfigError` si même le system, la `reserve` (schéma) et la sortie n'y tiennent pas."""
    fenetre = ctx.catalog.get(model_id).context_window
    if fenetre is None:
        return texte
    tokenizer = ctx.tokenizer_for(model_id)
    libre = fenetre - int(tokenizer.count(system)) - max_tokens - reserve - MARGE
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
