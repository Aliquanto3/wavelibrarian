"""Import des verdicts exportés par la page d'annotation dans le paquet YAML (story 9.4).

Édition textuelle prudente, ligne à ligne : seules les lignes `verdict:` et `note: ''` des
entrées retrouvées sont réécrites, le reste du fichier (ordre, commentaires, passages, notes déjà
saisies) est conservé octet pour octet. Le fichier résultat est relu avant écriture : même
nombre d'annotations, mêmes `answer_id` et Critères, sinon rien n'est écrit.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.scoring.calibration import lire_yaml

VERDICTS = ("yes", "no", "na")
_ID = "- answer_id: "
_CRITERE = "  criterion: "
_VERDICT = "  verdict: "
_NOTE_VIDE = "  note: ''"


@dataclass(frozen=True)
class Import:
    verdicts: int  # verdicts reportés
    notes: int  # notes reportées
    sans_verdict: int  # lignes du paquet restées sans verdict
    inconnus: list[str] = field(default_factory=list)  # clés du JSON absentes du paquet


def _lire_verdicts(chemin: Path) -> tuple[str | None, dict[str, dict[str, Any]]]:
    try:
        doc = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(str(chemin), f"lecture impossible : {exc}") from exc
    verdicts = doc.get("verdicts") if isinstance(doc, dict) else None
    if not isinstance(verdicts, dict):
        raise ConfigError(chemin.name, "objet `verdicts` attendu (export de la page d'annotation)")
    annotateur = doc.get("annotator")
    for cle, v in verdicts.items():
        if not isinstance(v, dict):
            raise ConfigError(chemin.name, f"{cle} : un objet {{verdict, note}} est attendu")
        verdict = v.get("verdict", "")
        if verdict not in ("", *VERDICTS):
            raise ConfigError(
                chemin.name, f"{cle} : verdict inconnu {verdict!r} ; permis : {', '.join(VERDICTS)}"
            )
    return (annotateur if isinstance(annotateur, str) else None), verdicts


def importer_verdicts(paquet: Path, verdicts_json: Path) -> Import:
    """Reporte les verdicts et les notes de `verdicts_json` dans `paquet` (réécrit en place).

    Un verdict du JSON remplace celui de la ligne ; une note du JSON n'est reportée que sur une
    note vide (une note déjà saisie dans le paquet reste). `ConfigError` si le JSON est invalide,
    s'il vient d'un autre annotateur que le paquet, ou si l'édition altérerait la structure."""
    annotateur_json, verdicts = _lire_verdicts(verdicts_json)
    avant = lire_yaml(paquet)
    if not isinstance(avant, dict) or not isinstance(avant.get("annotations"), list):
        raise ConfigError(paquet.name, "paquet d'annotation invalide (liste `annotations`)")
    if annotateur_json is not None and annotateur_json != avant.get("annotator"):
        raise ConfigError(
            verdicts_json.name,
            f"verdicts de {annotateur_json!r}, mais le paquet est celui de "
            f"{avant.get('annotator')!r}",
        )
    texte = paquet.read_text(encoding="utf-8")
    lignes = texte.split("\n")
    aid = crit = ""
    nb_verdicts = nb_notes = 0
    vus: set[str] = set()
    for i, ligne in enumerate(lignes):
        if ligne.startswith(_ID):
            aid, crit = _valeur(ligne[len(_ID) :]), ""
        elif ligne.startswith(_CRITERE):
            crit = _valeur(ligne[len(_CRITERE) :])
        elif ligne.startswith(_VERDICT) and aid and crit:
            cle = f"{aid}|{crit}"
            vus.add(cle)
            v = str(verdicts.get(cle, {}).get("verdict", ""))
            if v and ligne != f"{_VERDICT}{v}":
                lignes[i] = f"{_VERDICT}{v}"
                nb_verdicts += 1
        elif ligne == _NOTE_VIDE and aid and crit:
            note = str(verdicts.get(f"{aid}|{crit}", {}).get("note", "")).strip()
            if note:
                lignes[i] = "  note: " + json.dumps(note, ensure_ascii=False)
                nb_notes += 1
    apres_texte = "\n".join(lignes)
    paquet_apres = _relire(paquet, apres_texte)
    if _squelette(paquet_apres) != _squelette(avant):
        raise ConfigError(paquet.name, "l'import altérerait la structure du paquet : rien écrit")
    paquet.write_text(apres_texte, encoding="utf-8", newline="\n")
    sans = sum(1 for x in paquet_apres["annotations"] if x.get("verdict") not in VERDICTS)
    inconnus = sorted(k for k in verdicts if k not in vus and verdicts[k].get("verdict"))
    return Import(nb_verdicts, nb_notes, sans, inconnus)


def _valeur(brut: str) -> str:
    v = brut.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v


def _squelette(doc: dict[str, Any]) -> list[Any]:
    """Ce que l'import ne doit pas modifier : annotateur, identifiants, Critères, et toutes
    les clés autres que `verdict` et `note`."""
    autres = [
        {k: v for k, v in x.items() if k not in ("verdict", "note")} for x in doc["annotations"]
    ]
    return [(doc.get("annotator"), len(doc["annotations"])), *map(repr, autres)]


def _relire(paquet: Path, texte: str) -> dict[str, Any]:
    tmp = paquet.with_name(paquet.name + ".tmp-import")
    try:
        tmp.write_text(texte, encoding="utf-8", newline="\n")
        doc = lire_yaml(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    if not isinstance(doc, dict) or not isinstance(doc.get("annotations"), list):
        raise ConfigError(paquet.name, "l'import produirait un paquet illisible : rien écrit")
    return doc
