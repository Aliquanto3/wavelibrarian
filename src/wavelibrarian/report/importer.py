"""Import des verdicts exportés par la page d'annotation dans le paquet YAML (story 9.4).

Édition textuelle prudente, ligne à ligne : seules les lignes `verdict:` et les notes vides
(`note: ''`, `""`, `null`, `~` ou rien) des entrées retrouvées sont réécrites ; le reste du
fichier (ordre, commentaires, table des Passages, notes déjà saisies, fins de ligne LF ou CRLF)
est conservé octet pour octet. Le résultat est écrit dans un fichier temporaire voisin, relu
(même annotateur, mêmes lignes et clés hors verdict et note, verdicts et notes attendus), puis
substitué au paquet (`os.replace`) : en cas d'échec, le paquet n'est pas touché.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wavelibrarian.core.errors import ConfigError
from wavelibrarian.scoring.calibration import lire_yaml

VERDICTS = ("yes", "no", "na")
_ID = "- answer_id: "
_CRITERE = "  criterion: "
_VERDICT = "  verdict: "
_NOTES_VIDES = frozenset({"  note: ''", '  note: ""', "  note:", "  note: null", "  note: ~"})
# Caractères qu'un scalaire YAML entre guillemets ne garde pas tels quels (NEL, séparateurs de
# ligne et de paragraphe, contrôles C1, DEL, BOM, non-caractères, demi-codets) : échappés.
_A_ECHAPPER = re.compile("[\x7f-\x9f  ﻿￾￿\ud800-\udfff]")


@dataclass(frozen=True)
class Import:
    verdicts: int  # verdicts reportés
    notes: int  # notes reportées
    sans_verdict: int  # lignes du paquet restées sans verdict
    inconnus: list[str] = field(default_factory=list)  # clés du JSON absentes du paquet
    # Verdicts vidés dans la page (re-clic) mais conservés dans le paquet : l'import n'efface pas.
    vides_conserves: list[str] = field(default_factory=list)


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
        if v.get("note") is not None and not isinstance(v.get("note"), str):
            raise ConfigError(chemin.name, f"{cle} : la note doit être un texte")
    return (annotateur if isinstance(annotateur, str) else None), verdicts


def _note(v: dict[str, Any] | None) -> str:
    note = (v or {}).get("note")
    return note.strip() if isinstance(note, str) else ""


def _scalaire(texte: str) -> str:
    """Scalaire YAML entre guillemets doubles qui se relit à l'identique."""
    brut = json.dumps(texte, ensure_ascii=False)
    return _A_ECHAPPER.sub(lambda m: f"\\u{ord(m[0]):04x}", brut)


