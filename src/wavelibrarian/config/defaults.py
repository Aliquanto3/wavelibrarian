"""Chargement des réglages livrés : profils d'exécution et paramètres de coût (§4.2 bis, §4.3)."""

import os
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from wavelibrarian.config.schemas import CostSettings, ProfileSettings, valider
from wavelibrarian.core.errors import ConfigError

PROFILS = ("cpu", "gpu", "test")


def defaults_dir() -> Path:
    """Dossier `defaults/` livré dans le paquet."""
    return Path(str(files("wavelibrarian") / "defaults"))


def charger_yaml(chemin: Path) -> Any:
    """`yaml.safe_load` d'un fichier ; erreur de lecture ou de syntaxe = `ConfigError`."""
    try:
        return yaml.safe_load(chemin.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(str(chemin), f"fichier illisible ou YAML invalide : {exc}") from exc


def load_profile(name: str) -> ProfileSettings:
    """Charge un profil livré (`cpu`, `gpu` ou `test`)."""
    if name not in PROFILS:
        raise ConfigError("profile", f"profil inconnu : {name!r} (profils : {', '.join(PROFILS)})")
    chemin = defaults_dir() / "profiles" / f"{name}.yaml"
    return valider(ProfileSettings, charger_yaml(chemin), str(chemin))


def fusionner(base: dict[str, Any], surcharge: dict[str, Any]) -> dict[str, Any]:
    """Fusion clé par clé, récursive ; la surcharge l'emporte."""
    res = dict(base)
    for cle, val in surcharge.items():
        if isinstance(val, dict) and isinstance(res.get(cle), dict):
            res[cle] = fusionner(res[cle], val)
        else:
            res[cle] = val
    return res


def _lire_surcharge(chemin: Path) -> dict[str, Any]:
    data = charger_yaml(chemin)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(str(chemin), "un fichier de coûts doit être un dictionnaire")
    return data


def load_costs(wl_home: Path | None = None, experiment_costs: Path | None = None) -> CostSettings:
    """Résout les `CostSettings` : défauts, puis `<WL_HOME>/costs.yaml`, puis fichier d'Expérience.

    Les dates de chaque section sont conservées avec leurs valeurs.
    """
    base = defaults_dir() / "costs.yaml"
    donnees = _lire_surcharge(base)
    sources = [str(base)]
    if wl_home is None and os.environ.get("WL_HOME"):
        wl_home = Path(os.environ["WL_HOME"])
    if wl_home is not None and (wl_home / "costs.yaml").is_file():
        donnees = fusionner(donnees, _lire_surcharge(wl_home / "costs.yaml"))
        sources.append(str(wl_home / "costs.yaml"))
    if experiment_costs is not None:
        donnees = fusionner(donnees, _lire_surcharge(experiment_costs))
        sources.append(str(experiment_costs))
    return valider(CostSettings, donnees, " + ".join(sources))
