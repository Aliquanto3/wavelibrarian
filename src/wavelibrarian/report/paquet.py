"""Paquet d'annotation : export d'une Exécution terminée, un fichier par annotateur (FR-38, §4.6).

Le paquet reprend le format de `contracts.md` §4.6 (`annotator`, `annotations` de `answer_id`,
`criterion`, `verdict`, `note`) et y ajoute des clés de contexte en lecture seule, que le chargeur
de la story 5.1 ignore : `question`, `reference_answer`, `answer` et `cited_anchors` sur chaque
ligne ; sur la première ligne de chaque Réponse, `reference_passages` (texte des Ancrages de
référence) et `context_passages` (Passages fournis au Generator). C'est ce que reçoivent les Juges
(`JudgeInput`), rien de plus. `verdict` est vide (`""`) ; l'annotateur y met `yes` ou `no`. Le
tirage est stable à graine égale (AD-20) : la graine de l'Expérience (ou celle donnée) est dérivée
par `sha16("annotation", graine)`.
"""

import math
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.core.ids import sha16
from wavelibrarian.core.types import Answer, Question
from wavelibrarian.report.ancrages import ResolveurCorpus, resolveur_de
from wavelibrarian.report.lecture import charger
from wavelibrarian.scoring.panel import criteres_juges

TERMINEES = ("completed", "completed_with_errors")
NOM_ANNOTATEUR = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
# Noms de fichier réservés par Windows, quelle que soit la casse.
RESERVES = frozenset(
    {"con", "prn", "aux", "nul"} | {f"{p}{i}" for p in ("com", "lpt") for i in range(1, 10)}
)
ENTETE = (
    "# Paquet d'annotation (contracts.md §4.6) : remplacer chaque verdict '' par yes, no ou\n"
    "# na (sans objet : le Critère ne s'applique pas, p. ex. fidélité d'une Réponse vide).\n"
    "# Les clés question, reference_answer, answer, cited_anchors, reference_passages et\n"
    "# context_passages aident à annoter (ce que reçoivent les Juges) ; elles sont ignorées au\n"
    "# chargement. Les Passages ne figurent que sur la première ligne de chaque Réponse.\n"
)


class _Dumper(yaml.SafeDumper):
    """Textes sur plusieurs lignes (Passages) en bloc littéral `|`, lisibles à l'annotation."""


def _texte(dumper: yaml.SafeDumper, valeur: str) -> yaml.ScalarNode:
    style = "|" if "\n" in valeur else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", valeur, style=style)


_Dumper.add_representer(str, _texte)

TextesReference = Callable[[Answer, Question], list[str]]


@dataclass(frozen=True)
class Paquet:
    fichiers: dict[str, Path]  # annotateur -> fichier écrit
    n_reponses: int  # Réponses retenues
    n_doubles: int  # dont annotées par tous les annotateurs
    n_eligibles: int  # Réponses `ok` dont on a tiré
    autres: list[Path] = field(default_factory=list)  # YAML laissés dans le dossier (écrasement)
    alertes: list[str] = field(default_factory=list)  # Corpus relu : Ancrages non résolus, etc.


def graine_de_tirage(graine: int) -> int:
    """Graine du tirage dérivée de la graine de l'Expérience (AD-20)."""
    return int(sha16("annotation", str(graine)), 16)


def _valider_annotateurs(annotateurs: list[str]) -> None:
    if not annotateurs:
        raise ConfigError("annotateurs", "au moins un annotateur")
    for nom in annotateurs:
        if not NOM_ANNOTATEUR.fullmatch(nom):
            raise ConfigError("annotateurs", f"nom d'annotateur invalide : {nom!r}")
        if nom.casefold() in RESERVES:
            raise ConfigError("annotateurs", f"nom réservé par Windows : {nom!r}")
    # Même fichier sur un système insensible à la casse (NTFS) : `Anael` et `anael` sont doublons.
    if len({n.casefold() for n in annotateurs}) != len(annotateurs):
        raise ConfigError("annotateurs", "annotateurs en doublon (casse ignorée)")


