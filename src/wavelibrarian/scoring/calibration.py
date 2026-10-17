"""Annotations humaines : chargement et rapprochement des Réponses (FR-38, contrats §4.6)."""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from wavelibrarian.core.errors import ConfigError

CRITERES = ("correctness", "completeness", "faithfulness")
VERDICTS = {"yes": True, "no": False}

Cle = tuple[str, str, str]  # (annotateur, answer_id, criterion)


@dataclass(frozen=True)
class Annotations:
    """Verdicts booléens indexés par (annotateur, `answer_id`, `criterion`)."""

    verdicts: dict[Cle, bool]

    @property
    def annotateurs(self) -> list[str]:
        return sorted({k[0] for k in self.verdicts})


@dataclass(frozen=True)
class Rapprochement:
    annotations: Annotations
    ignorees: list[str]  # answer_id absents de l'Exécution, sans doublon, ordre d'apparition


def _lire_yaml(chemin: Path) -> Any:
    try:
        return yaml.safe_load(chemin.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(str(chemin), f"lecture impossible : {exc}") from exc


def charger_fichier(chemin: Path, deja: dict[Cle, bool] | None = None) -> dict[Cle, bool]:
    """Lit un fichier d'annotateur. Chemins d'erreur : `annotations[3].criterion`."""
    doc = _lire_yaml(chemin)
    if not isinstance(doc, dict):
        raise ConfigError("annotations", f"{chemin.name} : un mapping est attendu à la racine")
    annotateur = doc.get("annotator")
    if not isinstance(annotateur, str) or not annotateur.strip():
        raise ConfigError("annotator", f"{chemin.name} : annotateur manquant ou vide")
    liste = doc.get("annotations")
    if not isinstance(liste, list):
        raise ConfigError("annotations", f"{chemin.name} : une liste est attendue")
    out: dict[Cle, bool] = {} if deja is None else deja
    for i, ligne in enumerate(liste):
        base = f"annotations[{i}]"
        if not isinstance(ligne, dict):
            raise ConfigError(base, "un mapping est attendu")
        answer_id = ligne.get("answer_id")
        if not isinstance(answer_id, str) or not answer_id:
            raise ConfigError(f"{base}.answer_id", "identifiant de Réponse manquant")
        critere = ligne.get("criterion")
        if critere not in CRITERES:
            raise ConfigError(
                f"{base}.criterion", f"Critère inconnu {critere!r} ; permis : {', '.join(CRITERES)}"
            )
        verdict = ligne.get("verdict")
        # PyYAML (YAML 1.1) lit `yes` / `no` nus comme des booléens : acceptés.
        if isinstance(verdict, bool):
            valeur = verdict
        elif isinstance(verdict, str) and verdict in VERDICTS:
            valeur = VERDICTS[verdict]
        else:
            raise ConfigError(f"{base}.verdict", f"verdict inconnu {verdict!r} ; permis : yes, no")
        cle = (annotateur, answer_id, critere)
        if cle in out:
            raise ConfigError(
                base, f"doublon : {annotateur} a déjà annoté {answer_id} pour {critere}"
            )
        out[cle] = valeur
    return out


def charger_dossier(dossier: Path) -> Annotations:
    """Charge tous les `*.yaml` du dossier (un par annotateur), triés par nom."""
    fichiers = sorted(dossier.glob("*.yaml")) if dossier.is_dir() else []
    if not fichiers:
        raise ConfigError(str(dossier), "aucun fichier d'annotations (*.yaml)")
    verdicts: dict[Cle, bool] = {}
    for f in fichiers:
        charger_fichier(f, verdicts)
    return Annotations(verdicts)


def answer_ids_de_answers_jsonl(chemin: Path) -> set[str]:
    """Ensemble des `answer_id` d'un `answers.jsonl`."""
    ids: set[str] = set()
    try:
        lignes = chemin.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ConfigError(str(chemin), f"lecture impossible : {exc}") from exc
    for n, ligne in enumerate(lignes, 1):
        if not ligne.strip():
            continue
        try:
            ids.add(json.loads(ligne)["answer_id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ConfigError(f"{chemin.name}:{n}", "ligne illisible ou sans answer_id") from exc
    return ids


def rapprocher(annotations: Annotations, answer_ids: Iterable[str]) -> Rapprochement:
    """Garde les annotations dont l'`answer_id` complet est dans l'Exécution ; signale le reste."""
    connus = set(answer_ids)
    gardees: dict[Cle, bool] = {}
    ignorees: list[str] = []
    for cle, v in annotations.verdicts.items():
        if cle[1] in connus:
            gardees[cle] = v
        elif cle[1] not in ignorees:
            ignorees.append(cle[1])
    return Rapprochement(Annotations(gardees), ignorees)
