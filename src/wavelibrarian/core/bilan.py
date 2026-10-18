"""Causes d'une Exécution `completed_with_errors` (contracts.md §5, arbitrage P9, story 8.3).

Le runner les calcule et les écrit dans `manifest.json` (`causes`) ; la CLI et le Rapport les
décrivent avec `decrire_cause`. Le module vit dans `core` parce que `runner` et `report` sont
deux couches indépendantes (AD-1).
"""

from collections.abc import Iterable, Mapping
from typing import Any, Literal

Cause = Literal["no_ok_answer", "error_rate", "unjudged"]


def causes_execution(
    reponses: Mapping[str, Mapping[str, int]],
    non_jugees: Mapping[str, int],
    max_error_rate: float,
    configurations: Iterable[str],
) -> list[dict[str, Any]]:
    """Causes par Configuration, dans l'ordre de l'Expérience : `{config_id, cause, count}`.

    - `no_ok_answer` : aucune Réponse `ok` et au moins une en `error` (`count` : Réponses en
      `error`) ; une Configuration seulement `inapplicable` n'est pas en erreur.
    - `error_rate` : `error / (ok + error)` strictement au-dessus de `max_error_rate`
      (`count` : Réponses en `error`) ; les `inapplicable` n'entrent pas dans le taux.
    - `unjudged` : Critères jugés restés sans verdict de panel (`count` : Critères).
    """
    causes: list[dict[str, Any]] = []
    for config_id in configurations:
        compte = reponses.get(config_id, {})
        ok, erreurs = compte.get("ok", 0), compte.get("error", 0)
        if ok == 0 and erreurs > 0:
            causes.append({"config_id": config_id, "cause": "no_ok_answer", "count": erreurs})
        if erreurs and erreurs / (ok + erreurs) > max_error_rate:
            causes.append({"config_id": config_id, "cause": "error_rate", "count": erreurs})
        if n := non_jugees.get(config_id, 0):
            causes.append({"config_id": config_id, "cause": "unjudged", "count": n})
    return causes


def decrire_cause(cause: Mapping[str, Any], max_error_rate: float | None = None) -> str:
    """Une cause en français, pour le résumé de `wl run` et le bandeau du Rapport."""
    config_id, quoi, n = cause.get("config_id"), cause.get("cause"), cause.get("count", 0)
    if quoi == "no_ok_answer":
        texte = f"aucune Réponse `ok` ({n} en `error`)"
    elif quoi == "error_rate":
        seuil = "" if max_error_rate is None else f" ({max_error_rate * 100:g} %)"
        texte = f"{n} Réponse(s) en `error`, taux au-dessus de `max_error_rate`{seuil}"
    elif quoi == "unjudged":
        texte = f"{n} Critère(s) sans verdict de panel"
    else:
        texte = f"cause `{quoi}` ({n})"
    return f"`{config_id}` : {texte}"