def _yaml_du_dossier(vers: Path) -> list[Path]:
    if not vers.is_dir():
        return []
    return sorted(f for f in vers.iterdir() if f.is_file() and f.suffix in (".yaml", ".yml"))


def exporter_paquet(
    run_dir: Path,
    vers: Path,
    *,
    annotateurs: list[str],
    nombre: int = 30,
    graine: int | None = None,
    part_double: float = 0.2,
    ecraser: bool = False,
    textes_reference: TextesReference | None = None,
    wl_home: Path | None = None,
) -> Paquet:
    """Écrit `vers/<annotateur>.yaml` pour chaque annotateur. `ConfigError` si un réglage est
    invalide, si l'Exécution n'est pas terminée ou n'a aucune Réponse `ok`, ou si `vers` contient
    déjà un YAML (verdicts saisis, chargés aussi par `wl calibrer`) et que `ecraser` est faux.

    `textes_reference` : texte des Ancrages de référence d'une Réponse (injecté par les tests) ;
    sinon, avec `wl_home`, le Corpus est relu comme pour le Rapport (empreinte du manifeste
    comparée) ; sans l'un ni l'autre, `reference_passages` reste vide."""
    if nombre < 1:
        raise ConfigError("nombre", "au moins une Réponse à annoter")
    if not 0.0 <= part_double <= 1.0:
        raise ConfigError("part_double", f"{part_double} hors de [0, 1]")
    _valider_annotateurs(annotateurs)
    presents = _yaml_du_dossier(vers)
    if presents and not ecraser:
        noms = ", ".join(f.name for f in presents)
        raise ConfigError(
            "vers", f"{vers} contient déjà des annotations ({noms}) : --ecraser pour les remplacer"
        )
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
    resolveur: ResolveurCorpus | None = None
    texte_de: TextesReference | None = textes_reference
    if texte_de is None and wl_home is not None:
        inputs = ex.manifeste.get("inputs")
        resolveur = r = resolveur_de(
            ex.experience, wl_home, inputs if isinstance(inputs, dict) else {}
        )
        texte_de = lambda a, q: r.textes(a.config_id, a.phase, q)  # noqa: E731

    references: dict[str, list[str]] = {}
    for aid in retenues:
        rep = ex.reponses[aid]
        q = ex.jeu[rep.question_id]
        references[aid] = texte_de(rep, q) if texte_de is not None else []
    vers.mkdir(parents=True, exist_ok=True)
    fichiers: dict[str, Path] = {}
    for nom, ids in lignes.items():
        entrees: list[dict[str, Any]] = []
        for aid in sorted(ids):
            rep = ex.reponses[aid]
            question = ex.jeu[rep.question_id]
            for n, critere in enumerate(criteres_juges(question)):
                entree: dict[str, Any] = {
                    "answer_id": aid,
                    "criterion": critere,
                    "verdict": "",
                    "note": "",
                    "question": question.text,
                    "reference_answer": question.reference_answer,
                    "answer": rep.text,
                    "cited_anchors": [c.anchor_id for c in rep.citations],
                }
                if n == 0:
                    entree["reference_passages"] = list(references[aid])
                    entree["context_passages"] = list(rep.context_texts)
                entrees.append(entree)
        chemin = vers / f"{nom}.yaml"
        corps = yaml.dump(
            {"annotator": nom, "annotations": entrees},
            Dumper=_Dumper,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )
        chemin.write_text(ENTETE + corps, encoding="utf-8", newline="\n")
        fichiers[nom] = chemin
    ecrits = {p.name.casefold() for p in fichiers.values()}
    autres = [f for f in presents if f.name.casefold() not in ecrits]
    alertes = resolveur.alertes() if resolveur is not None else []
    return Paquet(fichiers, len(retenues), n_doubles, len(eligibles), autres, alertes)
