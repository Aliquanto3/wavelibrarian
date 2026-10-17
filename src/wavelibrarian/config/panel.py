"""Formation du Panel de Juges et choix du Juge closed-book (AD-14, FR-37)."""

import json
from collections.abc import Collection, Sequence
from pathlib import Path

from wavelibrarian.config.catalog import ModelCatalog
from wavelibrarian.core.errors import ConfigError

PANEL_MIN = 2  # moins de deux Juges admissibles : la Configuration est refusée


def excluded_judges(chemin: Path) -> frozenset[str]:
    """Juges exclus par un `calibration.json` (`{"judges": {<modèle>: {"excluded": bool}}}`)."""
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(
            "judges.excluded_from", f"calibration illisible : {chemin.as_posix()} ({exc})"
        ) from exc
    juges = donnees.get("judges") if isinstance(donnees, dict) else None
    if not isinstance(juges, dict):
        raise ConfigError(
            "judges.excluded_from", f"{chemin.as_posix()} : clé `judges` (dictionnaire) attendue"
        )
    return frozenset(
        str(modele)
        for modele, fiche in juges.items()  # pyright: ignore[reportUnknownVariableType]
        if isinstance(fiche, dict) and fiche.get("excluded") is True  # pyright: ignore[reportUnknownMemberType]
    )


def form_panel(
    pool: Sequence[str],
    panel_size: int,
    producers: Collection[str],
    catalog: ModelCatalog,
    excluded: Collection[str] = (),
) -> tuple[str, ...]:
    """Les `panel_size` premiers modèles du réservoir, dans l'ordre déclaré, d'une autre Famille.

    Écartés : les modèles de la Famille d'un `answer_producer` de la Configuration et les Juges
    exclus par la calibration. Moins de `PANEL_MIN` Juges restants : `ConfigError`.
    """
    familles = {catalog.get(m).family for m in producers}
    admissibles = [m for m in pool if m not in excluded and catalog.get(m).family not in familles]
    panel = tuple(admissibles[:panel_size])
    if len(panel) < PANEL_MIN:
        ecartes = [m for m in pool if m not in admissibles]
        raise ConfigError(
            "judges.pool",
            f"Panel de {len(panel)} Juge(s) (minimum {PANEL_MIN}) : réservoir "
            f"{', '.join(pool)}, panel_size {panel_size} ; écartés (Famille du Generator ou "
            f"exclus par la calibration) : {', '.join(ecartes) or 'aucun'}",
        )
    return panel


def closed_book_judge(tested_model: str, pool: Sequence[str], catalog: ModelCatalog) -> str:
    """Premier modèle du réservoir d'une autre Famille que `tested_model` (AD-14)."""
    famille = catalog.get(tested_model).family
    for modele in pool:
        if catalog.get(modele).family != famille:
            return modele
    raise ConfigError(
        "judges.pool",
        f"aucun Juge closed-book : tout le réservoir ({', '.join(pool)}) est de la Famille "
        f"« {famille} » du modèle testé {tested_model!r}",
    )
