"""Lecture et ajout de fichiers JSONL en ajout seulement (AD-11, story 4.11).

Un arrêt brutal peut laisser une dernière ligne tronquée, sans saut de ligne final. Les lecteurs
ignorent toute ligne qui n'est pas un objet JSON (avertissement au journal), et `terminer_ligne`
termine le fichier par `\n` avant tout ajout : la ligne tronquée reste seule sur sa ligne, et la
suivante ne s'y colle pas. Chaque ligne est écrite d'un bloc puis vidée sur disque : une ligne
invalide ne vient que de cette troncature, donc l'ignorer ne perd aucune donnée valide.
"""

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def terminer_ligne(chemin: Path) -> None:
    """Ajoute `\n` si le fichier existe, n'est pas vide et ne se termine pas par un saut de
    ligne. Sans effet sur un fichier absent, vide ou déjà terminé."""
    try:
        with chemin.open("rb+") as f:
            f.seek(0, 2)
            if f.tell() == 0:
                return
            f.seek(-1, 2)
            if f.read(1) != b"\n":
                f.write(b"\n")
    except FileNotFoundError:
        return


def lire_jsonl(chemin: Path) -> list[dict[str, Any]]:
    """Objets du fichier, dans l'ordre ; `[]` si le fichier est absent. Une ligne qui n'est pas
    un objet JSON (écriture interrompue) est ignorée et journalisée."""
    if not chemin.is_file():
        return []
    objets: list[dict[str, Any]] = []
    # Décodage ligne par ligne : une troncature au milieu d'un caractère multioctet n'invalide
    # que sa propre ligne (UnicodeDecodeError est une ValueError).
    for i, brute in enumerate(chemin.read_bytes().split(b"\n"), start=1):
        if not brute.strip():
            continue
        try:
            objet = json.loads(brute.decode("utf-8"))
        except ValueError:
            objet = None
        if not isinstance(objet, dict):
            log.warning(
                "%s ligne %d ignorée : objet JSON attendu (ligne tronquée ?)", chemin.name, i
            )
            continue
        objets.append(objet)
    return objets
