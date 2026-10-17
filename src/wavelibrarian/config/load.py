"""Chargement strict d'une Expérience (FR-9, AD-20)."""

from pathlib import Path

from wavelibrarian import registry
from wavelibrarian.config.defaults import charger_yaml
from wavelibrarian.config.experiment import Experiment
from wavelibrarian.config.resolve import verifier_configuration
from wavelibrarian.config.schemas import valider
from wavelibrarian.core.errors import ConfigError


def load_experiment(chemin: Path) -> Experiment:
    """Charge `chemin` par `yaml.safe_load` ; toute clé inconnue ou mal typée lève `ConfigError`.

    Les `params` de chaque Configuration sont validés contre le `Params` enregistré de son
    Architecture et de ses Composants. Le chemin de l'erreur est en notation pointée
    (`configurations[1].params.kk`).
    """
    donnees = charger_yaml(chemin)
    if not isinstance(donnees, dict):
        raise ConfigError(str(chemin), "une Expérience doit être un dictionnaire YAML")
    experience = valider(Experiment, donnees, str(chemin))
    vus: set[str] = set()
    for i, conf in enumerate(experience.configurations):
        if conf.id in vus:
            raise ConfigError(f"configurations[{i}].id", f"identifiant en double : {conf.id!r}")
        vus.add(conf.id)
    registry.discover()
    for i, conf in enumerate(experience.configurations):
        verifier_configuration(conf, f"configurations[{i}]")
    return experience
