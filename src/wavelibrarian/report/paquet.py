"""Paquet d'annotation : export d'une Exécution terminée, un fichier par annotateur (FR-38, §4.6).

Le paquet reprend le format de `contracts.md` §4.6 (`annotator`, `annotations` de `answer_id`,
`criterion`, `verdict`, `note`) et y ajoute des clés de contexte en lecture seule, que le chargeur
de la story 5.1 ignore, et qui ne figurent que sur la première ligne de chaque Réponse (story 9.4) :
`question`, `reference_answer`, `answer`, `cited_anchors` (identifiants d'Ancrage seulement),
`reference_passages` (texte des Ancrages de référence) et `context_passages` (Passages fournis au
Generator). C'est ce que reçoivent les Juges (`JudgeInput`), rien de plus. L'ancien format (ces clés
répétées sur chaque ligne) reste chargeable. `verdict` est vide (`""`) ; l'annotateur y met `yes`,
`no` ou `na`. Le tirage est stratifié par Configuration × Type de question (allocation
proportionnelle) et stable à graine égale (AD-20) : la graine de l'Expérience (ou celle donnée) est
dérivée par `sha16("annotation", graine)`. `exporter_depuis` tire une double annotation parmi les
lignes déjà annotées d'un paquet, stratifiées par Critère.
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
from wavelibrarian.scoring.calibration import lire_yaml
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
    "# chargement et ne figurent que sur la première ligne de chaque Réponse.\n"
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
    # Strate -> (retenues, disponibles) : « config × type » ou Critère (`--depuis`).
    repartition: dict[str, tuple[int, int]] = field(default_factory=dict)
    n_lignes: int = 0  # lignes (Réponse, Critère) par fichier d'annotateur


def graine_de_tirage(graine: int) -> int:
    """Graine du tirage dérivée de la graine de l'Expérience (AD-20)."""
    return int(sha16("annotation", str(graine)), 16)


def repartir(tailles: dict[str, int], nombre: int) -> dict[str, int]:
    """Allocation proportionnelle de `nombre` tirages entre strates de `tailles` données
    (plus grands restes), au moins un par strate non vide si `nombre` le permet, jamais plus que
    la taille d'une strate. Déterministe : égalités départagées par le nom de strate."""
    strates = sorted(k for k, t in tailles.items() if t > 0)
    total = sum(tailles[k] for k in strates)
    if nombre >= total:
        return {k: tailles[k] for k in strates}
    quota = {k: nombre * tailles[k] / total for k in strates}
    if nombre < len(strates):
        # Pas de place pour toutes les strates : les plus grands quotas d'abord.
        choisies = sorted(strates, key=lambda k: (-quota[k], k))[:nombre]
        return {k: (1 if k in choisies else 0) for k in strates}
    alloue = {k: min(tailles[k], max(1, math.floor(quota[k]))) for k in strates}
    while sum(alloue.values()) < nombre:
        k = min(
            (k for k in strates if alloue[k] < tailles[k]), key=lambda k: (alloue[k] - quota[k], k)
        )
        alloue[k] += 1
    while sum(alloue.values()) > nombre:
        k = max((k for k in strates if alloue[k] > 1), key=lambda k: (alloue[k] - quota[k], k))
        alloue[k] -= 1
    return alloue


def _tirer_par_strates(
    rng: random.Random, strates: dict[str, list[str]], nombre: int
) -> tuple[list[str], dict[str, tuple[int, int]]]:
    """Tire dans chaque strate (ordre des noms) ; rend les retenus et la répartition."""
    alloue = repartir({k: len(v) for k, v in strates.items()}, nombre)
    retenus: list[str] = []
    for k in sorted(alloue):
        retenus.extend(rng.sample(sorted(strates[k]), alloue[k]))
    return retenus, {k: (alloue[k], len(strates[k])) for k in sorted(alloue)}


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
    ok = [a for a in ex.reponses.values() if a.status == "ok" and a.question_id in ex.jeu]
    if not ok:
        raise ConfigError("run", "aucune Réponse `ok` à annoter")
    strates: dict[str, list[str]] = {}
    for a in ok:
        strates.setdefault(f"{a.config_id} × {ex.jeu[a.question_id].type}", []).append(a.answer_id)
    base = ex.experience.seed if graine is None else graine
    rng = random.Random(graine_de_tirage(base))
    retenues, repartition = _tirer_par_strates(rng, strates, nombre)
    rng.shuffle(retenues)  # l'ordre du tirage décide des doubles : pas de biais de strate
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
    n_lignes = 0
    for nom, ids in lignes.items():
        entrees: list[dict[str, Any]] = []
        for aid in sorted(ids):
            rep_ = ex.reponses[aid]
            question = ex.jeu[rep_.question_id]
            for n, critere in enumerate(criteres_juges(question)):
                entree: dict[str, Any] = {
                    "answer_id": aid,
                    "criterion": critere,
                    "verdict": "",
                    "note": "",
                }
                if n == 0:  # données propres à la Réponse : une seule fois
                    entree["question"] = question.text
                    entree["reference_answer"] = question.reference_answer
                    entree["answer"] = rep_.text
                    entree["cited_anchors"] = [c.anchor_id for c in rep_.citations]
                    entree["reference_passages"] = list(references[aid])
                    entree["context_passages"] = list(rep_.context_texts)
                entrees.append(entree)
        fichiers[nom] = _ecrire(vers, nom, entrees)
        n_lignes += len(entrees)
    alertes = resolveur.alertes() if resolveur is not None else []
    return Paquet(
        fichiers,
        len(retenues),
        n_doubles,
        len(ok),
        _autres(presents, fichiers),
        alertes,
        repartition,
        n_lignes,
    )


