"""Règles de fusion des mentions d'une entité, indépendantes de l'ordre des mentions.

Partagées par le GraphStore (entre Passages) et l'extracteur (dans un Passage).
"""

from collections.abc import Mapping

# Type donné à une entité créée par une relation : ne l'emporte jamais sur un type extrait.
KIND_GENERIQUE = "entity"


def meilleur_texte(a: str, b: str) -> str:
    """Description conservée : la plus longue, ex æquo la plus petite."""
    return min(a, b, key=lambda t: (-len(t), t)) if a and b else (a or b)


def meilleur_kind(a: str, b: str) -> str:
    """Un type extrait l'emporte sur le type générique ; entre deux types extraits, le plus
    petit."""
    if not a or a == KIND_GENERIQUE:
        return b or a
    if not b or b == KIND_GENERIQUE:
        return a
    return min(a, b)


def nom_canonique(noms: Mapping[str, int]) -> str:
    """Forme la plus mentionnée ; ex æquo celle qui garde le plus de caractères non ASCII
    (accents), puis la plus petite (« Éric » plutôt que « eric »)."""
    return min(noms, key=lambda n: (-noms[n], -sum(not c.isascii() for c in n), n))
