"""Paquet d'annotation : export d'une Exécution terminée, un fichier par annotateur (FR-38, §4.6).

Le paquet reprend le format de `contracts.md` §4.6 (`annotator`, `annotations` de `answer_id`,
`criterion`, `verdict`, `note`) et y ajoute, par ligne, `question`, `answer` et `cited_anchors` pour
annoter sans recopier : le chargeur de la story 5.1 ignore ces clés. `verdict` est vide (`""`) ;
l'annotateur y met `yes` ou `no`. Le tirage est stable à graine égale (AD-20) : la graine de
l'Expérience (ou celle donnée) est dérivée par `sha16("annotation", graine)`.
"""

import math
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import sha16
from wavelibrarian.report.lecture import charger
from wavelibrarian.scoring.panel import criteres_juges

TERMINEES = ("completed", "completed_with_errors")
NOM_ANNOTATEUR = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
ENTETE = (
    "# Paquet d'annotation (contracts.md §4.6) : remplacer chaque verdict '' par yes ou no.\n"
    "# Les clés question, answer et cited_anchors aident à annoter ; elles sont ignorées au "
    "chargement.\n"
)


@dataclass(frozen=True)
class Paquet:
    fichiers: dict[str, Path]  # annotateur -> fichier écrit
    n_reponses: int  # Réponses retenues
    n_doubles: int  # dont annotées par tous les annotateurs
    n_eligibles: int  # Réponses `ok` dont on a tiré


def graine_de_tirage(graine: int) -> int:
    """Graine du tirage dérivée de la graine de l'Expérience (AD-20)."""
    return int(sha16("annotation", str(graine)), 16)


def exporter_paquet(
    run_dir: Path,
    vers: Path,
    *,
    annotateurs: list[str],
    nombre: int = 30,
    graine: int | None = None,
    part_double: float = 0.2,
) -> Paquet:
    """Écrit `vers/<annotateur>.yaml` pour chaque annotateur. `ConfigError` si un réglage est
    invalide, si l'Exécution n'est pas terminée ou si elle n'a aucune Réponse `ok`."""
    if nombre < 1:
        raise ConfigError("nombre", "au moins une Réponse à annoter")
    if not 0.0 <= part_double <= 1.0:
        raise ConfigError("part_double", f"{part_double} hors de [0, 1]")
    if not annotateurs or len(set(annotateurs)) != len(annotateurs):
        raise ConfigError("annotateurs", "au moins un annotateur, sans doublon")
    for nom in annotateurs:
        if not NOM_ANNOTATEUR.fullmatch(nom):
            raise ConfigError("annotateurs", f"nom d'annotateur invalide : {nom!r}")
    ex = charger(run_dir)
    statut = ex.manifeste.get("status")
    if statut not in TERMINEES:
        raise ConfigError("run", f"Exécution non terminée (statut {statut!r})")
    eligibles = sorted(
        a.answer_id for a in ex.reponses.values() if a.status == "ok" and a.question_id in ex.jeu
    )
    if not eligibles:
        raise ConfigError("run", "aucune Réponse `ok` à annoter")
    base = ex.experience.seed if graine is None else graine
    rng = random.Random(graine_de_tirage(base))
    retenues = rng.sample(eligibles, min(nombre, len(eligibles)))
    n_doubles = math.floor(len(retenues) * part_double + 0.5) if len(annotateurs) > 1 else 0
    lignes: dict[str, list[str]] = {nom: [] for nom in annotateurs}
    for i, aid in enumerate(retenues):
        if i < n_doubles:
            destinataires = annotateurs
        else:
            destinataires = [annotateurs[(i - n_doubles) % len(annotateurs)]]
        for nom in destinataires:
            lignes[nom].append(aid)
    vers.mkdir(parents=True, exist_ok=True)
    fichiers: dict[str, Path] = {}
    for nom, ids in lignes.items():
        entrees: list[dict[str, Any]] = []
        for aid in sorted(ids):
            rep = ex.reponses[aid]
            question = ex.jeu[rep.question_id]
            for critere in criteres_juges(question):
                entrees.append(
                    {
                        "answer_id": aid,
                        "criterion": critere,
                        "verdict": "",
                        "note": "",
                        "question": question.text,
                        "answer": rep.text,
                        "cited_anchors": [c.anchor_id for c in rep.citations],
                    }
                )
        chemin = vers / f"{nom}.yaml"
        corps = yaml.safe_dump(
            {"annotator": nom, "annotations": entrees},
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )
        chemin.write_text(ENTETE + corps, encoding="utf-8", newline="\n")
        fichiers[nom] = chemin
    return Paquet(fichiers, len(retenues), n_doubles, len(eligibles))
