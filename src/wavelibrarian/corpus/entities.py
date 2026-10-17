"""Entités nommées par heuristique (FR-7) : séquences capitalisées hors début de phrase.

Aucun réseau, aucun LLM. Le premier mot de chaque phrase (ou de chaque Block) est écarté, car sa
majuscule ne dit rien ; les titres sont ignorés (ils sont presque toujours capitalisés).
"""

import re

from wavelibrarian.core.types import ParsedCorpus, ParsedDocument

_CAP = r"[A-ZÀ-ÖØ-Þ][\w-]*"
_LIAISON = r"(?:\s+(?:de la|de|du|des|of|the)\s+|\s+d['’]|\s+)"
_ENTITE = re.compile(rf"(?<![\w'’-])({_CAP}(?:{_LIAISON}{_CAP})*)")
_PHRASES = re.compile(r"(?<=[.!?…])\s+|\n+")


def extraire_entites(texte: str) -> set[str]:
    """Entités du texte, sous forme normalisée (minuscules, espaces simples)."""
    entites: set[str] = set()
    for phrase in _PHRASES.split(texte):
        morceaux = phrase.strip().split(None, 1)
        if len(morceaux) < 2:
            continue  # le seul mot d'une phrase est son début
        for m in _ENTITE.finditer(morceaux[1]):
            entites.add(" ".join(m.group(1).split()).casefold())
    return entites


def entites_du_document(doc: ParsedDocument) -> set[str]:
    texte = "\n".join(b.text for b in doc.blocks if b.kind != "heading")
    return extraire_entites(texte)


def link_density(corpus: ParsedCorpus) -> float:
    """Part des Documents qui partagent au moins une entité nommée avec un autre Document."""
    if not corpus.documents:
        return 0.0
    par_entite: dict[str, set[str]] = {}
    for doc in corpus.documents:
        for e in entites_du_document(doc):
            par_entite.setdefault(e, set()).add(doc.doc_id)
    lies = {d for docs in par_entite.values() if len(docs) > 1 for d in docs}
    return len(lies) / len(corpus.documents)