def _ecrire(vers: Path, nom: str, entrees: list[dict[str, Any]]) -> Path:
    chemin = vers / f"{nom}.yaml"
    corps = yaml.dump(
        {"annotator": nom, "annotations": entrees},
        Dumper=_Dumper,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    )
    chemin.write_text(ENTETE + corps, encoding="utf-8", newline="\n")
    return chemin


def _autres(presents: list[Path], fichiers: dict[str, Path]) -> list[Path]:
    ecrits = {p.name.casefold() for p in fichiers.values()}
    return [f for f in presents if f.name.casefold() not in ecrits]


DONNEES_DE_REPONSE = (
    "question",
    "reference_answer",
    "answer",
    "cited_anchors",
    "reference_passages",
    "context_passages",
)
ANNOTE = ("yes", "no", "na")


def exporter_depuis(
    source: Path,
    vers: Path,
    *,
    annotateurs: list[str],
    nombre: int = 30,
    graine: int | None = None,
    ecraser: bool = False,
) -> Paquet:
    """Double annotation : tire `nombre` lignes parmi les lignes déjà annotées (verdict `yes`,
    `no` ou `na`) du paquet `source`, stratifiées par Critère, et les écrit pour chaque
    annotateur, verdicts et notes vides. `answer_id` et Critères sont conservés ; les données
    de la Réponse passent sur la première ligne retenue de chaque Réponse. Graine par défaut : 0.
    `ConfigError` si la source est illisible ou sans ligne annotée, ou si un annotateur porte le
    nom de celui de la source."""
    if nombre < 1:
        raise ConfigError("nombre", "au moins une ligne à annoter")
    _valider_annotateurs(annotateurs)
    if not source.is_file():
        raise ConfigError("depuis", f"{source} : paquet introuvable (un fichier YAML est attendu)")
    doc = lire_yaml(source)
    lignes = doc.get("annotations") if isinstance(doc, dict) else None
    if not isinstance(lignes, list) or not all(isinstance(x, dict) for x in lignes):
        raise ConfigError("depuis", f"{source.name} : une liste d'annotations est attendue")
    origine = doc.get("annotator")
    if isinstance(origine, str) and origine.casefold() in {a.casefold() for a in annotateurs}:
        raise ConfigError(
            "annotateurs", f"{origine!r} a déjà annoté ce paquet : choisir un autre annotateur"
        )
    presents = _yaml_du_dossier(vers)
    if presents and not ecraser:
        noms = ", ".join(f.name for f in presents)
        raise ConfigError(
            "vers", f"{vers} contient déjà des annotations ({noms}) : --ecraser pour les remplacer"
        )
    donnees: dict[str, dict[str, Any]] = {}
    for ligne in lignes:  # les données de la Réponse viennent de n'importe laquelle de ses lignes
        d = donnees.setdefault(str(ligne.get("answer_id")), {})
        for cle in DONNEES_DE_REPONSE:
            if cle in ligne and cle not in d:
                d[cle] = ligne[cle]
    annotees = [i for i, x in enumerate(lignes) if x.get("verdict") in ANNOTE]
    if not annotees:
        raise ConfigError("depuis", f"{source.name} : aucune ligne annotée")
    strates: dict[str, list[str]] = {}
    for i in annotees:
        strates.setdefault(str(lignes[i].get("criterion")), []).append(str(i))
    rng = random.Random(graine_de_tirage(0 if graine is None else graine))
    choisies, repartition = _tirer_par_strates(rng, strates, nombre)
    entrees: list[dict[str, Any]] = []
    vues: set[str] = set()
    for i in sorted(int(c) for c in choisies):
        aid = str(lignes[i]["answer_id"])
        entree: dict[str, Any] = {
            "answer_id": aid,
            "criterion": lignes[i]["criterion"],
            "verdict": "",
            "note": "",
        }
        if aid not in vues:
            vues.add(aid)
            entree.update(donnees[aid])
        entrees.append(entree)
    vers.mkdir(parents=True, exist_ok=True)
    fichiers = {nom: _ecrire(vers, nom, entrees) for nom in annotateurs}
    return Paquet(
        fichiers,
        len(vues),
        len(vues),
        len(annotees),
        _autres(presents, fichiers),
        [],
        repartition,
        len(entrees),
    )
