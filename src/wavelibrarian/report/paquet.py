"""Paquet d'annotation : export d'une Exécution terminée, un fichier par annotateur (FR-38, §4.6).

Le paquet reprend le format de `contracts.md` §4.6 (`annotator`, `annotations` de `answer_id`,
`criterion`, `verdict`, `note`) et y ajoute des clés de contexte en lecture seule, que le chargeur
de la story 5.1 ignore, et qui ne figurent que sur la première ligne de chaque Réponse (story 9.4) :
`question`, `reference_answer`, `answer`, `cited_anchors` (identifiants d'Ancrage seulement),
`reference_passages` (Ancrages de référence) et `context_passages` (Passages fournis au Generator).
C'est ce que reçoivent les Juges (`JudgeInput`), rien de plus, et en entier. Les Passages sont
dédupliqués par contenu : la table `passages` en tête du fichier (clé : empreinte courte de
l'Ancrage et du texte ; valeur : `anchor`, `text`) porte chaque texte une fois, et les lignes s'y
réfèrent par clé (`S1 <clé>` pour un bloc de contexte `[S1] (ancrage) texte`, `<clé>` sinon) ;
`lire_paquet` rend les textes complets. L'ancien format (textes en clair, répétés) reste lisible.
`verdict` est vide (`""`) ; l'annotateur y met `yes`, `no` ou `na`. Le tirage est stratifié par
Configuration × Type de question (allocation proportionnelle) et stable à graine égale (AD-20) :
la graine de l'Expérience (ou celle donnée) est dérivée par `sha16("annotation", graine)`.
`exporter_depuis` tire une double annotation parmi les lignes déjà annotées d'un paquet,
stratifiées par Critère.
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
    "# chargement et ne figurent que sur la première ligne de chaque Réponse. Les Passages sont\n"
    "# dans la table `passages` en tête : `S1 <clé>` se lit `[S1] (anchor) text`.\n"
)
# Bloc de contexte du ContextBuilder `labeled` : `[S1] (ancrage, ancrage) texte`.
_BLOC = re.compile(r"\[(S\d+)\] \(([^()\n]*)\) (.*)", re.DOTALL)
_REF_BLOC = re.compile(r"(S\d+) (\S+)")
CLES_PASSAGES = ("context_passages", "reference_passages")


class TablePassages:
    """Table des Passages d'un fichier : chaque (Ancrage, texte) une seule fois, par clé courte
    (8 caractères de l'empreinte, 16 en cas de collision). Les références sont sans perte."""

    def __init__(self) -> None:
        self.entrees: dict[str, dict[str, str]] = {}

    def _cle(self, ancrage: str, texte: str) -> str:
        entree = {"anchor": ancrage, "text": texte} if ancrage else {"text": texte}
        empreinte = sha16("passage", ancrage, texte)
        for n in (8, 16):
            cle = empreinte[:n]
            if self.entrees.setdefault(cle, entree) == entree:
                return cle
        raise ConfigError("passages", f"collision d'empreintes sur {empreinte}")  # pragma: no cover

    def contexte(self, bloc: str) -> str:
        """`S1 <clé>` pour un bloc `[S1] (ancrage) texte`, `<clé>` du bloc entier sinon."""
        m = _BLOC.fullmatch(bloc)
        if m is None:
            return self._cle("", bloc)
        return f"{m[1]} {self._cle(m[2], m[3])}"

    def reference(self, texte: str, ancrage: str = "") -> str:
        return self._cle(ancrage, texte)


def _resoudre(table: dict[str, Any], ref: Any, ou: str) -> str:
    ref = str(ref)
    m = _REF_BLOC.fullmatch(ref)
    entree = table.get(m[2] if m else ref)
    if not isinstance(entree, dict) or not isinstance(entree.get("text"), str):
        raise ConfigError(ou, f"Passage {ref!r} absent de la table `passages`")
    if m is None:
        return entree["text"]
    return f"[{m[1]}] ({entree.get('anchor', '')}) {entree['text']}"


def resoudre_passages(doc: Any, nom: str = "paquet") -> Any:
    """Remplace, dans `doc` (paquet relu), les références de `context_passages` et
    `reference_passages` par les textes de la table `passages`, retirée ensuite. Sans table
    (ancien format), `doc` est rendu tel quel. `ConfigError` si une référence est inconnue."""
    if not isinstance(doc, dict) or "passages" not in doc:
        return doc
    brute = doc["passages"]
    if not isinstance(brute, dict):
        raise ConfigError("passages", f"{nom} : un mapping clé -> {{anchor, text}} est attendu")
    table = {str(k): v for k, v in brute.items()}
    out = {k: v for k, v in doc.items() if k != "passages"}
    lignes = doc.get("annotations")
    if isinstance(lignes, list):
        out["annotations"] = [_resoudre_ligne(table, x, i, nom) for i, x in enumerate(lignes)]
    return out


def _resoudre_ligne(table: dict[str, Any], ligne: Any, i: int, nom: str) -> Any:
    if not isinstance(ligne, dict):
        return ligne
    out = dict(ligne)
    for cle in CLES_PASSAGES:
        refs = ligne.get(cle)
        if isinstance(refs, list):
            out[cle] = [_resoudre(table, r, f"{nom} : annotations[{i}].{cle}") for r in refs]
    return out


def _ancrages_de_reference(doc: Any) -> dict[str, str]:
    """Texte -> Ancrage des entrées de la table `passages` (vide sans table) : `--depuis`
    garde l'Ancrage des Passages de référence."""
    table = doc.get("passages") if isinstance(doc, dict) else None
    lignes = doc.get("annotations") if isinstance(doc, dict) else None
    if not isinstance(table, dict) or not isinstance(lignes, list):
        return {}
    table = {str(k): v for k, v in table.items()}
    out: dict[str, str] = {}
    for ligne in lignes:
        refs = ligne.get("reference_passages") if isinstance(ligne, dict) else None
        for ref in refs if isinstance(refs, list) else ():
            entree = table.get(str(ref))
            if isinstance(entree, dict) and isinstance(entree.get("text"), str):
                out.setdefault(entree["text"], str(entree.get("anchor", "")))
    return out


def _meme_fichier(a: Path, b: Path) -> bool:
    try:
        return b.exists() and a.samefile(b)
    except OSError:
        return a.resolve() == b.resolve()


def lire_paquet(chemin: Path) -> Any:
    """Paquet relu (sans booléens implicites), Passages résolus en textes complets."""
    return resoudre_passages(lire_yaml(chemin), chemin.name)


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

    references: dict[str, list[tuple[str, str]]] = {}  # (texte, Ancrage)
    for aid in retenues:
        rep = ex.reponses[aid]
        q = ex.jeu[rep.question_id]
        textes = texte_de(rep, q) if texte_de is not None else []
        ids = resolveur(rep.config_id, rep.phase, q) if resolveur is not None else []
        if len(ids) != len(textes):
            ids = [""] * len(textes)
        references[aid] = list(zip(textes, ids, strict=True))
    vers.mkdir(parents=True, exist_ok=True)
    fichiers: dict[str, Path] = {}
    n_lignes = 0
    for nom, ids in lignes.items():
        table = TablePassages()
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
                    entree["reference_passages"] = [
                        table.reference(t, a) for t, a in references[aid]
                    ]
                    entree["context_passages"] = [table.contexte(b) for b in rep_.context_texts]
                entrees.append(entree)
        fichiers[nom] = _ecrire(vers, nom, entrees, table)
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


def _ecrire(vers: Path, nom: str, entrees: list[dict[str, Any]], table: TablePassages) -> Path:
    chemin = vers / f"{nom}.yaml"
    corps = yaml.dump(
        {"annotator": nom, "passages": table.entrees, "annotations": entrees},
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
    brut = lire_yaml(source)
    doc = resoudre_passages(brut, source.name)
    lignes = doc.get("annotations") if isinstance(doc, dict) else None
    if not isinstance(lignes, list) or not all(isinstance(x, dict) for x in lignes):
        raise ConfigError("depuis", f"{source.name} : une liste d'annotations est attendue")
    for i, x in enumerate(lignes):
        if not isinstance(x.get("answer_id"), str) or not x["answer_id"]:
            raise ConfigError(f"annotations[{i}].answer_id", f"{source.name} : identifiant absent")
        if not isinstance(x.get("criterion"), str) or not x["criterion"]:
            raise ConfigError(f"annotations[{i}].criterion", f"{source.name} : Critère absent")
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
    if any(_meme_fichier(source, vers / f"{nom}.yaml") for nom in annotateurs):
        raise ConfigError("vers", f"{source.name} serait écrasé par le paquet qu'il alimente")
    ancrages = _ancrages_de_reference(brut)
    donnees: dict[str, dict[str, Any]] = {}
    for ligne in lignes:  # les données de la Réponse viennent de n'importe laquelle de ses lignes
        d = donnees.setdefault(ligne["answer_id"], {})
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
    table = TablePassages()  # seuls les Passages des lignes retenues
    vues: set[str] = set()
    for i in sorted(int(c) for c in choisies):
        aid = lignes[i]["answer_id"]
        entree: dict[str, Any] = {
            "answer_id": aid,
            "criterion": lignes[i]["criterion"],
            "verdict": "",
            "note": "",
        }
        if aid not in vues:
            vues.add(aid)
            entree.update(donnees[aid])
            if isinstance(entree.get("context_passages"), list):
                entree["context_passages"] = [
                    table.contexte(str(t)) for t in entree["context_passages"]
                ]
            if isinstance(entree.get("reference_passages"), list):
                entree["reference_passages"] = [
                    table.reference(str(t), ancrages.get(str(t), ""))
                    for t in entree["reference_passages"]
                ]
        entrees.append(entree)
    vers.mkdir(parents=True, exist_ok=True)
    fichiers = {nom: _ecrire(vers, nom, entrees, table) for nom in annotateurs}
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
