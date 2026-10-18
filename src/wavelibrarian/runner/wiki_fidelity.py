"""Copie générique de `wiki_fidelity.json` dans `runs/<run_id>/` (story 7.3, contracts.md §5).

Le runner ne connaît pas `llm_wiki` : si le dossier d'index chargé contient `wiki_fidelity.json`,
son contenu est ajouté à `runs/<run_id>/wiki_fidelity.json`, un objet `{clé: contenu}` où la clé
est la Configuration (suffixée `@<palier>` pour un Palier, `@after_update` après mise à jour).
Fichier absent : rien n'est écrit. Réécrire une clé remplace sa valeur (reprise d'une Exécution).
"""

import json
import os
from pathlib import Path
from typing import Any

FICHIER = "wiki_fidelity.json"


def cle_de_copie(config_id: str, tier: int | None, post: str) -> str:
    cle = config_id or "-"
    if tier is not None:
        cle = f"{cle}@{tier}"
    if post == "update":
        cle = f"{cle}@after_update"
    return cle


def copier_fidelite(index_dir: Path, run_dir: Path, cle: str) -> bool:
    """Ajoute le fichier de `index_dir` à celui de `run_dir` sous `cle`. Faux si absent."""
    source = index_dir / FICHIER
    if not source.is_file():
        return False
    contenu = json.loads(source.read_text(encoding="utf-8"))
    destination = run_dir / FICHIER
    existant: dict[str, Any] = {}
    if destination.is_file():
        existant = json.loads(destination.read_text(encoding="utf-8"))
    existant[cle] = contenu
    run_dir.mkdir(parents=True, exist_ok=True)
    temporaire = destination.with_suffix(".json.tmp")
    texte = json.dumps(existant, ensure_ascii=False, indent=1, sort_keys=True)
    temporaire.write_bytes((texte + "\n").encode("utf-8"))
    os.replace(temporaire, destination)
    return True
