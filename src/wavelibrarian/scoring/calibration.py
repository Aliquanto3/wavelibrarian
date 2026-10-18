"""Annotations humaines : chargement et rapprochement des Réponses (FR-38, contrats §4.6)."""

import json
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.stats.kappa import cohen_kappa

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


class _Chargeur(yaml.SafeLoader):
    """`SafeLoader` sans booléens implicites (`yes`, `on`, `true` restent des chaînes) et qui
    refuse les clés dupliquées."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        vues: set[Any] = set()
        for cle_noeud, _ in node.value:
            cle = self.construct_object(cle_noeud, deep=deep)  # type: ignore[no-untyped-call]
            if cle in vues:
                raise yaml.constructor.ConstructorError(
                    None, None, f"clé dupliquée {cle!r}", cle_noeud.start_mark
                )
            vues.add(cle)
        return super().construct_mapping(node, deep=deep)


_Chargeur.yaml_implicit_resolvers = {
    premier: [(tag, rx) for tag, rx in resolveurs if tag != "tag:yaml.org,2002:bool"]
    for premier, resolveurs in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _lire_texte(chemin: Path) -> str:
    try:
        return chemin.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(str(chemin), f"fichier non encodé en UTF-8 : {exc}") from exc
    except OSError as exc:
        raise ConfigError(str(chemin), f"lecture impossible : {exc}") from exc


def _lire_yaml(chemin: Path) -> Any:
    texte = _lire_texte(chemin)
    try:
        return yaml.load(texte, Loader=_Chargeur)  # noqa: S506 (dérivé de SafeLoader)
    except yaml.YAMLError as exc:
        raise ConfigError(str(chemin), f"YAML invalide : {exc}") from exc


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
    nom = chemin.name
    for i, ligne in enumerate(liste):
        base = f"annotations[{i}]"
        if not isinstance(ligne, dict):
            raise ConfigError(base, f"{nom} : un mapping est attendu")
        answer_id = ligne.get("answer_id")
        if not isinstance(answer_id, str) or not answer_id:
            raise ConfigError(f"{base}.answer_id", f"{nom} : identifiant de Réponse manquant")
        critere = ligne.get("criterion")
        if critere not in CRITERES:
            raise ConfigError(
                f"{base}.criterion",
                f"{nom} : Critère inconnu {critere!r} ; permis : {', '.join(CRITERES)}",
            )
        verdict = ligne.get("verdict")
        # Le chargeur garde `yes` / `no` nus en chaînes : seuls ces deux mots sont permis.
        if not isinstance(verdict, str) or verdict not in VERDICTS:
            raise ConfigError(
                f"{base}.verdict", f"{nom} : verdict inconnu {verdict!r} ; permis : yes, no"
            )
        valeur = VERDICTS[verdict]
        cle = (annotateur, answer_id, critere)
        if cle in out:
            raise ConfigError(
                base, f"{nom} : doublon : {annotateur} a déjà annoté {answer_id} pour {critere}"
            )
        out[cle] = valeur
    return out


def charger_dossier(dossier: Path) -> Annotations:
    """Charge tous les `*.yaml` et `*.yml` du dossier (un par annotateur), triés par nom.

    Aucun fichier, ou aucune annotation dans l'ensemble des fichiers : `ConfigError`."""
    fichiers = (
        sorted(f for f in dossier.iterdir() if f.is_file() and f.suffix in (".yaml", ".yml"))
        if dossier.is_dir()
        else []
    )
    if not fichiers:
        raise ConfigError(str(dossier), "aucun fichier d'annotations (*.yaml, *.yml)")
    verdicts: dict[Cle, bool] = {}
    for f in fichiers:
        charger_fichier(f, verdicts)
    if not verdicts:
        raise ConfigError(str(dossier), "aucune annotation dans les fichiers du dossier")
    return Annotations(verdicts)


def answer_ids_de_answers_jsonl(chemin: Path) -> set[str]:
    """Ensemble des `answer_id` d'un `answers.jsonl`."""
    ids: set[str] = set()
    lignes = _lire_texte(chemin).splitlines()
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


# --- Calcul de la calibration d'un Juge (story 5.2) ----------------------------------------------

Passe = tuple[str, str, int]  # (answer_id, criterion, pass_id)


