"""Export d'un front de Pareto en liste `configurations:` (story 4.13, FR-41, contracts.md §8).

Le front exporté est lu dans `report/pareto.csv`, donc identique à celui du Rapport. Le fichier
écrit contient la clé `configurations:` seule ; collée dans une Expérience (ou fusionnée avec ses
autres clés), la liste est acceptée par `config/load.py`. Les Configurations viennent de
`experiment.resolved.yaml` ; un Parser résolu par format (`markdown+pdf_text`) redevient `auto`.
"""

import csv
from pathlib import Path
from typing import Any

import yaml

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.report.fronts import FRONT_REFERENCE
from wavelibrarian.report.lecture import lire_resolue

_CHAMPS = {"id", "architecture", "parser", "reuse_index", "params"}


def noms_des_fronts(pareto: Path) -> list[str]:
    """Noms de front de `pareto.csv`, dans l'ordre du fichier, sans doublon."""
    with pareto.open(encoding="utf-8", newline="") as f:
        return list(dict.fromkeys(ligne["front"] for ligne in csv.DictReader(f)))


def configurations_du_front(pareto: Path, front: str) -> list[str]:
    """`config_id` du front, dans l'ordre du fichier (coût croissant). `ConfigError` si le front est
    inconnu (le message liste les fronts disponibles)."""
    with pareto.open(encoding="utf-8", newline="") as f:
        ids = [ligne["config_id"] for ligne in csv.DictReader(f) if ligne["front"] == front]
    if not ids:
        disponibles = ", ".join(noms_des_fronts(pareto)) or "aucun"
        raise ConfigError("exporter-front", f"front inconnu ou vide : {front!r} ({disponibles})")
    return ids


def exporter_front(run_dir: Path, front: str, vers: Path) -> list[str]:
    """Écrit `vers` (liste `configurations:`) pour `front` ; rend les `config_id` exportés.

    `front` : `qualite-cout` (alias du front de référence) ou tout nom de `pareto.csv`.
    `reuse_index` n'est gardé que si sa cible est elle-même exportée : sinon la liste serait
    refusée dans une nouvelle Expérience (la Configuration reconstruit alors son index)."""
    pareto = run_dir / "report" / "pareto.csv"
    if not pareto.is_file():
        raise ConfigError(str(pareto), "pareto.csv absent : générer le Rapport d'abord")
    ids = configurations_du_front(pareto, front or FRONT_REFERENCE)
    par_id = {c.id: c for c in lire_resolue(run_dir).configurations}
    exportees: list[dict[str, Any]] = []
    for i in ids:
        conf = par_id.get(i)
        if conf is None:
            raise ConfigError(i, "Configuration du front absente de l'Expérience résolue")
        donnees = conf.model_dump(mode="json", include=_CHAMPS)
        if donnees.get("reuse_index") not in ids:
            donnees.pop("reuse_index", None)
        if "+" in donnees["parser"]["name"]:
            # Parser résolu par format (`markdown+pdf_text`) : pas un nom de Parser.
            donnees["parser"]["name"] = "auto"
        exportees.append(donnees)
    texte = yaml.safe_dump(
        {"configurations": exportees}, allow_unicode=True, sort_keys=False, default_flow_style=False
    )
    entete = (
        f"# Front `{front}` de l'Exécution {run_dir.name} ({len(ids)} Configuration(s) non "
        "dominée(s)).\n# À fusionner dans une Expérience : `configurations:` est acceptée par "
        "`config/load.py`.\n"
    )
    vers.parent.mkdir(parents=True, exist_ok=True)
    vers.write_text(entete + texte, encoding="utf-8", newline="\n")
    return ids
