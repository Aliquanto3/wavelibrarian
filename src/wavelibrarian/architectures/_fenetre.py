"""Contrôle de la fenêtre du modèle avant un appel, sans troncature silencieuse (leçon 7.1/7.2).

Partagé par les Architectures qui fournissent des sections ou des pages au Generator.
"""

import logging
from collections.abc import Sequence
from typing import Any

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import Passage, QuestionInput

_log = logging.getLogger(__name__)

# Réserve pour le system du générateur et l'habillage du message (« Contexte : », « Question : »).
MARGE_GENERATE = 256


def couper(texte: str, tokenizer: Any, limite: int) -> str:
    """Raccourcit `texte` (par pas de 20 %) jusqu'à tenir dans `limite` tokens."""
    coupe = texte
    while coupe and tokenizer.count(coupe) > limite:
        coupe = coupe[: int(len(coupe) * 0.8)]
    return coupe


def borner_passages(
    arch: Any, question: QuestionInput, lus: Sequence[Passage], nom: str
) -> list[Passage]:
    """Garde les Passages lus qui tiennent dans la fenêtre du générateur (avertissement).

    Écarte depuis le dernier ; un Passage seul trop long est tronqué ; une fenêtre sans place
    lève `ConfigError`. `arch` fournit `generator`, `context_builder`, `ctx` et `_fenetre`.
    """
    lus = list(lus)
    modele: str | None = getattr(arch.generator, "model_id", None)
    fenetre = arch._fenetre(modele) if modele else None
    if modele is None or fenetre is None or not lus:
        return lus
    tokenizer = arch.ctx.tokenizer_for(modele)
    fixe = (
        int(tokenizer.count(question.text))
        + sum(int(tokenizer.count(t.text)) for t in question.history)
        + int(getattr(arch.generator, "max_tokens", 0))
        + MARGE_GENERATE
    )
    if fixe >= fenetre:
        raise ConfigError(
            "generator",
            f"`{nom}` : la question et la sortie réservée ({fixe} tokens) ne laissent "
            f"aucune place dans la fenêtre de {fenetre} tokens de `{modele}`",
        )

    def taille(passages: list[Passage]) -> int:
        return int(tokenizer.count(arch.context_builder.build(passages).text)) + fixe

    gardes = list(lus)
    while len(gardes) > 1 and taille(gardes) > fenetre:
        gardes.pop()
    if len(gardes) < len(lus):
        _log.warning(
            "%s : %d section(s) lue(s) écartée(s), hors de la fenêtre de %d tokens",
            nom,
            len(lus) - len(gardes),
            fenetre,
        )
    if taille(gardes) > fenetre:  # un seul Passage, trop long : tronqué
        seul = gardes[0]
        habillage = taille([seul.model_copy(update={"text": ""})]) - fixe
        texte = couper(seul.text, tokenizer, fenetre - fixe - habillage)
        if not texte:
            raise ConfigError(
                "generator",
                f"`{nom}` : aucune section ne tient dans la fenêtre de {fenetre} tokens "
                f"de `{modele}`",
            )
        _log.warning("%s : section tronquée avant génération (fenêtre de %d tokens)", nom, fenetre)
        gardes = [seul.model_copy(update={"text": texte})]
    return gardes