@dataclass(frozen=True)
class FicheCritere:
    """Un Juge sur un Critère : kappa juge-humain (passe 0), instabilité, nombre d'items."""

    kappa: float | None
    instability: float | None
    n_items: int  # paires (annotateur, Réponse) comparées au verdict de la passe 0

    def en_json(self) -> dict[str, Any]:
        return {"kappa": self.kappa, "instability": self.instability, "n_items": self.n_items}


def fiches_du_juge(
    verdicts: Mapping[Passe, bool], annotations: Annotations, answer_ids: Collection[str]
) -> dict[str, FicheCritere]:
    """Fiches par Critère annoté d'un Juge, sur les Réponses `answer_ids` qu'il a pu noter.

    `verdicts` : ses verdicts par (answer_id, criterion, pass_id). Kappa : verdict de la passe 0
    contre chaque annotation (chaque annotateur compte séparément) ; une Réponse sans verdict de
    passe 0 (appel en échec) n'entre pas. Instabilité : part des Réponses annotées, notées à
    au moins deux passes, dont les verdicts diffèrent."""
    admises = set(answer_ids)
    fiches: dict[str, FicheCritere] = {}
    for critere in CRITERES:
        paires = [
            (humain, verdicts[(aid, critere, 0)])
            for (_, aid, c), humain in annotations.verdicts.items()
            if c == critere and aid in admises and (aid, critere, 0) in verdicts
        ]
        annotees = {aid for (_, aid, c) in annotations.verdicts if c == critere} & admises
        passes: dict[str, list[bool]] = {}
        for (aid, c, _), v in verdicts.items():
            if c == critere and aid in annotees:
                passes.setdefault(aid, []).append(v)
        notees = [vs for vs in passes.values() if len(vs) >= 2]
        if not annotees:
            continue
        fiches[critere] = FicheCritere(
            kappa=cohen_kappa([h for h, _ in paires], [j for _, j in paires]) if paires else None,
            instability=(sum(1 for vs in notees if len(set(vs)) > 1) / len(notees))
            if notees
            else None,
            n_items=len(paires),
        )
    return fiches


def kappa_inter_annotateurs(
    annotations: Annotations, answer_ids: Collection[str] | None = None
) -> list[dict[str, Any]]:
    """Kappa entre chaque couple d'annotateurs, par Critère, sur les Réponses annotées par les
    deux. `answer_ids` : restreint aux Réponses données (sinon toutes)."""
    noms = annotations.annotateurs
    sortie: list[dict[str, Any]] = []
    for i, a in enumerate(noms):
        for b in noms[i + 1 :]:
            criteres: dict[str, Any] = {}
            for critere in CRITERES:
                communs = sorted(
                    {k[1] for k in annotations.verdicts if k[0] == a and k[2] == critere}
                    & {k[1] for k in annotations.verdicts if k[0] == b and k[2] == critere}
                )
                if answer_ids is not None:
                    communs = [x for x in communs if x in set(answer_ids)]
                if not communs:
                    continue
                va = [annotations.verdicts[(a, x, critere)] for x in communs]
                vb = [annotations.verdicts[(b, x, critere)] for x in communs]
                criteres[critere] = {"kappa": cohen_kappa(va, vb), "n_items": len(communs)}
            sortie.append({"annotators": [a, b], "criteria": criteres})
    return sortie


def doublement_annotees(annotations: Annotations) -> set[str]:
    """Réponses annotées par au moins deux annotateurs (sur un même Critère)."""
    par: dict[tuple[str, str], set[str]] = {}
    for annotateur, aid, critere in annotations.verdicts:
        par.setdefault((aid, critere), set()).add(annotateur)
    return {aid for (aid, _), qui in par.items() if len(qui) >= 2}


def decider_exclusion(
    fiches: Mapping[str, FicheCritere], seuil: float
) -> tuple[bool, str | None, list[str]]:
    """Exclu si un kappa est sous le seuil ; un kappa indéfini n'exclut pas mais est signalé.

    Rend (exclu, raison en français, signalements)."""

    def fr(x: float) -> str:
        return f"{x:.2f}".replace(".", ",")

    raisons = [
        f"kappa {fr(f.kappa)} sous le seuil {fr(seuil)} sur {c}"
        for c, f in fiches.items()
        if f.kappa is not None and f.kappa < seuil
    ]
    signales = [
        f"kappa indéfini sur {c} (accord sur une seule classe ou aucun item), n'exclut pas le Juge"
        for c, f in fiches.items()
        if f.kappa is None
    ]
    return bool(raisons), ("; ".join(raisons) or None), signales
