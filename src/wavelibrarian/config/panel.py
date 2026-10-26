"""Formation du Panel de Juges et choix du Juge closed-book (AD-14, FR-37)."""

import json
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictBool

from wavelibrarian.config.catalog import ModelCatalog
from wavelibrarian.config.schemas import valider
from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.types import JUDGED_CRITERIA

PANEL_MIN = 2  # moins de deux Juges admissibles : la Configuration est refusée


def excluded_judges(chemin: Path) -> frozenset[str]:
    """Juges exclus par un `calibration.json` (`{"judges": {<modèle>: {"excluded": bool}}}`)."""
    calibration = _charger_calibration(chemin)
    return frozenset(m for m, fiche in calibration.judges.items() if fiche.excluded)


def _charger_calibration(chemin: Path) -> "_Calibration":
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(
            "judges.excluded_from", f"calibration illisible : {chemin.as_posix()} ({exc})"
        ) from exc
    try:
        return valider(_Calibration, donnees)
    except ConfigError as exc:
        raise ConfigError(
            "judges.excluded_from", f"{chemin.as_posix()} : {exc.path} : {exc.message}"
        ) from exc


def verifier_juge_unique(juge: str, chemin: Path, kappa_threshold: float) -> None:
    """Admet `juge` comme Juge unique (FR-37 amendé) : il figure dans la calibration `chemin`,
    non exclu, avec un kappa au moins égal à `kappa_threshold` sur chaque Critère jugé. Un kappa
    absent ou `null` (Critère non calibré) compte comme sous le seuil. `ConfigError` sinon."""
    chem = "judges.excluded_from"
    fiche = _charger_calibration(chemin).judges.get(juge)
    if fiche is None:
        raise ConfigError(
            chem, f"Juge unique {juge!r} absent de la calibration {chemin.as_posix()}"
        )
    if fiche.excluded:
        raise ConfigError(
            chem, f"Juge unique {juge!r} exclu par la calibration {chemin.as_posix()}"
        )
    criteres = fiche.criteria if isinstance(fiche.criteria, dict) else {}
    for critere in JUDGED_CRITERIA:
        f = criteres.get(critere)
        kappa = f.get("kappa") if isinstance(f, dict) else None
        if not isinstance(kappa, int | float) or isinstance(kappa, bool) or kappa < kappa_threshold:
            lu = "absent (Critère non calibré)" if not isinstance(kappa, int | float) else kappa
            raise ConfigError(
                chem,
                f"Juge unique {juge!r} : kappa {lu} sur le Critère {critere!r}, sous le seuil "
                f"{kappa_threshold} ({chemin.as_posix()})",
            )


class _FicheJuge(BaseModel):
    """Fiche d'un Juge : `excluded` booléen strict ; kappas par Critère sous `criteria`."""

    model_config = ConfigDict(extra="allow", frozen=True)
    excluded: StrictBool
    criteria: Any = None


class _Calibration(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    judges: dict[str, _FicheJuge]


def form_panel(
    pool: Sequence[str],
    panel_size: int,
    producers: Collection[str],
    catalog: ModelCatalog,
    excluded: Collection[str] = (),
    calibration: Path | None = None,
    kappa_threshold: float = 0.6,
) -> tuple[str, ...]:
    """Les `panel_size` premiers modèles du réservoir, dans l'ordre déclaré, d'une autre Famille.

    Écartés : les modèles de la Famille d'un `answer_producer` de la Configuration et les Juges
    exclus par la calibration. Moins de `PANEL_MIN` Juges restants : `ConfigError`.

    `panel_size` 1 (Juge unique calibré) n'est admis qu'avec `calibration`
    (`judges.excluded_from`) : le premier modèle du réservoir d'une autre Famille doit y
    figurer, non exclu, avec un kappa au moins égal à `kappa_threshold` sur chaque Critère jugé
    (`verifier_juge_unique`).
    """
    familles = {catalog.get(m).family for m in producers}
    if panel_size == 1:
        return _juge_unique(pool, familles, calibration, kappa_threshold, catalog)
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


def _juge_unique(
    pool: Sequence[str],
    familles: Collection[str],
    calibration: Path | None,
    kappa_threshold: float,
    catalog: ModelCatalog,
) -> tuple[str, ...]:
    if calibration is None:
        raise ConfigError(
            "judges.panel_size",
            "panel_size 1 (Juge unique) exige `judges.excluded_from`, un fichier de calibration "
            "où le Juge figure avec un kappa suffisant sur chaque Critère",
        )
    candidats = [m for m in pool if catalog.get(m).family not in familles]
    if not candidats:
        raise ConfigError(
            "judges.pool",
            f"aucun Juge unique admissible : tout le réservoir ({', '.join(pool)}) est de la "
            f"Famille du Generator ({', '.join(sorted(familles))}) ; demander un Juge d'une "
            "autre Famille (AD-14)",
        )
    verifier_juge_unique(candidats[0], calibration, kappa_threshold)
    return (candidats[0],)


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