def importer_verdicts(paquet: Path, verdicts_json: Path) -> Import:
    """Reporte les verdicts et les notes de `verdicts_json` dans `paquet` (remplacé en place).

    Un verdict du JSON remplace celui de la ligne ; un verdict vidé dans la page ne l'efface pas
    (compté dans `vides_conserves`). Une note du JSON n'est reportée que sur une note vide (une
    note déjà saisie dans le paquet reste). `ConfigError` si le JSON est invalide, s'il vient
    d'un autre annotateur que le paquet, ou si l'édition n'aboutit pas au paquet attendu."""
    annotateur_json, verdicts = _lire_verdicts(verdicts_json)
    avant = lire_yaml(paquet)
    if not isinstance(avant, dict) or not isinstance(avant.get("annotations"), list):
        raise ConfigError(paquet.name, "paquet d'annotation invalide (liste `annotations`)")
    if not all(isinstance(x, dict) for x in avant["annotations"]):
        raise ConfigError(paquet.name, "paquet d'annotation invalide (ligne sans mapping)")
    if annotateur_json is not None and annotateur_json != avant.get("annotator"):
        raise ConfigError(
            verdicts_json.name,
            f"verdicts de {annotateur_json!r}, mais le paquet est celui de "
            f"{avant.get('annotator')!r}",
        )
    try:
        texte = paquet.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(str(paquet), f"lecture impossible : {exc}") from exc
    lignes = texte.split("\n")
    aid = crit = ""
    nb_verdicts = nb_notes = 0
    vus: set[str] = set()
    for i, brute in enumerate(lignes):
        cr = "\r" if brute.endswith("\r") else ""  # fin de ligne CRLF conservée
        ligne = brute[: len(brute) - len(cr)]
        if ligne.startswith("- "):  # nouvelle entrée de liste : identifiants remis à zéro
            aid, crit = (_valeur(ligne[len(_ID) :]) if ligne.startswith(_ID) else ""), ""
        elif ligne.startswith(_CRITERE):
            crit = _valeur(ligne[len(_CRITERE) :])
        elif ligne.startswith(_VERDICT) and aid and crit:
            cle = f"{aid}|{crit}"
            vus.add(cle)
            v = str(verdicts.get(cle, {}).get("verdict", ""))
            if v and ligne != f"{_VERDICT}{v}":
                lignes[i] = f"{_VERDICT}{v}{cr}"
                nb_verdicts += 1
        elif ligne in _NOTES_VIDES and aid and crit:
            note = _note(verdicts.get(f"{aid}|{crit}"))
            if note:
                lignes[i] = f"  note: {_scalaire(note)}{cr}"
                nb_notes += 1
    apres = _ecrire_et_relire(paquet, "\n".join(lignes), avant, verdicts)
    sans = sum(1 for x in apres["annotations"] if x.get("verdict") not in VERDICTS)
    inconnus = sorted(k for k in verdicts if k not in vus and verdicts[k].get("verdict"))
    vides = sorted(
        f"{x.get('answer_id')}|{x.get('criterion')}"
        for x in avant["annotations"]
        if x.get("verdict") in VERDICTS
        and verdicts.get(f"{x.get('answer_id')}|{x.get('criterion')}", {}).get("verdict", None)
        == ""
    )
    return Import(nb_verdicts, nb_notes, sans, inconnus, vides)


def _valeur(brut: str) -> str:
    v = brut.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v


def _squelette(doc: dict[str, Any]) -> list[Any]:
    """Ce que l'import ne doit pas modifier : annotateur, table des Passages, identifiants,
    Critères, et toutes les clés autres que `verdict` et `note`."""
    autres = [
        {k: v for k, v in x.items() if k not in ("verdict", "note")} for x in doc["annotations"]
    ]
    entete = {k: v for k, v in doc.items() if k != "annotations"}
    return [repr(entete), len(doc["annotations"]), *map(repr, autres)]


def _attendus(avant: dict[str, Any], verdicts: dict[str, dict[str, Any]]) -> list[Any]:
    """Verdict et note attendus après import, ligne à ligne."""
    out: list[Any] = []
    for x in avant["annotations"]:
        v = verdicts.get(f"{x.get('answer_id')}|{x.get('criterion')}")
        verdict = str((v or {}).get("verdict", "")) or x.get("verdict")
        note = x.get("note")
        if not note and _note(v):
            note = _note(v)
        out.append((verdict, note))
    return out


def _ecrire_et_relire(
    paquet: Path, texte: str, avant: dict[str, Any], verdicts: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    tmp = paquet.with_name(paquet.name + ".tmp-import")
    try:
        tmp.write_bytes(texte.encode("utf-8"))
        doc = lire_yaml(tmp)
        if not isinstance(doc, dict) or not isinstance(doc.get("annotations"), list):
            raise ConfigError(paquet.name, "l'import produirait un paquet illisible : rien écrit")
        if _squelette(doc) != _squelette(avant):
            raise ConfigError(
                paquet.name, "l'import altérerait la structure du paquet : rien écrit"
            )
        obtenus = [(x.get("verdict"), x.get("note")) for x in doc["annotations"]]
        if obtenus != _attendus(avant, verdicts):
            raise ConfigError(
                paquet.name,
                "lignes du paquet non reconnues (format attendu : `- answer_id:` en tête "
                "d'entrée, puis `criterion`, `verdict`, `note`) : rien écrit",
            )
        os.replace(tmp, paquet)
    finally:
        tmp.unlink(missing_ok=True)
    return doc
