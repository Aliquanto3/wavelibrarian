"""Taux de fidélité des wikis dans le Rapport (story 7.3, FR-40) : `supported ÷ claims`.

Générique : lit `runs/<run_id>/wiki_fidelity.json` s'il existe, sans connaître l'Architecture.
"""

import json
from pathlib import Path
from typing import Any

FICHIER = "wiki_fidelity.json"


def taux_fidelite(run_dir: Path) -> dict[str, float | None]:
    """`supported ÷ claims` par Configuration ; `None` si aucune affirmation n'a été vérifiée.
    Dictionnaire vide si le fichier est absent."""
    chemin = run_dir / FICHIER
    if not chemin.is_file():
        return {}
    brut: dict[str, Any] = json.loads(chemin.read_text(encoding="utf-8"))
    return {
        cle: (v["supported"] / v["claims"] if v.get("claims") else None)
        for cle, v in sorted(brut.items())
    }


def section_fidelite(run_dir: Path) -> str:
    """Section Markdown du Rapport ; chaîne vide si le fichier est absent."""
    taux = taux_fidelite(run_dir)
    if not taux:
        return ""
    lignes = ["## Fidélité du wiki", "", "| Configuration | supported ÷ claims |", "| --- | --- |"]
    for cle, valeur in taux.items():
        lignes.append(f"| {cle} | {'n/a' if valeur is None else f'{valeur:.0%}'} |")
    return "\n".join(lignes) + "\n"
